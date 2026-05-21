from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.i18n.glossary import controlled_dictionary_payload, entity_translation_for, load_zh_aliases, translate_controlled, translate_structured_text  # noqa: E402
from metabolic_safety_etl.i18n.segments import segment_text  # noqa: E402
from metabolic_safety_etl.i18n.translation_memory import TranslationMemory  # noqa: E402


DOMAIN_ALIASES = {
    "interactions": "interactions",
    "interaction": "interactions",
    "dose-rules": "dose-rules",
    "dose_rules": "dose-rules",
    "drug-effects": "drug-effects",
    "drug_effects": "drug-effects",
}

DOMAIN_ID_KEYS = {
    "interactions": "interaction_id",
    "dose-rules": "rule_id",
    "drug-effects": "fact_id",
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


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def id_path(prefix: str, substance_id: str) -> str:
    digest = hashlib.sha256(str(substance_id).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}/{digest[:2]}/{digest}.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def parse_domains(value: str) -> list[str]:
    domains: list[str] = []
    for part in str(value or "").split(","):
        key = DOMAIN_ALIASES.get(part.strip())
        if key and key not in domains:
            domains.append(key)
    return domains or ["interactions", "dose-rules", "drug-effects"]


def iter_search_items(api_dir: Path) -> Iterator[dict[str, Any]]:
    path = api_dir / "search" / "index.json"
    if path.exists():
        for item in read_json(path, []):
            if isinstance(item, dict):
                yield item
        return
    for shard in sorted((api_dir / "search" / "shards").glob("*.json")):
        payload = read_json(shard, [])
        rows = payload.get("items") if isinstance(payload, dict) else payload
        for item in rows or []:
            if isinstance(item, dict):
                yield item


def iter_domain_files(api_dir: Path, domain: str) -> Iterator[tuple[str, str, Path]]:
    base = api_dir / domain / "by-substance"
    if not base.exists():
        return
    for path in sorted(base.glob("*/*.json")):
        rel = path.relative_to(api_dir).as_posix()
        yield rel, rel.removeprefix(f"{domain}/"), path


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("items") if isinstance(payload, dict) else payload
    return [row for row in rows or [] if isinstance(row, dict)]


def lookup_segmented(memory: TranslationMemory, locale: str, text: str, max_chars: int) -> str | None:
    segments = segment_text(text, max_chars=max_chars)
    if not segments:
        return None
    translated: list[str] = []
    for segment in segments:
        item = memory.usable_translation(locale, segment)
        if not item:
            return None
        translated.append(item)
    return " ".join(part.strip() for part in translated if part.strip()) or None


def translation_status(memory: TranslationMemory, locale: str, text: str) -> str:
    entry = memory.get(locale, text)
    return entry.status if entry else "pending"


def row_overlay(domain: str, row: dict[str, Any], memory: TranslationMemory, locale: str, max_chars: int) -> dict[str, Any] | None:
    row_key = DOMAIN_ID_KEYS[domain]
    row_id = str(row.get(row_key) or "")
    if not row_id:
        return None
    fields: dict[str, Any] = {}
    field_status: dict[str, str] = {}
    for field_name in CONTROLLED_FIELDS.get(domain, ()):
        translated = translate_controlled(field_name, row.get(field_name))
        if translated:
            fields[field_name] = translated
            field_status[field_name] = "rule_based"
    for field_name in TRANSLATABLE_FIELDS.get(domain, ()):
        value = row.get(field_name)
        if isinstance(value, str) and value.strip():
            structured = translate_structured_text(field_name, value)
            translated = structured or lookup_segmented(memory, locale, value, max_chars=max_chars)
            if translated:
                fields[field_name] = translated
                field_status[field_name] = "rule_based" if structured else translation_status(memory, locale, segment_text(value, max_chars=max_chars)[0])
    if domain == "dose-rules" and isinstance(row.get("thresholds"), list):
        translated_thresholds: list[dict[str, Any]] = []
        any_threshold = False
        for threshold in row.get("thresholds") or []:
            if not isinstance(threshold, dict):
                translated_thresholds.append({})
                continue
            out: dict[str, Any] = {}
            label = threshold.get("label")
            controlled_label = translate_controlled("threshold_label", label)
            if controlled_label:
                out["label"] = controlled_label
            elif isinstance(label, str) and label.strip():
                translated = lookup_segmented(memory, locale, label, max_chars=max_chars)
                if translated:
                    out["label"] = translated
            level = translate_controlled("level", threshold.get("level") or threshold.get("risk"))
            if level:
                out["level"] = level
            if out:
                any_threshold = True
            translated_thresholds.append(out)
        if any_threshold:
            fields["thresholds"] = translated_thresholds
            field_status["thresholds"] = "mixed"
    if domain == "dose-rules" and isinstance(row.get("population"), dict):
        age = translate_controlled("age_group", row["population"].get("age_group"))
        if age:
            fields.setdefault("population", {})["age_group"] = age
            field_status["population.age_group"] = "rule_based"
    if not fields:
        return None
    status = "machine_unreviewed" if any(value.startswith("machine") for value in field_status.values()) else "rule_based"
    return {
        row_key: row_id,
        "locale": locale,
        "fields": fields,
        "field_status": field_status,
        "status": status,
        "provider": "translation_memory",
    }


def export_domain(api_dir: Path, out_dir: Path, domain: str, memory: TranslationMemory, locale: str, max_chars: int) -> dict[str, Any]:
    records = 0
    subjects = 0
    status_counts: Counter[str] = Counter()
    for _rel_path, suffix, path in iter_domain_files(api_dir, domain):
        rows = rows_from_payload(read_json(path, []))
        overlay_rows = [row_overlay(domain, row, memory, locale, max_chars=max_chars) for row in rows]
        overlay_rows = [row for row in overlay_rows if row]
        if not overlay_rows:
            continue
        for row in overlay_rows:
            status_counts[str(row.get("status") or "unknown")] += 1
        write_json(out_dir / domain / suffix, {"locale": locale, "items": overlay_rows})
        records += len(overlay_rows)
        subjects += 1
    manifest = {
        "locale": locale,
        "domain": domain,
        "records": records,
        "subjects": subjects,
        "status_counts": dict(status_counts),
        "generated_at": now_utc(),
        "policy": "Translations are additive display overlays. Source English evidence remains authoritative; machine translations are unreviewed unless marked otherwise.",
    }
    write_json(out_dir / domain / "manifest.json", manifest)
    return manifest


def export_entities(api_dir: Path, out_dir: Path, locale: str, zh_aliases_path: Path | None) -> dict[str, Any]:
    zh_aliases = load_zh_aliases(zh_aliases_path)
    seen: set[str] = set()
    records = 0
    status_counts: Counter[str] = Counter()
    for item in iter_search_items(api_dir):
        sid = str(item.get("id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        translation = entity_translation_for(item, zh_aliases)
        if not translation:
            continue
        payload = {"id": sid, "locale": locale, **translation}
        write_json(out_dir / "entities" / "by-id" / id_path("", sid).lstrip("/"), payload)
        records += 1
        status_counts[str(payload.get("status") or "unknown")] += 1
    manifest = {
        "locale": locale,
        "records": records,
        "status_counts": dict(status_counts),
        "generated_at": now_utc(),
        "policy": "Entity translations merge curated local Chinese names and existing substance name_zh fields.",
    }
    write_json(out_dir / "entities" / "manifest.json", manifest)
    return manifest


def write_i18n_manifests(api_dir: Path, locale_root: Path, locale: str, domain_manifests: dict[str, dict[str, Any]], entity_manifest: dict[str, Any]) -> None:
    ui_payload = {
        "locale": locale,
        "controlled": controlled_dictionary_payload(),
        "translation_notice": "中文翻译用于辅助理解；英文原文和来源证据仍为准。机器翻译默认未人工复核。",
        "generated_at": now_utc(),
    }
    write_json(locale_root / "ui.json", ui_payload)
    locale_manifest = {
        "locale": locale,
        "generated_at": now_utc(),
        "ui": "ui.json",
        "entities": "entities/manifest.json",
        "domains": {domain: f"{domain}/manifest.json" for domain in sorted(domain_manifests)},
        "entity_records": entity_manifest.get("records", 0),
        "policy": "i18n overlays never replace source evidence. Use English fallback when a translation is missing or failed validation.",
    }
    write_json(locale_root / "manifest.json", locale_manifest)
    root_manifest = read_json(api_dir / "i18n" / "manifest.json", {"locales": []})
    locales = sorted(set([*root_manifest.get("locales", []), locale]))
    root_manifest.update({
        "locales": locales,
        "default_locale": "en",
        "generated_at": now_utc(),
        "available": {
            **root_manifest.get("available", {}),
            locale: {
                "manifest": f"{locale}/manifest.json",
                "ui": f"{locale}/ui.json",
                "entities": f"{locale}/entities/manifest.json",
                **{domain: f"{locale}/{domain}/manifest.json" for domain in sorted(domain_manifests)},
            },
        },
        "policy": "Static i18n overlays are display-only and do not change risk computation or evidence provenance.",
    })
    write_json(api_dir / "i18n" / "manifest.json", root_manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export zh-CN static i18n overlays from translation memory.")
    parser.add_argument("--api-dir", default="public/api", type=Path)
    parser.add_argument("--memory", default="build/i18n/translation_memory.sqlite", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--domains", default="interactions,dose-rules,drug-effects")
    parser.add_argument("--out-dir", default=None, type=Path, help="Defaults to <api-dir>/i18n/<locale>")
    parser.add_argument("--zh-aliases", default="data/overrides/drug_zh_aliases.csv", type=Path)
    parser.add_argument("--max-chars", default=1800, type=int)
    args = parser.parse_args()

    locale_root = args.out_dir or (args.api_dir / "i18n" / args.locale)
    memory = TranslationMemory(args.memory)
    try:
        domains = parse_domains(args.domains)
        entity_manifest = export_entities(args.api_dir, locale_root, args.locale, args.zh_aliases)
        domain_manifests = {domain: export_domain(args.api_dir, locale_root, domain, memory, args.locale, args.max_chars) for domain in domains}
        write_i18n_manifests(args.api_dir, locale_root, args.locale, domain_manifests, entity_manifest)
    finally:
        memory.close()
    print(f"i18n_locale={args.locale} out={locale_root}")
    print("domains=" + ",".join(domains))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
