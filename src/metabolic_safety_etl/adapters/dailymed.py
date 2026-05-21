from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from ..schemas import EvidenceFact, now_utc, slugify, stable_hash

DAILYMED_SPLS_ENDPOINT = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
DAILYMED_SOURCE_URL = "https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm"


def fetch_dailymed_facts(term: str, limit: int = 10, timeout: int = 30) -> list[EvidenceFact]:
    params = urlencode({"drug_name": term, "pagesize": str(limit)})
    url = f"{DAILYMED_SPLS_ENDPOINT}?{params}"
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    data = payload.get("data") or []
    facts: list[EvidenceFact] = []
    for item in data[:limit]:
        name = item.get("title") or item.get("drug_name") or term
        setid = item.get("setid")
        subject_id = slugify(term)
        identifiers = {
            "dailymed_setid": setid,
            "spl_version": item.get("spl_version"),
            "published_date": item.get("published_date"),
        }
        facts.append(
            EvidenceFact(
                fact_id=f"dailymed_label_{stable_hash(str(setid) + name)}",
                fact_type="source_text",
                subject_ids=[subject_id],
                claim={
                    "section": "label_metadata",
                    "text": name,
                    "identifiers": identifiers,
                },
                confidence="High",
                source_tier="Regulatory",
                source_name="DailyMed SPL",
                source_url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}" if setid else DAILYMED_SOURCE_URL,
                evidence_quote="DailyMed SPL metadata. Full SPL XML parsing should convert label sections into reviewed facts.",
                extraction_method="api",
                review_status="unreviewed",
                use_policy="evidence_source",
                updated_at=now_utc(),
            )
        )
    return facts
