from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from ..schemas import EvidenceFact, now_utc, slugify, stable_hash

RXNAV_DRUGS_ENDPOINT = "https://rxnav.nlm.nih.gov/REST/drugs.json"
RXNAV_SOURCE_URL = "https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html"


def fetch_rxnav_facts(term: str, limit: int = 25, timeout: int = 30) -> list[EvidenceFact]:
    params = urlencode({"name": term})
    url = f"{RXNAV_DRUGS_ENDPOINT}?{params}"
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    facts: list[EvidenceFact] = []
    seen: set[str] = set()
    for group in payload.get("drugGroup", {}).get("conceptGroup", []) or []:
        tty = group.get("tty")
        for concept in group.get("conceptProperties", []) or []:
            name = concept.get("name") or concept.get("synonym")
            rxcui = concept.get("rxcui")
            if not name or not rxcui or rxcui in seen:
                continue
            seen.add(rxcui)
            subject_id = slugify(name)
            facts.append(
                EvidenceFact(
                    fact_id=f"rxnav_identity_{stable_hash(rxcui)}",
                    fact_type="substance_identity",
                    subject_ids=[subject_id],
                    claim={
                        "name_en": name,
                        "category": "RxNorm concept",
                        "identifiers": {
                            "rxcui": rxcui,
                            "rxnorm_tty": tty,
                            "rxnorm_synonym": concept.get("synonym"),
                        },
                    },
                    confidence="High",
                    source_tier="Regulatory",
                    source_name="RxNav / RxNorm",
                    source_url=RXNAV_SOURCE_URL,
                    evidence_quote="RxNorm normalized clinical drug concept from NLM RxNav API.",
                    extraction_method="api",
                    review_status="machine_checked",
                    use_policy="mapping_only",
                    updated_at=now_utc(),
                )
            )
            if len(facts) >= limit:
                return facts
    return facts
