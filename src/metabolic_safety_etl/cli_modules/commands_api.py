"""API export and public enrichment commands: export-static-api, build-public-api."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..export import write_mobile_seed_files, write_sqlite
from ..fusion import build_dataset
from ..public_enrichment import (
    candidate_terms_from_dataset,
    dedupe_facts,
    fetch_psychonautwiki_enrichment_facts,
    fetch_public_enrichment_facts,
    load_extra_fact_files,
    load_seed_facts,
)
from ..raw_sources import load_raw_source_facts, load_remote_raw_source_facts
from ..static_api import export_static_api

from .commands_build import DEFAULT_FIXTURE
from .helpers import print_build_summary

DEFAULT_OPTIONAL_FACTS = Path("data/optional/public_facts.json")
DEFAULT_DOSE_RULE_FACTS = Path("data/overrides/dose_rules.json")


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
            workers=args.raw_source_workers,
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
            workers=args.raw_source_workers,
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
