from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.i18n.translation_memory import TranslationMemory, normalize_source_text  # noqa: E402


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def candidate_source_texts(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    return {normalize_source_text(str(row.get("source_text") or "")) for row in iter_jsonl(path) if row.get("source_text")}


def export_memory_jsonl(memory_path: Path, out_path: Path, locale: str, candidates_path: Path | None = None) -> int:
    wanted = candidate_source_texts(candidates_path)
    memory = TranslationMemory(memory_path)
    try:
        rows: list[dict[str, Any]] = []
        for entry in memory.iter_entries(locale):
            if not entry.translated_text:
                continue
            if entry.status == "failed_validation" or entry.validation_status == "failed":
                continue
            source_text = normalize_source_text(entry.source_text)
            if wanted is not None and source_text not in wanted:
                continue
            rows.append({
                "domain": entry.domain,
                "field_name": entry.field_name,
                "locale": entry.locale,
                "model": entry.model,
                "prompt_version": entry.prompt_version,
                "provider": entry.provider,
                "source_text": source_text,
                "status": entry.status,
                "translated_text": entry.translated_text,
                "validation_status": entry.validation_status or "passed",
            })
    finally:
        memory.close()
    rows.sort(key=lambda row: (row["domain"], row["field_name"], row["source_text"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export passed i18n translation memory rows to tracked JSONL.")
    parser.add_argument("--memory", default="build/i18n/translation_memory.sqlite", type=Path)
    parser.add_argument("--out", default="data/i18n/zh-CN/translation_memory.jsonl", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--candidates", type=Path, help="Optional candidate JSONL; export only matching source_text rows.")
    args = parser.parse_args()

    records = export_memory_jsonl(args.memory, args.out, args.locale, args.candidates)
    print(f"records={records} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
