from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.dose_rules import extract_dose_rule_facts, normalize_dose_rule_claim  # noqa: E402
from metabolic_safety_etl.schemas import EvidenceFact  # noqa: E402

API_VERSION = "static-drug-api-v1"

CONTENT_GROUPS = {
    "drug_effect": {
        "key": "drug_effects",
        "prefix": "drug-effects/by-substance",
        "manifest_dir": "drug-effects",
        "detail_count_key": "drug_effect_count",
        "policy": "Drug effect rows expose label indications, purpose, pharmacodynamics and ChEMBL mechanism evidence as searchable evidence snippets.",
    },
    "pharmacokinetics": {
        "key": "pharmacokinetics",
        "prefix": "pharmacokinetics/by-substance",
        "manifest_dir": "pharmacokinetics",
        "detail_count_key": "pharmacokinetic_count",
        "policy": "PK rows expose structured pharmacokinetic values and label excerpts as evidence, not individualized dosing advice.",
    },
    "enzyme_relation": {
        "key": "enzyme_relations",
        "prefix": "enzyme-relations/by-substance",
        "manifest_dir": "enzyme-relations",
        "detail_count_key": "enzyme_relation_count",
        "policy": "Enzyme rows expose extracted CYP and transporter relations for downstream interaction review.",
    },
}

SOURCE_TIER_SCORE = {
    "Guideline": 6,
    "Regulatory": 6,
    "Label": 5,
    "ManualReview": 5,
    "CuratedDB": 4,
    "Literature": 3,
    "Signal": 2,
    "Community": 1,
    "Fixture": 0,
    "Unknown": 0,
}

CONFIDENCE_SCORE = {"High": 3, "Medium": 2, "Low": 1, "Unknown": 0}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_json_array(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[dict[str, Any]]:
    """Stream a top-level JSON array without loading the full source layer."""
    decoder = json.JSONDecoder()
    buffer = ""
    in_array = False
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if chunk:
                buffer += chunk
            while True:
                buffer = buffer.lstrip()
                if not in_array:
                    if not buffer:
                        break
                    if buffer[0] != "[":
                        raise ValueError(f"expected JSON array in {path}")
                    buffer = buffer[1:]
                    in_array = True
                    continue
                buffer = buffer.lstrip()
                if not buffer:
                    break
                if buffer[0] == "]":
                    return
                if buffer[0] == ",":
                    buffer = buffer[1:]
                    continue
                try:
                    item, index = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if not chunk:
                        raise
                    break
                if isinstance(item, dict):
                    yield item
                buffer = buffer[index:]
            if not chunk:
                break


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
    claim = load_claim(row["claim_json"])
    section = str(row["section"] or "")
    if section and "section" not in claim:
        claim = {**claim, "section": section}
    return EvidenceFact(
        fact_id=str(row["fact_id"] or ""),
        fact_type=str(row["fact_type"] or ""),
        subject_ids=load_subject_ids(row),
        claim=claim,
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


def fact_subject_id(fact: EvidenceFact) -> str:
    return str(fact.subject_ids[0] if fact.subject_ids else "unknown")


def iter_fact_json(path: Path, fact_types: set[str] | None = None) -> Iterator[EvidenceFact]:
    if not path.exists():
        print(f"skip_missing_fact_json={path}")
        return
    for item in iter_json_array(path):
        if fact_types and item.get("fact_type") not in fact_types:
            continue
        try:
            yield EvidenceFact.from_dict(item)
        except Exception as exc:
            print(f"skip_fact_json_item={path} error={type(exc).__name__}: {exc}")


def compact_dose_candidate_fact(fact: EvidenceFact) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "source_key": fact.extraction_method,
        "source_name": fact.source_name,
        "source_url": fact.source_url,
        "source_tier": fact.source_tier,
        "confidence": fact.confidence,
        "section": fact.claim.get("section"),
        "value": fact.claim.get("value"),
        "value_max": fact.claim.get("value_max"),
        "unit": fact.claim.get("unit"),
        "candidate_kind": fact.claim.get("candidate_kind") or "dose_mention",
        "context": html_safe_excerpt(fact.claim.get("context") or fact.evidence_quote, 900),
    }


def compact_overdose_warning_fact(fact: EvidenceFact) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "source_key": fact.extraction_method,
        "source_name": fact.source_name,
        "source_url": fact.source_url,
        "source_tier": fact.source_tier,
        "confidence": fact.confidence,
        "risk_level": fact.risk_level or "Major",
        "section": fact.claim.get("section"),
        "text": html_safe_excerpt(fact.claim.get("overdose_text") or fact.evidence_quote, 1800),
    }

def compact_drug_effect_fact(fact: EvidenceFact) -> dict[str, Any]:
    claim = fact.claim
    effect_text = claim.get("effect_text") or claim.get("purpose") or claim.get("indication") or ""
    mechanism = claim.get("mechanism_of_action") or ""
    return {
        "fact_id": fact.fact_id,
        "source_key": fact.extraction_method,
        "source_name": fact.source_name,
        "source_url": fact.source_url,
        "source_tier": fact.source_tier,
        "confidence": fact.confidence,
        "section": claim.get("section"),
        "effect_text": html_safe_excerpt(effect_text, 2200),
        "mechanism_of_action": html_safe_excerpt(mechanism, 1600),
        "action_type": claim.get("action_type"),
        "target": claim.get("target"),
        "evidence": html_safe_excerpt(fact.evidence_quote, 1200),
    }


def compact_pharmacokinetics_fact(fact: EvidenceFact) -> dict[str, Any]:
    claim = fact.claim
    return {
        "fact_id": fact.fact_id,
        "source_key": fact.extraction_method,
        "source_name": fact.source_name,
        "source_url": fact.source_url,
        "source_tier": fact.source_tier,
        "confidence": fact.confidence,
        "section": claim.get("section"),
        "half_life_hours": claim.get("half_life_hours"),
        "half_life_hours_upper": claim.get("half_life_hours_upper"),
        "half_life_hours_mean": claim.get("half_life_hours_mean"),
        "onset_minutes": claim.get("onset_minutes"),
        "duration_minutes": claim.get("duration_minutes"),
        "route": claim.get("route"),
        "standard_type": claim.get("standard_type"),
        "clearance": claim.get("clearance"),
        "volume_distribution": claim.get("volume_distribution"),
        "bioavailability": claim.get("bioavailability"),
        "text": html_safe_excerpt(claim.get("text_excerpt") or fact.evidence_quote, 1400),
    }


def compact_enzyme_relation_fact(fact: EvidenceFact) -> dict[str, Any]:
    claim = fact.claim
    return {
        "fact_id": fact.fact_id,
        "source_key": fact.extraction_method,
        "source_name": fact.source_name,
        "source_url": fact.source_url,
        "source_tier": fact.source_tier,
        "confidence": fact.confidence,
        "section": claim.get("section"),
        "tag": claim.get("tag"),
        "enzyme": claim.get("enzyme"),
        "relation": claim.get("relation"),
        "text": html_safe_excerpt(fact.evidence_quote, 900),
    }


def compact_content_fact(fact: EvidenceFact) -> dict[str, Any] | None:
    if fact.fact_type == "drug_effect":
        row = compact_drug_effect_fact(fact)
        if row.get("effect_text") or row.get("mechanism_of_action") or row.get("target") or row.get("evidence"):
            return row
    if fact.fact_type == "pharmacokinetics":
        row = compact_pharmacokinetics_fact(fact)
        if any(row.get(key) not in (None, "") for key in ("half_life_hours", "half_life_hours_upper", "half_life_hours_mean", "onset_minutes", "duration_minutes", "clearance", "volume_distribution", "bioavailability", "text")):
            return row
    if fact.fact_type == "enzyme_relation":
        row = compact_enzyme_relation_fact(fact)
        if row.get("tag") or row.get("enzyme") or row.get("text"):
            return row
    return None


def compact_key(value: Any, limit: int = 700) -> str:
    return " ".join(str(value or "").lower().split())[:limit]


def content_dedupe_key(row: dict[str, Any]) -> str:
    basis = row.get("mechanism_of_action") or row.get("effect_text") or row.get("text") or row.get("tag") or row.get("fact_id")
    return compact_key(basis)


def content_priority(row: dict[str, Any]) -> tuple[int, int, int, int]:
    tier = SOURCE_TIER_SCORE.get(str(row.get("source_tier") or "Unknown"), 0)
    confidence = CONFIDENCE_SCORE.get(str(row.get("confidence") or "Unknown"), 0)
    mechanism = 1 if row.get("mechanism_of_action") or row.get("target") or row.get("tag") else 0
    text_size = min(len(str(row.get("effect_text") or row.get("mechanism_of_action") or row.get("text") or "")), 2000)
    return tier, confidence, mechanism, text_size


def add_capped_content_row(bucket: list[dict[str, Any]], seen_keys: set[str], row: dict[str, Any], max_per_subject: int) -> None:
    key = content_dedupe_key(row)
    if not key or key in seen_keys:
        return
    seen_keys.add(key)
    bucket.append(row)
    bucket.sort(key=content_priority, reverse=True)
    if max_per_subject and len(bucket) > max_per_subject:
        del bucket[max_per_subject:]


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


def load_json_identities(fact_json_paths: list[Path], needed_subjects: set[str], identities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not needed_subjects:
        return identities
    for path in fact_json_paths:
        for fact in iter_fact_json(path, {"substance_identity"}):
            sid = fact_subject_id(fact)
            if sid not in needed_subjects or sid in identities:
                continue
            claim = fact.claim
            identities[sid] = {
                "id": sid,
                "name_en": claim.get("name_en") or sid.replace("_", " ").title(),
                "name_zh": claim.get("name_zh"),
                "category": claim.get("category") or "DrugLabel",
                "aliases": identity_aliases(claim),
                "source_summary": [{
                    "source_name": fact.source_name,
                    "source_tier": fact.source_tier,
                    "source_url": fact.source_url,
                    "confidence": fact.confidence,
                    "review_status": fact.review_status,
                    "risk_level": fact.risk_level,
                }],
            }
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


def load_overlay_fact_json_rows(fact_json_paths: list[Path], max_per_subject: int = 0) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, str]]:
    dose_by_subject: dict[str, list[dict[str, Any]]] = {}
    overdose_by_subject: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    seen: set[str] = set()
    for path in fact_json_paths:
        loaded = 0
        for fact in iter_fact_json(path, {"dose_candidate", "overdose_warning"}):
            if fact.fact_id in seen:
                continue
            seen.add(fact.fact_id)
            sid = fact_subject_id(fact)
            names.setdefault(sid, sid.replace("_", " ").title())
            if fact.fact_type == "dose_candidate":
                bucket = dose_by_subject.setdefault(sid, [])
                if max_per_subject and len(bucket) >= max_per_subject:
                    continue
                bucket.append(compact_dose_candidate_fact(fact))
            elif fact.fact_type == "overdose_warning":
                bucket = overdose_by_subject.setdefault(sid, [])
                if max_per_subject and len(bucket) >= max_per_subject:
                    continue
                bucket.append(compact_overdose_warning_fact(fact))
            loaded += 1
            if loaded % 50000 == 0:
                print(f"overlay_fact_json_progress={path} facts={loaded}", flush=True)
        print(f"overlay_fact_json_loaded={path} facts={loaded}", flush=True)
    return dose_by_subject, overdose_by_subject, names

def empty_content_maps() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {spec["key"]: {} for spec in CONTENT_GROUPS.values()}


def load_content_rows(db_paths: list[Path], max_per_subject: int = 24) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, str]]:
    content_maps = empty_content_maps()
    names: dict[str, str] = {}
    seen_by_group: dict[str, dict[str, set[str]]] = {spec["key"]: {} for spec in CONTENT_GROUPS.values()}
    for db_path in db_paths:
        if not db_path.exists():
            continue
        for fact_type, spec in CONTENT_GROUPS.items():
            group_key = spec["key"]
            for row in iter_rows(db_path, fact_type):
                fact = row_to_fact(row)
                sid = fact_subject_id(fact)
                names.setdefault(sid, str(row["name"] or sid))
                payload = compact_content_fact(fact)
                if not payload:
                    continue
                bucket = content_maps[group_key].setdefault(sid, [])
                seen_keys = seen_by_group[group_key].setdefault(sid, set())
                add_capped_content_row(bucket, seen_keys, payload, max_per_subject=max_per_subject)
    return content_maps, names


def load_content_fact_json_rows(fact_json_paths: list[Path], max_per_subject: int = 24) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, str]]:
    content_maps = empty_content_maps()
    names: dict[str, str] = {}
    seen_by_group: dict[str, dict[str, set[str]]] = {spec["key"]: {} for spec in CONTENT_GROUPS.values()}
    for path in fact_json_paths:
        loaded = 0
        for fact in iter_fact_json(path, set(CONTENT_GROUPS)):
            spec = CONTENT_GROUPS.get(fact.fact_type)
            if not spec:
                continue
            sid = fact_subject_id(fact)
            names.setdefault(sid, sid.replace("_", " ").title())
            payload = compact_content_fact(fact)
            if not payload:
                continue
            group_key = spec["key"]
            bucket = content_maps[group_key].setdefault(sid, [])
            seen_keys = seen_by_group[group_key].setdefault(sid, set())
            add_capped_content_row(bucket, seen_keys, payload, max_per_subject=max_per_subject)
            loaded += 1
            if loaded % 50000 == 0:
                print(f"content_fact_json_progress={path} facts={loaded}", flush=True)
        print(f"content_fact_json_loaded={path} facts={loaded}", flush=True)
    return content_maps, names


def merge_content_maps(target: dict[str, dict[str, list[dict[str, Any]]]], incoming: dict[str, dict[str, list[dict[str, Any]]]], max_per_subject: int = 24) -> None:
    for group_key, subject_map in incoming.items():
        target_group = target.setdefault(group_key, {})
        for subject_id, rows in subject_map.items():
            bucket = target_group.setdefault(subject_id, [])
            seen_keys = {content_dedupe_key(item) for item in bucket}
            for row in rows:
                add_capped_content_row(bucket, seen_keys, row, max_per_subject=max_per_subject)


def content_subjects(content_maps: dict[str, dict[str, list[dict[str, Any]]]]) -> set[str]:
    subjects: set[str] = set()
    for subject_map in content_maps.values():
        subjects.update(subject_map)
    return subjects


def update_content_search_details(api_dir: Path, content_maps: dict[str, dict[str, list[dict[str, Any]]]], names: dict[str, str], identities: dict[str, dict[str, Any]]) -> int:
    search_path = api_dir / "search" / "index.json"
    search_index = read_json(search_path, [])
    by_id = {str(item.get("id")): item for item in search_index if item.get("id")}
    all_subjects = sorted(content_subjects(content_maps))
    for sid in all_subjects:
        paths = {
            "substance": id_path("substances/by-id", sid),
            "interactions": id_path("interactions/by-substance", sid),
            "dose_rules": id_path("dose-rules/by-substance", sid),
            "dose_candidates": id_path("dose-candidates/by-substance", sid),
            "overdose_warnings": id_path("overdose-warnings/by-substance", sid),
            "drug_effects": id_path("drug-effects/by-substance", sid),
            "pharmacokinetics": id_path("pharmacokinetics/by-substance", sid),
            "enzyme_relations": id_path("enzyme-relations/by-substance", sid),
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
        for spec in CONTENT_GROUPS.values():
            detail[spec["detail_count_key"]] = len(content_maps.get(spec["key"], {}).get(sid, []))
        detail["remote_source"] = API_VERSION
        write_json(detail_path, detail)
    rows = sorted(by_id.values(), key=lambda item: ((item.get("name_zh") or item.get("name_en") or item.get("id") or "").lower(), item.get("id") or ""))
    write_json(search_path, rows)
    return len(rows)


def export_content_overlay_from_sources(api_dir: Path, db_paths: list[Path], fact_json_paths: list[Path], max_per_subject: int = 24) -> dict[str, Any]:
    content_maps, names = load_content_rows(db_paths, max_per_subject=max_per_subject)
    json_maps, json_names = load_content_fact_json_rows(fact_json_paths, max_per_subject=max_per_subject)
    merge_content_maps(content_maps, json_maps, max_per_subject=max_per_subject)
    names.update({key: value for key, value in json_names.items() if key not in names})
    all_subjects = content_subjects(content_maps)
    identities = load_identities(db_paths, all_subjects)
    identities = load_json_identities(fact_json_paths, all_subjects, identities)
    for fact_type, spec in CONTENT_GROUPS.items():
        group_key = spec["key"]
        prefix = spec["prefix"]
        for sid, rows in sorted(content_maps.get(group_key, {}).items()):
            if rows:
                rows.sort(key=content_priority, reverse=True)
                write_json(api_dir / id_path(prefix, sid), rows)
    search_count = update_content_search_details(api_dir, content_maps, names, identities)
    summary: dict[str, Any] = {
        "generated_from": [str(path) for path in [*db_paths, *fact_json_paths]],
        "search_substances": search_count,
        "max_per_substance": max_per_subject or None,
    }
    for spec in CONTENT_GROUPS.values():
        group_key = spec["key"]
        subject_map = content_maps.get(group_key, {})
        count = sum(len(rows) for rows in subject_map.values())
        summary[group_key] = count
        summary[f"substances_with_{group_key}"] = len(subject_map)
        write_json(api_dir / spec["manifest_dir"] / "manifest.json", {
            "generated_from": summary["generated_from"],
            "records": count,
            "subjects": len(subject_map),
            "max_per_substance": max_per_subject or None,
            "policy": spec["policy"],
        })
    return summary


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


def load_rule_source_facts(db_paths: list[Path], fact_json_paths: list[Path] | None = None) -> list[EvidenceFact]:
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
    for path in fact_json_paths or []:
        loaded = 0
        for fact in iter_fact_json(path, {"dose_candidate", "overdose_warning"}):
            if fact.fact_id in seen:
                continue
            seen.add(fact.fact_id)
            facts.append(fact)
            loaded += 1
            if loaded % 50000 == 0:
                print(f"dose_rule_fact_json_progress={path} facts={loaded}", flush=True)
        print(f"dose_rule_fact_json_loaded={path} facts={loaded}", flush=True)
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


def merge_generated_dose_rules(api_dir: Path, db_paths: list[Path], fact_json_paths: list[Path], dataset_version: str, names: dict[str, str]) -> dict[str, Any]:
    source_facts = load_rule_source_facts(db_paths, fact_json_paths)
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
        "generated_from": [str(path) for path in [*db_paths, *fact_json_paths]],
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



def normalize_search_term(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").replace("-", " ").split())


def search_shard_key(value: Any) -> str:
    text = normalize_search_term(value).replace(" ", "")
    if not text:
        return "other"
    char = text[0]
    if char.isascii() and char.isalnum():
        prefix = "".join(ch.lower() for ch in text if ch.isascii() and ch.isalnum())[:2]
        return prefix or char.lower()
    return f"u{ord(char):04x}"


def search_terms_for_item(item: dict[str, Any]) -> list[str]:
    aliases = item.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [part.strip() for part in aliases.replace("|", ",").split(",") if part.strip()]
    terms = [item.get("id"), item.get("name_zh"), item.get("name_en"), *aliases[:8]]
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = normalize_search_term(term)
        if not normalized:
            continue
        pieces = [normalized]
        for token in normalized.split():
            if len(token) >= 4 and not token.isdigit() and any(char.isalpha() for char in token):
                pieces.append(token)
        compact = normalized.replace(" ", "")
        if compact and not compact.isascii():
            pieces.extend(list(compact)[:6])
        for piece in pieces:
            key = piece.strip()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
    return out


def compact_search_item(item: dict[str, Any]) -> dict[str, Any]:
    aliases = item.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [part.strip() for part in aliases.replace("|", ",").split(",") if part.strip()]
    paths = item.get("paths") or {}
    compact_paths = {"substance": paths.get("substance")} if isinstance(paths, dict) and paths.get("substance") else {}
    return {
        "id": item.get("id"),
        "name_zh": item.get("name_zh"),
        "name_en": item.get("name_en"),
        "category": item.get("category"),
        "aliases": aliases[:8] if isinstance(aliases, list) else [],
        "paths": compact_paths,
    }


def export_search_lookup(api_dir: Path) -> dict[str, Any]:
    search_path = api_dir / "search" / "index.json"
    rows = read_json(search_path, [])
    if not isinstance(rows, list):
        rows = []
    shard_root = api_dir / "search" / "shards"
    shutil.rmtree(shard_root, ignore_errors=True)
    shards: dict[str, dict[str, dict[str, Any]]] = {}
    for item in rows:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        compact = compact_search_item(item)
        keys = {search_shard_key(term) for term in search_terms_for_item(compact)}
        if not keys:
            keys = {"other"}
        for key in keys:
            shards.setdefault(key, {})[str(compact["id"])] = compact
    shard_summary: dict[str, int] = {}
    for key, by_id in sorted(shards.items()):
        payload = sorted(by_id.values(), key=lambda item: ((item.get("name_zh") or item.get("name_en") or item.get("id") or "").lower(), item.get("id") or ""))
        write_json(shard_root / f"{key}.json", payload)
        shard_summary[key] = len(payload)
    manifest = {
        "items": len(rows),
        "shards": shard_summary,
        "shard_path": "search/shards/{key}.json",
        "policy": "Search UI should load shard files by query prefix instead of parsing the full search/index.json on page open.",
    }
    write_json(api_dir / "search" / "manifest.json", manifest)
    return manifest


def export_overlay(api_dir: Path, db_paths: list[Path], max_per_subject: int = 0, max_content_per_subject: int = 24) -> dict[str, Any]:
    dose_by_subject, overdose_by_subject, names = load_overlay_rows(db_paths, max_per_subject=max_per_subject)
    return export_overlay_from_maps(api_dir, db_paths, [], dose_by_subject, overdose_by_subject, names, max_per_subject, max_content_per_subject)


def export_overlay_from_sources(api_dir: Path, db_paths: list[Path], fact_json_paths: list[Path], max_per_subject: int = 0, max_content_per_subject: int = 24) -> dict[str, Any]:
    dose_by_subject, overdose_by_subject, names = load_overlay_rows(db_paths, max_per_subject=max_per_subject)
    json_dose_by_subject, json_overdose_by_subject, json_names = load_overlay_fact_json_rows(fact_json_paths, max_per_subject=max_per_subject)
    merge_subject_maps(dose_by_subject, json_dose_by_subject)
    merge_subject_maps(overdose_by_subject, json_overdose_by_subject)
    names.update({key: value for key, value in json_names.items() if key not in names})
    return export_overlay_from_maps(api_dir, db_paths, fact_json_paths, dose_by_subject, overdose_by_subject, names, max_per_subject, max_content_per_subject)


def merge_subject_maps(target: dict[str, list[dict[str, Any]]], incoming: dict[str, list[dict[str, Any]]]) -> None:
    for subject_id, rows in incoming.items():
        bucket = target.setdefault(subject_id, [])
        seen = {str(item.get("fact_id")) for item in bucket if item.get("fact_id")}
        for row in rows:
            fact_id = str(row.get("fact_id") or "")
            if fact_id and fact_id in seen:
                continue
            bucket.append(row)
            if fact_id:
                seen.add(fact_id)


def export_overlay_from_maps(api_dir: Path, db_paths: list[Path], fact_json_paths: list[Path], dose_by_subject: dict[str, list[dict[str, Any]]], overdose_by_subject: dict[str, list[dict[str, Any]]], names: dict[str, str], max_per_subject: int = 0, max_content_per_subject: int = 24) -> dict[str, Any]:
    all_subjects = set(dose_by_subject) | set(overdose_by_subject)
    identities = load_identities(db_paths, all_subjects)
    identities = load_json_identities(fact_json_paths, all_subjects, identities)
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
    dose_rule_overlay = merge_generated_dose_rules(api_dir, db_paths, fact_json_paths, dataset_version, names)
    content_overlay = export_content_overlay_from_sources(api_dir, db_paths, fact_json_paths, max_per_subject=max_content_per_subject)
    search_count = len(read_json(api_dir / "search" / "index.json", []))
    overlay_manifest = {
        "generated_from": [str(path) for path in [*db_paths, *fact_json_paths]],
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
    counts["drug_effects"] = content_overlay.get("drug_effects", 0)
    counts["pharmacokinetics"] = content_overlay.get("pharmacokinetics", 0)
    counts["enzyme_relations"] = content_overlay.get("enzyme_relations", 0)
    paths = manifest.setdefault("paths", {})
    paths["dose_candidates_by_substance"] = "search index item paths.dose_candidates"
    paths["overdose_warnings_by_substance"] = "search index item paths.overdose_warnings"
    paths["drug_effects_by_substance"] = "search index item paths.drug_effects"
    paths["pharmacokinetics_by_substance"] = "search index item paths.pharmacokinetics"
    paths["enzyme_relations_by_substance"] = "search index item paths.enzyme_relations"
    paths["search_shards"] = "search/shards/{key}.json"
    search_overlay = export_search_lookup(api_dir)
    manifest["search_overlay"] = {
        "manifest": "search/manifest.json",
        "items": search_overlay.get("items", 0),
        "shards": len(search_overlay.get("shards", {})),
        "policy": search_overlay.get("policy"),
    }
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
    manifest["drug_effect_overlay"] = {
        "manifest": "drug-effects/manifest.json",
        "policy": CONTENT_GROUPS["drug_effect"]["policy"],
    }
    manifest["pharmacokinetics_overlay"] = {
        "manifest": "pharmacokinetics/manifest.json",
        "policy": CONTENT_GROUPS["pharmacokinetics"]["policy"],
    }
    manifest["enzyme_relation_overlay"] = {
        "manifest": "enzyme-relations/manifest.json",
        "policy": CONTENT_GROUPS["enzyme_relation"]["policy"],
    }
    write_json(manifest_path, manifest)
    return overlay_manifest | {"search_substances": search_count, "dose_rule_overlay": dose_rule_overlay, "content_overlay": content_overlay}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export dose candidates and overdosage warnings from structured SQLite or streamed EvidenceFact JSON into static API overlay files.")
    parser.add_argument("--api-dir", default="public/api")
    parser.add_argument("--structured-db", action="append", default=[])
    parser.add_argument("--fact-json", action="append", default=[], help="EvidenceFact JSON array to stream; can be repeated")
    parser.add_argument("--max-per-substance", type=int, default=0)
    parser.add_argument("--max-content-per-substance", type=int, default=24, help="Maximum exported effect/PK/enzyme rows per substance; 0 exports all")
    args = parser.parse_args()
    db_paths = [Path(item) for item in args.structured_db]
    fact_json_paths = [Path(item) for item in args.fact_json]
    if not db_paths and not fact_json_paths:
        raise SystemExit("at least one --structured-db or --fact-json is required")
    summary = export_overlay_from_sources(Path(args.api_dir), db_paths, fact_json_paths, max_per_subject=args.max_per_substance, max_content_per_subject=args.max_content_per_substance)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
