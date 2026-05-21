from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.i18n.translation_memory import TranslationMemory  # noqa: E402


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def seed_memory(jsonl_path: Path, memory_path: Path, default_locale: str) -> int:
    memory = TranslationMemory(memory_path)
    count = 0
    try:
        for row in iter_jsonl(jsonl_path):
            source_text = str(row.get("source_text") or "").strip()
            translated_text = str(row.get("translated_text") or "").strip()
            if not source_text or not translated_text:
                continue
            memory.upsert(
                locale=str(row.get("locale") or default_locale),
                source_text=source_text,
                translated_text=translated_text,
                domain=str(row.get("domain") or ""),
                field_name=str(row.get("field_name") or ""),
                status=str(row.get("status") or "machine_unreviewed"),
                provider=str(row.get("provider") or "checked_in_jsonl"),
                model=str(row.get("model") or ""),
                prompt_version=str(row.get("prompt_version") or ""),
                validation_status=str(row.get("validation_status") or "passed"),
                validation_reasons=str(row.get("validation_reasons") or ""),
            )
            count += 1
    finally:
        memory.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SQLite i18n translation memory from checked-in JSONL.")
    parser.add_argument("--jsonl", default="data/i18n/zh-CN/translation_memory.jsonl", type=Path)
    parser.add_argument("--memory", default="build/i18n/translation_memory.sqlite", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    args = parser.parse_args()

    records = seed_memory(args.jsonl, args.memory, args.locale)
    print(f"records={records} memory={args.memory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
