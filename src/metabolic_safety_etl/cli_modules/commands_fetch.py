"""Fetch commands: individual source fetchers and the combined fetch-public."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..adapters.chembl import fetch_chembl_facts
from ..adapters.dailymed import fetch_dailymed_facts
from ..adapters.openfda import fetch_label_facts
from ..adapters.psychonautwiki import fetch_substance_facts
from ..adapters.rxnav import fetch_rxnav_facts
from ..export import write_json

from .helpers import write_facts


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
