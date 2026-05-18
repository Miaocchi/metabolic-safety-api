from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from .adapters.chembl import fetch_chembl_facts
from .adapters.dailymed import fetch_dailymed_facts
from .adapters.ddinter import find_ddinter_csvs, load_ddinter_csv_facts
from .adapters.openfda import fetch_label_facts
from .adapters.psychonautwiki import fetch_substance_facts
from .adapters.rxnav import fetch_rxnav_facts
from .export import write_json, write_mobile_seed_files, write_sqlite
from .fusion import build_dataset, load_facts
from .io import read_json
from .raw_sources import fetch_remote_bulk_manifests, load_raw_source_facts, load_remote_raw_source_facts, mirror_remote_raw_sources
from .public_enrichment import (
    candidate_terms_from_dataset,
    dedupe_facts,
    fetch_psychonautwiki_enrichment_facts,
    fetch_public_enrichment_facts,
    load_extra_fact_files,
    load_seed_facts,
)
from .source_catalog import source_status_dicts
from .static_api import export_static_api

DEFAULT_FIXTURE = Path("data/fixtures/evidence_facts.json")
DEFAULT_OPTIONAL_FACTS = Path("data/optional/public_facts.json")
DEFAULT_DOSE_RULE_FACTS = Path("data/overrides/dose_rules.json")


def extend_facts_from_path(facts: list, path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if path.exists():
        facts.extend(load_facts(read_json(path)))



def cmd_build(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    raw = read_json(input_path)
    facts = load_facts(raw)
    dataset = build_dataset(facts, args.dataset_version)
    out_dir = Path(args.out)
    write_mobile_seed_files(out_dir, dataset)
    write_sqlite(out_dir / "app_seed.sqlite", dataset)
    print_build_summary(dataset, out_dir)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    args.input = str(DEFAULT_FIXTURE)
    return cmd_build(args)


def cmd_import_ddinter(args: argparse.Namespace) -> int:
    paths = find_ddinter_csvs(Path(args.input_dir))
    if not paths:
        raise SystemExit(f"No DDInter CSV files found in {args.input_dir}")
    facts = load_ddinter_csv_facts(paths, args.max_interactions, Path(args.zh_aliases) if args.zh_aliases else None)
    extend_facts_from_path(facts, args.supplement_facts)
    extend_facts_from_path(facts, args.dose_rule_facts)
    extend_facts_from_path(facts, args.optional_facts)
    dataset = build_dataset(facts, args.dataset_version)
    out_dir = Path(args.out)
    write_mobile_seed_files(out_dir, dataset)
    write_sqlite(out_dir / "app_seed.sqlite", dataset)
    print(f"source_files={len(paths)}")
    print_build_summary(dataset, out_dir)
    return 0


def cmd_fetch_openfda(args: argparse.Namespace) -> int:
    return write_facts(fetch_label_facts(args.term, args.limit), Path(args.out))


def cmd_fetch_dailymed(args: argparse.Namespace) -> int:
    return write_facts(fetch_dailymed_facts(args.term, args.limit), Path(args.out))


def cmd_fetch_rxnav(args: argparse.Namespace) -> int:
    return write_facts(fetch_rxnav_facts(args.term, args.limit), Path(args.out))


def cmd_fetch_chembl(args: argparse.Namespace) -> int:
    return write_facts(fetch_chembl_facts(args.term, args.limit), Path(args.out))


def cmd_fetch_psychonautwiki(args: argparse.Namespace) -> int:
    return write_facts(fetch_substance_facts(args.limit, args.offset), Path(args.out))


def cmd_fetch_public(args: argparse.Namespace) -> int:
    facts = []
    errors: list[str] = []
    fetchers = [
        ("rxnav", lambda: fetch_rxnav_facts(args.term, args.limit)),
        ("chembl", lambda: fetch_chembl_facts(args.term, args.limit)),
        ("dailymed", lambda: fetch_dailymed_facts(args.term, args.limit)),
        ("openfda", lambda: fetch_label_facts(args.term, args.limit)),
    ]
    for name, fetcher in fetchers:
        try:
            facts.extend(fetcher())
        except Exception as exc:  # network/API failures should not stop other sources
            errors.append(f"{name}: {exc}")
    write_json(Path(args.out), [fact.to_dict() for fact in facts])
    print(f"facts={len(facts)}")
    if errors:
        print("errors=" + " | ".join(errors))
    print(f"out={Path(args.out).resolve()}")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    payload = source_status_dicts()
    if out:
        write_json(out, payload)
        print(f"out={out.resolve()}")
    else:
        for source in payload:
            print(f"{source['key']}\t{source['status']}\t{source['name']}\t{source['note']}")
    return 0




def cmd_remote_manifests(args: argparse.Namespace) -> int:
    source_keys = [item.strip() for item in args.sources.split(",") if item.strip()]
    manifests = fetch_remote_bulk_manifests(source_keys)
    payload = {
        "sources": {
            key: {
                "fingerprint": manifest.get("fingerprint"),
                "source_url": manifest.get("source_url"),
                "parts": len(manifest.get("parts") or []),
                "total_records": manifest.get("total_records"),
                "total_size_mb": manifest.get("total_size_mb"),
                "manifest": manifest,
            }
            for key, manifest in manifests.items()
        }
    }
    if args.out:
        write_json(Path(args.out), payload)
        print(f"out={Path(args.out).resolve()}")
    for key, row in payload["sources"].items():
        print(f"source={key} fingerprint={row['fingerprint']} parts={row['parts']} records={row.get('total_records')}")
    if args.fingerprint_out:
        combined = ",".join(f"{key}:{row['fingerprint']}" for key, row in sorted(payload["sources"].items()))
        Path(args.fingerprint_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.fingerprint_out).write_text(combined, encoding="utf-8")
        print(f"fingerprint_out={Path(args.fingerprint_out).resolve()}")
    return 0


def cmd_build_remote_source_facts(args: argparse.Namespace) -> int:
    source_keys = [item.strip() for item in args.sources.split(",") if item.strip()]
    facts, summary = load_remote_raw_source_facts(
        source_keys,
        temp_dir=Path(args.temp_dir) if args.temp_dir else None,
        max_records_per_source=args.raw_max_records or 0,
        max_parts_per_source=args.raw_stream_max_parts,
    )
    out = Path(args.out)
    write_json(out, [fact.to_dict() for fact in facts])
    if args.summary_out:
        write_json(Path(args.summary_out), summary)
    print(f"remote_source_facts={len(facts)}")
    print(f"remote_source_summary={summary}")
    print(f"out={out.resolve()}")
    return 0

def cmd_mirror_raw_sources(args: argparse.Namespace) -> int:
    source_keys = [item.strip() for item in args.sources.split(",") if item.strip()]
    summary = mirror_remote_raw_sources(
        source_keys,
        raw_dir=Path(args.raw_dir),
        proxy=args.proxy,
        max_parts_per_source=args.max_parts,
        overwrite=args.overwrite,
    )
    print(f"mirror_summary={summary}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    raw = read_json(Path(args.input))
    facts = load_facts(raw)
    dataset = build_dataset(facts, args.dataset_version)
    risk_counts: dict[str, int] = {}
    for interaction in dataset["interactions_core"]:
        risk_counts[interaction["risk_level"]] = risk_counts.get(interaction["risk_level"], 0) + 1
    print(f"substances={len(dataset['substances_core'])}")
    print(f"interactions={len(dataset['interactions_core'])}")
    print(f"risk_counts={risk_counts}")
    return 0



def cmd_export_static_api(args: argparse.Namespace) -> int:
    manifest = export_static_api(Path(args.input_dir), Path(args.out))
    counts = manifest.get("counts", {})
    print(f"api_version={manifest.get('api_version')}")
    print(f"substances={counts.get('substances', 0)}")
    print(f"interactions={counts.get('interactions', 0)}")
    print(f"dose_rules={counts.get('dose_rules', 0)}")
    print(f"out={Path(args.out).resolve()}")
    return 0

def cmd_build_public_api(args: argparse.Namespace) -> int:
    supplement_paths = [
        Path(args.supplement_facts),
        Path(args.dose_rule_facts),
        Path(args.optional_facts),
    ]
    facts, source_files = load_seed_facts(
        ddinter_dir=Path(args.ddinter_dir),
        fixture_path=DEFAULT_FIXTURE,
        zh_aliases=Path(args.zh_aliases) if args.zh_aliases else None,
        supplement_facts=supplement_paths,
        max_interactions=args.max_interactions,
    )

    extra_roots = [Path(item) for item in args.extra_facts]
    if extra_roots:
        facts.extend(load_extra_fact_files(extra_roots))
    if not args.skip_raw_sources:
        raw_facts, raw_summary = load_raw_source_facts(
            Path(args.raw_dir),
            max_records_per_source=args.raw_max_records or 0,
            max_files_per_source=args.raw_max_files,
        )
        facts.extend(raw_facts)
        print(f"raw_source_facts={len(raw_facts)}")
        print(f"raw_source_summary={raw_summary}")
    if args.stream_raw_sources:
        remote_keys = [item.strip() for item in args.raw_stream_sources.split(",") if item.strip()]
        remote_facts, remote_summary = load_remote_raw_source_facts(
            remote_keys,
            temp_dir=Path(args.raw_stream_temp_dir) if args.raw_stream_temp_dir else None,
            max_records_per_source=args.raw_max_records or 0,
            max_parts_per_source=args.raw_stream_max_parts,
        )
        facts.extend(remote_facts)
        print(f"remote_raw_source_facts={len(remote_facts)}")
        print(f"remote_raw_source_summary={remote_summary}")
    facts = dedupe_facts(facts)

    first_pass = build_dataset(facts, args.dataset_version)
    terms = candidate_terms_from_dataset(first_pass, args.max_public_terms)
    print(f"seed_source_files={len(source_files)}")
    print(f"seed_facts={len(facts)}")
    print(f"public_candidate_terms={len(terms)}")

    enrichment_facts = []
    public_counts: dict[str, int] = {}
    if args.skip_network:
        print("public_enrichment=skipped")
    else:
        enabled_sources = [item.strip() for item in args.public_sources.split(",") if item.strip()]
        if terms and enabled_sources:
            public_batch, public_counts = fetch_public_enrichment_facts(
                terms=terms,
                per_source_limit=args.public_limit,
                timeout=args.public_timeout,
                workers=args.public_workers,
                enabled_sources=enabled_sources,
            )
            enrichment_facts.extend(public_batch)
        if args.psychonautwiki_pages > 0:
            enrichment_facts.extend(fetch_psychonautwiki_enrichment_facts(args.psychonautwiki_pages, args.psychonautwiki_page_size))

    all_facts = dedupe_facts([*facts, *enrichment_facts])
    dataset = build_dataset(all_facts, args.dataset_version)
    out_dir = Path(args.out)
    write_mobile_seed_files(out_dir, dataset)
    write_sqlite(out_dir / "app_seed.sqlite", dataset)
    manifest = export_static_api(out_dir, Path(args.api_out))
    print_build_summary(dataset, out_dir)
    print(f"public_enrichment_facts={len(enrichment_facts)}")
    if public_counts:
        print(f"public_enrichment_counts={public_counts}")
    print(f"api_out={Path(args.api_out).resolve()}")
    print(f"api_counts={manifest.get('counts', {})}")
    return 0


def write_facts(facts, out_path: Path) -> int:
    write_json(out_path, [fact.to_dict() for fact in facts])
    print(f"facts={len(facts)}")
    print(f"out={out_path.resolve()}")
    return 0


def print_build_summary(dataset: dict, out_dir: Path) -> None:
    print(f"dataset_version={dataset['dataset_version']}")
    print(f"substances={len(dataset['substances_core'])}")
    print(f"interactions={len(dataset['interactions_core'])}")
    print(f"facts={len(dataset['evidence_facts'])}")
    print(f"out={out_dir.resolve()}")


def add_term_limit_out(sub, name: str, help_text: str, func) -> None:
    parser = sub.add_parser(name, help=help_text)
    parser.add_argument("--term", required=True, help="Drug/substance search term")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--out", required=True)
    parser.set_defaults(func=func)


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
