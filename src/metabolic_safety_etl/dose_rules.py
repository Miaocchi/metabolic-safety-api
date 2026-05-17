from __future__ import annotations

import re
from typing import Iterable

from .schemas import EvidenceFact, now_utc, slugify, stable_hash

SALT_WORDS = {
    "hydrochloride", "hcl", "tartrate", "citrate", "sodium", "potassium", "succinate",
    "maleate", "phosphate", "sulfate", "mesylate", "besylate", "bitartrate", "calcium",
    "extended", "release", "tablet", "tablets", "capsule", "capsules", "oral", "solution",
}

DAILY_PATTERNS = [
    re.compile(r"(?:must|should)\s+not\s+exceed(?:\s+a\s+total\s+of)?\s+(?P<dose>\d+(?:\.\d+)?)\s*mg\s+(?:daily|per\s+day|a\s+day|in\s+24\s+hours)", re.I),
    re.compile(r"maximum\s+(?:recommended\s+)?(?:total\s+)?(?:daily\s+)?(?:dose|dosage)[^.;:]{0,100}?(?P<dose>\d+(?:\.\d+)?)\s*mg\s*(?:/\s*day|per\s+day|daily|a\s+day)?", re.I),
    re.compile(r"up\s+to\s+(?:a\s+)?maximum\s+of\s+(?P<dose>\d+(?:\.\d+)?)\s*mg\s*(?:/\s*day|per\s+day|daily|a\s+day)", re.I),
    re.compile(r"(?:not\s+more\s+than|no\s+more\s+than)\s+(?P<dose>\d+(?:\.\d+)?)\s*mg\s*(?:/\s*day|per\s+day|daily|a\s+day)", re.I),
]

SINGLE_PATTERNS = [
    re.compile(r"maximum\s+(?:recommended\s+)?(?:single\s+)?(?:dose|dosage)[^.;:]{0,100}?(?P<dose>\d+(?:\.\d+)?)\s*mg", re.I),
    re.compile(r"single\s+dose\s+(?:of\s+)?(?P<dose>\d+(?:\.\d+)?)\s*mg", re.I),
]


def extract_dose_rule_facts(facts: Iterable[EvidenceFact]) -> list[EvidenceFact]:
    source_texts: dict[str, list[EvidenceFact]] = {}
    existing_subjects: set[str] = set()
    for fact in facts:
        if fact.fact_type == "dose_rule" and fact.subject_ids:
            existing_subjects.add(fact.subject_ids[0])
        if fact.fact_type != "source_text" or not fact.subject_ids:
            continue
        section = str(fact.claim.get("section") or "").lower()
        if section not in {"dosage_and_administration", "overdosage", "dosage_forms_and_strengths"}:
            continue
        source_texts.setdefault(fact.subject_ids[0], []).append(fact)

    generated: list[EvidenceFact] = []
    for subject_id, group in sorted(source_texts.items()):
        base_subject = normalize_label_subject(subject_id)
        if subject_id in existing_subjects or base_subject in existing_subjects:
            continue
        joined = "\n".join(str(item.claim.get("text") or "") for item in group)
        max_daily = _best_match(joined, DAILY_PATTERNS)
        if not max_daily:
            continue
        max_single = _best_match(joined, SINGLE_PATTERNS)
        thresholds = []
        if max_single:
            thresholds.append({"kind": "single", "level": "Moderate", "limit": max_single, "label": f"single dose reaches/exceeds extracted label ceiling {max_single:g} mg"})
        thresholds.extend([
            {"kind": "window", "level": "Moderate", "limit": max_daily, "label": f"24h total reaches/exceeds extracted label ceiling {max_daily:g} mg"},
            {"kind": "window", "level": "Major", "limit": max_daily * 2, "label": f"24h total reaches/exceeds 2x extracted label ceiling {max_daily * 2:g} mg"},
            {"kind": "window", "level": "Contraindicated", "limit": max_daily * 4, "label": f"24h total reaches/exceeds 4x extracted label ceiling {max_daily * 4:g} mg"},
        ])
        first = group[0]
        subject_terms = sorted({subject_id, base_subject, subject_id.replace("_", " "), base_subject.replace("_", " ")})
        generated.append(
            EvidenceFact(
                fact_id=f"dose_rule_auto_{stable_hash(subject_id + str(max_daily))}",
                fact_type="dose_rule",
                subject_ids=[base_subject],
                claim={
                    "rule_id": f"auto_{base_subject}_daily_label_{stable_hash(subject_id + str(max_daily), 8)}",
                    "match_terms": subject_terms,
                    "unit": "mg",
                    "route": "Oral",
                    "window_hours": 24,
                    "thresholds": thresholds,
                    "note": "Automatically extracted from public drug label text; keep as candidate until manually reviewed.",
                },
                confidence="Medium",
                source_tier=first.source_tier,
                source_name=f"{first.source_name} auto dose extractor",
                source_url=first.source_url,
                evidence_quote=_evidence_window(joined, max_daily),
                extraction_method="regex_label_extractor",
                review_status="unreviewed",
                use_policy="candidate_safety_rule",
                updated_at=now_utc(),
            )
        )
    return generated


def normalize_label_subject(subject_id: str) -> str:
    parts = [part for part in slugify(subject_id).split("_") if part and part not in SALT_WORDS]
    return "_".join(parts[:3]) or slugify(subject_id)


def _best_match(text: str, patterns: list[re.Pattern]) -> float | None:
    candidates: list[float] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            try:
                value = float(match.group("dose"))
            except (TypeError, ValueError):
                continue
            if 0 < value <= 100000:
                candidates.append(value)
    if not candidates:
        return None
    return max(candidates)


def _evidence_window(text: str, dose: float) -> str:
    needle = f"{dose:g}"
    idx = text.find(needle)
    if idx < 0:
        return text[:600]
    start = max(0, idx - 260)
    end = min(len(text), idx + 340)
    return text[start:end]
