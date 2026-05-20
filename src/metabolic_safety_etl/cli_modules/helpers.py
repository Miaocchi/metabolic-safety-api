"""Shared CLI helpers: argument binding shortcuts and output utilities."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..export import write_json
from ..fusion import load_facts
from ..io import read_json


def extend_facts_from_path(facts: list, path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if path.exists():
        facts.extend(load_facts(read_json(path)))


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
