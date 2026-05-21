from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metabolic_safety_etl.i18n.openai_client import OpenAICompatibleClient, PROMPT_VERSION  # noqa: E402
from metabolic_safety_etl.i18n.placeholders import protect_text, restore_text  # noqa: E402
from metabolic_safety_etl.i18n.translation_memory import TranslationMemory  # noqa: E402
from metabolic_safety_etl.i18n.validators import clean_translation_artifacts, validate_translation  # noqa: E402


DEFAULT_BASE_URL = "https://maas-api.cn-huabei-1.xf-yun.com/v2"


class RateLimiter:
    def __init__(self, qps: float):
        self.qps = max(float(qps), 0.1)
        self.lock = threading.Lock()
        self.allow_at = time.monotonic()

    def wait(self) -> None:
        interval = 1.0 / self.qps
        with self.lock:
            now = time.monotonic()
            if now < self.allow_at:
                sleep_for = self.allow_at - now
                self.allow_at += interval
            else:
                sleep_for = 0.0
                self.allow_at = now + interval
        if sleep_for > 0:
            time.sleep(sleep_for)


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def translate_one(
    candidate: dict[str, Any],
    *,
    memory_path: Path,
    client: OpenAICompatibleClient,
    limiter: RateLimiter,
    locale: str,
    glossary_terms: list[str],
    retries: int,
    dry_run: bool,
) -> dict[str, Any]:
    source_text = str(candidate.get("source_text") or "")
    domain = str(candidate.get("domain") or "")
    field_name = str(candidate.get("field_name") or "")
    local_memory = TranslationMemory(memory_path)
    try:
        existing = local_memory.usable_translation(locale, source_text)
        if existing:
            return {"status": "cached", "text_hash": candidate.get("text_hash")}
        if dry_run:
            local_memory.upsert(
                locale=locale,
                source_text=source_text,
                translated_text="",
                domain=domain,
                field_name=field_name,
                status="pending",
                provider="openai_compatible",
                model=client.model,
                prompt_version=PROMPT_VERSION,
                validation_status="pending",
            )
            return {"status": "pending", "text_hash": candidate.get("text_hash")}
        protected = protect_text(source_text, glossary_terms=glossary_terms)
        last_error = ""
        for attempt in range(retries + 1):
            try:
                limiter.wait()
                protected_output = client.translate(protected.text, strict=attempt > 0)
                restored = restore_text(protected_output, protected.placeholders).strip().strip('"').strip()
                restored = clean_translation_artifacts(restored)
                result = validate_translation(source_text, restored, protected.placeholders, protected_output=protected_output)
                if result.ok:
                    local_memory.upsert(
                        locale=locale,
                        source_text=source_text,
                        translated_text=restored,
                        domain=domain,
                        field_name=field_name,
                        status="machine_unreviewed",
                        provider="openai_compatible",
                        model=client.model,
                        prompt_version=PROMPT_VERSION,
                        validation_status="passed",
                    )
                    return {"status": "translated", "text_hash": candidate.get("text_hash")}
                last_error = ";".join(result.reasons)
            except Exception as exc:  # noqa: BLE001 - batch tool should record and continue
                last_error = str(exc)
                time.sleep(min(8, 1 + attempt * 2))
        local_memory.upsert(
            locale=locale,
            source_text=source_text,
            translated_text="",
            domain=domain,
            field_name=field_name,
            status="failed_validation",
            provider="openai_compatible",
            model=client.model,
            prompt_version=PROMPT_VERSION,
            validation_status="failed",
            validation_reasons=last_error,
        )
        return {"status": "failed", "text_hash": candidate.get("text_hash"), "error": last_error}
    finally:
        local_memory.close()


def glossary_terms_from_candidates(candidates: list[dict[str, Any]], max_terms: int = 5000) -> list[str]:
    terms: set[str] = set()
    for row in candidates:
        text = str(row.get("source_text") or "")
        for token in text.replace(";", " ").replace(",", " ").split():
            clean = token.strip("()[]{}.,;: ")
            if 4 <= len(clean) <= 80 and any(ch.isalpha() for ch in clean):
                if clean.isupper() or any(ch.isdigit() for ch in clean):
                    terms.add(clean)
    return sorted(terms, key=len, reverse=True)[:max_terms]


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate candidate JSONL with an OpenAI-compatible Hunyuan-MT API.")
    parser.add_argument("--candidates", default="build/i18n/zh-CN/candidates.jsonl", type=Path)
    parser.add_argument("--memory", default="build/i18n/translation_memory.sqlite", type=Path)
    parser.add_argument("--locale", default="zh-CN")
    parser.add_argument("--base-url", default=os.getenv("HUNYUAN_OPENAI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.getenv("HUNYUAN_MODEL", "xophunyuan7bmt"))
    parser.add_argument("--api-key-env", default="HUNYUAN_API_KEY")
    parser.add_argument("--concurrency", default=20, type=int)
    parser.add_argument("--qps", default=20.0, type=float)
    parser.add_argument("--limit", default=0, type=int, help="Optional max candidates to process")
    parser.add_argument("--retries", default=2, type=int)
    parser.add_argument("--timeout", default=120, type=int)
    parser.add_argument("--minimal-payload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--failures", default="build/i18n/zh-CN/failed_translations.jsonl", type=Path)
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env)
    if not api_key and not args.dry_run:
        raise SystemExit(f"Missing API key. Set {args.api_key_env}=... (do not commit it).")

    candidates = list(iter_jsonl(args.candidates))
    if args.limit and args.limit > 0:
        candidates = candidates[:args.limit]
    memory = TranslationMemory(args.memory)
    pending = [row for row in candidates if not memory.usable_translation(args.locale, str(row.get("source_text") or ""))]
    memory.close()
    print(f"candidates={len(candidates)} pending={len(pending)} memory={args.memory}")
    if not pending:
        return 0

    client = OpenAICompatibleClient(
        base_url=args.base_url,
        api_key=api_key or "dry-run",
        model=args.model,
        timeout_seconds=args.timeout,
        minimal_payload=args.minimal_payload,
    )
    limiter = RateLimiter(args.qps)
    glossary_terms = glossary_terms_from_candidates(pending)
    failures: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [
            executor.submit(
                translate_one,
                row,
                memory_path=args.memory,
                client=client,
                limiter=limiter,
                locale=args.locale,
                glossary_terms=glossary_terms,
                retries=args.retries,
                dry_run=args.dry_run,
            )
            for row in pending
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            status = str(result.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
            if status == "failed":
                failures.append(result)
            if index % 100 == 0 or index == len(futures):
                print(f"processed={index}/{len(futures)} counts={counts}")
    if failures:
        write_jsonl(args.failures, failures)
        print(f"failures={len(failures)} path={args.failures}")
    print("done", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
