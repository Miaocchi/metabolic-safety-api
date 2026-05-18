from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

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
    manifest_path = api_dir / "manifest.json"
    manifest = read_json(manifest_path, {})
    counts = manifest.setdefault("counts", {})
    counts["substances"] = search_count
    counts["dose_candidates"] = dose_count
    counts["overdose_warnings"] = overdose_count
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
    write_json(manifest_path, manifest)
    return overlay_manifest | {"search_substances": search_count}


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
