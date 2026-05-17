from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from typing import Any


SOURCE_TIER_RANK = {
    "Community": 1,
    "Signal": 2,
    "Literature": 3,
    "CuratedDB": 4,
    "Label": 5,
    "Regulatory": 6,
    "Guideline": 6,
    "LicensedCommercial": 6,
    "ManualReview": 5,
    "Fixture": 0,
}

CONFIDENCE_RANK = {
    "Unknown": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
}

RISK_RANK = {
    "Unknown": -1,
    "NoKnownClinicalSignificance": 0,
    "Minor": 1,
    "Moderate": 2,
    "Major": 3,
    "Contraindicated": 4,
}

RISK_ACTION = {
    "Contraindicated": "highest_alert",
    "Major": "avoid_or_modify_therapy",
    "Moderate": "monitor_closely",
    "Minor": "caution_or_spacing",
    "NoKnownClinicalSignificance": "silent_unless_requested",
    "Unknown": "show_uncertainty",
}

RISK_ALIASES = {
    "x": "Contraindicated",
    "contraindicated": "Contraindicated",
    "danger": "Contraindicated",
    "dangerous": "Contraindicated",
    "d": "Major",
    "major": "Major",
    "unsafe": "Major",
    "c": "Moderate",
    "moderate": "Moderate",
    "caution": "Moderate",
    "b": "Minor",
    "minor": "Minor",
    "low risk": "Minor",
    "low risk & synergy": "Minor",
    "low risk & no synergy": "NoKnownClinicalSignificance",
    "a": "NoKnownClinicalSignificance",
    "none": "NoKnownClinicalSignificance",
    "no known interaction": "NoKnownClinicalSignificance",
    "unknown": "Unknown",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return normalized.strip("_") or "unknown"


def stable_hash(payload: str, length: int = 16) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def normalize_risk(value: str | None) -> str:
    if not value:
        return "Unknown"
    key = value.strip().lower()
    return RISK_ALIASES.get(key, value if value in RISK_RANK else "Unknown")


def canonical_pair(subject_ids: list[str]) -> tuple[str, str]:
    if len(subject_ids) != 2:
        raise ValueError("interaction facts must contain exactly two subject_ids")
    a, b = sorted(subject_ids)
    return a, b


@dataclass(frozen=True)
class EvidenceFact:
    fact_id: str
    fact_type: str
    subject_ids: list[str]
    claim: dict[str, Any]
    risk_level: str = "Unknown"
    confidence: str = "Unknown"
    source_tier: str = "Community"
    source_name: str = ""
    source_url: str = ""
    evidence_quote: str = ""
    extraction_method: str = "manual"
    review_status: str = "unreviewed"
    use_policy: str = "candidate_signal"
    updated_at: str = field(default_factory=now_utc)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "EvidenceFact":
        required = ["fact_type", "subject_ids", "claim"]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"missing required fact fields: {', '.join(missing)}")
        subject_ids = [slugify(str(item)) for item in data["subject_ids"]]
        risk_level = normalize_risk(data.get("risk_level"))
        confidence = data.get("confidence", "Unknown")
        if confidence not in CONFIDENCE_RANK:
            confidence = "Unknown"
        source_tier = data.get("source_tier", "Community")
        if source_tier not in SOURCE_TIER_RANK:
            source_tier = "Community"
        fact_id = data.get("fact_id") or make_fact_id(data.get("fact_type", "fact"), subject_ids, data.get("claim", {}), data.get("source_name", ""))
        return EvidenceFact(
            fact_id=fact_id,
            fact_type=str(data["fact_type"]),
            subject_ids=subject_ids,
            claim=dict(data["claim"]),
            risk_level=risk_level,
            confidence=confidence,
            source_tier=source_tier,
            source_name=str(data.get("source_name", "")),
            source_url=str(data.get("source_url", "")),
            evidence_quote=str(data.get("evidence_quote", "")),
            extraction_method=str(data.get("extraction_method", "manual")),
            review_status=str(data.get("review_status", "unreviewed")),
            use_policy=str(data.get("use_policy", "candidate_signal")),
            updated_at=str(data.get("updated_at", now_utc())),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_fact_id(fact_type: str, subject_ids: list[str], claim: dict[str, Any], source_name: str) -> str:
    basis = f"{fact_type}|{'|'.join(sorted(subject_ids))}|{claim}|{source_name}"
    return f"fact_{stable_hash(basis)}"
