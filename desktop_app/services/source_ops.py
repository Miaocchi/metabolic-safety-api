"""Source operations: fetching, caching, bulk sync, public sync, rebuild.

This module contains the heavy-lifting logic that was previously inlined in
``server.py``.  It is split from the HTTP handler so that job logic,
network helpers, and rebuild orchestration can be tested and reasoned about
independently.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

from desktop_app.config import (
    ACTIVE_DB_POINTER,
    BUILD,
    DATASET_VERSION,
    DDINTER_DIR,
    DIRECT_PUBLIC_SOURCES,
    DOSE_RULES_FACTS,
    FAERS_SIGNAL_CACHE_SECONDS,
    OPTIONAL_DIR,
    OPTIONAL_FACTS,
    PHARMGKB_BULK_FILES,
    PUBLIC_SYNC_MAX_WORKERS,
    PUBLIC_SYNC_SOURCE_LIMITS,
    PUBLIC_SYNC_TIMEOUTS,
    RAW_DIR,
    ROOT,
    SOURCE_NAME_TO_KEY,
    SOURCE_UPDATE_META,
    SUPPLEMENT_FACTS,
    ZH_ALIASES,
)
from desktop_app.services.security import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    clean_faers_query_term,
    looks_like_public_api_term,
    safe_filename,
    split_candidate_terms,
    stable_text_hash,
    validate_download_url,
)
from desktop_app.services.job_manager import REBUILD_LOCK, update_job

# -- ETL adapter imports (sys.path already set by config.py) ----------------
from metabolic_safety_etl.adapters.chembl import fetch_chembl_facts          # noqa: E402
from metabolic_safety_etl.adapters.dailymed import fetch_dailymed_facts      # noqa: E402
from metabolic_safety_etl.adapters.ddinter import (                         # noqa: E402
    find_ddinter_csvs,
    load_ddinter_csv_facts,
)
from metabolic_safety_etl.adapters.openfda import (                         # noqa: E402
    fetch_event_signal_facts,
    fetch_label_facts,
)
from metabolic_safety_etl.adapters.label_bulk import (                      # noqa: E402
    fetch_dailymed_label_manifest,
    fetch_openfda_label_manifest,
)
from metabolic_safety_etl.adapters.psychonautwiki import fetch_substance_facts  # noqa: E402
from metabolic_safety_etl.adapters.rxnav import fetch_rxnav_facts           # noqa: E402
from metabolic_safety_etl.export import write_json, write_mobile_seed_files, write_sqlite  # noqa: E402
from metabolic_safety_etl.fusion import build_dataset, load_facts           # noqa: E402
from metabolic_safety_etl.io import read_json                               # noqa: E402
from metabolic_safety_etl.raw_sources import load_raw_source_facts          # noqa: E402
from metabolic_safety_etl.source_catalog import source_status_dicts         # noqa: E402

__all__ = [
    "append_optional_facts",
    "bulk_sync_one_source",
    "bulk_sync_sources",
    "download_manifest_parts",
    "download_url",
    "fetch_bulk_manifest",
    "fetch_chembl_bulk_manifest",
    "fetch_direct_public_facts",
    "fetch_faers_signal_facts_cached",
    "fetch_github_release_manifest",
    "fetch_pharmgkb_bulk_manifest",
    "fetch_zenodo_manifest",
    "faers_query_terms",
    "optional_fact_counts_by_source",
    "public_sync_terms",
    "rebuild_seed_dataset",
    "record_public_sync_meta",
    "record_rebuild_source_meta",
    "run_bulk_sync_job",
    "run_public_sync_job",
    "run_rebuild_job",
    "should_query_public_source",
    "sync_public_sources",
    "update_source_meta",
]

# -- FAERS signal cache -----------------------------------------------------
_FAERS_SIGNAL_CACHE: dict[str, tuple[float, list]] = {}
_FAERS_SIGNAL_LOCK = __import__("threading").Lock()


# -- Direct public source fetching ------------------------------------------

def fetch_direct_public_facts(
    key: str, term: str, limit: int, timeout: int | None = None,
):
    """Fetch candidate facts from a single public source by *key*."""
    timeout_value = timeout or 30
    if key == "openfda_label":
        return fetch_label_facts(term, limit, timeout=timeout_value)
    if key == "openfda_event":
        return fetch_event_signal_facts(term, limit, timeout=timeout_value)
    if key == "dailymed":
        return fetch_dailymed_facts(term, limit, timeout=timeout_value)
    if key == "rxnav":
        return fetch_rxnav_facts(term, limit, timeout=timeout_value)
    if key == "chembl":
        return fetch_chembl_facts(term, limit, timeout=timeout_value)
    if key == "psychonautwiki":
        return fetch_substance_facts(limit=limit, offset=0)
    raise ValueError(f"Unsupported source: {key}")


# -- FAERS signal cache + helpers -------------------------------------------

def fetch_faers_signal_facts_cached(term: str, limit: int):
    """Fetch FAERS signal facts with an in-memory TTL cache."""
    normalized = term.strip()
    if not normalized:
        return []
    cache_key = f"{normalized.lower()}::{int(limit)}"
    now = time.time()
    with _FAERS_SIGNAL_LOCK:
        cached = _FAERS_SIGNAL_CACHE.get(cache_key)
        if cached and now - cached[0] < FAERS_SIGNAL_CACHE_SECONDS:
            return list(cached[1])
    facts = fetch_event_signal_facts(normalized, limit=limit, timeout=8)
    with _FAERS_SIGNAL_LOCK:
        _FAERS_SIGNAL_CACHE[cache_key] = (now, list(facts))
    return facts


def faers_query_terms(row: sqlite3.Row) -> list[str]:
    """Derive candidate FAERS query terms from a substance row."""
    identifiers: dict = {}
    try:
        identifiers = json.loads(row["identifiers_json"] or "{}")
    except Exception:
        identifiers = {}
    candidates: list[str] = []
    for value in (row["name_en"], identifiers.get("rxnorm_synonym"), row["id"]):
        candidates.extend(split_candidate_terms(value))
    aliases = identifiers.get("aliases")
    if isinstance(aliases, str):
        for alias in aliases.split("|"):
            candidates.extend(split_candidate_terms(alias))
    elif isinstance(aliases, list):
        for alias in aliases:
            candidates.extend(split_candidate_terms(alias))

    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        term = clean_faers_query_term(candidate)
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms[:4]


# -- Optional-facts persistence ---------------------------------------------

def append_optional_facts(facts) -> int:
    """Merge *facts* into the optional-facts JSON file, keyed by fact_id."""
    OPTIONAL_DIR.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if OPTIONAL_FACTS.exists():
        existing = read_json(OPTIONAL_FACTS)
    by_id = {item.get("fact_id"): item for item in existing if item.get("fact_id")}
    for fact in facts:
        item = fact.to_dict()
        by_id[item["fact_id"]] = item
    payload = sorted(
        by_id.values(),
        key=lambda item: (item.get("source_name", ""), item.get("fact_id", "")),
    )
    write_json(OPTIONAL_FACTS, payload)
    return len(payload)


def optional_fact_counts_by_source() -> dict[str, int]:
    """Return per-source-key counts from the optional-facts file."""
    if not OPTIONAL_FACTS.exists():
        return {}
    counts: dict[str, int] = {}
    try:
        for item in read_json(OPTIONAL_FACTS):
            key = SOURCE_NAME_TO_KEY.get(item.get("source_name", ""))
            if key:
                counts[key] = counts.get(key, 0) + 1
    except Exception:
        return {}
    return counts


def update_source_meta(key: str, detail: dict) -> dict:
    """Merge *detail* into ``SOURCE_UPDATE_META[key]`` and persist."""
    meta: dict = {}
    if SOURCE_UPDATE_META.exists():
        loaded = read_json(SOURCE_UPDATE_META)
        if isinstance(loaded, dict):
            meta = loaded
    from metabolic_safety_etl.schemas import now_utc
    meta[key] = {"updated_at": now_utc(), **detail}
    write_json(SOURCE_UPDATE_META, meta)
    return meta


# -- Bulk sync --------------------------------------------------------------

def bulk_sync_sources(key: str, progress=None) -> dict:
    """Run bulk sync for one or all sources."""
    from desktop_app.config import BULK_SOURCE_CONFIG, BULK_SOURCE_ORDER

    keys = BULK_SOURCE_ORDER if key == "all" else [key]
    results: list[dict] = []
    needs_rebuild = False
    downloaded_files = 0
    skipped_files = 0
    errors = 0
    total = max(len(keys), 1)
    for index, source_key in enumerate(keys, start=1):
        start = int((index - 1) / total * 86)
        span = max(1, int(86 / total))

        def step(value: int, message: str, _start=start, _span=span) -> None:
            if progress:
                progress(_start + int(max(0, min(value, 100)) * _span / 100), message)

        config = BULK_SOURCE_CONFIG.get(source_key, {})
        step(0, f"\u5168\u91cf\u5904\u7406 {index}/{total}\uff1a{config.get('label', source_key)}...")
        result = bulk_sync_one_source(source_key, step)
        results.append(result)
        needs_rebuild = needs_rebuild or bool(result.get("needs_rebuild"))
        downloaded_files += int(result.get("downloaded_files") or 0)
        skipped_files += int(result.get("skipped_files") or 0)
        errors += int(result.get("errors") or 0)
    return {
        "key": key,
        "sources": results,
        "needs_rebuild": needs_rebuild,
        "downloaded_files": downloaded_files,
        "skipped_files": skipped_files,
        "errors": errors,
        "message": (
            f"\u5168\u91cf\u62c9\u53d6\u5b8c\u6210\uff1a\u5904\u7406 {len(results)} \u4e2a\u6e90\uff0c"
            f"\u4e0b\u8f7d {downloaded_files} \u4e2a\u6587\u4ef6\uff0c"
            f"\u590d\u7528 {skipped_files} \u4e2a\u5df2\u5b58\u5728\u6587\u4ef6\uff0c"
            f"\u9519\u8bef {errors} \u4e2a\u3002"
        ),
    }


def bulk_sync_one_source(key: str, progress=None) -> dict:
    """Run bulk sync for a single source key."""
    from desktop_app.config import BULK_SOURCE_CONFIG

    config = BULK_SOURCE_CONFIG[key]
    mode = config.get("mode")

    if mode == "local_rebuild":
        target = config.get("out_dir")
        if isinstance(target, Path) and target.is_dir():
            files = [item for item in target.glob("**/*") if item.is_file()]
            size = sum(item.stat().st_size for item in files)
        elif isinstance(target, Path) and target.exists():
            files = [target]
            size = target.stat().st_size
        else:
            files = []
            size = 0
        update_source_meta(key, {
            "mode": "local_source_ready",
            "files": len(files),
            "bytes": size,
            "path": str(target.relative_to(ROOT)) if isinstance(target, Path) and target.exists() else str(target),
        })
        if progress:
            progress(100, f"{config['label']}\uff1a\u53d1\u73b0 {len(files)} \u4e2a\u672c\u5730\u6587\u4ef6\uff0c\u5c06\u5728\u91cd\u5efa\u65f6\u7eb3\u5165\u3002")
        return {
            "key": key, "mode": mode, "files": len(files), "bytes": size,
            "needs_rebuild": True, "downloaded_files": 0,
            "skipped_files": len(files), "errors": 0,
        }

    if mode == "api_full" and key == "psychonautwiki":
        facts = []
        offset = 0
        limit = 100
        max_pages = 40
        for page in range(max_pages):
            if progress:
                progress(int(page / max_pages * 80), f"PsychonautWiki \u5168\u91cf\u9875 {page + 1}/{max_pages}\uff0coffset={offset}...")
            batch = fetch_substance_facts(limit=limit, offset=offset)
            if not batch:
                break
            facts.extend(batch)
            if len(batch) < max(5, limit // 3):
                break
            offset += limit
        stored = append_optional_facts(facts)
        update_source_meta(key, {
            "mode": "api_full", "facts": len(facts),
            "optional_total": stored, "pages": (offset // limit) + 1,
        })
        if progress:
            progress(100, f"PsychonautWiki \u5168\u91cf\u5019\u9009\u5df2\u4fdd\u5b58\uff1a{len(facts)} \u6761\u4e8b\u5b9e\uff0c\u7d2f\u8ba1 {stored} \u6761\u3002")
        return {
            "key": key, "mode": mode, "facts": len(facts),
            "needs_rebuild": True, "downloaded_files": 0,
            "skipped_files": 0, "errors": 0,
        }

    if mode == "licensed_or_external":
        note = (
            "RxNorm \u5168\u91cf\u5305\u901a\u5e38\u901a\u8fc7 RxNav-in-a-Box / RxNorm release \u83b7\u53d6\uff0c"
            "\u90e8\u5206\u8bcd\u8868\u9700\u8981 UMLS \u8bb8\u53ef\uff1b"
            "\u672c\u5730\u53ea\u8bb0\u5f55\u6765\u6e90\u72b6\u6001\uff0c\u4e0d\u81ea\u52a8\u4e0b\u8f7d\u3002"
        )
        update_source_meta(key, {"mode": "external_required", "note": note})
        if progress:
            progress(100, note)
        return {
            "key": key, "mode": mode, "message": note,
            "needs_rebuild": False, "downloaded_files": 0,
            "skipped_files": 0, "errors": 0,
        }

    if mode == "download_manifest":
        manifest = fetch_bulk_manifest(key)
        parts = manifest.get("parts", []) or []
        out_dir = config["out_dir"]
        result = download_manifest_parts(parts, out_dir, progress=progress)
        update_source_meta(key, {
            "mode": "bulk_download",
            "files": result["downloaded_files"] + result["skipped_files"],
            "downloaded_files": result["downloaded_files"],
            "skipped_files": result["skipped_files"],
            "errors": result["errors"],
            "records": manifest.get("total_records"),
            "total_size_mb": manifest.get("total_size_mb"),
            "out_dir": str(out_dir.relative_to(ROOT)),
        })
        result.update({
            "key": key, "mode": mode,
            "records": manifest.get("total_records"),
            "total_size_mb": manifest.get("total_size_mb"),
            "needs_rebuild": False,
        })
        return result

    raise ValueError(f"Unsupported bulk source mode: {key} / {mode}")


# -- Bulk manifest fetchers -------------------------------------------------

def fetch_bulk_manifest(key: str) -> dict:
    """Dispatch to the correct manifest fetcher for *key*."""
    if key == "openfda_label":
        return fetch_openfda_label_manifest()
    if key == "dailymed":
        return fetch_dailymed_label_manifest()
    if key == "chembl":
        return fetch_chembl_bulk_manifest()
    if key == "foodrugs":
        return fetch_zenodo_manifest("8192515", "foodrugs")
    if key == "onsides":
        return fetch_github_release_manifest("tatonetti-lab", "onsides", "onsides")
    if key == "pharmgkb":
        return fetch_pharmgkb_bulk_manifest()
    raise ValueError(f"No bulk manifest adapter for {key}")


def fetch_chembl_bulk_manifest() -> dict:
    url = "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/"
    with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-local"}), timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(r'href="([^"]+)"', html)))
    parts = []
    for name in names:
        if re.search(r"chembl_.*_sqlite\.tar\.gz$", name) or re.search(r"chembl_.*_sqlite\.tar\.gz\.sha256sum$", name):
            parts.append({"name": name, "url": urljoin(url, name), "records": None, "size_mb": None})
    return {"source": "chembl", "source_url": url, "parts": parts, "total_records": None, "total_size_mb": None}


def fetch_zenodo_manifest(record_id: str, source: str) -> dict:
    url = f"https://zenodo.org/api/records/{record_id}"
    with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-local"}), timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = []
    for item in payload.get("files", []) or []:
        links = item.get("links") or {}
        file_url = links.get("self") or links.get("download")
        if not file_url:
            continue
        size = item.get("size") or 0
        parts.append({
            "name": item.get("key") or Path(urlparse(file_url).path).name,
            "url": file_url, "records": None,
            "size_mb": round(size / 1024 / 1024, 2) if size else None,
        })
    return {
        "source": source, "source_url": url, "parts": parts,
        "total_records": None,
        "total_size_mb": sum(part.get("size_mb") or 0 for part in parts),
    }


def fetch_github_release_manifest(owner_repo: str, repo_name: str, source: str) -> dict:
    api_url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    try:
        with urlopen(Request(api_url, headers={"User-Agent": "metabolic-safety-local"}), timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts = [
            {
                "name": asset.get("name"),
                "url": asset.get("browser_download_url"),
                "records": None,
                "size_mb": round((asset.get("size") or 0) / 1024 / 1024, 2),
            }
            for asset in payload.get("assets", []) or []
            if asset.get("browser_download_url")
        ]
        if parts:
            return {
                "source": source, "source_url": api_url, "parts": parts,
                "total_records": None,
                "total_size_mb": sum(part.get("size_mb") or 0 for part in parts),
            }
    except Exception:
        pass
    default_branch = "main"
    try:
        repo_api = f"https://api.github.com/repos/{owner_repo}"
        with urlopen(Request(repo_api, headers={"User-Agent": "metabolic-safety-local"}), timeout=20) as response:
            repo_payload = json.loads(response.read().decode("utf-8"))
            default_branch = repo_payload.get("default_branch") or default_branch
    except Exception:
        pass
    archive_url = f"https://github.com/{owner_repo}/archive/refs/heads/{default_branch}.zip"
    return {
        "source": source,
        "source_url": f"https://github.com/{owner_repo}",
        "parts": [{"name": f"{repo_name}-{default_branch}.zip", "url": archive_url, "records": None, "size_mb": None}],
        "total_records": None, "total_size_mb": None,
    }


def fetch_pharmgkb_bulk_manifest() -> dict:
    base = "https://api.pharmgkb.org/v1/download/file/data/"
    parts = []
    for name in PHARMGKB_BULK_FILES:
        url = base + name
        size_mb = None
        try:
            req = Request(url, headers={"User-Agent": "metabolic-safety-local"}, method="HEAD")
            with urlopen(req, timeout=12) as response:
                size = int(response.headers.get("Content-Length") or 0)
                size_mb = round(size / 1024 / 1024, 2) if size else None
        except Exception:
            continue
        parts.append({"name": name, "url": url, "records": None, "size_mb": size_mb})
    return {
        "source": "pharmgkb", "source_url": base, "parts": parts,
        "total_records": None,
        "total_size_mb": sum(part.get("size_mb") or 0 for part in parts),
    }


# -- Download helpers -------------------------------------------------------

def download_manifest_parts(
    parts: list[dict],
    out_dir: Path,
    progress=None,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    errors = 0
    total = max(len(parts), 1)
    for index, part in enumerate(parts, start=1):
        url = part.get("url")
        if not url:
            errors += 1
            continue
        name = part.get("name") or Path(urlparse(url).path).name or f"part_{index}.bin"
        target = out_dir / safe_filename(name)
        if progress:
            progress(int((index - 1) / total * 100), f"\u4e0b\u8f7d {index}/{len(parts)}\uff1a{target.name}")
        try:
            status = download_url(url, target, max_bytes=max_bytes)
            if status == "skipped":
                skipped += 1
            else:
                downloaded += 1
        except Exception as exc:
            errors += 1
            if progress:
                progress(
                    int(index / total * 100),
                    f"\u4e0b\u8f7d\u5931\u8d25\uff0c\u5df2\u8df3\u8fc7\uff1a{target.name}\uff08{type(exc).__name__}\uff09",
                )
    if progress:
        progress(100, f"\u4e0b\u8f7d\u5b8c\u6210\uff1a\u65b0\u589e {downloaded} \u4e2a\uff0c\u590d\u7528 {skipped} \u4e2a\uff0c\u9519\u8bef {errors} \u4e2a\u3002")
    return {"downloaded_files": downloaded, "skipped_files": skipped, "errors": errors, "out_dir": str(out_dir)}


def download_url(url: str, target: Path, max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES) -> str:
    if target.exists() and target.stat().st_size > 0:
        return "skipped"
    validate_download_url(url)
    tmp = target.with_name(target.name + ".part")
    req = Request(url, headers={"User-Agent": "metabolic-safety-local"})
    total_bytes = 0
    with urlopen(req, timeout=60) as response, tmp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                handle.close()
                tmp.unlink(missing_ok=True)
                raise ValueError(
                    f"Download exceeds max bytes ({max_bytes:,}): {url}"
                )
            handle.write(chunk)
    tmp.replace(target)
    return "downloaded"


# -- Public source sync -----------------------------------------------------

def sync_public_sources(progress=None, max_terms: int | None = None) -> None:
    def step(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    terms = public_sync_terms(max_terms)
    tasks = [
        (key, term, limit)
        for term in terms
        for key, limit in PUBLIC_SYNC_SOURCE_LIMITS.items()
        if should_query_public_source(key, term)
    ]
    attempted_counts: dict[str, int] = {key: 0 for key in PUBLIC_SYNC_SOURCE_LIMITS}
    for key, _, _ in tasks:
        attempted_counts[key] = attempted_counts.get(key, 0) + 1

    total_tasks = max(len(tasks), 1)
    fetched: list = []
    errors_by_source: dict[str, int] = {key: 0 for key in PUBLIC_SYNC_SOURCE_LIMITS}
    step(3, f"\u51c6\u5907\u5e76\u53d1\u540c\u6b65\u516c\u5f00\u68c0\u7d22\u6e90\uff1a{len(terms)} \u4e2a\u6838\u5fc3\u7269\u8d28\uff0c{len(tasks)} \u4e2a API \u8bf7\u6c42...")
    with ThreadPoolExecutor(max_workers=PUBLIC_SYNC_MAX_WORKERS) as executor:
        future_map = {
            executor.submit(
                fetch_direct_public_facts, key, term, limit,
                PUBLIC_SYNC_TIMEOUTS.get(key, 8),
            ): (key, term)
            for key, term, limit in tasks
        }
        for done, future in enumerate(as_completed(future_map), start=1):
            key, term = future_map[future]
            label = DIRECT_PUBLIC_SOURCES.get(key, {}).get("label", key)
            try:
                batch = future.result()
                fetched.extend(batch)
                message = f"\u516c\u5f00\u6e90\u540c\u6b65 {done}/{total_tasks}\uff1a{label} \u00b7 {term}\uff0c\u547d\u4e2d {len(batch)} \u6761"
            except Exception as exc:
                errors_by_source[key] = errors_by_source.get(key, 0) + 1
                message = f"\u516c\u5f00\u6e90\u540c\u6b65 {done}/{total_tasks}\uff1a{label} \u00b7 {term} \u8d85\u65f6/\u65e0\u7ed3\u679c\uff0c\u5df2\u8df3\u8fc7\uff08{type(exc).__name__}\uff09"
            step(3 + int(done / total_tasks * 62), message)

    step(66, "\u540c\u6b65 PsychonautWiki \u6279\u91cf\u5019\u9009...")
    try:
        psychonaut_facts = fetch_substance_facts(limit=50, offset=0)
        fetched.extend(psychonaut_facts)
        attempted_counts["psychonautwiki"] = 1
    except Exception:
        errors_by_source["psychonautwiki"] = errors_by_source.get("psychonautwiki", 0) + 1
    stored = append_optional_facts(fetched)
    record_public_sync_meta(fetched, stored, attempted_counts, errors_by_source)
    step(70, f"\u516c\u5f00\u6e90\u5019\u9009\u5df2\u4fdd\u5b58\uff1a\u65b0\u589e/\u66f4\u65b0 {len(fetched)} \u6761\uff0c\u7d2f\u8ba1 {stored} \u6761\u3002")


def public_sync_terms(max_terms: int | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    if ZH_ALIASES.exists():
        with ZH_ALIASES.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                _add_public_sync_term(terms, seen, row.get("name_en"))
                for alias in (row.get("aliases") or "").split("|"):
                    if alias.isascii():
                        _add_public_sync_term(terms, seen, alias)
                if max_terms and len(terms) >= max_terms:
                    return terms[:max_terms]

    rows = read_json(BUILD / "init_substances.json") if (BUILD / "init_substances.json").exists() else []
    for row in rows:
        name = row.get("name_en") or row.get("id")
        _add_public_sync_term(terms, seen, name)
        if max_terms and len(terms) >= max_terms:
            break
    return terms[:max_terms] if max_terms else terms


def _add_public_sync_term(terms: list[str], seen: set[str], value: object) -> None:
    term = str(value or "").strip()
    key = term.lower()
    if not term or key in seen or not looks_like_public_api_term(term):
        return
    terms.append(term)
    seen.add(key)


def should_query_public_source(key: str, term: str) -> bool:
    if key in {"openfda_label", "dailymed"}:
        return looks_like_public_api_term(term)
    return True


def record_public_sync_meta(
    facts,
    stored: int,
    attempted_counts: dict[str, int] | None = None,
    errors_by_source: dict[str, int] | None = None,
) -> None:
    from metabolic_safety_etl.schemas import now_utc

    counts: dict[str, int] = {}
    for fact in facts:
        key = SOURCE_NAME_TO_KEY.get(fact.source_name)
        if key:
            counts[key] = counts.get(key, 0) + 1
    meta: dict = {}
    if SOURCE_UPDATE_META.exists():
        loaded = read_json(SOURCE_UPDATE_META)
        if isinstance(loaded, dict):
            meta = loaded
    timestamp = now_utc()
    attempted_counts = attempted_counts or {}
    errors_by_source = errors_by_source or {}
    for key in sorted(set(counts) | set(attempted_counts) | set(errors_by_source)):
        meta[key] = {
            "updated_at": timestamp,
            "mode": "public_sync",
            "facts": counts.get(key, 0),
            "attempted": attempted_counts.get(key, 0),
            "errors": errors_by_source.get(key, 0),
            "optional_total": stored,
            "timeout_seconds": PUBLIC_SYNC_TIMEOUTS.get(key),
        }
    write_json(SOURCE_UPDATE_META, meta)


# -- Seed rebuild -----------------------------------------------------------

def rebuild_seed_dataset(progress=None) -> dict:
    def step(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    step(5, "\u626b\u63cf DDInter \u5168\u91cf CSV...")
    paths = find_ddinter_csvs(DDINTER_DIR)
    if not paths:
        raise RuntimeError(f"No DDInter CSV files found in {DDINTER_DIR}")
    step(15, f"\u8bfb\u53d6 DDInter CSV\uff1a{len(paths)} \u4e2a\u6587\u4ef6...")
    facts = load_ddinter_csv_facts(paths, None, ZH_ALIASES if ZH_ALIASES.exists() else None)
    step(45, f"DDInter \u5df2\u8f7d\u5165\uff1a{len(facts)} \u6761\u4e8b\u5b9e\uff0c\u5408\u5e76\u672c\u5730\u8865\u5145\u4e8b\u5b9e...")
    if SUPPLEMENT_FACTS.exists():
        facts.extend(load_facts(read_json(SUPPLEMENT_FACTS)))
    if DOSE_RULES_FACTS.exists():
        facts.extend(load_facts(read_json(DOSE_RULES_FACTS)))
    step(55, "\u5408\u5e76\u5df2\u62c9\u53d6\u7684\u516c\u5f00\u6e90\u5019\u9009\u4e8b\u5b9e...")
    if OPTIONAL_FACTS.exists():
        facts.extend(load_facts(read_json(OPTIONAL_FACTS)))
    step(60, "\u62bd\u53d6\u5df2\u4e0b\u8f7d\u7684 openFDA/DailyMed/ChEMBL/FooDrugs/OnSIDES/PharmGKB \u672c\u5730\u5168\u91cf\u5305...")
    raw_facts, raw_summary = load_raw_source_facts(RAW_DIR, max_records_per_source=100000, max_files_per_source=0)
    facts.extend(raw_facts)
    step(65, f"\u672c\u5730\u5168\u91cf\u5305\u5019\u9009\u5df2\u878d\u5408\uff1a{len(raw_facts)} \u6761\uff1b{raw_summary}")
    step(68, f"\u6267\u884c\u591a\u6e90\u878d\u5408\uff1a{len(facts)} \u6761\u8bc1\u636e\u4e8b\u5b9e...")
    dataset = build_dataset(facts, DATASET_VERSION)
    step(78, "\u5199\u5165 JSON \u79cd\u5b50\u6587\u4ef6...")
    write_mobile_seed_files(BUILD, dataset)
    step(86, "\u5199\u5165 SQLite \u68c0\u7d22\u5e93...")
    next_db = BUILD / f"app_seed.{DATASET_VERSION}.{len(dataset['evidence_facts'])}.{int(time.time())}.sqlite"
    write_sqlite(next_db, dataset)
    step(96, "\u5207\u6362\u5f53\u524d\u6d3b\u8dc3 SQLite...")
    ACTIVE_DB_POINTER.write_text(next_db.name, encoding="utf-8")
    manifest = read_json(BUILD / "manifest.json")
    record_rebuild_source_meta(manifest, len(paths))
    return {"manifest": manifest, "dataset": dataset}


def record_rebuild_source_meta(manifest: dict, ddinter_files: int) -> None:
    from metabolic_safety_etl.schemas import now_utc

    meta: dict = {}
    if SOURCE_UPDATE_META.exists():
        loaded = read_json(SOURCE_UPDATE_META)
        if isinstance(loaded, dict):
            meta = loaded
    timestamp = now_utc()
    meta["ddinter"] = {
        "updated_at": timestamp,
        "mode": "included_in_full_rebuild",
        "files": ddinter_files,
        "substances": manifest.get("substances_count"),
        "interactions": manifest.get("interactions_count"),
        "facts": manifest.get("facts_count"),
    }
    if SUPPLEMENT_FACTS.exists():
        meta["supplemental"] = {
            "updated_at": timestamp,
            "mode": "included_in_full_rebuild",
            "file": str(SUPPLEMENT_FACTS.relative_to(ROOT)),
        }
    if DOSE_RULES_FACTS.exists():
        meta["dose_rules"] = {
            "updated_at": timestamp,
            "mode": "included_in_full_rebuild",
            "file": str(DOSE_RULES_FACTS.relative_to(ROOT)),
        }
    write_json(SOURCE_UPDATE_META, meta)


# -- Job runners (called inside REBUILD_LOCK) --------------------------------

def run_rebuild_job(job_id: str) -> None:
    with REBUILD_LOCK:
        try:
            result = rebuild_seed_dataset(
                lambda progress, message: update_job(job_id, progress, message),
            )
            update_job(
                job_id, 100,
                "\u672c\u5730\u5e93\u5df2\u91cd\u5efa\u3002\u9875\u9762\u4f1a\u91cd\u65b0\u52a0\u8f7d\u6570\u636e\u3002",
                status="done", manifest=result.get("manifest", {}),
            )
        except Exception as exc:
            update_job(job_id, 100, str(exc), status="error", error=type(exc).__name__)


def run_public_sync_job(job_id: str, max_terms: int | None = None) -> None:
    with REBUILD_LOCK:
        try:
            sync_public_sources(
                lambda progress, message: update_job(job_id, progress, message),
                max_terms=max_terms,
            )
            result = rebuild_seed_dataset(
                lambda progress, message: update_job(job_id, 70 + int(progress * 0.3), message),
            )
            update_job(
                job_id, 100,
                "\u516c\u5f00\u6e90\u540c\u6b65\u5b8c\u6210\uff0c\u4e14\u672c\u5730\u5e93\u5df2\u91cd\u5efa\u3002",
                status="done", manifest=result.get("manifest", {}),
            )
        except Exception as exc:
            update_job(job_id, 100, str(exc), status="error", error=type(exc).__name__)


def run_bulk_sync_job(job_id: str, key: str) -> None:
    with REBUILD_LOCK:
        try:
            result = bulk_sync_sources(
                key, lambda progress, message: update_job(job_id, progress, message),
            )
            if result.get("needs_rebuild"):
                update_job(job_id, 88, "\u5df2\u62c9\u53d6\u9700\u8981\u5165\u5e93\u7684\u6e90\uff0c\u5f00\u59cb\u91cd\u5efa\u672c\u5730\u68c0\u7d22\u5e93...")
                rebuilt = rebuild_seed_dataset(
                    lambda progress, message: update_job(job_id, 88 + int(progress * 0.11), message),
                )
                result["manifest"] = rebuilt.get("manifest", {})
            update_job(
                job_id, 100,
                result.get("message") or "\u5168\u91cf\u62c9\u53d6\u4efb\u52a1\u5b8c\u6210\u3002",
                status="done", bulk=result,
            )
        except Exception as exc:
            update_job(job_id, 100, str(exc), status="error", error=type(exc).__name__)
