from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from ..schemas import EvidenceFact, now_utc, slugify, stable_hash

CHEMBL_MOLECULE_SEARCH = "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json"
CHEMBL_SOURCE_URL = "https://www.ebi.ac.uk/chembl/"


def fetch_chembl_facts(term: str, limit: int = 10, timeout: int = 30) -> list[EvidenceFact]:
    params = urlencode({"q": term, "limit": str(limit)})
    url = f"{CHEMBL_MOLECULE_SEARCH}?{params}"
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    facts: list[EvidenceFact] = []
    for molecule in payload.get("molecules", []) or []:
        chembl_id = molecule.get("molecule_chembl_id")
        name = molecule.get("pref_name") or molecule.get("molecule_synonyms", [{}])[0].get("molecule_synonym")
        if not chembl_id or not name:
            continue
        subject_id = slugify(name)
        props = molecule.get("molecule_properties") or {}
        alogp = _to_float(props.get("alogp"))
        claim = {
            "name_en": name.title() if name.isupper() else name,
            "category": molecule.get("molecule_type") or "ChEMBL molecule",
            "solubility": "Lipophilic" if alogp is not None and alogp >= 2 else None,
            "identifiers": {
                "chembl_id": chembl_id,
                "molecule_type": molecule.get("molecule_type"),
                "max_phase": molecule.get("max_phase"),
                "full_mwt": props.get("full_mwt"),
                "alogp": props.get("alogp"),
            },
        }
        facts.append(
            EvidenceFact(
                fact_id=f"chembl_identity_{stable_hash(chembl_id)}",
                fact_type="substance_identity",
                subject_ids=[subject_id],
                claim=claim,
                confidence="Medium",
                source_tier="CuratedDB",
                source_name="ChEMBL",
                source_url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/",
                evidence_quote="ChEMBL molecule search result with curated chemical identifiers and properties.",
                extraction_method="api",
                review_status="machine_checked",
                use_policy="evidence_source",
                updated_at=now_utc(),
            )
        )
    return facts


def _to_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
