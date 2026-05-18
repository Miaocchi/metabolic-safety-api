from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import shutil
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import zipfile
from typing import Any, Iterable, Iterator

from .adapters.label_bulk import fetch_dailymed_label_manifest, fetch_openfda_label_manifest
from .dose_rules import extract_dose_candidate_facts
from .io import read_json
from .schemas import EvidenceFact, now_utc, slugify, stable_hash

OPENFDA_SECTIONS = ("pharmacokinetics", "clinical_pharmacology", "drug_interactions", "overdosage", "warnings", "boxed_warning")
OPENFDA_DOSE_SECTIONS = ("dosage_and_administration", "dosage_forms_and_strengths", "overdosage")
OPENFDA_EFFECT_SECTIONS = ("mechanism_of_action", "pharmacodynamics")
DAILYMED_SECTION_HINTS = ("PHARMACOKINETICS", "CLINICAL PHARMACOLOGY", "DRUG INTERACTIONS", "OVERDOSAGE", "WARNINGS", "BOXED WARNING")
DAILYMED_DOSE_SECTION_HINTS = ("DOSAGE AND ADMINISTRATION", "DOSAGE FORMS AND STRENGTHS", "OVERDOSAGE")
DAILYMED_EFFECT_SECTION_HINTS = ("INDICATIONS AND USAGE", "PURPOSE", "MECHANISM OF ACTION", "PHARMACODYNAMICS")
CYP_RE = re.compile(r"\bCYP(?:1A2|2A6|2B6|2C8|2C9|2C19|2D6|2E1|3A4|3A5|3A7|4A11)\b", re.I)
HALF_LIFE_RE = re.compile(
    r"(?:half[-\s]?life|t\s*1\s*/\s*2|t1/2|terminal\s+half[-\s]?life)"
    r"[^.;\n]{0,140}?"
    r"(?P<first>\d+(?:\.\d+)?)"
    r"(?:\s*(?:-|to)\s*(?P<second>\d+(?:\.\d+)?))?"
    r"\s*(?P<unit>hours?|hrs?|h|minutes?|mins?|days?|d)\b",
    re.I,
)


def load_raw_source_facts(raw_dir: Path, max_records_per_source: int = 100_000, max_files_per_source: int = 0, workers: int = 0) -> tuple[list[EvidenceFact], dict[str, dict[str, Any]]]:
    raw_dir = Path(raw_dir)
    loaders = {
        "openfda_label": lambda: load_openfda_bulk_facts(raw_dir / "openfda_label", max_records_per_source, max_files_per_source),
        "dailymed": lambda: load_dailymed_bulk_facts(raw_dir / "dailymed_spl", max_records_per_source, max_files_per_source),
        "chembl": lambda: load_chembl_bulk_facts(raw_dir / "chembl", max_records_per_source),
        "foodrugs": lambda: load_foodrugs_bulk_facts(raw_dir / "foodrugs", max_records_per_source, max_files_per_source),
        "onsides": lambda: load_onsides_bulk_facts(raw_dir / "onsides", max_records_per_source, max_files_per_source),
        "pharmgkb": lambda: load_pharmgkb_bulk_facts(raw_dir / "pharmgkb", max_records_per_source, max_files_per_source),
    }
    facts: list[EvidenceFact] = []
    summary: dict[str, dict[str, Any]] = {}

    def run_loader(key: str) -> tuple[str, list[EvidenceFact]]:
        return key, loaders[key]()

    max_workers = workers if workers > 0 else min(len(loaders), 6)
    if max_workers <= 1:
        for key in loaders:
            try:
                _, batch = run_loader(key)
                facts.extend(batch)
                summary[key] = {"facts": len(batch), "status": "loaded" if batch else "no_local_files"}
            except Exception as exc:
                summary[key] = {"facts": 0, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
        return dedupe_fact_objects(facts), summary

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_key = {executor.submit(run_loader, key): key for key in loaders}
        for future in as_completed(future_by_key):
            key = future_by_key[future]
            try:
                _, batch = future.result()
                facts.extend(batch)
                summary[key] = {"facts": len(batch), "status": "loaded" if batch else "no_local_files"}
            except Exception as exc:
                summary[key] = {"facts": 0, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return dedupe_fact_objects(facts), dict(sorted(summary.items()))


def load_openfda_bulk_facts(source_dir: Path, max_records: int = 100_000, max_files: int = 0) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen = 0
    for path in select_files(iter_files(source_dir), max_files):
        if path.suffix == ".part" or not zipfile.is_zipfile(path):
            continue
        for result in iter_openfda_results(path):
            facts.extend(openfda_result_facts(result))
            seen += 1
            if max_records and seen >= max_records:
                return dedupe_fact_objects(facts)
    return dedupe_fact_objects(facts)


def iter_openfda_results(path: Path) -> Iterator[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".json"):
                with archive.open(name) as handle:
                    yield from iter_results_array(handle)


def iter_results_array(binary_handle, chunk_size: int = 1024 * 1024) -> Iterator[dict[str, Any]]:
    reader = io.TextIOWrapper(binary_handle, encoding="utf-8", errors="replace")
    buffer = ""
    while True:
        chunk = reader.read(chunk_size)
        if not chunk:
            return
        buffer += chunk
        match = re.search(r'"results"\s*:\s*\[', buffer)
        if match:
            buffer = buffer[match.end():]
            break
        buffer = buffer[-128:]
    index = 0
    depth = 0
    in_string = False
    escape = False
    obj_chars: list[str] = []
    while True:
        if index >= len(buffer):
            chunk = reader.read(chunk_size)
            if not chunk:
                return
            buffer = chunk
            index = 0
            continue
        char = buffer[index]
        index += 1
        if depth == 0:
            if char == "{":
                depth = 1
                in_string = False
                escape = False
                obj_chars = [char]
            elif char == "]":
                return
            continue
        obj_chars.append(char)
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads("".join(obj_chars))
                    except json.JSONDecodeError:
                        pass
                    obj_chars = []


def openfda_result_facts(result: dict[str, Any]) -> list[EvidenceFact]:
    openfda = result.get("openfda") if isinstance(result.get("openfda"), dict) else {}
    names = list_values(openfda.get("generic_name")) or list_values(openfda.get("substance_name")) or list_values(openfda.get("brand_name"))
    subject_name = names[0] if names else str(result.get("set_id") or "unknown_label")
    subject_id = slugify(subject_name)
    aliases = sorted(set(list_values(openfda.get("brand_name")) + list_values(openfda.get("substance_name")) + names), key=str.lower)
    url = "https://open.fda.gov/apis/drug/label/"
    basis = str(result.get("set_id") or result.get("id") or subject_name)
    facts = [
        EvidenceFact(
            fact_id=f"openfda_bulk_identity_{stable_hash(basis + subject_id)}",
            fact_type="substance_identity",
            subject_ids=[subject_id],
            claim={"name_en": subject_name, "category": "DrugLabel", "identifiers": {"aliases": aliases[:30], "rxcui": list_values(openfda.get("rxcui"))[:12], "unii": list_values(openfda.get("unii"))[:12], "spl_id": first_value(openfda.get("spl_id")), "set_id": result.get("set_id")}},
            confidence="High",
            source_tier="Regulatory",
            source_name="openFDA drug label bulk",
            source_url=url,
            evidence_quote="Bulk openFDA label metadata.",
            extraction_method="bulk_json",
            review_status="machine_checked",
            use_policy="evidence_source",
            updated_at=now_utc(),
        )
    ]
    effect_sections = [(section, joined_sections(result, (section,))) for section in OPENFDA_EFFECT_SECTIONS]
    clinical_pharmacology = joined_sections(result, ("clinical_pharmacology",))
    if re.search(r"mechanism\s+of\s+action|pharmacodynamic", clinical_pharmacology, re.I):
        effect_sections.append(("clinical_pharmacology", clinical_pharmacology))
    facts.extend(drug_effect_facts(subject_id, effect_sections, "openFDA drug label bulk", url, "bulk_json"))
    facts.extend(pk_and_enzyme_facts(subject_id, joined_sections(result, OPENFDA_SECTIONS), "openFDA drug label bulk", url, "bulk_json"))
    overdose_text = joined_sections(result, ("overdosage",))
    if overdose_text:
        facts.append(overdose_warning_fact(subject_id, overdose_text, "openFDA drug label bulk", url, "bulk_json", "overdose"))
    for section in OPENFDA_DOSE_SECTIONS:
        section_text = joined_sections(result, (section,))
        if section_text:
            facts.extend(extract_dose_candidate_facts(subject_id, section_text, "openFDA drug label bulk", url, "bulk_json", section=section))
    return facts


def load_dailymed_bulk_facts(source_dir: Path, max_records: int = 100_000, max_files: int = 0) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen = 0
    for path in select_files(iter_files(source_dir), max_files):
        if path.suffix == ".part" or not zipfile.is_zipfile(path):
            continue
        for xml_bytes in iter_dailymed_xml(path):
            try:
                facts.extend(dailymed_xml_facts(xml_bytes))
            except Exception:
                continue
            seen += 1
            if max_records and seen >= max_records:
                return dedupe_fact_objects(facts)
    return dedupe_fact_objects(facts)


def iter_dailymed_xml(outer_path: Path) -> Iterator[bytes]:
    with zipfile.ZipFile(outer_path) as outer:
        for member in outer.namelist():
            lower = member.lower()
            if lower.endswith(".xml"):
                yield outer.read(member)
            elif lower.endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(outer.read(member))) as inner:
                        for inner_name in inner.namelist():
                            if inner_name.lower().endswith(".xml"):
                                yield inner.read(inner_name)
                except Exception:
                    continue


def dailymed_xml_facts(xml_bytes: bytes) -> list[EvidenceFact]:
    root = ET.fromstring(xml_bytes)
    title = clean_label_title(first_text(root, "title") or "DailyMed SPL")
    subject_id = slugify(title)
    setid = first_attr(root, "setId", "root")
    url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}" if setid else "https://dailymed.nlm.nih.gov/"
    facts = [
        EvidenceFact(
            fact_id=f"dailymed_bulk_identity_{stable_hash(str(setid) + subject_id)}",
            fact_type="substance_identity",
            subject_ids=[subject_id],
            claim={"name_en": title, "category": "DrugLabel", "identifiers": {"dailymed_setid": setid}},
            confidence="High",
            source_tier="Regulatory",
            source_name="DailyMed SPL bulk",
            source_url=url,
            evidence_quote="Bulk DailyMed SPL metadata.",
            extraction_method="bulk_spl_xml",
            review_status="machine_checked",
            use_policy="evidence_source",
            updated_at=now_utc(),
        )
    ]
    sections = list(spl_sections(root))
    effect_sections = [(section_title, text) for section_title, text in sections if matches_any(section_title, DAILYMED_EFFECT_SECTION_HINTS)]
    facts.extend(drug_effect_facts(subject_id, effect_sections, "DailyMed SPL bulk", url, "bulk_spl_xml"))
    text = "\n".join(text for section_title, text in sections if matches_any(section_title, DAILYMED_SECTION_HINTS))
    facts.extend(pk_and_enzyme_facts(subject_id, text, "DailyMed SPL bulk", url, "bulk_spl_xml"))
    overdose_text = "\n".join(text for section_title, text in sections if matches_any(section_title, ("OVERDOSAGE",)))
    if overdose_text:
        facts.append(overdose_warning_fact(subject_id, overdose_text, "DailyMed SPL bulk", url, "bulk_spl_xml", "overdose"))
    dose_text = "\n".join(text for section_title, text in sections if matches_any(section_title, DAILYMED_DOSE_SECTION_HINTS))
    if dose_text:
        facts.extend(extract_dose_candidate_facts(subject_id, dose_text, "DailyMed SPL bulk", url, "bulk_spl_xml", section="dosage"))
    return facts


def drug_effect_facts(subject_id: str, sections: Iterable[tuple[str, str]], source_name: str, source_url: str, method: str) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    for section, text in sections:
        clean = squash(text)
        if not clean:
            continue
        section_name = squash(section or "drug_effect") or "drug_effect"
        lower_section = section_name.lower()
        claim: dict[str, Any] = {"section": section_name, "effect_text": clean[:2500]}
        if "mechanism" in lower_section:
            claim["mechanism_of_action"] = clean[:1600]
        confidence = "High" if "mechanism" in lower_section or "pharmacodynamic" in lower_section else "Medium"
        facts.append(EvidenceFact(
            fact_id=f"{slugify(source_name)}_effect_{stable_hash(subject_id + section_name + clean[:1000])}",
            fact_type="drug_effect",
            subject_ids=[subject_id],
            claim=claim,
            confidence=confidence,
            source_tier="Regulatory",
            source_name=source_name,
            source_url=source_url,
            evidence_quote=clean[:1200],
            extraction_method=f"{method}_drug_effect",
            review_status="unreviewed",
            use_policy="candidate_signal",
            updated_at=now_utc(),
        ))
    return facts


def overdose_warning_fact(subject_id: str, text: str, source_name: str, source_url: str, method: str, section: str) -> EvidenceFact:
    clean = squash(text)
    return EvidenceFact(
        fact_id=f"{slugify(source_name)}_overdose_{stable_hash(subject_id + clean[:1000])}",
        fact_type="overdose_warning",
        subject_ids=[subject_id],
        claim={"overdose_text": clean[:2500], "section": section},
        risk_level="Major",
        confidence="Medium",
        source_tier="Regulatory",
        source_name=source_name,
        source_url=source_url,
        evidence_quote=clean[:1200],
        extraction_method=f"{method}_overdose_warning",
        review_status="unreviewed",
        use_policy="candidate_signal",
        updated_at=now_utc(),
    )


def pk_and_enzyme_facts(subject_id: str, text: str, source_name: str, source_url: str, method: str) -> list[EvidenceFact]:
    if not text:
        return []
    facts: list[EvidenceFact] = []
    half_life = extract_half_life_hours(text)
    if half_life is not None:
        facts.append(EvidenceFact(
            fact_id=f"{slugify(source_name)}_pk_{stable_hash(subject_id + str(half_life))}",
            fact_type="pharmacokinetics",
            subject_ids=[subject_id],
            claim={"half_life_hours": half_life},
            confidence="Medium",
            source_tier="Regulatory",
            source_name=source_name,
            source_url=source_url,
            evidence_quote=snippet_around(text, "half", 500),
            extraction_method=method,
            review_status="unreviewed",
            use_policy="candidate_signal",
            updated_at=now_utc(),
        ))
    for enzyme, relation, snippet in extract_cyp_relations(text)[:8]:
        facts.append(EvidenceFact(
            fact_id=f"{slugify(source_name)}_{subject_id}_{enzyme}_{relation}_{stable_hash(snippet)}",
            fact_type="enzyme_relation",
            subject_ids=[subject_id],
            claim={"tag": f"{enzyme}_{relation}", "context": snippet},
            confidence="Low" if relation == "mentioned" else "Medium",
            source_tier="Regulatory",
            source_name=source_name,
            source_url=source_url,
            evidence_quote=snippet,
            extraction_method=method,
            review_status="unreviewed",
            use_policy="candidate_signal",
            updated_at=now_utc(),
        ))
    return facts


def load_pharmgkb_bulk_facts(source_dir: Path, max_records: int = 100_000, max_files: int = 0) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    count = 0
    for name, rows in iter_tabular_source(source_dir, max_files=max_files):
        lower_name = name.lower()
        if not any(token in lower_name for token in ("drug", "chemical", "guideline", "label")):
            continue
        for row in rows:
            drug = pick_column(row, ("Name", "Chemical", "Drug", "Drug Name", "Object Name"))
            if not drug:
                continue
            subject_id = slugify(drug)
            aliases = split_aliases(pick_column(row, ("Generic Names", "Trade Names", "Alternate Names", "Synonyms")))
            facts.append(EvidenceFact(
                fact_id=f"pharmgkb_identity_{stable_hash(subject_id + str(row))}",
                fact_type="substance_identity",
                subject_ids=[subject_id],
                claim={"name_en": drug, "category": pick_column(row, ("Type", "Entity Type")) or "PharmGKB chemical", "identifiers": {"aliases": aliases, "pharmgkb_id": pick_column(row, ("PharmGKB Accession Id", "PharmGKB ID"))}},
                confidence="High",
                source_tier="Guideline",
                source_name="PharmGKB / ClinPGx bulk",
                source_url="https://api.pharmgkb.org/",
                evidence_quote="Bulk PharmGKB row.",
                extraction_method="bulk_tsv",
                review_status="machine_checked",
                use_policy="evidence_source",
                updated_at=now_utc(),
            ))
            count += 1
            if max_records and count >= max_records:
                return dedupe_fact_objects(facts)
    return dedupe_fact_objects(facts)


def load_onsides_bulk_facts(source_dir: Path, max_records: int = 100_000, max_files: int = 0) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    count = 0
    for name, rows in iter_tabular_source(source_dir, max_files=max_files):
        if not any(token in name.lower() for token in ("side", "offsides", "onsides", "adverse", "event")):
            continue
        for row in rows:
            drug = pick_column(row, ("drug", "drug_name", "concept_name", "ingredient", "drug_concept_name", "name"))
            event = pick_column(row, ("adverse_event", "event", "condition", "condition_name", "meddra_name", "side_effect"))
            if not drug or not event:
                continue
            subject_id = slugify(drug)
            facts.append(identity_fact(subject_id, drug, "Adverse event signal", "OnSIDES bulk", "Signal", "https://github.com/tatonetti-lab/onsides", "bulk_csv"))
            facts.append(EvidenceFact(
                fact_id=f"onsides_adverse_{stable_hash(subject_id + event + str(row))}",
                fact_type="adverse_event",
                subject_ids=[subject_id],
                claim={"event": event, "raw": compact_row(row, 12)},
                confidence="Low",
                source_tier="Signal",
                source_name="OnSIDES bulk",
                source_url="https://github.com/tatonetti-lab/onsides",
                evidence_quote=event[:600],
                extraction_method="bulk_csv",
                review_status="unreviewed",
                use_policy="candidate_signal",
                updated_at=now_utc(),
            ))
            count += 1
            if max_records and count >= max_records:
                return dedupe_fact_objects(facts)
    return dedupe_fact_objects(facts)


def load_foodrugs_bulk_facts(source_dir: Path, max_records: int = 100_000, max_files: int = 0) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    count = 0
    for name, rows in iter_tabular_source(source_dir, max_files=max_files):
        if not any(token in name.lower() for token in ("food", "drug", "interaction", "dfi")):
            continue
        for row in rows:
            drug = pick_column(row, ("drug", "drug_name", "compound", "chemical", "drugbank_name"))
            food = pick_column(row, ("food", "food_name", "ingredient", "nutrient", "bioactive"))
            if not drug or not food:
                continue
            drug_id = slugify(drug)
            food_id = slugify(food)
            facts.append(identity_fact(drug_id, drug, "Drug", "FooDrugs bulk", "Signal", "https://zenodo.org/records/8192515", "bulk_tabular"))
            facts.append(identity_fact(food_id, food, "Food/Bioactive", "FooDrugs bulk", "Signal", "https://zenodo.org/records/8192515", "bulk_tabular"))
            facts.append(EvidenceFact(
                fact_id=f"foodrugs_pair_{stable_hash(drug + food + str(row))}",
                fact_type="food_interaction",
                subject_ids=[drug_id, food_id],
                claim={"mechanism": pick_column(row, ("mechanism", "interaction", "type")), "note": pick_column(row, ("note", "description", "evidence")) or f"FooDrugs candidate food-drug signal: {drug} / {food}"},
                risk_level="Moderate" if re.search(r"inhibit|contra|risk|avoid|major", str(row), re.I) else "Unknown",
                confidence="Low",
                source_tier="Signal",
                source_name="FooDrugs bulk",
                source_url="https://zenodo.org/records/8192515",
                evidence_quote=str(compact_row(row, 12))[:600],
                extraction_method="bulk_tabular",
                review_status="unreviewed",
                use_policy="candidate_signal",
                updated_at=now_utc(),
            ))
            count += 1
            if max_records and count >= max_records:
                return dedupe_fact_objects(facts)
    return dedupe_fact_objects(facts)


def load_chembl_bulk_facts(source_dir: Path, max_records: int = 100_000) -> list[EvidenceFact]:
    sqlite_paths = list(source_dir.glob("**/*.sqlite")) + list(source_dir.glob("**/*.db")) + list(source_dir.glob("**/*.sqlite3"))
    if not sqlite_paths:
        sqlite_paths = extract_chembl_sqlite_archives(source_dir)
    facts: list[EvidenceFact] = []
    count = 0
    for db_path in sqlite_paths:
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                try:
                    mechanism_rows = conn.execute("""
                        SELECT md.chembl_id, md.pref_name, dm.mechanism_of_action, dm.action_type, td.pref_name target_name
                        FROM drug_mechanism dm
                        JOIN molecule_dictionary md ON md.molregno = dm.molregno
                        LEFT JOIN target_dictionary td ON td.tid = dm.tid
                        WHERE md.pref_name IS NOT NULL
                          AND (dm.mechanism_of_action IS NOT NULL OR td.pref_name IS NOT NULL)
                        ORDER BY md.pref_name
                    """)
                    for mech in mechanism_rows:
                        name = mech["pref_name"]
                        subject_id = slugify(name)
                        facts.append(EvidenceFact(
                            fact_id=f"chembl_bulk_effect_{stable_hash(str(mech['chembl_id']) + subject_id + str(mech['mechanism_of_action']) + str(mech['target_name']))}",
                            fact_type="drug_effect",
                            subject_ids=[subject_id],
                            claim={"mechanism_of_action": mech["mechanism_of_action"] or "", "action_type": mech["action_type"] or "", "target": mech["target_name"] or ""},
                            confidence="High",
                            source_tier="CuratedDB",
                            source_name="ChEMBL drug mechanism",
                            source_url="https://www.ebi.ac.uk/chembl/",
                            evidence_quote=mech["mechanism_of_action"] or mech["target_name"] or "ChEMBL mechanism",
                            extraction_method="bulk_sqlite_mechanism",
                            review_status="machine_checked",
                            use_policy="evidence_source",
                            updated_at=now_utc(),
                        ))
                        count += 1
                        if max_records and count >= max_records:
                            return dedupe_fact_objects(facts)
                except sqlite3.Error:
                    pass
                rows = conn.execute("""
                    SELECT md.chembl_id, md.pref_name, md.molecule_type, cp.alogp, cp.psa, cp.full_mwt
                    FROM molecule_dictionary md
                    LEFT JOIN compound_properties cp ON cp.molregno = md.molregno
                    WHERE md.pref_name IS NOT NULL
                    ORDER BY md.pref_name
                """)
                for row in rows:
                    name = row["pref_name"]
                    subject_id = slugify(name)
                    solubility = None
                    try:
                        alogp = float(row["alogp"]) if row["alogp"] is not None else None
                        if alogp is not None:
                            solubility = "Lipophilic" if alogp >= 2 else "Hydrophilic"
                    except (TypeError, ValueError):
                        pass
                    facts.append(EvidenceFact(
                        fact_id=f"chembl_bulk_identity_{stable_hash(str(row['chembl_id']) + subject_id)}",
                        fact_type="substance_identity",
                        subject_ids=[subject_id],
                        claim={"name_en": name, "category": row["molecule_type"] or "ChEMBL molecule", "solubility": solubility, "identifiers": {"chembl_id": row["chembl_id"], "alogp": row["alogp"], "psa": row["psa"], "full_mwt": row["full_mwt"]}},
                        confidence="High",
                        source_tier="CuratedDB",
                        source_name="ChEMBL bulk",
                        source_url="https://www.ebi.ac.uk/chembl/",
                        evidence_quote="Bulk ChEMBL molecule row.",
                        extraction_method="bulk_sqlite",
                        review_status="machine_checked",
                        use_policy="evidence_source",
                        updated_at=now_utc(),
                    ))
                    count += 1
                    if max_records and count >= max_records:
                        return dedupe_fact_objects(facts)
        except Exception:
            continue
    return dedupe_fact_objects(facts)


def extract_chembl_sqlite_archives(source_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    cache_dir = source_dir / "_extracted"
    for archive_path in source_dir.glob("*.tar.gz"):
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive_path, "r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile() or not re.search(r"\.(sqlite|db|sqlite3)$", member.name, re.I):
                        continue
                    target = cache_dir / Path(member.name).name
                    if not target.exists():
                        source = archive.extractfile(member)
                        if source:
                            with source, target.open("wb") as out:
                                while True:
                                    chunk = source.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    out.write(chunk)
                    extracted.append(target)
        except Exception:
            continue
    return extracted


def iter_tabular_source(source_dir: Path, max_files: int = 0) -> Iterator[tuple[str, Iterator[dict[str, str]]]]:
    for path in select_files(iter_files(source_dir), max_files):
        lower = path.name.lower()
        if path.suffix == ".part":
            continue
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.namelist():
                    if not re.search(r"\.(csv|tsv|txt)$", member, re.I):
                        continue
                    with archive.open(member) as handle:
                        yield member, read_delimited_rows(io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace"), member)
        elif re.search(r"\.(csv|tsv|txt)$", lower):
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                yield path.name, read_delimited_rows(handle, path.name)
        elif lower.endswith(".json"):
            payload = read_json(path)
            if isinstance(payload, list):
                yield path.name, iter([item for item in payload if isinstance(item, dict)])


def read_delimited_rows(handle: Iterable[str], name: str) -> Iterator[dict[str, str]]:
    cached: list[str] = []
    sample = ""
    iterator = iter(handle)
    for _ in range(20):
        try:
            line = next(iterator)
        except StopIteration:
            break
        cached.append(line)
        sample += line
    if not cached:
        return
    delimiter = "\t" if name.lower().endswith(".tsv") or sample.count("\t") > sample.count(",") else ","
    reader = csv.DictReader([*cached, *iterator], delimiter=delimiter)
    for row in reader:
        if row:
            yield {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}


def identity_fact(subject_id: str, name: str, category: str, source_name: str, tier: str, source_url: str, method: str) -> EvidenceFact:
    return EvidenceFact(
        fact_id=f"{slugify(source_name)}_identity_{stable_hash(subject_id + name)}",
        fact_type="substance_identity",
        subject_ids=[subject_id],
        claim={"name_en": name, "category": category, "identifiers": {}},
        confidence="Low" if tier == "Signal" else "Medium",
        source_tier=tier,
        source_name=source_name,
        source_url=source_url,
        evidence_quote=f"Bulk identity row for {name}.",
        extraction_method=method,
        review_status="unreviewed",
        use_policy="candidate_signal",
        updated_at=now_utc(),
    )


def extract_half_life_hours(text: str) -> float | None:
    match = HALF_LIFE_RE.search(squash(text))
    if not match:
        return None
    first = float(match.group("first"))
    second = float(match.group("second")) if match.group("second") else None
    value = (first + second) / 2 if second else first
    unit = match.group("unit").lower()
    if unit.startswith("min"):
        return round(value / 60, 3)
    if unit.startswith("day") or unit == "d":
        return round(value * 24, 3)
    return round(value, 3)


def extract_cyp_relations(text: str) -> list[tuple[str, str, str]]:
    squashed = squash(text)
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in CYP_RE.finditer(squashed):
        enzyme = match.group(0).upper()
        context = squashed[max(0, match.start() - 120):min(len(squashed), match.end() + 120)]
        lowered = context.lower()
        relation = "mentioned"
        if re.search(r"\b(inhibitor|inhibits|inhibit|inhibition)\b", lowered):
            relation = "inhibitor"
        elif re.search(r"\b(inducer|induces|induce|induction)\b", lowered):
            relation = "inducer"
        elif re.search(r"\b(substrate|metabolized|metabolised|metabolism|mediated by|primarily by)\b", lowered):
            relation = "substrate"
        key = (enzyme, relation)
        if key not in seen:
            seen.add(key)
            rows.append((enzyme, relation, context[:500]))
    return rows


def iter_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    return sorted(item for item in path.glob("**/*") if item.is_file())


def select_files(files: list[Path], max_files: int = 0) -> list[Path]:
    return files[:max_files] if max_files else files


def list_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def first_value(value: object) -> str | None:
    values = list_values(value)
    return values[0] if values else None


def joined_sections(result: dict[str, Any], names: Iterable[str]) -> str:
    values: list[str] = []
    for name in names:
        section = result.get(name)
        if isinstance(section, list):
            values.extend(str(item) for item in section if item)
        elif isinstance(section, str):
            values.append(section)
    return "\n".join(values)


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def snippet_around(text: str, needle: str, width: int = 500) -> str:
    squashed = squash(text)
    index = squashed.lower().find(needle.lower())
    if index < 0:
        return squashed[:width]
    start = max(0, index - width // 2)
    return squashed[start:start + width]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_text(root: ET.Element, local: str) -> str | None:
    for element in root.iter():
        if local_name(element.tag) == local:
            text = " ".join(part.strip() for part in element.itertext() if part and part.strip())
            if text:
                return text
    return None


def first_attr(root: ET.Element, local: str, attr: str) -> str | None:
    for element in root.iter():
        if local_name(element.tag) == local and element.attrib.get(attr):
            return element.attrib.get(attr)
    return None


def spl_sections(root: ET.Element) -> Iterator[tuple[str, str]]:
    for section in root.iter():
        if local_name(section.tag) != "section":
            continue
        title = ""
        text = ""
        for child in section:
            if local_name(child.tag) == "title":
                title = squash(" ".join(child.itertext()))
            elif local_name(child.tag) == "text":
                text = squash(" ".join(child.itertext()))
        if title or text:
            yield title, text


def clean_label_title(title: str) -> str:
    clean = squash(title)
    clean = re.sub(r"^HIGHLIGHTS OF PRESCRIBING INFORMATION\s*", "", clean, flags=re.I)
    clean = re.sub(r"\s*\(.*?\)\s*$", "", clean).strip()
    return clean[:120] or "DailyMed SPL"


def matches_any(value: str, hints: Iterable[str]) -> bool:
    upper = value.upper()
    return any(hint in upper for hint in hints)


def pick_column(row: dict[str, str], names: Iterable[str]) -> str:
    lower_map = {key.lower().replace(" ", "_").replace("-", "_"): value for key, value in row.items()}
    for name in names:
        key = name.lower().replace(" ", "_").replace("-", "_")
        if lower_map.get(key):
            return lower_map[key]
    for key, value in row.items():
        normalized = key.lower().replace(" ", "_").replace("-", "_")
        if any(name.lower().replace(" ", "_").replace("-", "_") in normalized for name in names) and value:
            return value
    return ""


def split_aliases(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[|;,]", value or "") if part.strip()][:30]


def compact_row(row: dict[str, str], limit: int = 12) -> dict[str, str]:
    out: dict[str, str] = {}
    for index, (key, value) in enumerate(row.items()):
        if index >= limit:
            break
        out[key] = value[:300]
    return out


def dedupe_fact_objects(facts: Iterable[EvidenceFact]) -> list[EvidenceFact]:
    by_id: dict[str, EvidenceFact] = {}
    for fact in facts:
        by_id[fact.fact_id] = fact
    return [by_id[key] for key in sorted(by_id)]
REMOTE_RAW_SOURCE_KEYS = ("openfda_label", "dailymed", "chembl", "foodrugs", "onsides", "pharmgkb")
REMOTE_RAW_SOURCE_DIRS = {
    "openfda_label": "openfda_label",
    "dailymed": "dailymed_spl",
    "chembl": "chembl",
    "foodrugs": "foodrugs",
    "onsides": "onsides",
    "pharmgkb": "pharmgkb",
}
PHARMGKB_BULK_FILES = (
    "clinicalAnnotations.zip",
    "clinicalVariants.zip",
    "variantAnnotations.zip",
    "drugLabels.zip",
    "guidelineAnnotations.json.zip",
    "relationships.zip",
    "drugs.zip",
    "genes.zip",
    "variants.zip",
    "chemicals.zip",
    "phenotypes.zip",
)


def normalize_proxy(proxy: str | None) -> str:
    value = str(proxy or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "http://" + value
    return value


def configure_url_proxy(proxy: str | None) -> str:
    value = normalize_proxy(proxy)
    if not value:
        return ""
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[key] = value
    return value


def mirror_remote_raw_sources(
    source_keys: Iterable[str],
    raw_dir: Path,
    proxy: str | None = None,
    max_parts_per_source: int = 0,
    overwrite: bool = False,
) -> dict[str, dict[str, Any]]:
    """Download upstream bulk files into a persistent raw mirror for offline analysis."""
    proxy_value = configure_url_proxy(proxy)
    requested = [key.strip() for key in source_keys if key and key.strip()]
    if not requested:
        requested = list(REMOTE_RAW_SOURCE_KEYS)
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, Any]] = {}
    if proxy_value:
        print(f"mirror_raw_proxy={proxy_value}", flush=True)
    print(f"mirror_raw_dir={raw_dir.resolve()}", flush=True)
    for key in requested:
        if key not in REMOTE_RAW_SOURCE_KEYS:
            summary[key] = {"status": "unsupported", "downloaded_files": 0, "skipped_files": 0, "errors": 0}
            continue
        try:
            summary[key] = mirror_remote_source(key, raw_dir, max_parts_per_source, overwrite)
        except Exception as exc:
            summary[key] = {"status": "error", "downloaded_files": 0, "skipped_files": 0, "errors": 1, "error": f"{type(exc).__name__}: {exc}"}
            print(f"mirror_raw_error={key} error={type(exc).__name__}: {exc}", flush=True)
    return summary


def mirror_remote_source(key: str, raw_dir: Path, max_parts: int = 0, overwrite: bool = False) -> dict[str, Any]:
    manifest = fetch_remote_bulk_manifest(key)
    parts = manifest.get("parts") or []
    if max_parts:
        parts = parts[:max_parts]
    out_dir = Path(raw_dir) / REMOTE_RAW_SOURCE_DIRS[key]
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    errors = 0
    for index, part in enumerate(parts, start=1):
        url = part.get("url")
        if not url:
            errors += 1
            continue
        target = out_dir / safe_filename(part.get("name") or url)
        label = f"mirror_raw_download={key} part={index}/{len(parts)} name={target.name}"
        try:
            status = download_url(url, target, skip_existing=not overwrite, progress_label=label)
            if status == "skipped":
                skipped += 1
            else:
                downloaded += 1
        except Exception as exc:
            errors += 1
            print(f"mirror_raw_error={key} part={index} error={type(exc).__name__}: {exc}", flush=True)
    info = {
        "status": "loaded" if downloaded or skipped else "no_files",
        "remote_parts": len(parts),
        "downloaded_files": downloaded,
        "skipped_files": skipped,
        "errors": errors,
        "out_dir": str(out_dir.resolve()),
        "source_url": manifest.get("source_url"),
        "total_records": manifest.get("total_records"),
        "total_size_mb": manifest.get("total_size_mb"),
    }
    print(f"mirror_raw_summary={key} {info}", flush=True)
    return info


def load_remote_raw_source_facts(
    source_keys: Iterable[str],
    temp_dir: Path | None = None,
    max_records_per_source: int = 100_000,
    max_parts_per_source: int = 0,
    workers: int = 0,
) -> tuple[list[EvidenceFact], dict[str, dict[str, Any]]]:
    """Download remote bulk packages one part at a time, parse, then delete.

    This keeps the runner from needing a persistent raw mirror. The output is
    still compact EvidenceFact rows, not raw label/XML redistribution.
    """
    requested = [key.strip() for key in source_keys if key and key.strip()]
    if not requested:
        requested = list(REMOTE_RAW_SOURCE_KEYS)
    root = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp(prefix="metabolic_raw_stream_"))
    root.mkdir(parents=True, exist_ok=True)
    all_facts: list[EvidenceFact] = []
    summary: dict[str, dict[str, Any]] = {}
    def run_stream(key: str) -> tuple[str, list[EvidenceFact], dict[str, Any]]:
        if key not in REMOTE_RAW_SOURCE_KEYS:
            return key, [], {"facts": 0, "status": "unsupported"}
        facts, info = stream_remote_source(key, root / key, max_records_per_source, max_parts_per_source)
        return key, facts, info

    try:
        max_workers = workers if workers > 0 else min(len(requested), 4)
        if max_workers <= 1:
            for key in requested:
                try:
                    _, facts, info = run_stream(key)
                    all_facts.extend(facts)
                    summary[key] = info
                except Exception as exc:
                    summary[key] = {"facts": 0, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_by_key = {executor.submit(run_stream, key): key for key in requested}
                for future in as_completed(future_by_key):
                    key = future_by_key[future]
                    try:
                        _, facts, info = future.result()
                        all_facts.extend(facts)
                        summary[key] = info
                    except Exception as exc:
                        summary[key] = {"facts": 0, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if temp_dir is None:
            shutil.rmtree(root, ignore_errors=True)
    return dedupe_fact_objects(all_facts), dict(sorted(summary.items()))


def stream_remote_source(key: str, work_dir: Path, max_records: int = 100_000, max_parts: int = 0) -> tuple[list[EvidenceFact], dict[str, Any]]:
    manifest = fetch_remote_bulk_manifest(key)
    parts = manifest.get("parts") or []
    if max_parts:
        parts = parts[:max_parts]
    facts: list[EvidenceFact] = []
    downloaded = 0
    errors = 0
    for index, part in enumerate(parts, start=1):
        url = part.get("url")
        if not url:
            errors += 1
            continue
        part_dir = work_dir / f"part_{index:04d}"
        shutil.rmtree(part_dir, ignore_errors=True)
        part_dir.mkdir(parents=True, exist_ok=True)
        target = part_dir / safe_filename(part.get("name") or url)
        try:
            print(f"remote_raw_download={key} part={index}/{len(parts)} name={target.name}", flush=True)
            download_url(url, target)
            downloaded += 1
            remaining = 0 if not max_records else max(max_records - len(facts), 1)
            facts.extend(load_downloaded_part_facts(key, part_dir, remaining))
            print(f"remote_raw_progress={key} part={index}/{len(parts)} facts={len(facts)}", flush=True)
            if max_records and len(facts) >= max_records:
                break
        except Exception as exc:
            errors += 1
            print(f"remote_raw_error={key} part={index} error={type(exc).__name__}: {exc}", flush=True)
        finally:
            shutil.rmtree(part_dir, ignore_errors=True)
    info = {
        "facts": len(facts),
        "status": "loaded" if facts else "no_facts",
        "remote_parts": len(parts),
        "downloaded_parts": downloaded,
        "errors": errors,
        "source_url": manifest.get("source_url"),
        "total_records": manifest.get("total_records"),
        "total_size_mb": manifest.get("total_size_mb"),
    }
    return dedupe_fact_objects(facts), info


def write_remote_raw_source_facts_json(
    source_keys: Iterable[str],
    out_path: Path,
    summary_out: Path | None = None,
    temp_dir: Path | None = None,
    max_records_per_source: int = 100_000,
    max_parts_per_source: int = 0,
) -> dict[str, dict[str, Any]]:
    """Stream remote source facts directly to a JSON array without retaining all rows."""
    requested = [key.strip() for key in source_keys if key and key.strip()]
    if not requested:
        requested = list(REMOTE_RAW_SOURCE_KEYS)
    root = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp(prefix="metabolic_raw_stream_"))
    root.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    first = True
    try:
        with out_path.open("w", encoding="utf-8") as handle:
            handle.write("[\n")
            for key in requested:
                if key not in REMOTE_RAW_SOURCE_KEYS:
                    summary[key] = {"facts": 0, "status": "unsupported"}
                    continue
                source_count, info = stream_remote_source_to_json(
                    key,
                    root / key,
                    handle,
                    seen_ids,
                    first,
                    max_records_per_source,
                    max_parts_per_source,
                )
                first = info.pop("first_after", first)
                summary[key] = info | {"facts": source_count, "status": "loaded" if source_count else "no_facts"}
            handle.write("\n]\n")
    finally:
        if temp_dir is None:
            shutil.rmtree(root, ignore_errors=True)
    summary = dict(sorted(summary.items()))
    if summary_out:
        Path(summary_out).parent.mkdir(parents=True, exist_ok=True)
        Path(summary_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def stream_remote_source_to_json(
    key: str,
    work_dir: Path,
    handle,
    seen_ids: set[str],
    first: bool,
    max_records: int = 100_000,
    max_parts: int = 0,
) -> tuple[int, dict[str, Any]]:
    manifest = fetch_remote_bulk_manifest(key)
    parts = manifest.get("parts") or []
    if max_parts:
        parts = parts[:max_parts]
    written = 0
    downloaded = 0
    errors = 0
    for index, part in enumerate(parts, start=1):
        url = part.get("url")
        if not url:
            errors += 1
            continue
        part_dir = work_dir / f"part_{index:04d}"
        shutil.rmtree(part_dir, ignore_errors=True)
        part_dir.mkdir(parents=True, exist_ok=True)
        target = part_dir / safe_filename(part.get("name") or url)
        try:
            print(f"remote_raw_download={key} part={index}/{len(parts)} name={target.name}", flush=True)
            download_url(url, target)
            downloaded += 1
            remaining = 0 if not max_records else max(max_records - written, 1)
            for fact in load_downloaded_part_facts(key, part_dir, remaining):
                if fact.fact_id in seen_ids:
                    continue
                seen_ids.add(fact.fact_id)
                if not first:
                    handle.write(",\n")
                json.dump(fact.to_dict(), handle, ensure_ascii=False, sort_keys=True)
                first = False
                written += 1
                if max_records and written >= max_records:
                    break
            print(f"remote_raw_progress={key} part={index}/{len(parts)} facts={written}", flush=True)
            if max_records and written >= max_records:
                break
        except Exception as exc:
            errors += 1
            print(f"remote_raw_error={key} part={index} error={type(exc).__name__}: {exc}", flush=True)
        finally:
            shutil.rmtree(part_dir, ignore_errors=True)
    info = {
        "remote_parts": len(parts),
        "downloaded_parts": downloaded,
        "errors": errors,
        "source_url": manifest.get("source_url"),
        "total_records": manifest.get("total_records"),
        "total_size_mb": manifest.get("total_size_mb"),
        "first_after": first,
    }
    return written, info

def load_downloaded_part_facts(key: str, part_dir: Path, max_records: int = 100_000) -> list[EvidenceFact]:
    if key == "openfda_label":
        return load_openfda_bulk_facts(part_dir, max_records=max_records)
    if key == "dailymed":
        return load_dailymed_bulk_facts(part_dir, max_records=max_records)
    if key == "chembl":
        return load_chembl_bulk_facts(part_dir, max_records=max_records)
    if key == "foodrugs":
        return load_foodrugs_bulk_facts(part_dir, max_records=max_records)
    if key == "onsides":
        return load_onsides_bulk_facts(part_dir, max_records=max_records)
    if key == "pharmgkb":
        return load_pharmgkb_bulk_facts(part_dir, max_records=max_records)
    return []


def fetch_remote_bulk_manifest(key: str) -> dict[str, Any]:
    if key == "openfda_label":
        return fetch_openfda_label_manifest()
    if key == "dailymed":
        return fetch_dailymed_label_manifest()
    if key == "chembl":
        return fetch_chembl_bulk_manifest()
    if key == "foodrugs":
        return fetch_zenodo_manifest("8192515", "foodrugs")
    if key == "onsides":
        return fetch_github_release_manifest("tatonetti-lab/onsides", "onsides", "onsides")
    if key == "pharmgkb":
        return fetch_pharmgkb_bulk_manifest()
    raise ValueError(f"unsupported remote raw source: {key}")




def fetch_remote_bulk_manifests(source_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    requested = [key.strip() for key in source_keys if key and key.strip()] or list(REMOTE_RAW_SOURCE_KEYS)
    manifests: dict[str, dict[str, Any]] = {}
    for key in requested:
        manifest = fetch_remote_bulk_manifest(key)
        manifest["fingerprint"] = manifest_fingerprint(manifest)
        manifests[key] = manifest
    return manifests


def manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = {
        "source": manifest.get("source"),
        "source_url": manifest.get("source_url"),
        "export_date": manifest.get("export_date"),
        "total_records": manifest.get("total_records"),
        "total_size_mb": manifest.get("total_size_mb"),
        "parts": sorted(
            [
                {
                    "name": part.get("name"),
                    "url": part.get("url"),
                    "records": part.get("records"),
                    "size_mb": part.get("size_mb"),
                    "checksum": part.get("checksum"),
                    "etag": part.get("etag"),
                    "last_modified": part.get("last_modified"),
                    "updated_at": part.get("updated_at"),
                }
                for part in manifest.get("parts", []) or []
            ],
            key=lambda item: (str(item.get("name") or ""), str(item.get("url") or "")),
        ),
    }
    return stable_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True), 32)


def fetch_url_head_metadata(url: str, timeout: int = 20) -> dict[str, Any]:
    try:
        with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-etl"}, method="HEAD"), timeout=timeout) as response:
            size = int(response.headers.get("Content-Length") or 0)
            return {
                "size_mb": round(size / 1024 / 1024, 2) if size else None,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
    except Exception:
        return {}


def fetch_chembl_bulk_manifest() -> dict[str, Any]:
    url = "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/"
    with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-etl"}), timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(r'href="([^"]+)"', html)))
    parts = []
    for name in names:
        if re.search(r"chembl_.*_sqlite\.tar\.gz$", name):
            parts.append({"name": name, "url": urljoin(url, name), "records": None, **fetch_url_head_metadata(urljoin(url, name), timeout=12)})
    return {"source": "chembl", "source_url": url, "parts": parts, "total_records": None, "total_size_mb": None}


def fetch_zenodo_manifest(record_id: str, source: str) -> dict[str, Any]:
    url = f"https://zenodo.org/api/records/{record_id}"
    with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-etl"}), timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = []
    for item in payload.get("files", []) or []:
        links = item.get("links") or {}
        file_url = links.get("self") or links.get("download")
        if not file_url:
            continue
        size = item.get("size") or 0
        parts.append({"name": item.get("key") or Path(urlparse(file_url).path).name, "url": file_url, "records": None, "size_mb": round(size / 1024 / 1024, 2) if size else None, "checksum": item.get("checksum")})
    return {"source": source, "source_url": url, "parts": parts, "total_records": None, "total_size_mb": sum(part.get("size_mb") or 0 for part in parts)}


def fetch_github_release_manifest(owner_repo: str, repo_name: str, source: str) -> dict[str, Any]:
    api_url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    try:
        with urlopen(Request(api_url, headers={"User-Agent": "metabolic-safety-etl"}), timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts = [
            {"name": asset.get("name"), "url": asset.get("browser_download_url"), "records": None, "size_mb": round((asset.get("size") or 0) / 1024 / 1024, 2), "updated_at": asset.get("updated_at"), "id": asset.get("id")}
            for asset in payload.get("assets", []) or []
            if asset.get("browser_download_url")
        ]
        if parts:
            return {"source": source, "source_url": api_url, "tag_name": payload.get("tag_name"), "published_at": payload.get("published_at"), "updated_at": payload.get("updated_at"), "parts": parts, "total_records": None, "total_size_mb": sum(part.get("size_mb") or 0 for part in parts)}
    except Exception:
        pass
    branch = "main"
    try:
        repo_api = f"https://api.github.com/repos/{owner_repo}"
        with urlopen(Request(repo_api, headers={"User-Agent": "metabolic-safety-etl"}), timeout=20) as response:
            branch = json.loads(response.read().decode("utf-8")).get("default_branch") or branch
    except Exception:
        pass
    archive_url = f"https://github.com/{owner_repo}/archive/refs/heads/{branch}.zip"
    return {"source": source, "source_url": f"https://github.com/{owner_repo}", "parts": [{"name": f"{repo_name}-{branch}.zip", "url": archive_url, "records": None, "size_mb": None}], "total_records": None, "total_size_mb": None}


def fetch_pharmgkb_bulk_manifest() -> dict[str, Any]:
    base = "https://api.pharmgkb.org/v1/download/file/data/"
    parts = []
    for name in PHARMGKB_BULK_FILES:
        url = base + name
        meta = fetch_url_head_metadata(url, timeout=12)
        parts.append({"name": name, "url": url, "records": None, **meta})
    return {"source": "pharmgkb", "source_url": base, "parts": parts, "total_records": None, "total_size_mb": sum(part.get("size_mb") or 0 for part in parts) or None}


def download_url(url: str, target: Path, skip_existing: bool = False, progress_label: str = "") -> str:
    if skip_existing and target.exists() and target.stat().st_size > 0:
        if progress_label:
            print(f"{progress_label} status=skipped bytes={target.stat().st_size}", flush=True)
        return "skipped"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    req = Request(url, headers={"User-Agent": "metabolic-safety-etl"})
    with urlopen(req, timeout=600) as response, tmp.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        next_report = 256 * 1024 * 1024
        if progress_label:
            print(f"{progress_label} status=start total_bytes={total}", flush=True)
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if progress_label and downloaded >= next_report:
                print(f"{progress_label} status=progress downloaded_bytes={downloaded} total_bytes={total}", flush=True)
                next_report += 256 * 1024 * 1024
    tmp.replace(target)
    if progress_label:
        print(f"{progress_label} status=downloaded bytes={target.stat().st_size}", flush=True)
    return "downloaded"


def safe_filename(value: str) -> str:
    name = Path(urlparse(str(value)).path).name if "/" in str(value) else str(value)
    name = re.sub(r"[^A-Za-z0-9._+\-()\[\] ]+", "_", name).strip(" .")
    return name or "download.bin"