"""Shared path constants and source configuration for the desktop app.

This module is imported first by all desktop_app sub-modules.  It inserts
``ROOT / "src"`` onto ``sys.path`` so that ``metabolic_safety_etl`` is
importable without requiring an editable install.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path roots
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

STATIC = Path(__file__).resolve().parent / "static"
REMOTE_STATIC_API = ROOT / "build" / "static_api_preview"
DATA = ROOT / "data"
BUILD = ROOT / "build"
SEED_DB = BUILD / "app_seed.sqlite"
ACTIVE_DB_POINTER = BUILD / "active_seed_db.txt"
DDINTER_DIR = DATA / "raw" / "ddinter"
ZH_ALIASES = DATA / "overrides" / "drug_zh_aliases.csv"
SUPPLEMENT_FACTS = DATA / "overrides" / "supplemental_facts.json"
DOSE_RULES_FACTS = DATA / "overrides" / "dose_rules.json"
OPTIONAL_DIR = DATA / "optional"
OPTIONAL_FACTS = OPTIONAL_DIR / "public_facts.json"
SOURCE_UPDATE_META = BUILD / "source_update_meta.json"
DATASET_VERSION = "2026-05-17"
RAW_DIR = DATA / "raw"

# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
RISK_ORDER_SQL = (
    "CASE risk_level "
    "WHEN 'Contraindicated' THEN 5 "
    "WHEN 'Major' THEN 4 "
    "WHEN 'Moderate' THEN 3 "
    "WHEN 'Minor' THEN 2 "
    "WHEN 'NoKnownClinicalSignificance' THEN 1 "
    "ELSE 0 END"
)

# ---------------------------------------------------------------------------
# FAERS constants
# ---------------------------------------------------------------------------
SEVERE_FAERS_REACTIONS = {
    "DEATH", "RESPIRATORY DEPRESSION", "COMA", "LOSS OF CONSCIOUSNESS",
    "SEROTONIN SYNDROME", "QT PROLONGATION", "TORSADES DE POINTES", "OVERDOSE",
}
FAERS_SIGNAL_CACHE_SECONDS = 6 * 60 * 60

# ---------------------------------------------------------------------------
# Direct public source configuration
# ---------------------------------------------------------------------------
DIRECT_PUBLIC_SOURCES: dict[str, dict] = {
    "openfda_label":    {"label": "openFDA Drug Label",        "requires_term": True,  "default_limit": 3,  "max_limit": 10},
    "openfda_event":    {"label": "openFDA FAERS adverse event","requires_term": True,  "default_limit": 5,  "max_limit": 15},
    "dailymed":         {"label": "DailyMed SPL",              "requires_term": True,  "default_limit": 5,  "max_limit": 20},
    "rxnav":            {"label": "RxNav / RxNorm",            "requires_term": True,  "default_limit": 12, "max_limit": 30},
    "chembl":           {"label": "ChEMBL",                    "requires_term": True,  "default_limit": 8,  "max_limit": 20},
    "psychonautwiki":   {"label": "PsychonautWiki",            "requires_term": False, "default_limit": 25, "max_limit": 100},
}
PUBLIC_SYNC_SOURCE_LIMITS: dict[str, int] = {
    "rxnav": 2, "chembl": 2, "openfda_label": 1, "openfda_event": 1, "dailymed": 1,
}
PUBLIC_SYNC_TIMEOUTS: dict[str, int] = {
    "rxnav": 8, "chembl": 8, "openfda_label": 6, "openfda_event": 8, "dailymed": 6,
}
PUBLIC_SYNC_MAX_WORKERS = 8

# ---------------------------------------------------------------------------
# Bulk source configuration
# ---------------------------------------------------------------------------
BULK_SOURCE_ORDER: list[str] = [
    "ddinter", "openfda_label", "dailymed", "rxnav", "chembl",
    "psychonautwiki", "supplemental", "dose_rules", "foodrugs",
    "onsides", "pharmgkb",
]

BULK_SOURCE_CONFIG: dict[str, dict] = {
    "ddinter":       {"label": "\u91cd\u65b0\u7eb3\u5165 DDInter CSV",        "mode": "local_rebuild",     "out_dir": DDINTER_DIR},
    "openfda_label": {"label": "\u5168\u91cf\u4e0b\u8f7d openFDA \u6807\u7b7e\u5305", "mode": "download_manifest", "out_dir": RAW_DIR / "openfda_label", "large": True},
    "dailymed":      {"label": "\u5168\u91cf\u4e0b\u8f7d DailyMed SPL \u5305",       "mode": "download_manifest", "out_dir": RAW_DIR / "dailymed_spl",  "large": True},
    "rxnav":         {"label": "\u8bb0\u5f55 RxNorm \u5168\u91cf\u6765\u6e90\u72b6\u6001",  "mode": "licensed_or_external"},
    "chembl":        {"label": "\u5168\u91cf\u4e0b\u8f7d ChEMBL SQLite",             "mode": "download_manifest", "out_dir": RAW_DIR / "chembl",        "large": True},
    "psychonautwiki":{"label": "\u5168\u91cf\u540c\u6b65 PsychonautWiki",            "mode": "api_full"},
    "supplemental":  {"label": "\u91cd\u65b0\u7eb3\u5165\u672c\u5730\u8865\u5145\u4e8b\u5b9e", "mode": "local_rebuild", "out_dir": SUPPLEMENT_FACTS},
    "dose_rules":    {"label": "\u91cd\u65b0\u7eb3\u5165\u5242\u91cf\u89c4\u5219\u5e93",     "mode": "local_rebuild", "out_dir": DOSE_RULES_FACTS},
    "foodrugs":      {"label": "\u5168\u91cf\u4e0b\u8f7d FooDrugs Zenodo",            "mode": "download_manifest", "out_dir": RAW_DIR / "foodrugs",      "large": True},
    "onsides":       {"label": "\u5168\u91cf\u4e0b\u8f7d OnSIDES Release",            "mode": "download_manifest", "out_dir": RAW_DIR / "onsides",       "large": True},
    "pharmgkb":      {"label": "\u5168\u91cf\u4e0b\u8f7d PharmGKB/ClinPGx \u5305",            "mode": "download_manifest", "out_dir": RAW_DIR / "pharmgkb"},
}

PHARMGKB_BULK_FILES: list[str] = [
    "clinicalAnnotations.zip", "clinicalVariants.zip", "variantAnnotations.zip",
    "automatedAnnotations.zip", "drugLabels.zip", "guidelineAnnotations.zip",
    "relationships.zip", "drugs.zip", "genes.zip", "variants.zip",
    "chemicals.zip", "diseases.zip", "phenotypes.zip",
]

SOURCE_NAME_TO_KEY: dict[str, str] = {
    "openFDA drug label":        "openfda_label",
    "openFDA FAERS adverse event":"openfda_event",
    "DailyMed SPL":              "dailymed",
    "RxNav / RxNorm":            "rxnav",
    "ChEMBL":                    "chembl",
    "PsychonautWiki GraphQL":    "psychonautwiki",
}
