from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .schemas import EvidenceFact, now_utc, slugify, stable_hash

SALT_WORDS = {
    "hydrochloride", "hcl", "tartrate", "citrate", "sodium", "potassium", "succinate",
    "maleate", "phosphate", "sulfate", "mesylate", "besylate", "bitartrate", "calcium",
    "extended", "release", "tablet", "tablets", "capsule", "capsules", "oral", "solution",
}

DOSE_AMOUNT = r"(?P<dose>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|ug|micrograms?|g|grams?)"
DOSE_RANGE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)"
    r"(?:\s*(?:-|to|through)\s*(?P<value2>\d+(?:\.\d+)?))?"
    r"\s*(?P<unit>mg/kg/day|mg/kg/dose|mcg/kg/min|mcg/kg/day|mcg/kg|ug/kg|micrograms?/kg|mg|mcg|ug|micrograms?|g|grams?|mL|ml|units?|IU|%)\b",
    re.I,
)

DAILY_PATTERNS = [
    re.compile(rf"(?:must|should)\s+not\s+exceed(?:\s+a\s+total\s+of)?\s+{DOSE_AMOUNT}\s*(?:/\s*day|daily|per\s+day|a\s+day|in\s+24\s+hours)", re.I),
    re.compile(rf"maximum\s+(?:recommended\s+)?(?:total\s+)?(?:daily\s+)?(?:dose|dosage)[^.;:]{{0,120}}?{DOSE_AMOUNT}\s*(?:/\s*day|per\s+day|daily|a\s+day)?", re.I),
    re.compile(rf"up\s+to\s+(?:a\s+)?maximum\s+of\s+{DOSE_AMOUNT}\s*(?:/\s*day|per\s+day|daily|a\s+day)", re.I),
    re.compile(rf"(?:not\s+more\s+than|no\s+more\s+than)\s+{DOSE_AMOUNT}\s*(?:/\s*day|per\s+day|daily|a\s+day|in\s+24\s+hours)", re.I),
    re.compile(rf"(?:do\s+not|don'?t)\s+(?:take|administer|use)\s+more\s+than\s+{DOSE_AMOUNT}\s*(?:/\s*day|per\s+day|daily|a\s+day|in\s+24\s+hours)", re.I),
]

SINGLE_PATTERNS = [
    re.compile(rf"maximum\s+(?:recommended\s+)?single\s+(?:dose|dosage)[^.;:]{{0,120}}?{DOSE_AMOUNT}", re.I),
    re.compile(rf"single\s+dose\s+(?:of\s+)?{DOSE_AMOUNT}", re.I),
    re.compile(rf"(?:not\s+more\s+than|no\s+more\s+than)\s+{DOSE_AMOUNT}\s+(?:at\s+one\s+time|per\s+dose|in\s+a\s+single\s+dose)", re.I),
]

MAX_HINT_RE = re.compile(r"\b(maximum|max\.?|not\s+exceed|no\s+more\s+than|not\s+more\s+than|do\s+not\s+(?:take|use|administer)\s+more\s+than)\b", re.I)
DAILY_HINT_RE = re.compile(r"\b(day|daily|per\s+day|a\s+day|24\s*hours?|24\s*h|total\s+daily)\b", re.I)
SINGLE_HINT_RE = re.compile(r"\b(single\s+dose|per\s+dose|one\s+time|at\s+one\s+time)\b", re.I)
DOSE_ACTION_RE = re.compile(r"\b(dose|dosage|administer|take|recommended|usual|initial|starting|maintenance|titrate|titrated)\b", re.I)
STRENGTH_ONLY_RE = re.compile(r"\b(dosage\s+forms?|strengths?|supplied|available\s+as|capsules?|tablets?|vials?|injection\s+contains)\b", re.I)
ROUTE_RE = re.compile(r"\b(oral|intravenous|iv|subcutaneous|sublingual|intranasal|topical|transdermal|inhalation|rectal)\b", re.I)

UNIT_TO_MG = {
    "mg": 1.0,
    "mcg": 0.001,
    "ug": 0.001,
    "microgram": 0.001,
    "micrograms": 0.001,
    "g": 1000.0,
    "gram": 1000.0,
    "grams": 1000.0,
}


@dataclass(frozen=True)
class DoseMatch:
    value_mg: float
    evidence: str
    kind: str


def extract_dose_candidate_facts(
    subject_id: str,
    text: str,
    source_name: str,
    source_url: str,
    method: str,
    section: str = "dosage",
    max_candidates: int = 40,
) -> list[EvidenceFact]:
    """Extract conservative dose candidates from label text.

    These are not final safety rules. They preserve local context so the
    dose-rule normalizer can promote only explicit maxima into dose_rule rows.
    """
    clean_text = squash(text)
    if not clean_text:
        return []
    facts: list[EvidenceFact] = []
    seen: set[tuple[str, str, str]] = set()
    for match in DOSE_RANGE.finditer(clean_text):
        unit = str(match.group("unit") or "").strip()
        key = (match.group("value"), match.group("value2") or "", unit.lower())
        if key in seen:
            continue
        seen.add(key)
        context = clean_text[max(0, match.start() - 180):min(len(clean_text), match.end() + 180)]
        try:
            value = float(match.group("value"))
            value_max = float(match.group("value2")) if match.group("value2") else None
        except (TypeError, ValueError):
            continue
        facts.append(EvidenceFact(
            fact_id=f"dose_candidate_{stable_hash(subject_id + source_name + section + context)}",
            fact_type="dose_candidate",
            subject_ids=[subject_id],
            claim={
                "value": value,
                "value_max": value_max,
                "unit": unit,
                "context": context,
                "section": section,
                "candidate_kind": classify_candidate_context(context),
            },
            confidence="Low",
            source_tier="Regulatory",
            source_name=source_name,
            source_url=source_url,
            evidence_quote=context[:600],
            extraction_method=f"{method}_dose_candidate",
            review_status="unreviewed",
            use_policy="candidate_signal",
            updated_at=now_utc(),
        ))
        if len(facts) >= max_candidates:
            break
    return facts


def extract_dose_rule_facts(facts: Iterable[EvidenceFact]) -> list[EvidenceFact]:
    """Promote high-signal label dose text into normalized dose_rule facts.

    Explicit maximum / not-exceed wording becomes a candidate ceiling rule. If a
    substance also has an overdosage warning, therapeutic dose candidates can
    become softer screening rules marked review_required.
    """
    source_texts: dict[str, list[EvidenceFact]] = {}
    candidates: dict[str, list[EvidenceFact]] = {}
    overdose_warnings: dict[str, list[EvidenceFact]] = {}
    existing_subjects: set[str] = set()
    for fact in facts:
        if fact.fact_type == "dose_rule" and fact.subject_ids:
            existing_subjects.add(fact.subject_ids[0])
            existing_subjects.add(normalize_label_subject(fact.subject_ids[0]))
        if not fact.subject_ids:
            continue
        if fact.fact_type == "source_text":
            section = str(fact.claim.get("section") or "").lower()
            if section in {"dosage_and_administration", "overdosage", "dosage_forms_and_strengths", "dosage", "overdose"}:
                source_texts.setdefault(fact.subject_ids[0], []).append(fact)
        elif fact.fact_type == "dose_candidate":
            candidates.setdefault(fact.subject_ids[0], []).append(fact)
        elif fact.fact_type == "overdose_warning":
            overdose_warnings.setdefault(fact.subject_ids[0], []).append(fact)

    generated: list[EvidenceFact] = []
    for subject_id in sorted(set(source_texts) | set(candidates) | set(overdose_warnings)):
        base_subject = normalize_label_subject(subject_id)
        if subject_id in existing_subjects or base_subject in existing_subjects:
            continue
        group = [*source_texts.get(subject_id, []), *candidates.get(subject_id, []), *overdose_warnings.get(subject_id, [])]
        if not group:
            continue
        evidence_text = "\n".join(fact_text(fact) for fact in group)
        subject_candidates = candidates.get(subject_id, [])
        has_overdose_warning = bool(overdose_warnings.get(subject_id))
        daily = best_match(evidence_text, DAILY_PATTERNS, "window") or best_candidate_match(subject_candidates, "window")
        single = best_match(evidence_text, SINGLE_PATTERNS, "single") or best_candidate_match(subject_candidates, "single")
        if has_overdose_warning and not (daily or single):
            daily = best_screening_candidate_match(subject_candidates, "window")
            single = best_screening_candidate_match(subject_candidates, "single")
        if not daily and not single:
            continue
        first = strongest_source(group)
        generated.append(make_dose_rule_fact(base_subject, subject_id, daily, single, first, evidence_text, has_overdose_warning))
    return generated


def normalize_dose_rule_claim(subject_id: str, claim: dict) -> dict | None:
    thresholds = normalize_thresholds(claim.get("thresholds") or [])
    if not thresholds:
        return None
    match_terms = normalize_match_terms(claim.get("match_terms") or claim.get("match") or [], subject_id)
    unit = normalize_rule_unit(str(claim.get("unit") or "mg"))
    if unit not in {"mg", "g"}:
        return None
    rule_id = str(claim.get("rule_id") or f"dose_{stable_hash(subject_id + str(claim))}")
    return {
        "schema_version": str(claim.get("schema_version") or "dose_rule_v2"),
        "rule_id": rule_id,
        "subject_id": subject_id,
        "match_terms": match_terms,
        "unit": unit,
        "route": claim.get("route") or "Oral",
        "window_hours": safe_float(claim.get("window_hours"), 24.0),
        "thresholds": thresholds,
        "basis": claim.get("basis") or infer_rule_basis(thresholds),
        "population": claim.get("population") or {"age_group": "adult_or_unspecified", "review_required": True},
        "condition": claim.get("condition") or {},
        "normalized_from": claim.get("normalized_from") or [],
        "original_subject_id": claim.get("original_subject_id"),
        "note": claim.get("note"),
    }


def make_dose_rule_fact(base_subject: str, original_subject: str, daily: DoseMatch | None, single: DoseMatch | None, first: EvidenceFact, evidence_text: str, overdose_supported: bool = False) -> EvidenceFact:
    thresholds: list[dict] = []
    screening = bool((daily and daily.kind.startswith("screening")) or (single and single.kind.startswith("screening")))
    if single:
        if single.kind.startswith("screening"):
            thresholds.extend(screening_thresholds("single", single.value_mg))
        else:
            thresholds.append({"kind": "single", "level": "Moderate", "limit": round(single.value_mg, 4), "label": f"single dose reaches/exceeds extracted label ceiling {single.value_mg:g} mg"})
            thresholds.append({"kind": "single", "level": "Major", "limit": round(single.value_mg * 2, 4), "label": f"single dose reaches/exceeds 2x extracted label ceiling {single.value_mg * 2:g} mg"})
    if daily:
        if daily.kind.startswith("screening"):
            thresholds.extend(screening_thresholds("window", daily.value_mg))
        else:
            thresholds.extend([
                {"kind": "window", "level": "Moderate", "limit": round(daily.value_mg, 4), "label": f"24h total reaches/exceeds extracted label ceiling {daily.value_mg:g} mg"},
                {"kind": "window", "level": "Major", "limit": round(daily.value_mg * 2, 4), "label": f"24h total reaches/exceeds 2x extracted label ceiling {daily.value_mg * 2:g} mg"},
                {"kind": "window", "level": "Contraindicated", "limit": round(daily.value_mg * 4, 4), "label": f"24h total reaches/exceeds 4x extracted label ceiling {daily.value_mg * 4:g} mg"},
            ])
    if not daily and single and not single.kind.startswith("screening"):
        thresholds.append({"kind": "single", "level": "Contraindicated", "limit": round(single.value_mg * 4, 4), "label": f"single dose reaches/exceeds 4x extracted label ceiling {single.value_mg * 4:g} mg"})
    route = detect_route(evidence_text)
    subject_terms = normalize_match_terms([original_subject, base_subject, original_subject.replace("_", " "), base_subject.replace("_", " ")], base_subject)
    evidence = daily.evidence if daily else single.evidence if single else evidence_text[:600]
    basis = "overdose_warning_supported_dose_screening" if screening else "adult_or_unspecified_label_ceiling"
    normalized_from = ["dose_candidate", "source_text"]
    if overdose_supported:
        normalized_from.append("overdose_warning")
    note = "Automatically extracted from public label maxima. Treat as a candidate safety rule until source review validates route, age, indication and formulation."
    if screening:
        note = "Soft screening rule derived from dose candidates and an overdosage warning section. It is intentionally conservative evidence for review, not a validated clinical maximum."
    return EvidenceFact(
        fact_id=f"dose_rule_auto_{stable_hash(base_subject + str(daily) + str(single))}",
        fact_type="dose_rule",
        subject_ids=[base_subject],
        claim={
            "schema_version": "dose_rule_v2",
            "rule_id": f"auto_{base_subject}_label_{stable_hash(base_subject + evidence, 8)}",
            "match_terms": subject_terms,
            "original_subject_id": original_subject,
            "unit": "mg",
            "route": route,
            "window_hours": 24,
            "thresholds": thresholds,
            "basis": basis,
            "population": {"age_group": "adult_or_unspecified", "review_required": True},
            "condition": {"overdose_warning_supported": overdose_supported, "screening_rule": screening},
            "normalized_from": normalized_from,
            "note": note,
        },
        confidence="Medium" if first.source_tier in {"Regulatory", "Guideline"} else "Low",
        source_tier=first.source_tier,
        source_name=f"{first.source_name} auto dose normalizer",
        source_url=first.source_url,
        evidence_quote=evidence[:1200],
        extraction_method="regex_label_dose_rule_v3",
        review_status="unreviewed",
        use_policy="candidate_safety_rule",
        updated_at=now_utc(),
    )


def fact_text(fact: EvidenceFact) -> str:
    if fact.fact_type == "source_text":
        return str(fact.claim.get("text") or "")
    if fact.fact_type == "dose_candidate":
        return str(fact.claim.get("context") or fact.evidence_quote or "")
    if fact.fact_type == "overdose_warning":
        return str(fact.claim.get("overdose_text") or fact.claim.get("text") or fact.evidence_quote or "")
    return fact.evidence_quote or ""


def best_match(text: str, patterns: list[re.Pattern], kind: str) -> DoseMatch | None:
    candidates: list[DoseMatch] = []
    clean_text = squash(text)
    for pattern in patterns:
        for match in pattern.finditer(clean_text):
            value = normalize_to_mg(match.group("dose"), match.group("unit"))
            if value is None or not (0 < value <= 1_000_000):
                continue
            context = clean_text[max(0, match.start() - 220):min(len(clean_text), match.end() + 260)]
            if kind == "window" and not (MAX_HINT_RE.search(context) and DAILY_HINT_RE.search(context)):
                continue
            if kind == "single" and not (MAX_HINT_RE.search(context) or SINGLE_HINT_RE.search(context)):
                continue
            candidates.append(DoseMatch(value, context, kind))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.value_mg)


def best_candidate_match(candidates: list[EvidenceFact], kind: str) -> DoseMatch | None:
    matches: list[DoseMatch] = []
    for fact in candidates:
        context = str(fact.claim.get("context") or "")
        if not MAX_HINT_RE.search(context):
            continue
        if kind == "window" and not DAILY_HINT_RE.search(context):
            continue
        if kind == "single" and not SINGLE_HINT_RE.search(context):
            continue
        unit = str(fact.claim.get("unit") or "")
        if unit.lower() not in UNIT_TO_MG:
            continue
        raw_value = fact.claim.get("value_max") or fact.claim.get("value")
        value = normalize_to_mg(raw_value, unit)
        if value is None or not (0 < value <= 1_000_000):
            continue
        matches.append(DoseMatch(value, context, kind))
    if not matches:
        return None
    return max(matches, key=lambda item: item.value_mg)


def best_screening_candidate_match(candidates: list[EvidenceFact], kind: str) -> DoseMatch | None:
    matches: list[tuple[int, DoseMatch]] = []
    for fact in candidates:
        context = str(fact.claim.get("context") or fact.evidence_quote or "")
        unit = str(fact.claim.get("unit") or "")
        if unit.lower() not in UNIT_TO_MG:
            continue
        if kind == "window" and not DAILY_HINT_RE.search(context):
            continue
        if kind == "single" and not (SINGLE_HINT_RE.search(context) or re.search(r"\btake\s+(?:a|one|1)\b", context, re.I)):
            continue
        score = candidate_context_score(context)
        if score < 2:
            continue
        raw_value = fact.claim.get("value_max") or fact.claim.get("value")
        value = normalize_to_mg(raw_value, unit)
        if value is None or not (0 < value <= 1_000_000):
            continue
        matches.append((score, DoseMatch(value, context, f"screening_{kind}")))
    if not matches:
        return None
    return max(matches, key=lambda item: (item[0], item[1].value_mg))[1]


def candidate_context_score(context: str) -> int:
    score = 0
    if MAX_HINT_RE.search(context):
        score += 6
    if DAILY_HINT_RE.search(context):
        score += 4
    if SINGLE_HINT_RE.search(context):
        score += 3
    if DOSE_ACTION_RE.search(context):
        score += 2
    if STRENGTH_ONLY_RE.search(context) and not re.search(r"\b(take|administer|dose|dosage)\b", context, re.I):
        score -= 5
    return score


def screening_thresholds(kind: str, baseline_mg: float) -> list[dict]:
    subject = "24h total" if kind == "window" else "single dose"
    return [
        {"kind": kind, "level": "Moderate", "limit": round(baseline_mg * 3, 4), "label": f"{subject} reaches/exceeds 3x extracted dose candidate {baseline_mg * 3:g} mg"},
        {"kind": kind, "level": "Major", "limit": round(baseline_mg * 6, 4), "label": f"{subject} reaches/exceeds 6x extracted dose candidate {baseline_mg * 6:g} mg"},
        {"kind": kind, "level": "Contraindicated", "limit": round(baseline_mg * 10, 4), "label": f"{subject} reaches/exceeds 10x extracted dose candidate {baseline_mg * 10:g} mg"},
    ]


def normalize_thresholds(thresholds: list) -> list[dict]:
    out: list[dict] = []
    for item in thresholds:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "window")
        if kind not in {"single", "window"}:
            kind = "window"
        level = str(item.get("level") or "Moderate")
        if level not in {"Minor", "Moderate", "Major", "Contraindicated"}:
            level = "Moderate"
        limit = safe_float(item.get("limit"), None)
        if limit is None or limit <= 0:
            continue
        label = str(item.get("label") or f"{kind} dose reaches/exceeds {limit:g}")
        out.append({"kind": kind, "level": level, "limit": round(limit, 6), "label": label})
    return sorted(out, key=lambda row: (0 if row["kind"] == "single" else 1, row["limit"], row["level"]))


def normalize_label_subject(subject_id: str) -> str:
    parts = [part for part in slugify(subject_id).split("_") if part and part not in SALT_WORDS]
    return "_".join(parts[:3]) or slugify(subject_id)


def normalize_match_terms(values: Iterable, subject_id: str) -> list[str]:
    terms = [subject_id, subject_id.replace("_", " ")]
    for value in values or []:
        text = str(value or "").strip()
        if text:
            terms.append(text)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out[:40]


def normalize_rule_unit(unit: str) -> str:
    lowered = unit.lower().strip()
    if lowered in {"g", "gram", "grams"}:
        return "g"
    return "mg"


def normalize_to_mg(value, unit: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    factor = UNIT_TO_MG.get(str(unit or "").lower())
    if factor is None:
        return None
    return number * factor


def classify_candidate_context(context: str) -> str:
    if MAX_HINT_RE.search(context) and DAILY_HINT_RE.search(context):
        return "max_daily_candidate"
    if MAX_HINT_RE.search(context) and SINGLE_HINT_RE.search(context):
        return "max_single_candidate"
    if re.search(r"\b(recommended|usual|starting|initial)\b", context, re.I):
        return "therapeutic_range_candidate"
    return "dose_mention"


def detect_route(text: str) -> str:
    match = ROUTE_RE.search(text or "")
    if not match:
        return "Oral"
    value = match.group(1).lower()
    return {
        "iv": "IV",
        "intravenous": "IV",
        "subcutaneous": "Subcutaneous",
        "sublingual": "Sublingual",
        "intranasal": "Intranasal",
        "topical": "Topical",
        "transdermal": "Transdermal",
        "inhalation": "Inhalation",
        "rectal": "Rectal",
        "oral": "Oral",
    }.get(value, "Oral")


def strongest_source(group: list[EvidenceFact]) -> EvidenceFact:
    rank = {"Guideline": 6, "Regulatory": 6, "Label": 5, "CuratedDB": 4, "Literature": 3, "Signal": 2, "Community": 1}
    return max(group, key=lambda fact: rank.get(fact.source_tier, 0))


def infer_rule_basis(thresholds: list[dict]) -> str:
    kinds = {item.get("kind") for item in thresholds}
    if "window" in kinds and "single" in kinds:
        return "single_and_window_ceiling"
    if "window" in kinds:
        return "window_ceiling"
    return "single_ceiling"


def safe_float(value, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()
