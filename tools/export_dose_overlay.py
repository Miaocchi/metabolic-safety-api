from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.dose_rules import extract_dose_rule_facts, normalize_dose_rule_claim  # noqa: E402
from metabolic_safety_etl.schemas import EvidenceFact  # noqa: E402

API_VERSION = "static-drug-api-v1"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def id_path(prefix: str, substance_id: str) -> str:
    digest = hashlib.sha256(str(substance_id).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}/{digest[:2]}/{digest}.json"


def html_safe_excerpt(value: str, limit: int = 900) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def load_claim(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def load_subject_ids(row: sqlite3.Row) -> list[str]:
    raw = row["subject_ids_json"]
    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, list) and payload:
                return [str(item) for item in payload if str(item)]
        except Exception:
            pass
    return [str(row["subject_id"] or "unknown")]


def row_to_fact(row: sqlite3.Row) -> EvidenceFact:
    return EvidenceFact(
        fact_id=str(row["fact_id"] or ""),
        fact_type=str(row["fact_type"] or ""),
        subject_ids=load_subject_ids(row),
        claim=load_claim(row["claim_json"]),
        risk_level=str(row["risk_level"] or "Unknown"),
        confidence=str(row["confidence"] or "Unknown"),
        source_tier=str(row["source_tier"] or "Community"),
        source_name=str(row["source_name"] or row["source_key"] or "Unknown"),
        source_url=str(row["source_url"] or ""),
        evidence_quote=str(row["evidence_quote"] or ""),
        extraction_method=str(row["extraction_method"] or "structured_sqlite"),
        review_status=str(row["review_status"] or "unreviewed"),
        use_policy=str(row["use_policy"] or "candidate_signal"),
        updated_at=str(row["updated_at"] or ""),
    )


def identity_aliases(claim: dict[str, Any]) -> list[str]:
    identifiers = claim.get("identifiers") if isinstance(claim.get("identifiers"), dict) else {}
    aliases: list[str] = []
    for key in ("aliases", "brand_names", "trade_names", "synonyms"):
        value = identifiers.get(key)
        if isinstance(value, list):
            aliases.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str):
            aliases.extend(part.strip() for part in value.replace("|", ",").replace(";", ",").split(",") if part.strip())
    out: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        key = alias.lower()
        if key not in seen:
            seen.add(key)
            out.append(alias)
    return out[:12]


def iter_rows(db_path: Path, fact_type: str) -> Iterable[sqlite3.Row]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        query = """
            SELECT fact_id, source_key, fact_type, subject_id, subject_ids_json, name, section,
                   claim_json, risk_level, confidence, source_tier, source_name, source_url,
                   evidence_quote, extraction_method, review_status, use_policy, updated_at
            FROM facts
            WHERE fact_type = ?
            ORDER BY subject_id, fact_id
        """
        yield from con.execute(query, (fact_type,))
    finally:
        con.close()


def load_identities(db_paths: list[Path], needed_subjects: set[str]) -> dict[str, dict[str, Any]]:
    identities: dict[str, dict[str, Any]] = {}
    if not needed_subjects:
        return identities
    for db_path in db_paths:
        if not db_path.exists():
            continue
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        try:
            for row in con.execute("""
                SELECT subject_id, name, claim_json, confidence, source_tier, source_name, source_url
                FROM facts
                WHERE fact_type = 'substance_identity'
            """):
                sid = str(row["subject_id"] or "")
                if sid not in needed_subjects or sid in identities:
                    continue
                claim = load_claim(row["claim_json"])
                identities[sid] = {
                    "id": sid,
                    "name_en": claim.get("name_en") or row["name"] or sid.replace("_", " ").title(),
                    "name_zh": claim.get("name_zh"),
                    "category": claim.get("category") or "DrugLabel",
                    "aliases": identity_aliases(claim),
                    "source_summary": [{
                        "source_name": row["source_name"],
                        "source_tier": row["source_tier"],
                        "source_url": row["source_url"],
                        "confidence": row["confidence"],
                        "review_status": "machine_checked",
                        "risk_level": "Unknown",
                    }],
                }
        finally:
            con.close()
    return identities


def compact_dose_candidate(row: sqlite3.Row) -> dict[str, Any]:
    claim = load_claim(row["claim_json"])
    return {
        "fact_id": row["fact_id"],
        "source_key": row["source_key"],
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "source_tier": row["source_tier"],
        "confidence": row["confidence"],
        "section": row["section"],
        "value": claim.get("value"),
        "value_max": claim.get("value_max"),
        "unit": claim.get("unit"),
        "candidate_kind": claim.get("candidate_kind") or "dose_mention",
        "context": html_safe_excerpt(claim.get("context") or row["evidence_quote"], 900),
    }


def compact_overdose_warning(row: sqlite3.Row) -> dict[str, Any]:
    claim = load_claim(row["claim_json"])
    return {
        "fact_id": row["fact_id"],
        "source_key": row["source_key"],
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "source_tier": row["source_tier"],
        "confidence": row["confidence"],
        "risk_level": row["risk_level"] or "Major",
        "section": row["section"],
        "text": html_safe_excerpt(claim.get("overdose_text") or row["evidence_quote"], 1800),
    }


def load_overlay_rows(db_paths: list[Path], max_per_subject: int = 0) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, str]]:
    dose_by_subject: dict[str, list[dict[str, Any]]] = {}
    overdose_by_subject: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    seen: set[str] = set()
    for db_path in db_paths:
        if not db_path.exists():
            print(f"skip_missing_db={db_path}")
            continue
        for row in iter_rows(db_path, "dose_candidate"):
            fid = str(row["fact_id"])
            if fid in seen:
                continue
            seen.add(fid)
            sid = str(row["subject_id"] or "unknown")
            bucket = dose_by_subject.setdefault(sid, [])
            if max_per_subject and len(bucket) >= max_per_subject:
                continue
            names.setdefault(sid, str(row["name"] or sid))
            bucket.append(compact_dose_candidate(row))
        for row in iter_rows(db_path, "overdose_warning"):
            fid = str(row["fact_id"])
            if fid in seen:
                continue
            seen.add(fid)
            sid = str(row["subject_id"] or "unknown")
            bucket = overdose_by_subject.setdefault(sid, [])
            if max_per_subject and len(bucket) >= max_per_subject:
                continue
            names.setdefault(sid, str(row["name"] or sid))
            bucket.append(compact_overdose_warning(row))
    return dose_by_subject, overdose_by_subject, names


def update_search_and_details(api_dir: Path, dose_by_subject: dict[str, list[dict[str, Any]]], overdose_by_subject: dict[str, list[dict[str, Any]]], names: dict[str, str], identities: dict[str, dict[str, Any]]) -> int:
    search_path = api_dir / "search" / "index.json"
    search_index = read_json(search_path, [])
    by_id = {str(item.get("id")): item for item in search_index if item.get("id")}
    all_subjects = sorted(set(dose_by_subject) | set(overdose_by_subject))
    for sid in all_subjects:
        paths = {
            "substance": id_path("substances/by-id", sid),
            "interactions": id_path("interactions/by-substance", sid),
            "dose_rules": id_path("dose-rules/by-substance", sid),
            "dose_candidates": id_path("dose-candidates/by-substance", sid),
            "overdose_warnings": id_path("overdose-warnings/by-substance", sid),
        }
        if sid not in by_id:
            identity = identities.get(sid, {})
            by_id[sid] = {
                "id": sid,
                "name_zh": identity.get("name_zh"),
                "name_en": identity.get("name_en") or names.get(sid) or sid.replace("_", " ").title(),
                "category": identity.get("category") or "DrugLabel",
                "aliases": identity.get("aliases") or [],
                "paths": paths,
            }
        else:
            by_id[sid].setdefault("paths", {}).update(paths)
            if identities.get(sid):
                by_id[sid]["aliases"] = sorted(set((by_id[sid].get("aliases") or []) + identities[sid].get("aliases", [])), key=str.lower)[:12]
        detail_path = api_dir / by_id[sid]["paths"]["substance"]
        detail = read_json(detail_path, {})
        if not detail:
            identity = identities.get(sid, {})
            detail = {
                "id": sid,
                "name_zh": identity.get("name_zh"),
                "name_en": identity.get("name_en") or by_id[sid].get("name_en"),
                "category": identity.get("category") or by_id[sid].get("category") or "DrugLabel",
                "aliases": identity.get("aliases") or by_id[sid].get("aliases") or [],
                "source_summary": identity.get("source_summary") or [],
                "remote_source": API_VERSION,
            }
        detail.setdefault("paths", {}).update(by_id[sid]["paths"])
        detail["dose_candidate_count"] = len(dose_by_subject.get(sid, []))
        detail["overdose_warning_count"] = len(overdose_by_subject.get(sid, []))
        detail["remote_source"] = API_VERSION
        write_json(detail_path, detail)
    rows = sorted(by_id.values(), key=lambda item: ((item.get("name_zh") or item.get("name_en") or item.get("id") or "").lower(), item.get("id") or ""))
    write_json(search_path, rows)
    return len(rows)


def load_rule_source_facts(db_paths: list[Path]) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen: set[str] = set()
    for db_path in db_paths:
        if not db_path.exists():
            continue
        for fact_type in ("dose_candidate", "overdose_warning"):
            for row in iter_rows(db_path, fact_type):
                fid = str(row["fact_id"] or "")
                if fid in seen:
                    continue
                seen.add(fid)
                facts.append(row_to_fact(row))
    return facts


def dose_rule_row(fact: EvidenceFact, dataset_version: str) -> dict[str, Any] | None:
    if not fact.subject_ids:
        return None
    subject_id = fact.subject_ids[0]
    normalized = normalize_dose_rule_claim(subject_id, fact.claim)
    if not normalized:
        return None
    return {
        **normalized,
        "source_name": fact.source_name,
        "source_tier": fact.source_tier,
        "source_url": fact.source_url,
        "confidence": fact.confidence,
        "review_status": fact.review_status,
        "dataset_version": dataset_version,
        "remote_source": API_VERSION,
        "evidence_refs": [{
            "fact_id": fact.fact_id,
            "source_tier": fact.source_tier,
            "source_name": fact.source_name,
            "source_url": fact.source_url,
            "confidence": fact.confidence,
            "risk_level": fact.risk_level,
            "review_status": fact.review_status,
        }],
    }


def load_existing_rule_buckets(api_dir: Path) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    root = api_dir / "dose-rules" / "by-substance"
    if not root.exists():
        return buckets
    for path in root.glob("**/*.json"):
        rows = read_json(path, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            subject_id = str(row.get("subject_id") or "unknown")
            buckets.setdefault(subject_id, []).append(row)
    return buckets


def merge_generated_dose_rules(api_dir: Path, db_paths: list[Path], dataset_version: str, names: dict[str, str]) -> dict[str, Any]:
    source_facts = load_rule_source_facts(db_paths)
    generated_facts = extract_dose_rule_facts(source_facts)
    buckets = load_existing_rule_buckets(api_dir)
    generated_rules = 0
    written_subjects: set[str] = set()
    for fact in generated_facts:
        rule = dose_rule_row(fact, dataset_version)
        if not rule:
            continue
        subjects = {str(rule.get("subject_id") or "")}
        original_subject = rule.get("original_subject_id")
        if original_subject:
            subjects.add(str(original_subject))
        for subject_id in subjects:
            if not subject_id:
                continue
            subject_rule = dict(rule)
            if subject_id != rule.get("subject_id"):
                subject_rule["canonical_subject_id"] = rule.get("subject_id")
                subject_rule["subject_id"] = subject_id
            bucket = buckets.setdefault(subject_id, [])
            by_rule = {str(item.get("rule_id")): item for item in bucket if item.get("rule_id")}
            rule_id = str(subject_rule.get("rule_id") or "")
            if rule_id and rule_id in by_rule:
                continue
            bucket.append(subject_rule)
            written_subjects.add(subject_id)
            generated_rules += 1
    for subject_id, rows in sorted(buckets.items()):
        if not rows:
            continue
        rows.sort(key=lambda item: (str(item.get("basis") or ""), str(item.get("rule_id") or "")))
        write_json(api_dir / id_path("dose-rules/by-substance", subject_id), rows)
    unique_rule_ids = {str(row.get("rule_id")) for rows in buckets.values() for row in rows if row.get("rule_id")}
    logical_count = len(unique_rule_ids)
    update_dose_rule_search_details(api_dir, buckets, names)
    manifest = {
        "generated_from": [str(path) for path in db_paths],
        "source_facts": len(source_facts),
        "generated_rule_files_added": generated_rules,
        "unique_dose_rules": logical_count,
        "subjects_with_dose_rules": len(buckets),
        "policy": "dose_rules include curated ceilings, explicit label maxima, and review-required overdose-warning-supported screening rules derived from dose candidates.",
    }
    write_json(api_dir / "dose-rules" / "manifest.json", manifest)
    return manifest


def update_dose_rule_search_details(api_dir: Path, buckets: dict[str, list[dict[str, Any]]], names: dict[str, str]) -> None:
    search_path = api_dir / "search" / "index.json"
    search_index = read_json(search_path, [])
    by_id = {str(item.get("id")): item for item in search_index if item.get("id")}
    for subject_id, rows in buckets.items():
        paths = {
            "substance": id_path("substances/by-id", subject_id),
            "interactions": id_path("interactions/by-substance", subject_id),
            "dose_rules": id_path("dose-rules/by-substance", subject_id),
            "dose_candidates": id_path("dose-candidates/by-substance", subject_id),
            "overdose_warnings": id_path("overdose-warnings/by-substance", subject_id),
        }
        if subject_id not in by_id:
            by_id[subject_id] = {
                "id": subject_id,
                "name_zh": None,
                "name_en": names.get(subject_id) or subject_id.replace("_", " ").title(),
                "category": "DoseRule",
                "aliases": [],
                "paths": paths,
            }
        else:
            by_id[subject_id].setdefault("paths", {}).update(paths)
        detail_path = api_dir / by_id[subject_id]["paths"]["substance"]
        detail = read_json(detail_path, {})
        if not detail:
            detail = {
                "id": subject_id,
                "name_zh": by_id[subject_id].get("name_zh"),
                "name_en": by_id[subject_id].get("name_en"),
                "category": by_id[subject_id].get("category") or "DoseRule",
                "aliases": by_id[subject_id].get("aliases") or [],
                "source_summary": [],
                "remote_source": API_VERSION,
            }
        detail.setdefault("paths", {}).update(by_id[subject_id]["paths"])
        detail["dose_rule_count"] = len(rows)
        detail["remote_source"] = API_VERSION
        write_json(detail_path, detail)
    rows = sorted(by_id.values(), key=lambda item: ((item.get("name_zh") or item.get("name_en") or item.get("id") or "").lower(), item.get("id") or ""))
    write_json(search_path, rows)


def export_overlay(api_dir: Path, db_paths: list[Path], max_per_subject: int = 0) -> dict[str, Any]:
    dose_by_subject, overdose_by_subject, names = load_overlay_rows(db_paths, max_per_subject=max_per_subject)
    all_subjects = set(dose_by_subject) | set(overdose_by_subject)
    identities = load_identities(db_paths, all_subjects)
    for sid, rows in dose_by_subject.items():
        write_json(api_dir / id_path("dose-candidates/by-substance", sid), rows)
    for sid, rows in overdose_by_subject.items():
        write_json(api_dir / id_path("overdose-warnings/by-substance", sid), rows)
    search_count = update_search_and_details(api_dir, dose_by_subject, overdose_by_subject, names, identities)
    dose_count = sum(len(rows) for rows in dose_by_subject.values())
    overdose_count = sum(len(rows) for rows in overdose_by_subject.values())
    manifest_path = api_dir / "manifest.json"
    manifest = read_json(manifest_path, {})
    dataset_version = str(manifest.get("dataset_version") or "overlay")
    dose_rule_overlay = merge_generated_dose_rules(api_dir, db_paths, dataset_version, names)
    search_count = len(read_json(api_dir / "search" / "index.json", []))
    overlay_manifest = {
        "generated_from": [str(path) for path in db_paths],
        "substances_with_dose_candidates": len(dose_by_subject),
        "substances_with_overdose_warnings": len(overdose_by_subject),
        "dose_candidates": dose_count,
        "overdose_warnings": overdose_count,
        "max_per_substance": max_per_subject or None,
        "policy": "dose_candidates are searchable evidence snippets, not final overdose thresholds. dose_rules remain the alerting layer.",
    }
    write_json(api_dir / "dose-candidates" / "manifest.json", overlay_manifest)
    write_json(api_dir / "overdose-warnings" / "manifest.json", overlay_manifest)
    counts = manifest.setdefault("counts", {})
    counts["substances"] = search_count
    counts["dose_candidates"] = dose_count
    counts["overdose_warnings"] = overdose_count
    counts["dose_rules"] = dose_rule_overlay.get("unique_dose_rules", counts.get("dose_rules", 0))
    paths = manifest.setdefault("paths", {})
    paths["dose_candidates_by_substance"] = "search index item paths.dose_candidates"
    paths["overdose_warnings_by_substance"] = "search index item paths.overdose_warnings"
    manifest["dose_candidate_overlay"] = {
        "manifest": "dose-candidates/manifest.json",
        "policy": overlay_manifest["policy"],
    }
    manifest["overdose_warning_overlay"] = {
        "manifest": "overdose-warnings/manifest.json",
        "policy": overlay_manifest["policy"],
    }
    manifest["dose_rule_overlay"] = {
        "manifest": "dose-rules/manifest.json",
        "policy": dose_rule_overlay["policy"],
    }
    write_json(manifest_path, manifest)
    return overlay_manifest | {"search_substances": search_count, "dose_rule_overlay": dose_rule_overlay}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export dose candidates and overdosage warnings from local structured SQLite facts into static API overlay files.")
    parser.add_argument("--api-dir", default="public/api")
    parser.add_argument("--structured-db", action="append", required=True)
    parser.add_argument("--max-per-substance", type=int, default=0)
    args = parser.parse_args()
    db_paths = [Path(item) for item in args.structured_db]
    summary = export_overlay(Path(args.api_dir), db_paths, max_per_subject=args.max_per_substance)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
