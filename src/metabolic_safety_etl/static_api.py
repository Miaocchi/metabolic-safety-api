from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from typing import Any


API_VERSION = "static-drug-api-v1"


def write_compact_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def reset_output_dir(out_dir: Path) -> None:
    if out_dir.exists():
        if out_dir.resolve() == out_dir.resolve().anchor:
            raise ValueError(f"refusing to clear root directory: {out_dir}")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_key(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "unknown"))
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "unknown"


def write_source_library(api_out_dir: Path, evidence_facts: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for fact in evidence_facts:
        source_name = str(fact.get("source_name") or "Unknown source")
        key = source_key(source_name)
        row = by_source.setdefault(
            key,
            {
                "key": key,
                "source_name": source_name,
                "source_tier": fact.get("source_tier") or "Unknown",
                "source_url": fact.get("source_url") or "",
                "facts": 0,
                "fact_types": {},
                "risk_levels": {},
                "confidence": {},
                "review_status": {},
                "use_policy": {},
                "sample_subjects": [],
            },
        )
        row["facts"] += 1
        for group_key, fact_key in (
            ("fact_types", "fact_type"),
            ("risk_levels", "risk_level"),
            ("confidence", "confidence"),
            ("review_status", "review_status"),
            ("use_policy", "use_policy"),
        ):
            value = str(fact.get(fact_key) or "Unknown")
            row[group_key][value] = row[group_key].get(value, 0) + 1
        if not row.get("source_url") and fact.get("source_url"):
            row["source_url"] = fact.get("source_url")
        subjects = fact.get("subject_ids") or []
        if isinstance(subjects, list):
            for subject in subjects:
                if len(row["sample_subjects"]) >= 12:
                    break
                subject_value = str(subject)
                if subject_value and subject_value not in row["sample_subjects"]:
                    row["sample_subjects"].append(subject_value)

    source_dir = api_out_dir / "sources"
    rows = sorted(by_source.values(), key=lambda item: (-int(item.get("facts") or 0), item.get("source_name") or ""))
    for row in rows:
        detail_path = source_dir / "by-key" / f"{row['key']}.json"
        write_compact_json(detail_path, row)
        row["path"] = f"sources/by-key/{row['key']}.json"
    index_payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sources_count": len(rows),
        "facts_count": len(evidence_facts),
        "merge_policy": "Online source layers are fused by source tier and confidence. Higher-risk reviewed evidence is not downgraded by lower-tier community or signal data.",
        "items": rows,
    }
    write_compact_json(source_dir / "index.json", index_payload)
    return {
        "index": "sources/index.json",
        "sources_count": len(rows),
        "facts_count": len(evidence_facts),
    }


def write_full_package(input_dir: Path, api_out_dir: Path, seed_manifest: dict[str, Any], counts: dict[str, int], source_library: dict[str, Any]) -> dict[str, Any]:
    package_dir = api_out_dir / "packages" / "full"
    package_dir.mkdir(parents=True, exist_ok=True)
    zip_path = package_dir / "fused-online-library.zip"
    files = [
        (input_dir / "manifest.json", "manifest.json"),
        (input_dir / "init_substances.json", "init_substances.json"),
        (input_dir / "init_interactions.json", "init_interactions.json"),
        (input_dir / "init_dose_rules.json", "init_dose_rules.json"),
        (input_dir / "evidence_facts.json", "evidence_facts.json"),
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, arcname in files:
            if source.exists():
                archive.write(source, arcname)
    package_manifest = {
        "package_version": "fused-online-library-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset_version": seed_manifest.get("dataset_version"),
        "counts": counts,
        "source_library": source_library,
        "files": {
            "zip": "fused-online-library.zip",
            "zip_sha256": sha256_file(zip_path),
            "zip_bytes": zip_path.stat().st_size,
        },
        "local_policy": "The local app keeps its current lightweight local seed, private journal and profile storage. This full package is hosted online for remote fallback, review tools and optional future import flows only.",
        "merge_policy": "This package is the fused read-only online library. It is built from all included open/local source layers with source-tier precedence; lower-tier sources can supplement aliases, PK candidates and evidence text but cannot downgrade higher-risk reviewed rules.",
        "warning": seed_manifest.get("warning") or "Prototype data. Do not use as clinical decision support without source review and validation.",
    }
    write_compact_json(package_dir / "manifest.json", package_manifest)
    return {
        "manifest": "packages/full/manifest.json",
        "zip": "packages/full/fused-online-library.zip",
        "format": package_manifest["package_version"],
        "zip_sha256": package_manifest["files"]["zip_sha256"],
        "zip_bytes": package_manifest["files"]["zip_bytes"],
    }


def id_path(prefix: str, substance_id: str) -> str:
    digest = hashlib.sha256(str(substance_id).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}/{digest[:2]}/{digest}.json"


def compact_search_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    return re.sub(r"[\s_\-./()[\]{}]+", "", text)


def search_shard_key(value: Any) -> str:
    text = compact_search_text(value)
    if not text:
        return "other"
    char = text[0]
    if char.isascii() and char.isalnum():
        prefix = "".join(part for part in text if part.isascii() and part.isalnum())[:2]
        return prefix or char
    return f"u{ord(char):04x}"


def primary_search_key(entry: dict[str, Any]) -> str:
    return search_shard_key(entry.get("name_en") or entry.get("name_zh") or entry.get("id"))


def write_search_shards(api_out_dir: Path, search_index: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in search_index:
        keys = {
            primary_search_key(row),
            search_shard_key(row.get("id")),
            search_shard_key(row.get("name_en")),
            search_shard_key(row.get("name_zh")),
        }
        for alias in row.get("aliases") or []:
            keys.add(search_shard_key(alias))
        for key in sorted(key for key in keys if key):
            buckets.setdefault(key, []).append(row)

    shard_counts: dict[str, int] = {}
    for key, rows in sorted(buckets.items()):
        deduped = list({str(row.get("id")): row for row in rows if row.get("id")}.values())
        deduped.sort(key=lambda item: ((item.get("name_zh") or item.get("name_en") or item.get("id") or "").lower(), item.get("id") or ""))
        write_compact_json(api_out_dir / "search" / "shards" / f"{key}.json", deduped)
        shard_counts[key] = len(deduped)

    manifest = {
        "items": len(search_index),
        "policy": "Search UI should load shard files by query prefix instead of parsing the full search/index.json on page open.",
        "shard_path": "search/shards/{key}.json",
        "shards": shard_counts,
    }
    write_compact_json(api_out_dir / "search" / "manifest.json", manifest)
    return manifest


def write_adverse_signal_api(api_out_dir: Path, evidence_facts: list[dict[str, Any]], substances_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    severe = {"DEATH", "CARDIAC ARREST", "RESPIRATORY DEPRESSION", "COMA", "SEIZURE", "CONVULSION", "SEROTONIN SYNDROME"}
    moderate_signal_min_count = 20
    grouped: dict[str, dict[str, Any]] = {}
    for fact in evidence_facts:
        if fact.get("fact_type") != "adverse_event_signal":
            continue
        subject_ids = fact.get("subject_ids") or []
        subject_id = str(subject_ids[0]) if subject_ids else ""
        if not subject_id:
            continue
        substance = substances_by_id.get(subject_id)
        claim = fact.get("claim") if isinstance(fact.get("claim"), dict) else {}
        reaction = str(claim.get("reaction") or "").strip()
        row = grouped.setdefault(
            subject_id,
            {
                "risk_kind": "signal",
                "signal_id": f"static_signal_{subject_id}",
                "substance_id": subject_id,
                "substance_name": substance_display_name(substance, subject_id),
                "query_term": claim.get("query_term") or subject_id,
                "reactions": [],
                "risk_level": "Minor",
                "confidence": fact.get("confidence") or "Low",
                "source_tier": fact.get("source_tier") or "Signal",
                "interaction_type": "adverse_event_signal",
                "source_name": fact.get("source_name") or "openFDA FAERS adverse event",
                "source_url": fact.get("source_url") or "https://open.fda.gov/apis/drug/event/",
                "note": "静态库中的 FAERS 自发不良事件报告计数只提示药物警戒候选信号，不代表因果关系、发生率或确认联用冲突。",
            },
        )
        if reaction:
            row["reactions"].append({
                "reaction": reaction,
                "label": claim.get("reaction_label_zh") or reaction,
                "count": int(claim.get("count") or 0),
            })
        reaction_count = int(claim.get("count") or 0)
        if (reaction_count >= moderate_signal_min_count and str(fact.get("risk_level") or "").lower() == "moderate") or reaction.upper() in severe:
            row["risk_level"] = "Moderate"

    for subject_id, row in sorted(grouped.items()):
        row["reactions"] = sorted(row.get("reactions") or [], key=lambda item: int(item.get("count") or 0), reverse=True)
        write_compact_json(api_out_dir / "adverse_signals" / f"{subject_id}.json", row)
    return {"path": "adverse_signals/{id}.json", "items": len(grouped)}


def aliases_from_identifiers(identifiers: dict[str, Any] | None) -> list[str]:
    if not isinstance(identifiers, dict):
        return []
    aliases: list[str] = []
    for key in ("aliases", "rxnorm_synonym", "synonyms", "brand_names", "trade_names"):
        value = identifiers.get(key)
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace(";", ",").split(",")]
            aliases.extend(part for part in parts if part)
        elif isinstance(value, list):
            aliases.extend(str(part).strip() for part in value if str(part).strip())
    return sorted(set(aliases), key=str.lower)


def compact_substance(row: dict[str, Any]) -> dict[str, Any]:
    identifiers = row.get("identifiers") if isinstance(row.get("identifiers"), dict) else {}
    aliases = aliases_from_identifiers(identifiers)
    payload = {
        "id": row.get("id"),
        "name_zh": row.get("name_zh"),
        "name_en": row.get("name_en"),
        "category": row.get("category"),
        "solubility": row.get("solubility"),
        "base_half_life": row.get("base_half_life"),
        "base_onset": row.get("base_onset"),
        "base_duration": row.get("base_duration"),
        "pharmacokinetics": row.get("pharmacokinetics_detail") or [],
        "identifiers": identifiers,
        "aliases": aliases,
        "cyp_tags": row.get("cyp_tags") or [],
        "source_summary": row.get("source_summary") or [],
        "dataset_version": row.get("dataset_version"),
        "remote_source": API_VERSION,
    }
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def search_entry(row: dict[str, Any], paths: dict[str, str]) -> dict[str, Any]:
    identifiers = row.get("identifiers") if isinstance(row.get("identifiers"), dict) else {}
    aliases = aliases_from_identifiers(identifiers)
    return {
        "id": row.get("id"),
        "name_zh": row.get("name_zh"),
        "name_en": row.get("name_en"),
        "category": row.get("category"),
        "aliases": aliases[:8],
        "paths": paths,
    }


def substance_display_name(row: dict[str, Any] | None, substance_id: str) -> str:
    if not row:
        return substance_id
    return row.get("name_zh") or row.get("name_en") or substance_id


def interaction_payload(row: dict[str, Any], substances_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    a_id = row.get("substance_a_id")
    b_id = row.get("substance_b_id")
    a = substances_by_id.get(str(a_id))
    b = substances_by_id.get(str(b_id))
    return {
        "interaction_id": row.get("interaction_id"),
        "substance_a_id": a_id,
        "substance_b_id": b_id,
        "substance_a_name": substance_display_name(a, str(a_id)),
        "substance_b_name": substance_display_name(b, str(b_id)),
        "substance_a_name_en": a.get("name_en") if a else None,
        "substance_b_name_en": b.get("name_en") if b else None,
        "interaction_type": row.get("interaction_type"),
        "risk_level": row.get("risk_level"),
        "confidence": row.get("confidence"),
        "source_tier": row.get("source_tier"),
        "action": row.get("action"),
        "mechanism": row.get("mechanism"),
        "note": row.get("note"),
        "conflict_status": row.get("conflict_status"),
        "remote_source": API_VERSION,
    }


def export_static_api(input_dir: Path, out_dir: Path, reset: bool = True) -> dict[str, Any]:
    """Export fused seed JSON into a GitHub Pages friendly static JSON API."""
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    if reset:
        reset_output_dir(out_dir)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    substances = read_json(input_dir / "init_substances.json", [])
    interactions = read_json(input_dir / "init_interactions.json", [])
    dose_rules = read_json(input_dir / "init_dose_rules.json", [])
    seed_manifest = read_json(input_dir / "manifest.json", {})
    evidence_facts = read_json(input_dir / "evidence_facts.json", [])
    if not isinstance(evidence_facts, list):
        evidence_facts = []

    substances_by_id = {str(row.get("id")): row for row in substances if row.get("id")}
    paths_by_id = {
        substance_id: {
            "substance": id_path("substances/by-id", substance_id),
            "interactions": id_path("interactions/by-substance", substance_id),
            "dose_rules": id_path("dose-rules/by-substance", substance_id),
        }
        for substance_id in substances_by_id
    }
    interaction_buckets: dict[str, list[dict[str, Any]]] = {substance_id: [] for substance_id in substances_by_id}
    for row in interactions:
        payload = interaction_payload(row, substances_by_id)
        a_id = str(payload.get("substance_a_id") or "")
        b_id = str(payload.get("substance_b_id") or "")
        if a_id:
            interaction_buckets.setdefault(a_id, []).append(payload)
        if b_id and b_id != a_id:
            interaction_buckets.setdefault(b_id, []).append(payload)

    dose_buckets: dict[str, list[dict[str, Any]]] = {}
    for rule in dose_rules:
        subject_id = str(rule.get("subject_id") or "")
        if subject_id:
            dose_buckets.setdefault(subject_id, []).append(rule)

    search_index = [search_entry(row, paths_by_id[str(row.get("id"))]) for row in substances if row.get("id")]
    search_index.sort(key=lambda item: ((item.get("name_zh") or item.get("name_en") or item.get("id") or "").lower(), item.get("id") or ""))
    write_compact_json(out_dir / "search" / "index.json", search_index)
    search_manifest = write_search_shards(out_dir, search_index)

    for substance_id, row in sorted(substances_by_id.items()):
        detail = compact_substance(row)
        detail["interaction_count"] = len(interaction_buckets.get(substance_id, []))
        detail["dose_rule_count"] = len(dose_buckets.get(substance_id, []))
        detail["paths"] = paths_by_id[substance_id]
        write_compact_json(out_dir / paths_by_id[substance_id]["substance"], detail)

    for substance_id, rows in sorted(interaction_buckets.items()):
        if not rows:
            continue
        rows.sort(key=lambda item: (str(item.get("risk_level") or ""), str(item.get("interaction_id") or "")))
        write_compact_json(out_dir / paths_by_id.get(substance_id, {"interactions": id_path("interactions/by-substance", substance_id)})["interactions"], rows)

    for substance_id, rows in sorted(dose_buckets.items()):
        rows.sort(key=lambda item: str(item.get("rule_id") or ""))
        write_compact_json(out_dir / paths_by_id.get(substance_id, {"dose_rules": id_path("dose-rules/by-substance", substance_id)})["dose_rules"], rows)

    counts = {
        "substances": len(substances_by_id),
        "interactions": len(interactions),
        "dose_rules": len(dose_rules),
    }
    source_library = write_source_library(out_dir, evidence_facts)
    adverse_signals = write_adverse_signal_api(out_dir, evidence_facts, substances_by_id)
    full_package = write_full_package(input_dir, out_dir, seed_manifest, counts, source_library)

    manifest = {
        "api_version": API_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset_version": seed_manifest.get("dataset_version"),
        "counts": counts,
        "paths": {
            "search_index": "search/index.json",
            "search_manifest": "search/manifest.json",
            "substance_by_id": "search index item paths.substance",
            "interactions_by_substance": "search index item paths.interactions",
            "dose_rules_by_substance": "search index item paths.dose_rules",
            "adverse_signals": adverse_signals["path"],
        },
        "search": search_manifest,
        "adverse_signals": adverse_signals,
        "online_library": {
            "mode": "remote_static_fused_source_layers",
            "source_library": source_library,
            "full_package": full_package,
            "local_policy": "Local app storage remains local-first; this online library is queried only when remote fallback is enabled or when a review/import tool explicitly downloads the package.",
        },
        "full_package": full_package,
        "source_library": source_library,
        "privacy_note": "Static API only receives HTTP requests for the files the client fetches. Enable remote fallback only if sending search terms/IDs to the configured host is acceptable.",
        "warning": seed_manifest.get("warning") or "Prototype data. Do not use as clinical decision support without source review and validation.",
    }
    write_compact_json(out_dir / "manifest.json", manifest)
    return manifest
