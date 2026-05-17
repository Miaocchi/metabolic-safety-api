from __future__ import annotations

import json
from urllib.request import Request, urlopen

from ..schemas import EvidenceFact, now_utc, slugify, stable_hash

GRAPHQL_ENDPOINT = "https://api.psychonautwiki.org"

QUERY = """
query FetchSubstances($limit: Int!, $offset: Int!) {
  substances(limit: $limit, offset: $offset) {
    name
    summary
    class { chemical psychoactive }
    roas {
      name
      dose {
        units
        threshold
        light { min max }
        common { min max }
        strong { min max }
        heavy
      }
      duration {
        onset { min max units }
        peak { min max units }
        offset { min max units }
        total { min max units }
      }
      bioavailability { min max }
    }
  }
}
"""


def fetch_substance_facts(limit: int = 25, offset: int = 0) -> list[EvidenceFact]:
    body = json.dumps({"query": QUERY, "variables": {"limit": limit, "offset": offset}}).encode("utf-8")
    request = Request(GRAPHQL_ENDPOINT, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])

    facts: list[EvidenceFact] = []
    for item in payload.get("data", {}).get("substances", []):
        subject_id = slugify(item.get("name") or "unknown")
        classes = item.get("class") or {}
        facts.append(
            EvidenceFact(
                fact_id=f"pw_identity_{stable_hash(subject_id)}",
                fact_type="substance_identity",
                subject_ids=[subject_id],
                claim={
                    "name_en": item.get("name"),
                    "category": classes.get("psychoactive") or classes.get("chemical"),
                    "identifiers": {"psychonautwiki_name": item.get("name")},
                },
                confidence="Low",
                source_tier="Community",
                source_name="PsychonautWiki GraphQL",
                source_url=GRAPHQL_ENDPOINT,
                evidence_quote=(item.get("summary") or "")[:600],
                extraction_method="api",
                review_status="unreviewed",
                use_policy="candidate_signal",
                updated_at=now_utc(),
            )
        )
        for roa in item.get("roas") or []:
            duration = roa.get("duration") or {}
            total = duration.get("total") or {}
            onset = duration.get("onset") or {}
            common = ((roa.get("dose") or {}).get("common") or {})
            facts.append(
                EvidenceFact(
                    fact_id=f"pw_roa_{stable_hash(subject_id + str(roa.get('name')))}",
                    fact_type="pharmacokinetics",
                    subject_ids=[subject_id],
                    claim={
                        "route": roa.get("name"),
                        "onset_minutes": _range_mean(onset),
                        "duration_minutes": _range_mean(total),
                        "community_common_dose": _range_mean(common),
                        "community_dose_units": (roa.get("dose") or {}).get("units"),
                        "bioavailability": roa.get("bioavailability"),
                    },
                    confidence="Low",
                    source_tier="Community",
                    source_name="PsychonautWiki GraphQL",
                    source_url=GRAPHQL_ENDPOINT,
                    evidence_quote="Community maintained ROA/dose/duration field.",
                    extraction_method="api",
                    review_status="unreviewed",
                    use_policy="candidate_signal",
                    updated_at=now_utc(),
                )
            )
    return facts


def _range_mean(value: object) -> float | None:
    if not isinstance(value, dict):
        return None
    nums = [value.get("min"), value.get("max")]
    nums = [float(num) for num in nums if isinstance(num, (int, float))]
    if not nums:
        return None
    return sum(nums) / len(nums)
