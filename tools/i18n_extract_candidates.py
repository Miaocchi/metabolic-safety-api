from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.i18n.glossary import load_zh_aliases, normalize_key, translate_controlled, translate_structured_text  # noqa: E402
from metabolic_safety_etl.i18n.segments import normalize_segment_text, segment_text  # noqa: E402
from metabolic_safety_etl.i18n.translation_memory import text_hash  # noqa: E402


DOMAIN_ALIASES = {
    "interactions": "interactions",
    "interaction": "interactions",
    "dose-rules": "dose-rules",
    "dose_rules": "dose-rules",
    "dose_rule": "dose-rules",
    "drug-effects": "drug-effects",
    "drug_effects": "drug-effects",
    "drug_effect": "drug-effects",
}

TRANSLATABLE_FIELDS = {
    "interactions": ("mechanism", "note"),
    "dose-rules": ("note",),
    "drug-effects": ("effect_text", "mechanism_of_action", "evidence"),
}

CONTROLLED_FIELDS = {
    "interactions": ("interaction_type", "risk_level", "confidence", "source_tier", "action"),
    "dose-rules": ("route", "review_status", "confidence", "source_tier"),
    "drug-effects": ("section", "action_type", "confidence", "source_tier"),
}

NESTED_TRANSLATABLE = {
    "dose-rules": (("thresholds", "label", "threshold_label"),),
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def parse_domains(value: str) -> list[str]:
    domains: list[str] = []
    for part in str(value or "").split(","):
        key = DOMAIN_ALIASES.get(part.strip())
        if key and key not in domains:
            domains.append(key)
    return domains or ["interactions", "dose-rules", "drug-effects"]


def iter_search_items(api_dir: Path) -> Iterator[dict[str, Any]]:
    search_index = api_dir / "search" / "index.json"
    if search_index.exists():
        for item in read_json(search_index, []):
            if isinstance(item, dict):
                yield item
        return
    shard_dir = api_dir / "search" / "shards"
    for path in sorted(shard_dir.glob("*.json")):
        payload = read_json(path, [])
        rows = payload.get("items") if isinstance(payload, dict) else payload
        for item in rows or []:
            if isinstance(item, dict):
                yield item


def iter_domain_files(api_dir: Path, domain: str) -> Iterator[tuple[str, Path]]:
    base = api_dir / domain / "by-substance"
    if not base.exists():
        return
    for path in sorted(base.glob("*/*.json")):
        yield path.relative_to(api_dir).as_posix(), path


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("items") if isinstance(payload, dict) else payload
    return [row for row in rows or [] if isinstance(row, dict)]


def add_candidate(
    by_hash: dict[str, dict[str, Any]],
    *,
    locale: str,
    domain: str,
    path: str,
    row_key: str,
    row_id: str,
    field_name: str,
    source_text: str,
    max_chars: int,
) -> None:
    for index, segment in enumerate(segment_text(source_text, max_chars=max_chars)):
        clean = normalize_segment_text(segment)
        if not clean:
            continue
        key = text_hash(clean)
        row = by_hash.setdefault(
            key,
            {
                "locale": locale,
                "text_hash": key,
                "source_text": clean,
                "domain": domain,
                "field_name": field_name,
                "occurrences": [],
            },
        )
        row["occurrences"].append({
            "path": path,
            "row_key": row_key,
            "row_id": row_id,
            "segment_index": index,
        })


def row_id_for(domain: str, row: dict[str, Any]) -> tuple[str, str]:
    if domain == "interactions":
        return "interaction_id", str(row.get("interaction_id") or "")
    if domain == "dose-rules":
        return "rule_id", str(row.get("rule_id") or "")
    return "fact_id", str(row.get("fact_id") or "")


def extract_candidates(api_dir: Path, domains: list[str], locale: str, max_chars: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_hash: dict[str, dict[str, Any]] = {}
    domain_counts: Counter[str] = Counter()
    row_counts: Counter[str] = Counter()
    controlled_counts: Counter[str] = Counter()
    for domain in domains:
        for rel_path, path in iter_domain_files(api_dir, domain):
            rows = rows_from_payload(read_json(path, []))
            row_counts[domain] += len(rows)
            for row in rows:
                row_key, row_id = row_id_for(domain, row)
                if not row_id:
                    continue
                for field_name in CONTROLLED_FIELDS.get(domain, ()):
                    value = row.get(field_name)
                    if translate_controlled(field_name, value):
                        controlled_counts[f"{domain}.{field_name}"] += 1
                for field_name in TRANSLATABLE_FIELDS.get(domain, ()):
                    value = row.get(field_name)
                    if isinstance(value, str) and value.strip() and not translate_structured_text(field_name, value):
                        add_candidate(by_hash, locale=locale, domain=domain, path=rel_path, row_key=row_key, row_id=row_id, field_name=field_name, source_text=value, max_chars=max_chars)
                        domain_counts[domain] += 1
                for array_key, nested_key, field_alias in NESTED_TRANSLATABLE.get(domain, ()):
                    items = row.get(array_key)
                    if not isinstance(items, list):
                        continue
                    for nested_index, nested in enumerate(items):
                        if not isinstance(nested, dict):
                            continue
                        value = nested.get(nested_key)
                        if isinstance(value, str) and value.strip() and not translate_controlled(field_alias, value):
                            add_candidate(by_hash, locale=locale, domain=domain, path=rel_path, row_key=row_key, row_id=row_id, field_name=f"{array_key}.{nested_index}.{nested_key}", source_text=value, max_chars=max_chars)
                            domain_counts[domain] += 1
    report = {
        "locale": locale,
        "api_dir": str(api_dir),
        "domains": domains,
        "rows_scanned": dict(row_counts),
        "translatable_field_occurrences": dict(domain_counts),
        "unique_segments": len(by_hash),
        "controlled_vocab_hits": dict(controlled_counts),
    }
    return sorted(by_hash.values(), key=lambda item: (item["domain"], item["field_name"], item["source_text"])), report


def entity_coverage(api_dir: Path, zh_aliases_path: Path | None) -> dict[str, Any]:
    zh_aliases = load_zh_aliases(zh_aliases_path)
    total = 0
    existing_zh = 0
    alias_matches = 0
    seen: set[str] = set()
    for item in iter_search_items(api_dir):
        sid = str(item.get("id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        total += 1
        if item.get("name_zh"):
            existing_zh += 1
        name_en = normalize_key(item.get("name_en") or item.get("name") or "")
        if name_en and name_en in zh_aliases:
            alias_matches += 1
    return {
        "substances": total,
        "existing_name_zh": existing_zh,
        "zh_alias_csv_entries": len(zh_aliases),
        "zh_alias_name_matches": alias_matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract unique zh-CN translation candidates from static API overlays.")
    parser.add_argument("--api-dir", default="public/api", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--domains", default="interactions,dose-rules,drug-effects")
    parser.add_argument("--out", default="build/i18n/zh-CN/candidates.jsonl", type=Path)
    parser.add_argument("--report", default="build/i18n/zh-CN/coverage_report.json", type=Path)
    parser.add_argument("--zh-aliases", default="data/overrides/drug_zh_aliases.csv", type=Path)
    parser.add_argument("--max-chars", default=1800, type=int)
    args = parser.parse_args()

    domains = parse_domains(args.domains)
    candidates, report = extract_candidates(args.api_dir, domains, args.locale, args.max_chars)
    report["entity_coverage"] = entity_coverage(args.api_dir, args.zh_aliases)
    written = write_jsonl(args.out, candidates)
    report["candidate_file"] = str(args.out)
    report["candidate_rows"] = written
    write_json(args.report, report)
    print(f"candidates={written}")
    print(f"report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
