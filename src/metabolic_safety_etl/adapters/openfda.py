from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from ..schemas import EvidenceFact, now_utc, slugify, stable_hash

OPENFDA_LABEL_ENDPOINT = "https://api.fda.gov/drug/label.json"
OPENFDA_EVENT_ENDPOINT = "https://api.fda.gov/drug/event.json"
SEVERE_FAERS_REACTIONS = {
    "DEATH",
    "RESPIRATORY DEPRESSION",
    "COMA",
    "LOSS OF CONSCIOUSNESS",
    "SEROTONIN SYNDROME",
    "QT PROLONGATION",
    "TORSADES DE POINTES",
    "OVERDOSE",
}


def fetch_label_facts(term: str, limit: int = 5, timeout: int = 30) -> list[EvidenceFact]:
    """Fetch semi-structured FDA label sections as source_text facts.

    This adapter intentionally does not turn label text into final DDI rules.
    Downstream extraction or manual review should convert source_text into PK/DDI/DFI facts.
    """
    safe_term = term.strip()
    search = f'openfda.generic_name:"{safe_term}" OR openfda.brand_name:"{safe_term}" OR openfda.substance_name:"{safe_term}"'
    params = urlencode({"search": search, "limit": str(limit)})
    url = f"{OPENFDA_LABEL_ENDPOINT}?{params}"
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    facts: list[EvidenceFact] = []
    for index, result in enumerate(payload.get("results", [])):
        openfda = result.get("openfda", {})
        subject_name = _first(openfda.get("generic_name")) or _first(openfda.get("substance_name")) or safe_term
        subject_id = slugify(subject_name)
        identifiers = {
            "rxcui": openfda.get("rxcui", []),
            "unii": openfda.get("unii", []),
            "spl_id": _first(openfda.get("spl_id")),
            "set_id": result.get("set_id"),
        }
        facts.append(
            EvidenceFact(
                fact_id=f"openfda_identity_{stable_hash(subject_id + str(index))}",
                fact_type="substance_identity",
                subject_ids=[subject_id],
                claim={
                    "name_en": subject_name,
                    "category": "DrugLabel",
                    "identifiers": identifiers,
                },
                confidence="High",
                source_tier="Regulatory",
                source_name="openFDA drug label",
                source_url=url,
                evidence_quote="Structured openFDA label metadata.",
                extraction_method="api",
                review_status="machine_checked",
                use_policy="evidence_source",
                updated_at=now_utc(),
            )
        )
        for section in ("boxed_warning", "warnings", "dosage_and_administration", "dosage_forms_and_strengths", "overdosage", "drug_interactions", "pharmacokinetics", "clinical_pharmacology"):
            text_values = result.get(section) or []
            if not text_values:
                continue
            joined = "\n".join(text_values)
            facts.append(
                EvidenceFact(
                    fact_id=f"openfda_{section}_{stable_hash(subject_id + joined[:500])}",
                    fact_type="source_text",
                    subject_ids=[subject_id],
                    claim={"section": section, "text": joined},
                    confidence="High",
                    source_tier="Regulatory",
                    source_name="openFDA drug label",
                    source_url=url,
                    evidence_quote=joined[:600],
                    extraction_method="api",
                    review_status="unreviewed",
                    use_policy="evidence_source",
                    updated_at=now_utc(),
                )
            )
    return facts


def fetch_event_signal_facts(term: str, limit: int = 5, timeout: int = 30) -> list[EvidenceFact]:
    """Fetch FAERS adverse-event report counts as low-confidence signal facts.

    The openFDA drug/event endpoint contains spontaneous adverse event reports.
    These counts are not causality, incidence, or confirmed interaction evidence.
    They are only suitable for pharmacovigilance candidate hints.
    """
    safe_term = term.strip()
    if not safe_term:
        return []
    limit = max(1, min(int(limit), 25))
    search = (
        f'patient.drug.openfda.generic_name:"{safe_term}" OR '
        f'patient.drug.openfda.brand_name:"{safe_term}" OR '
        f'patient.drug.medicinalproduct:"{safe_term}"'
    )
    params = urlencode({
        "search": search,
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": str(limit),
    })
    url = f"{OPENFDA_EVENT_ENDPOINT}?{params}"
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return []
        raise

    subject_id = slugify(safe_term)
    facts: list[EvidenceFact] = []
    for index, row in enumerate(payload.get("results", [])):
        reaction = str(row.get("term") or "").strip()
        if not reaction:
            continue
        count = int(row.get("count") or 0)
        reaction_label = reaction_title(reaction)
        facts.append(
            EvidenceFact(
                fact_id=f"openfda_event_{stable_hash(subject_id + reaction + str(index))}",
                fact_type="adverse_event_signal",
                subject_ids=[subject_id],
                claim={
                    "reaction": reaction,
                    "reaction_label_zh": reaction_label,
                    "count": count,
                    "query_term": safe_term,
                    "signal_kind": "faers_report_count",
                    "limitations": "spontaneous_reports_not_causal",
                },
                risk_level="Moderate" if reaction.upper() in SEVERE_FAERS_REACTIONS else "Minor",
                confidence="Low",
                source_tier="Signal",
                source_name="openFDA FAERS adverse event",
                source_url=url,
                evidence_quote=f"FAERS reports mentioning {safe_term}: {reaction} count={count}. Not causal.",
                extraction_method="api_count",
                review_status="unreviewed",
                use_policy="candidate_signal",
                updated_at=now_utc(),
            )
        )
    return facts


def reaction_title(value: str) -> str:
    mapping = {
        "DRUG INEFFECTIVE": "药物效果不足",
        "FATIGUE": "疲劳",
        "NAUSEA": "恶心",
        "HEADACHE": "头痛",
        "DIZZINESS": "头晕",
        "VOMITING": "呕吐",
        "DIARRHOEA": "腹泻",
        "SOMNOLENCE": "嗜睡",
        "ANXIETY": "焦虑",
        "INSOMNIA": "失眠",
        "RASH": "皮疹",
        "PRURITUS": "瘙痒",
        "DYSPNOEA": "呼吸困难",
        "CHEST PAIN": "胸痛",
        "PALPITATIONS": "心悸",
        "TACHYCARDIA": "心动过速",
        "HYPOTENSION": "低血压",
        "HYPERTENSION": "高血压",
        "LOSS OF CONSCIOUSNESS": "意识丧失",
        "SYNCOPE": "晕厥",
        "OVERDOSE": "过量",
        "DEATH": "死亡",
        "RESPIRATORY DEPRESSION": "呼吸抑制",
        "SEROTONIN SYNDROME": "血清素综合征",
        "QT PROLONGATION": "QT 间期延长",
    }
    upper = value.strip().upper()
    return mapping.get(upper, value.title())


def _first(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None