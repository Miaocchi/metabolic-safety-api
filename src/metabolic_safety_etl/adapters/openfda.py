from __future__ import annotations

import json
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from ..schemas import EvidenceFact, now_utc, slugify, stable_hash

OPENFDA_LABEL_ENDPOINT = "https://api.fda.gov/drug/label.json"


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


def _first(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None
