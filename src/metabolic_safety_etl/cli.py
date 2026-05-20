"""CLI entry-point for metabolic safety ETL.

All command implementations live in ``metabolic_safety_etl.cli_modules``;
this file re-exports them so that ``build_parser`` and ``main`` continue to
work exactly as before.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

# -- Re-export public command functions/constants so that ``build_parser`` can
#    reference them by name without changing CLI behaviour. Lower-level helper
#    functions live in ``cli_modules.helpers`` and are internal implementation
#    details.
from .cli_modules.commands_build import cmd_build, cmd_demo, cmd_import_ddinter, cmd_inspect
from .cli_modules.commands_fetch import (
    cmd_fetch_chembl,
    cmd_fetch_dailymed,
    cmd_fetch_openfda,
    cmd_fetch_psychonautwiki,
    cmd_fetch_public,
    cmd_fetch_rxnav,
)
from .cli_modules.commands_api import cmd_build_public_api, cmd_export_static_api
from .cli_modules.commands_sources import (
    cmd_build_remote_source_facts,
    cmd_mirror_raw_sources,
    cmd_remote_manifests,
    cmd_sources,
)
from .cli_modules.helpers import add_term_limit_out

# Re-export constants that external callers may reference via cli.*
from .cli_modules.commands_api import DEFAULT_DOSE_RULE_FACTS, DEFAULT_OPTIONAL_FACTS
from .cli_modules.commands_build import DEFAULT_FIXTURE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local evidence fusion ETL for metabolic safety app seeds")
    parser.add_argument("--dataset-version", default=date.today().isoformat(), help="Version string written into seed outputs")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Build mobile seed files from bundled fixture data")
    demo.add_argument("--out", default="build", help="Output directory")
    demo.set_defaults(func=cmd_demo)

    build = sub.add_parser("build", help="Build mobile seed files from evidence facts JSON")
    build.add_argument("--input", required=True, help="Evidence facts JSON")
    build.add_argument("--out", default="build", help="Output directory")
    build.set_defaults(func=cmd_build)

    import_ddinter = sub.add_parser("import-ddinter", help="Build seed files from downloaded DDInter 2.0 CSV files")
    import_ddinter.add_argument("--input-dir", default="data/raw/ddinter", help="Directory containing DDInter CSV files")
    import_ddinter.add_argument("--out", default="build", help="Output directory")
    import_ddinter.add_argument("--max-interactions", type=int, default=None, help="Optional cap for faster UI tests")
    import_ddinter.add_argument("--zh-aliases", default="data/overrides/drug_zh_aliases.csv", help="Optional CSV with name_en,name_zh,aliases")
    import_ddinter.add_argument("--supplement-facts", default="data/overrides/supplemental_facts.json", help="Optional EvidenceFact JSON for substances not covered by DDInter")
    import_ddinter.add_argument("--dose-rule-facts", default=str(DEFAULT_DOSE_RULE_FACTS), help="Optional dose rule EvidenceFact JSON")
    import_ddinter.add_argument("--optional-facts", default=str(DEFAULT_OPTIONAL_FACTS), help="Optional public API EvidenceFact JSON cache")
    import_ddinter.set_defaults(func=cmd_import_ddinter)

    public_api = sub.add_parser("build-public-api", help="Build and export a fused static API with all feasible open/non-commercial sources")
    public_api.add_argument("--ddinter-dir", default="data/raw/ddinter", help="Directory containing DDInter CSV files")
    public_api.add_argument("--out", default="build", help="Output directory for mobile seed files")
    public_api.add_argument("--api-out", default="public/api", help="Output directory for the static JSON API")
    public_api.add_argument("--max-interactions", type=int, default=None, help="Optional DDInter cap for fast tests")
    public_api.add_argument("--zh-aliases", default="data/overrides/drug_zh_aliases.csv", help="Optional CSV with name_en,name_zh,aliases")
    public_api.add_argument("--supplement-facts", default="data/overrides/supplemental_facts.json")
    public_api.add_argument("--dose-rule-facts", default=str(DEFAULT_DOSE_RULE_FACTS))
    public_api.add_argument("--optional-facts", default=str(DEFAULT_OPTIONAL_FACTS), help="Cached public API EvidenceFact JSON")
    public_api.add_argument("--extra-facts", action="append", default=["data/optional", "data/overrides"], help="Extra EvidenceFact JSON file or directory; repeatable")
    public_api.add_argument("--raw-dir", default="data/raw", help="Directory containing downloaded bulk source files")
    public_api.add_argument("--raw-max-records", type=int, default=100000, help="Max records parsed per local bulk source; 0 means no cap")
    public_api.add_argument("--raw-max-files", type=int, default=0, help="Max files parsed per local bulk source; 0 means all files")
    public_api.add_argument("--raw-source-workers", type=int, default=0, help="Parallel raw source workers; 0 means auto per source")
    public_api.add_argument("--skip-raw-sources", action="store_true", help="Do not parse locally downloaded bulk source files")
    public_api.add_argument("--stream-raw-sources", action="store_true", help="Download remote bulk source parts one at a time, parse, and delete")
    public_api.add_argument("--raw-stream-sources", default="openfda_label,dailymed,chembl,foodrugs,onsides,pharmgkb", help="Comma-separated remote bulk sources to stream")
    public_api.add_argument("--raw-stream-max-parts", type=int, default=0, help="Max remote parts per source; 0 means all parts")
    public_api.add_argument("--raw-stream-temp-dir", default="", help="Optional temp directory for streamed remote parts")
    public_api.add_argument("--public-sources", default="rxnav,chembl,dailymed,openfda_label", help="Comma-separated public API sources")
    public_api.add_argument("--max-public-terms", type=int, default=120, help="Max terms selected from the fused seed for API enrichment")
    public_api.add_argument("--public-limit", type=int, default=2, help="Per-source result limit per term")
    public_api.add_argument("--public-timeout", type=int, default=20, help="HTTP timeout seconds for public APIs")
    public_api.add_argument("--public-workers", type=int, default=8, help="Parallel public API workers")
    public_api.add_argument("--psychonautwiki-pages", type=int, default=3, help="PsychonautWiki pages to fetch; 0 disables")
    public_api.add_argument("--psychonautwiki-page-size", type=int, default=100)
    public_api.add_argument("--skip-network", action="store_true", help="Build from local files only")
    public_api.set_defaults(func=cmd_build_public_api)

    add_term_limit_out(sub, "fetch-openfda", "Fetch source_text facts from openFDA labels", cmd_fetch_openfda)
    add_term_limit_out(sub, "fetch-dailymed", "Fetch DailyMed SPL metadata facts", cmd_fetch_dailymed)
    add_term_limit_out(sub, "fetch-rxnav", "Fetch RxNorm identity/mapping facts", cmd_fetch_rxnav)
    add_term_limit_out(sub, "fetch-chembl", "Fetch ChEMBL molecule facts", cmd_fetch_chembl)
    add_term_limit_out(sub, "fetch-public", "Fetch public API facts from RxNav, ChEMBL, DailyMed and openFDA", cmd_fetch_public)

    fetch_pw = sub.add_parser("fetch-psychonautwiki", help="Fetch community ROA/duration candidate facts")
    fetch_pw.add_argument("--limit", type=int, default=10)
    fetch_pw.add_argument("--offset", type=int, default=0)
    fetch_pw.add_argument("--out", required=True)
    fetch_pw.set_defaults(func=cmd_fetch_psychonautwiki)

    export_api = sub.add_parser("export-static-api", help="Export build seed JSON into a GitHub Pages compatible static JSON API")
    export_api.add_argument("--input-dir", default="build", help="Directory containing init_substances/interactions/dose_rules JSON")
    export_api.add_argument("--out", default="public/api", help="Output directory for static JSON API")
    export_api.set_defaults(func=cmd_export_static_api)

    sources = sub.add_parser("sources", help="List source integration status")
    sources.add_argument("--out", default=None)
    sources.set_defaults(func=cmd_sources)


    remote_manifests = sub.add_parser("remote-manifests", help="Fetch upstream bulk manifests and print stable fingerprints for CI caches")
    remote_manifests.add_argument("--sources", default="openfda_label,dailymed,chembl,foodrugs,onsides,pharmgkb")
    remote_manifests.add_argument("--out", default="")
    remote_manifests.add_argument("--fingerprint-out", default="")
    remote_manifests.set_defaults(func=cmd_remote_manifests)

    remote_facts = sub.add_parser("build-remote-source-facts", help="Stream selected remote bulk sources into EvidenceFact JSON for cacheable CI layers")
    remote_facts.add_argument("--sources", default="openfda_label")
    remote_facts.add_argument("--out", required=True)
    remote_facts.add_argument("--summary-out", default="")
    remote_facts.add_argument("--temp-dir", default="")
    remote_facts.add_argument("--raw-max-records", type=int, default=0)
    remote_facts.add_argument("--raw-stream-max-parts", type=int, default=0)
    remote_facts.add_argument("--workers", type=int, default=0, help="Parallel remote source workers; 0 means auto")
    remote_facts.set_defaults(func=cmd_build_remote_source_facts)

    mirror_raw = sub.add_parser(
        "mirror-raw-sources",
        help="Download upstream bulk source files into a raw mirror for offline structure analysis",
    )
    mirror_raw.add_argument(
        "--raw-dir",
        default="D:/metabolic-safety-data/raw",
        help="Persistent raw mirror directory used only for offline analysis",
    )
    mirror_raw.add_argument(
        "--sources",
        default="openfda_label,dailymed,chembl,foodrugs,onsides,pharmgkb",
        help="Comma-separated remote bulk sources",
    )
    mirror_raw.add_argument(
        "--proxy",
        default="",
        help="HTTP/HTTPS proxy, for example http://127.0.0.1:2081",
    )
    mirror_raw.add_argument("--max-parts", type=int, default=0, help="Max parts per source; 0 means all")
    mirror_raw.add_argument("--overwrite", action="store_true", help="Re-download files even if present")
    mirror_raw.set_defaults(func=cmd_mirror_raw_sources)

    inspect = sub.add_parser("inspect", help="Inspect risk distribution without writing seed files")
    inspect.add_argument("--input", required=True)
    inspect.set_defaults(func=cmd_inspect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
