"""Build / dataset commands: build, demo, import-ddinter, inspect."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..adapters.ddinter import find_ddinter_csvs, load_ddinter_csv_facts
from ..export import write_mobile_seed_files, write_sqlite
from ..fusion import build_dataset, load_facts
from ..io import read_json

from .helpers import extend_facts_from_path, print_build_summary


DEFAULT_FIXTURE = Path("data/fixtures/evidence_facts.json")


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
