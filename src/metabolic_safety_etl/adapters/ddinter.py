from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from ..schemas import EvidenceFact, RISK_RANK, now_utc, normalize_risk, slugify, stable_hash

DDINTER_DOWNLOAD_URL = "https://ddinter2.scbdd.com/download/"


def load_zh_aliases(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not path.exists():
        return {}
    aliases: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name_en = (row.get("name_en") or "").strip()
            name_zh = (row.get("name_zh") or "").strip()
            extra = (row.get("aliases") or "").strip()
            if not name_en or not name_zh:
                continue
            aliases[slugify(name_en)] = {"name_zh": name_zh, "aliases": extra}
    return aliases


def load_ddinter_csv_facts(
    paths: Iterable[Path],
    max_interactions: int | None = None,
    zh_aliases_path: Path | None = None,
) -> list[EvidenceFact]:
    """Convert DDInter 2.0 downloadable CSV files into normalized evidence facts.

    DDInter public CSV contains pair IDs, names and severity level. Chinese names are
    added from a local override table because DDInter itself is English-first.
    """
    zh_aliases = load_zh_aliases(zh_aliases_path)
    drugs: dict[str, dict[str, str]] = {}
    pair_levels: dict[tuple[str, str], set[str]] = {}
    pair_names: dict[tuple[str, str], tuple[str, str]] = {}

    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                id_a = (row.get("DDInterID_A") or "").strip()
                id_b = (row.get("DDInterID_B") or "").strip()
                name_a = (row.get("Drug_A") or "").strip()
                name_b = (row.get("Drug_B") or "").strip()
                if not id_a or not id_b or not name_a or not name_b:
                    continue
                subject_a = slugify(name_a)
                subject_b = slugify(name_b)
                drugs[subject_a] = {"name": name_a, "ddinter_id": id_a}
                drugs[subject_b] = {"name": name_b, "ddinter_id": id_b}
                pair = tuple(sorted([subject_a, subject_b]))
                pair_levels.setdefault(pair, set()).add(normalize_risk(row.get("Level")))
                pair_names[pair] = (name_a, name_b)

    facts: list[EvidenceFact] = []
    timestamp = now_utc()
    for subject_id, drug in sorted(drugs.items()):
        alias = zh_aliases.get(subject_id, {})
        identifiers = {"ddinter_id": drug["ddinter_id"]}
        if alias.get("aliases"):
            identifiers["aliases"] = alias["aliases"]
        claim = {
            "name_en": drug["name"],
            "category": "Drug",
            "identifiers": identifiers,
        }
        if alias.get("name_zh"):
            claim["name_zh"] = alias["name_zh"]
        facts.append(
            EvidenceFact(
                fact_id=f"ddinter_identity_{stable_hash(subject_id)}",
                fact_type="substance_identity",
                subject_ids=[subject_id],
                claim=claim,
                risk_level="Unknown",
                confidence="Medium" if alias.get("name_zh") else "Low",
                source_tier="CuratedDB",
                source_name="DDInter 2.0 + local zh aliases",
                source_url=DDINTER_DOWNLOAD_URL,
                evidence_quote="DDInter 2.0 downloadable CSV drug identifier/name field; Chinese name from local override when present.",
                extraction_method="csv",
                review_status="machine_checked",
                use_policy="evidence_source",
                updated_at=timestamp,
            )
        )

    count = 0
    for pair, levels in sorted(pair_levels.items()):
        if max_interactions is not None and count >= max_interactions:
            break
        known_levels = [level for level in levels if level != "Unknown"]
        chosen = max(known_levels or ["Unknown"], key=lambda level: RISK_RANK.get(level, -1))
        confidence = "Medium" if chosen != "Unknown" else "Unknown"
        name_a, name_b = pair_names[pair]
        facts.append(
            EvidenceFact(
                fact_id=f"ddinter_interaction_{stable_hash('|'.join(pair))}",
                fact_type="drug_interaction",
                subject_ids=list(pair),
                claim={
                    "mechanism": None,
                    "note": f"DDInter 2.0 severity={chosen}; raw_levels={','.join(sorted(levels))}; labels={name_a} / {name_b}",
                },
                risk_level=chosen,
                confidence=confidence,
                source_tier="CuratedDB",
                source_name="DDInter 2.0",
                source_url=DDINTER_DOWNLOAD_URL,
                evidence_quote=f"DDInter 2.0 CSV pair level: {chosen}",
                extraction_method="csv",
                review_status="machine_checked",
                use_policy="core_rule" if chosen != "Unknown" else "candidate_signal",
                updated_at=timestamp,
            )
        )
        count += 1
    return facts


def find_ddinter_csvs(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("ddinter_code_*.csv")) or sorted(input_dir.glob("*.csv"))
