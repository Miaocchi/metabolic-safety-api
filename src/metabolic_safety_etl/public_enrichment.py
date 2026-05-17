from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
from typing import Callable, Iterable

from .adapters.chembl import fetch_chembl_facts
from .adapters.dailymed import fetch_dailymed_facts
from .adapters.ddinter import find_ddinter_csvs, load_ddinter_csv_facts
from .adapters.openfda import fetch_label_facts
from .adapters.psychonautwiki import fetch_substance_facts
from .adapters.rxnav import fetch_rxnav_facts
from .fusion import load_facts
from .io import read_json
from .schemas import EvidenceFact

Fetcher = Callable[[str, int, int], list[EvidenceFact]]


PUBLIC_FETCHERS: dict[str, Fetcher] = {
    "rxnav": lambda term, limit, timeout: fetch_rxnav_facts(term, limit=limit, timeout=timeout),
    "chembl": lambda term, limit, timeout: fetch_chembl_facts(term, limit=limit, timeout=timeout),
    "dailymed": lambda term, limit, timeout: fetch_dailymed_facts(term, limit=limit, timeout=timeout),
    "openfda_label": lambda term, limit, timeout: fetch_label_facts(term, limit=limit, timeout=timeout),
}


def load_seed_facts(
    ddinter_dir: Path,
    fixture_path: Path,
    zh_aliases: Path | None,
    supplement_facts: Iterable[Path],
    max_interactions: int | None = None,
) -> tuple[list[EvidenceFact], list[str]]:
    sources: list[str] = []
    paths = find_ddinter_csvs(ddinter_dir)
    if paths:
        facts = load_ddinter_csv_facts(paths, max_interactions=max_interactions, zh_aliases_path=zh_aliases)
        sources.extend(str(path) for path in paths)
    else:
        facts = load_facts(read_json(fixture_path)) if fixture_path.exists() else []
        if fixture_path.exists():
            sources.append(str(fixture_path))
    for path in supplement_facts:
        if path.exists():
            loaded = read_json(path)
            if isinstance(loaded, list):
                facts.extend(load_facts(loaded))
                sources.append(str(path))
    return facts, sources


def load_extra_fact_files(paths: Iterable[Path]) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen_files: set[Path] = set()
    for root in paths:
        candidates = [root] if root.is_file() else sorted(root.glob("**/*.json")) if root.exists() else []
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen_files:
                continue
            seen_files.add(resolved)
            try:
                payload = read_json(path)
                if isinstance(payload, list):
                    facts.extend(load_facts(payload))
            except Exception as exc:
                print(f"skip_extra_fact_file={path} error={type(exc).__name__}: {exc}")
    return facts


def candidate_terms_from_dataset(dataset: dict, max_terms: int) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        if len(terms) >= max_terms:
            return
        term = str(value or "").strip()
        if not looks_like_public_api_term(term):
            return
        key = term.lower()
        if key in seen:
            return
        seen.add(key)
        terms.append(term)

    preferred = []
    for row in dataset.get("substances_core", []):
        source_summary = row.get("source_summary") or []
        has_regulatory = any(item.get("source_tier") in {"Regulatory", "Guideline", "Label"} for item in source_summary)
        has_curated = any(item.get("source_tier") == "CuratedDB" for item in source_summary)
        score = 0 if has_regulatory else 1 if has_curated else 2
        preferred.append((score, row.get("name_en") or row.get("id") or "", row))
    for _, _, row in sorted(preferred, key=lambda item: (item[0], str(item[1]).lower())):
        add(row.get("name_en") or row.get("id"))
        identifiers = row.get("identifiers") or {}
        if isinstance(identifiers, dict):
            add(identifiers.get("rxnorm_synonym"))
            aliases = identifiers.get("aliases")
            if isinstance(aliases, str):
                for alias in re.split(r"[,;|]", aliases):
                    add(alias)
    return terms


def looks_like_public_api_term(term: str) -> bool:
    if not re.search(r"[A-Za-z]", term):
        return False
    if len(term) < 2 or len(term) > 64:
        return False
    if term[0].isdigit():
        return False
    if re.search(r"[{}\[\]\\]", term):
        return False
    if term.count(" ") > 4:
        return False
    lowered = f" {term.lower()} "
    noisy_words = (
        " oral ", " tablet", " capsule", " injection", " solution", " suspension",
        " pack", " kit", " prefilled", " syringe", " auto-injector", " vial",
        " extended release", " delayed release", " mg/", " ml ",
    )
    return not any(word in lowered for word in noisy_words)


def fetch_public_enrichment_facts(
    terms: list[str],
    per_source_limit: int = 3,
    timeout: int = 20,
    workers: int = 8,
    enabled_sources: Iterable[str] | None = None,
) -> tuple[list[EvidenceFact], dict[str, int]]:
    source_keys = [key for key in (enabled_sources or PUBLIC_FETCHERS.keys()) if key in PUBLIC_FETCHERS]
    facts: list[EvidenceFact] = []
    counts = {key: 0 for key in source_keys}
    errors = {key: 0 for key in source_keys}
    jobs = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        for term in terms:
            for key in source_keys:
                fetcher = PUBLIC_FETCHERS[key]
                jobs.append(executor.submit(_fetch_one, key, term, fetcher, per_source_limit, timeout))
        total = len(jobs)
        for index, future in enumerate(as_completed(jobs), start=1):
            key, term, batch, error = future.result()
            if error:
                errors[key] = errors.get(key, 0) + 1
            else:
                facts.extend(batch)
                counts[key] = counts.get(key, 0) + len(batch)
            if index % 50 == 0 or index == total:
                print(f"public_enrichment_progress={index}/{total} facts={len(facts)}")
    counts.update({f"{key}_errors": value for key, value in errors.items() if value})
    return dedupe_facts(facts), counts


def _fetch_one(key: str, term: str, fetcher: Fetcher, limit: int, timeout: int) -> tuple[str, str, list[EvidenceFact], str | None]:
    try:
        return key, term, fetcher(term, limit, timeout), None
    except Exception as exc:
        return key, term, [], f"{type(exc).__name__}: {exc}"


def fetch_psychonautwiki_enrichment_facts(pages: int, page_size: int = 100) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for page in range(max(0, pages)):
        offset = page * page_size
        try:
            batch = fetch_substance_facts(limit=page_size, offset=offset)
        except Exception as exc:
            print(f"psychonautwiki_page_error={page} error={type(exc).__name__}: {exc}")
            break
        if not batch:
            break
        facts.extend(batch)
        print(f"psychonautwiki_progress={page + 1}/{pages} facts={len(facts)}")
        if len(batch) < max(5, page_size // 3):
            break
    return dedupe_facts(facts)


def dedupe_facts(facts: Iterable[EvidenceFact]) -> list[EvidenceFact]:
    by_id: dict[str, EvidenceFact] = {}
    for fact in facts:
        by_id[fact.fact_id] = fact
    return [by_id[key] for key in sorted(by_id)]
