from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import re
import sqlite3
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Iterable, Iterator

from .io import read_json
from .schemas import EvidenceFact, now_utc, slugify, stable_hash

OPENFDA_SECTIONS = ("pharmacokinetics", "clinical_pharmacology", "drug_interactions", "overdosage", "warnings", "boxed_warning")
DAILYMED_SECTION_HINTS = ("PHARMACOKINETICS", "CLINICAL PHARMACOLOGY", "DRUG INTERACTIONS", "OVERDOSAGE", "WARNINGS", "BOXED WARNING")
CYP_RE = re.compile(r"\bCYP(?:1A2|2A6|2B6|2C8|2C9|2C19|2D6|2E1|3A4|3A5|3A7|4A11)\b", re.I)
HALF_LIFE_RE = re.compile(
    r"(?:half[-\s]?life|t\s*1\s*/\s*2|t1/2|terminal\s+half[-\s]?life)"
    r"[^.;\n]{0,140}?"
    r"(?P<first>\d+(?:\.\d+)?)"
    r"(?:\s*(?:-|to)\s*(?P<second>\d+(?:\.\d+)?))?"
    r"\s*(?P<unit>hours?|hrs?|h|minutes?|mins?|days?|d)\b",
    re.I,
)


def load_raw_source_facts(raw_dir: Path, max_records_per_source: int = 100_000, max_files_per_source: int = 0) -> tuple[list[EvidenceFact], dict[str, dict[str, Any]]]:
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
    for key, loader in loaders.items():
        try:
            batch = loader()
            facts.extend(batch)
            summary[key] = {"facts": len(batch), "status": "loaded" if batch else "no_local_files"}
        except Exception as exc:
            summary[key] = {"facts": 0, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return dedupe_fact_objects(facts), summary


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
    facts.extend(pk_and_enzyme_facts(subject_id, joined_sections(result, OPENFDA_SECTIONS), "openFDA drug label bulk", url, "bulk_json"))
    return facts


def load_dailymed_bulk_facts(source_dir: Path, max_records: int = 100_000, max_files: int = 0) -> list[EvidenceFact]:
    facts: list[EvidenceFact] = []
    seen = 0
    for path in select_files(iter_files(source_dir), max_files):
        if path.suffix == ".part" or not zipfile.is_zipfile(path):
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith(".xml"):
                    continue
                try:
                    with archive.open(member) as handle:
                        facts.extend(dailymed_xml_facts(handle.read()))
                except Exception:
                    continue
                seen += 1
                if max_records and seen >= max_records:
                    return dedupe_fact_objects(facts)
    return dedupe_fact_objects(facts)


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
    text = "\n".join(text for section_title, text in spl_sections(root) if matches_any(section_title, DAILYMED_SECTION_HINTS))
    facts.extend(pk_and_enzyme_facts(subject_id, text, "DailyMed SPL bulk", url, "bulk_spl_xml"))
    return facts


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