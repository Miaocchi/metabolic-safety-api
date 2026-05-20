from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from .dose_rules import extract_dose_rule_facts, normalize_dose_rule_claim
from .schemas import (
    CONFIDENCE_RANK,
    RISK_ACTION,
    RISK_RANK,
    SOURCE_TIER_RANK,
    EvidenceFact,
    canonical_pair,
    normalize_risk,
    slugify,
    stable_hash,
)

INTERACTION_TYPES = {"drug_interaction", "food_interaction"}


def _ranked_max(values: list[str], ranks: dict[str, int], default: str) -> str:
    if not values:
        return default
    return max(values, key=lambda item: ranks.get(item, ranks.get(default, 0)))


def _source_summary(facts: list[EvidenceFact]) -> list[dict[str, Any]]:
    return [
        {
            "fact_id": fact.fact_id,
            "source_tier": fact.source_tier,
            "source_name": fact.source_name,
            "source_url": fact.source_url,
            "confidence": fact.confidence,
            "risk_level": fact.risk_level,
            "review_status": fact.review_status,
        }
        for fact in facts
    ]


def build_substances_core(facts: list[EvidenceFact], dataset_version: str) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    supporting: dict[str, list[EvidenceFact]] = defaultdict(list)
    pk_facts_by_subject: dict[str, list[EvidenceFact]] = defaultdict(list)
    hl_best_score: dict[str, list[int]] = {}

    for fact in facts:
        if not fact.subject_ids:
            continue
        subject_id = fact.subject_ids[0]
        if subject_id not in records:
            records[subject_id] = {
                "id": subject_id,
                "name_zh": None,
                "name_en": subject_id.replace("_", " ").title(),
                "category": None,
                "solubility": None,
                "base_half_life": None,
                "base_onset": None,
                "base_duration": None,
                "identifiers": {},
                "cyp_tags": [],
                "dataset_version": dataset_version,
            }
            hl_best_score[subject_id] = [0]

        if fact.fact_type == "substance_identity":
            claim = fact.claim
            for key in ("name_zh", "name_en", "category", "solubility"):
                if claim.get(key):
                    records[subject_id][key] = _scalar(claim[key])
            records[subject_id]["identifiers"].update({key: _scalar(value) for key, value in claim.get("identifiers", {}).items()})
            supporting[subject_id].append(fact)

        if fact.fact_type == "pharmacokinetics":
            claim = fact.claim
            pk_facts_by_subject[subject_id].append(fact)
            if claim.get("half_life_hours") is not None:
                records[subject_id]["base_half_life"] = _pick_best_half_life(
                    records[subject_id]["base_half_life"],
                    _numeric(claim["half_life_hours"]),
                    fact,
                    hl_best_score[subject_id],
                )
            if claim.get("onset_minutes") is not None:
                records[subject_id]["base_onset"] = _numeric(claim["onset_minutes"])
            if claim.get("duration_minutes") is not None:
                records[subject_id]["base_duration"] = _numeric(claim["duration_minutes"])
            supporting[subject_id].append(fact)

        if fact.fact_type == "enzyme_relation":
            tag = fact.claim.get("tag")
            if tag and tag not in records[subject_id]["cyp_tags"]:
                records[subject_id]["cyp_tags"].append(tag)
            supporting[subject_id].append(fact)

    out = []
    for subject_id, record in sorted(records.items()):
        record["source_summary"] = _source_summary(supporting.get(subject_id, []))
        record["pharmacokinetics_detail"] = _build_pk_detail(pk_facts_by_subject.get(subject_id, []))
        out.append(record)
    return out


def _scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float)) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_best_half_life(current: float | None, candidate: float | None, fact: EvidenceFact, best_score: list[int] | None = None) -> float | None:
    """Pick the best half-life value using source-tier and confidence.

    Uses a composite score (tier_rank * 10 + confidence_rank) to prefer
    higher-quality sources.  ``best_score`` is a mutable single-element list
    that tracks the winning score across invocations for the same substance.
    """
    if candidate is None:
        return current
    if current is None:
        if best_score is not None:
            tier_rank = SOURCE_TIER_RANK.get(fact.source_tier, 0)
            conf_rank = CONFIDENCE_RANK.get(fact.confidence, 0)
            best_score[0] = tier_rank * 10 + conf_rank
        return candidate
    tier_rank = SOURCE_TIER_RANK.get(fact.source_tier, 0)
    conf_rank = CONFIDENCE_RANK.get(fact.confidence, 0)
    candidate_score = tier_rank * 10 + conf_rank
    if best_score is not None and candidate_score > best_score[0]:
        best_score[0] = candidate_score
        return candidate
    if best_score is None:
        return candidate
    return current


def _build_pk_detail(pk_facts: list[EvidenceFact]) -> list[dict[str, Any]]:
    """Build structured pharmacokinetics detail array from PK evidence facts."""
    if not pk_facts:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fact in sorted(pk_facts, key=lambda f: (
        -SOURCE_TIER_RANK.get(f.source_tier, 0),
        -CONFIDENCE_RANK.get(f.confidence, 0),
    )):
        claim = fact.claim
        hl = claim.get("half_life_hours")
        dedupe_key = f"{hl}|{fact.source_name}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        row: dict[str, Any] = {
            "half_life_hours": _numeric(hl),
            "source_name": fact.source_name,
            "source_tier": fact.source_tier,
            "confidence": fact.confidence,
        }
        for key in ("half_life_hours_upper", "half_life_hours_mean", "onset_minutes", "duration_minutes",
                     "bioavailability", "clearance", "volume_distribution", "route", "standard_type"):
            if claim.get(key) is not None:
                row[key] = claim[key]
        rows.append(row)
    return rows


def merge_interactions(facts: list[EvidenceFact], dataset_version: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[EvidenceFact]] = defaultdict(list)
    for fact in facts:
        if fact.fact_type not in INTERACTION_TYPES:
            continue
        a, b = canonical_pair(fact.subject_ids)
        groups[(a, b, fact.fact_type)].append(fact)

    merged: list[dict[str, Any]] = []
    for (a, b, interaction_type), group in sorted(groups.items()):
        known = [fact for fact in group if normalize_risk(fact.risk_level) != "Unknown"]
        if known:
            risk_level = _ranked_max([fact.risk_level for fact in known], RISK_RANK, "Unknown")
            supporting_risk = [fact for fact in known if fact.risk_level == risk_level]
        else:
            risk_level = "Unknown"
            supporting_risk = group

        confidence = _ranked_max([fact.confidence for fact in supporting_risk], CONFIDENCE_RANK, "Unknown")
        source_tier = _ranked_max([fact.source_tier for fact in supporting_risk], SOURCE_TIER_RANK, "Community")
        risk_values = sorted({fact.risk_level for fact in group})
        conflict_status = "conflicting" if len([risk for risk in risk_values if risk != "Unknown"]) > 1 else "consistent"

        mechanisms = []
        notes = []
        for fact in group:
            mechanism = fact.claim.get("mechanism")
            note = fact.claim.get("note")
            if mechanism and mechanism not in mechanisms:
                mechanisms.append(mechanism)
            if note and note not in notes:
                notes.append(note)

        interaction_id = f"int_{stable_hash('|'.join([a, b, interaction_type]))}"
        merged.append(
            {
                "interaction_id": interaction_id,
                "substance_a_id": a,
                "substance_b_id": b,
                "interaction_type": interaction_type,
                "risk_level": risk_level,
                "confidence": confidence,
                "source_tier": source_tier,
                "action": RISK_ACTION.get(risk_level, "show_uncertainty"),
                "mechanism": "; ".join(mechanisms) if mechanisms else None,
                "note": " | ".join(notes) if notes else None,
                "evidence_refs": _source_summary(group),
                "conflict_status": conflict_status,
                "dataset_version": dataset_version,
            }
        )
    return merged



def build_dose_rules_core(facts: list[EvidenceFact], dataset_version: str) -> list[dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    supporting: dict[str, list[EvidenceFact]] = defaultdict(list)
    for fact in facts:
        if fact.fact_type != "dose_rule" or not fact.subject_ids:
            continue
        subject_id = fact.subject_ids[0]
        normalized = normalize_dose_rule_claim(subject_id, fact.claim)
        if not normalized:
            continue
        rule_id = normalized["rule_id"]
        rules[rule_id] = {
            **normalized,
            "source_name": fact.source_name,
            "source_tier": fact.source_tier,
            "source_url": fact.source_url,
            "confidence": fact.confidence,
            "review_status": fact.review_status,
            "dataset_version": dataset_version,
        }
        supporting[rule_id].append(fact)
    out = []
    for rule_id, rule in sorted(rules.items()):
        rule["evidence_refs"] = _source_summary(supporting.get(rule_id, []))
        out.append(rule)
    return out

def build_dataset(facts: list[EvidenceFact], dataset_version: str) -> dict[str, Any]:
    normalized_facts = list(facts)
    normalized_facts.extend(extract_dose_rule_facts(normalized_facts))
    return {
        "dataset_version": dataset_version,
        "substances_core": build_substances_core(normalized_facts, dataset_version),
        "interactions_core": merge_interactions(normalized_facts, dataset_version),
        "dose_rules_core": build_dose_rules_core(normalized_facts, dataset_version),
        "evidence_facts": [fact.to_dict() for fact in normalized_facts],
    }


def load_facts(data: list[dict[str, Any]]) -> list[EvidenceFact]:
    return [EvidenceFact.from_dict(item) for item in data]


def normalize_subject_id(value: str) -> str:
    return slugify(value)
