# Raw Source Database Notes

This document records the observed shape of each bulk/raw source, how the ETL currently handles it, and the safety/privacy boundaries to preserve.

Local reference root used during inspection:

```text
/mnt/d/metabolic-safety-data/raw
```

The local raw data is reference-only. CI must reproduce extraction by downloading the upstream sources through the workflow and ETL commands, not by depending on local disk paths.

## Source Summary

| Source | Local Path | Main Format | Current Handler | Primary Output Facts |
| --- | --- | --- | --- | --- |
| openFDA drug labels | `raw/openfda_label/` | zip files containing JSON result arrays | `load_openfda_bulk_facts()` | identity, PK, CYP/enzyme, drug effect, dose candidates, overdose warnings |
| DailyMed SPL | `raw/dailymed_spl/` | large zip files containing nested label zip/XML files | `load_dailymed_bulk_facts()` | identity, PK, CYP/enzyme, drug effect, dose candidates, overdose warnings |
| ChEMBL | `raw/chembl/` | SQLite database inside `.tar.gz`, extracted to `_extracted/*.db` | `load_chembl_bulk_facts()` | identity, drug effect, pharmacokinetics/half-life |
| FooDrugs | `raw/foodrugs/` | MySQL dump `.sql` files | `load_foodrugs_bulk_facts()` | food interaction candidate signals, drug/food identity |
| OnSIDES | `raw/onsides/` | zip containing CSV tables | `load_onsides_bulk_facts()` | adverse event candidate signals, product identity |
| PharmGKB | `raw/pharmgkb/` | zip files containing TSV/JSON files | `load_pharmgkb_bulk_facts()` | identity and guideline/label-related substance records |
| DDInter | `raw/ddinter/` | CSV files | `load_ddinter_csv_facts()` | drug/drug and food/drug interactions |

## openFDA Drug Labels

### Observed Shape

Local files are named like:

```text
label (part 1 of 13)
label (part 10 of 13)
...
label (part 13 of 13)
```

They are valid zip archives even though they do not use a `.zip` extension. Each archive contains one JSON file, for example:

```text
drug-label-0001-of-0013.json
```

The JSON contains a top-level `results` array. Records may contain `openfda` metadata plus label sections such as:

```text
pharmacokinetics
clinical_pharmacology
warnings
boxed_warning
dosage_and_administration
dosage_forms_and_strengths
mechanism_of_action
pharmacodynamics
```

### Processing

Current handler:

```text
load_openfda_bulk_facts(source_dir, max_records, max_files)
```

Key behavior:

- Uses `zipfile.is_zipfile()` instead of relying on file extension.
- Streams the `results` array with `iter_results_array()` to avoid loading full bulk files into memory.
- Creates `substance_identity` from `openfda.generic_name`, `substance_name`, or `brand_name`.
- Extracts half-life and CYP/enzyme relations from PK/clinical sections via `pk_and_enzyme_facts()`.
- Extracts dose candidates from dosage/overdose sections.
- Emits overdose warning facts from `overdosage`.

### Safety Notes

- Regulatory source tier, but most text-derived PK/CYP/dose facts are still machine-extracted candidates unless reviewed.
- `source_text`/label text alone should not become a final safety rule without extraction and review.

## DailyMed SPL

### Observed Shape

Local files include:

```text
dm_spl_release_human_rx_part1.zip
dm_spl_release_human_rx_part2.zip
dm_spl_release_human_otc_part1.zip
dm_spl_release_animal.zip
dm_spl_release_homeopathic.zip
...
```

Outer archives contain many nested zip files, for example:

```text
human_rx/20240101_<setid>.zip
otc/20090619_<setid>.zip
animal/20100419_<setid>.zip
```

Nested zip files contain SPL XML labels.

### Processing

Current handler:

```text
load_dailymed_bulk_facts(source_dir, max_records, max_files)
```

Key behavior:

- Reads XML directly if an outer archive contains `.xml` files.
- Reads nested zip members and extracts inner XML files.
- Parses SPL XML with `xml.etree.ElementTree`.
- Uses local tag matching to handle HL7 namespaces.
- Extracts section titles/text with `spl_sections()`.
- Uses section hint lists for PK, CYP/enzyme, dose, overdose, and effect extraction.

### Safety Notes

- Regulatory source tier.
- SPL structure can include product labels, OTC labels, animal labels, homeopathic labels, and other non-core medication labels. Downstream review should account for label/product context.

## ChEMBL

### Observed Shape

Local extracted database:

```text
raw/chembl/_extracted/chembl_36.db
```

Important tables observed:

```text
activities
assays
compound_records
molecule_dictionary
compound_properties
drug_mechanism
target_dictionary
```

Important columns:

```text
activities.standard_type
activities.standard_value
activities.standard_units
activities.standard_relation
activities.upper_value
activities.standard_upper_value
compound_records.record_id
compound_records.molregno
molecule_dictionary.molregno
molecule_dictionary.pref_name
molecule_dictionary.chembl_id
```

Half-life activity types observed in the local DB include:

```text
T1/2
t1/2
Plasma half life
Plasma half-life
Half duration
```

Large observed counts include `T1/2` with `hr`, so `T1/2` and `t1/2` must stay in the whitelist.

### Processing

Current handler:

```text
load_chembl_bulk_facts(source_dir, max_records)
```

Key behavior:

- Finds local `.sqlite`, `.db`, or `.sqlite3` files.
- If no SQLite DB exists, extracts ChEMBL SQLite DBs from `.tar.gz` into `_extracted/`.
- Extracts pharmacokinetics/half-life facts before broad mechanism/identity rows so debug-capped CI runs still exercise half-life extraction.
- Converts units to hours with `_chembl_pk_to_hours()`.
- Emits `pharmacokinetics` facts with:
  - `half_life_hours`
  - `standard_type`
  - `standard_relation`
  - `standard_value`
  - `standard_units`
  - optional `half_life_hours_upper`
  - optional `half_life_hours_mean`
- Extracts mechanism facts from `drug_mechanism` joined to `molecule_dictionary` and `target_dictionary`.
- Extracts identity/solubility from `molecule_dictionary` and `compound_properties`.

### Safety Notes

- ChEMBL is treated as `CuratedDB`, below regulatory labels in source-tier precedence.
- PK values can be assay/population-specific. The fused `base_half_life` is a best available default, not a patient-specific guarantee.
- Higher-tier regulatory label half-life should beat ChEMBL when both exist.

## FooDrugs

### Observed Shape

Local files:

```text
FinalFooDrugs_v2.sql
FinalFooDrugs_v3.sql
FinalFooDrugs_v4.sql
```

They are large MySQL dumps, not CSV/TSV files.

Observed tables include:

```text
TM_interactions
cmap
cmap_foodrugs
misc_sample
misc_study
nodes
sample
study
texts
topTable
```

Important table:

```sql
CREATE TABLE `TM_interactions` (
  `TM_interactions_ID` int NOT NULL,
  `texts_ID` int NOT NULL,
  `start_index` int DEFAULT NULL,
  `end_index` int DEFAULT NULL,
  `food` varchar(150) DEFAULT NULL,
  `drug` varchar(150) DEFAULT NULL,
  PRIMARY KEY (`TM_interactions_ID`)
)
```

Observed insert shape:

```sql
INSERT INTO `TM_interactions` VALUES
(0,0,0,116,'Grapefruit','abemaciclib'),
(1,0,1943,2220,'carbohydrate','abemaciclib'),
...
```

Some dumps may include explicit column names; the current parser supports both explicit and implicit forms.

### Processing

Current handler:

```text
load_foodrugs_bulk_facts(source_dir, max_records, max_files)
```

Key behavior:

- First attempts generic tabular handling for CSV/TSV/JSON forms if present.
- If no tabular facts are found, reads `.sql` files and parses `INSERT INTO \`TM_interactions\`` rows.
- For implicit insert rows, uses default column order:
  - `TM_interactions_ID`
  - `texts_ID`
  - `start_index`
  - `end_index`
  - `food`
  - `drug`
- Emits:
  - `substance_identity` for drug
  - `substance_identity` for food/bioactive
  - `food_interaction` for the pair

### Safety Notes

- FooDrugs is treated as `Signal`.
- Emitted food interactions use `risk_level = Unknown` by default.
- These facts are text-mined candidate signals and must not downgrade or override curated/regulatory risks.

## OnSIDES

### Observed Shape

Local archive:

```text
onsides-v3.1.1.zip
```

Important members:

```text
csv/product_label.csv
csv/product_adverse_effect.csv
csv/vocab_meddra_adverse_effect.csv
csv/vocab_rxnorm_ingredient.csv
csv/vocab_rxnorm_product.csv
```

Observed columns:

```text
product_label.csv:
label_id, source, source_product_name, source_product_id, source_label_url

product_adverse_effect.csv:
product_label_id, effect_id, label_section, effect_meddra_id, match_method, pred0, pred1

vocab_meddra_adverse_effect.csv:
meddra_id, meddra_name, meddra_term_type
```

The adverse event table stores IDs, not readable drug/event names. It must be joined against vocabulary tables.

### Processing

Current handler:

```text
load_onsides_bulk_facts(source_dir, max_records, max_files)
```

Key behavior:

- First attempts explicit OnSIDES v3 joined extraction with `load_onsides_joined_facts()`.
- Builds `label_id -> source_product_name` from `product_label.csv`.
- Builds `meddra_id -> meddra_name` from `vocab_meddra_adverse_effect.csv`.
- Reads `product_adverse_effect.csv` and emits readable adverse event facts.
- Falls back to generic tabular extraction if the canonical joined layout is absent.

### Safety Notes

- OnSIDES is treated as `Signal`.
- Adverse event rows are candidate signals only.
- These rows should not be presented as confirmed contraindications or used to lower higher-tier evidence.

## PharmGKB

### Observed Shape

Local files include:

```text
chemicals.zip
clinicalAnnotations.zip
clinicalVariants.zip
drugLabels.zip
drugs.zip
genes.zip
guidelineAnnotations.json.zip
phenotypes.zip
relationships.zip
variantAnnotations.zip
variants.zip
```

Observed members and columns include:

```text
drugs.zip -> drugs.tsv
PharmGKB Accession Id, Name, Generic Names, Trade Names, Brand Mixtures, Type, Cross-references, ...

chemicals.zip -> chemicals.tsv
PharmGKB Accession Id, Name, Generic Names, Trade Names, Brand Mixtures, Type, Cross-references, ...

drugLabels.zip -> drugLabels.tsv
PharmGKB ID, Name, Source, Biomarker Flag, Testing Level, Has Prescribing Info, Has Dosing Info, ...

clinicalAnnotations.zip -> clinical_annotations.tsv
Clinical Annotation ID, Variant/Haplotypes, Gene, Level of Evidence, Drug(s), Phenotype(s), URL, ...
```

### Processing

Current handler:

```text
load_pharmgkb_bulk_facts(source_dir, max_records, max_files)
```

Key behavior:

- Uses generic zip/tabular reading for TSV/CSV/TXT members.
- Processes filenames containing drug, chemical, guideline, or label tokens.
- Emits `substance_identity` facts from rows with recognizable drug/chemical names.
- Captures aliases from generic/trade/alternate/synonym fields when present.

### Safety Notes

- PharmGKB is treated as `Guideline` for current identity/guideline-adjacent facts.
- PGx annotations require careful interpretation. A label/guideline mention should not automatically become a direct safety rule without rule extraction/review.

## DDInter

### Observed Shape

DDInter source files live under:

```text
raw/ddinter/
```

The project already has a dedicated adapter for DDInter CSV files.

### Processing

Current handler:

```text
find_ddinter_csvs(input_dir)
load_ddinter_csv_facts(paths, max_interactions, zh_aliases)
```

Key behavior:

- Finds DDInter CSV files from the configured input directory.
- Emits interaction facts for core seed generation.
- Supports Chinese aliases via the optional aliases file.

### Safety Notes

- DDInter interactions are structured interaction evidence, but conflict handling still follows fusion rules.
- `Unknown` is not treated as safe.
- Candidate/community/signal sources cannot downgrade higher-tier evidence.

## CI/Reproducibility Notes

The GitHub Pages workflow builds/cache source layers per source:

```text
.github/workflows/build-data-api.yml
```

Current source matrix:

```text
openfda_label
dailymed
chembl
foodrugs
onsides
pharmgkb
```

Important CLI path:

```text
python -m metabolic_safety_etl.cli build-remote-source-facts \
  --sources <source> \
  --out <source-cache>/evidence_facts.json \
  --summary-out <source-cache>/summary.json \
  --temp-dir <runner-temp>/metabolic-raw-stream/<source> \
  --raw-max-records <cap> \
  --raw-stream-max-parts <cap>
```

The deploy job restores all cached source-layer `evidence_facts.json` files and passes them to `build-public-api` via `--extra-facts`.

## Validation Commands

Python tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Raw source focused tests:

```bash
PYTHONPATH=src python3 -m unittest tests.test_raw_sources -v
```

Mobile build:

```bash
cd mobile_pwa && npm run build
```

Note: Vite 7 requires Node >=20.19. The current local Node 18.20.4 may still build but emits a warning.

## Open Follow-Ups

- Confirm CI remote FooDrugs Zenodo files are the same MySQL dump shape observed locally.
- Confirm CI remote OnSIDES release/fallback archive contains the same `csv/*` layout observed locally.
- Consider adding remote smoke jobs with small `raw_stream_max_parts` and `raw_max_records` caps before full scheduled builds.
- Keep journal/profile/private mobile data out of remote static/live source requests unless explicitly consented.
