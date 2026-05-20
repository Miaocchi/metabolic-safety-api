"""Source management commands: sources, remote-manifests, build-remote-source-facts, mirror-raw-sources."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..export import write_json
from ..raw_sources import (
    fetch_remote_bulk_manifests,
    mirror_remote_raw_sources,
    write_remote_raw_source_facts_json,
)
from ..source_catalog import source_status_dicts


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
    out = Path(args.out)
    summary = write_remote_raw_source_facts_json(
        source_keys,
        out,
        summary_out=Path(args.summary_out) if args.summary_out else None,
        temp_dir=Path(args.temp_dir) if args.temp_dir else None,
        max_records_per_source=args.raw_max_records or 0,
        max_parts_per_source=args.raw_stream_max_parts,
    )
    total = sum(int(row.get("facts") or 0) for row in summary.values())
    print(f"remote_source_facts={total}")
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
