from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Iterator


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_source_text(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryEntry:
    locale: str
    text_hash: str
    source_text: str
    translated_text: str
    domain: str
    field_name: str
    status: str
    provider: str
    model: str
    prompt_version: str
    validation_status: str
    validation_reasons: str
    updated_at: str


class TranslationMemory:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.ensure_schema()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def ensure_schema(self) -> None:
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_memory (
                    locale TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL DEFAULT '',
                    domain TEXT NOT NULL DEFAULT '',
                    field_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    prompt_version TEXT NOT NULL DEFAULT '',
                    validation_status TEXT NOT NULL DEFAULT '',
                    validation_reasons TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (locale, text_hash)
                )
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tm_domain ON translation_memory(locale, domain, field_name)")
            self.conn.commit()

    def get(self, locale: str, source_or_hash: str) -> MemoryEntry | None:
        key = source_or_hash if re.fullmatch(r"[0-9a-f]{64}", source_or_hash) else text_hash(source_or_hash)
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM translation_memory WHERE locale = ? AND text_hash = ?",
                (locale, key),
            ).fetchone()
        if not row:
            return None
        return MemoryEntry(**dict(row))

    def usable_translation(self, locale: str, source_text: str) -> str | None:
        entry = self.get(locale, source_text)
        if not entry or not entry.translated_text:
            return None
        if entry.status == "failed_validation" or entry.validation_status == "failed":
            return None
        return entry.translated_text

    def upsert(
        self,
        *,
        locale: str,
        source_text: str,
        translated_text: str,
        domain: str,
        field_name: str,
        status: str,
        provider: str = "",
        model: str = "",
        prompt_version: str = "",
        validation_status: str = "",
        validation_reasons: str = "",
    ) -> None:
        normalized = normalize_source_text(source_text)
        key = text_hash(normalized)
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO translation_memory (
                    locale, text_hash, source_text, translated_text, domain, field_name,
                    status, provider, model, prompt_version, validation_status,
                    validation_reasons, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(locale, text_hash) DO UPDATE SET
                    source_text = excluded.source_text,
                    translated_text = excluded.translated_text,
                    domain = excluded.domain,
                    field_name = excluded.field_name,
                    status = excluded.status,
                    provider = excluded.provider,
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    validation_status = excluded.validation_status,
                    validation_reasons = excluded.validation_reasons,
                    updated_at = excluded.updated_at
                """,
                (
                    locale,
                    key,
                    normalized,
                    translated_text,
                    domain,
                    field_name,
                    status,
                    provider,
                    model,
                    prompt_version,
                    validation_status,
                    validation_reasons,
                    now_utc(),
                ),
            )
            self.conn.commit()

    def iter_entries(self, locale: str | None = None) -> Iterator[MemoryEntry]:
        if locale:
            cursor = self.conn.execute("SELECT * FROM translation_memory WHERE locale = ?", (locale,))
        else:
            cursor = self.conn.execute("SELECT * FROM translation_memory")
        for row in cursor:
            yield MemoryEntry(**dict(row))

    def stats(self, locale: str | None = None) -> dict[str, Any]:
        params: tuple[Any, ...] = (locale,) if locale else ()
        where = "WHERE locale = ?" if locale else ""
        with self._lock:
            rows = self.conn.execute(
                f"SELECT status, COUNT(*) AS n FROM translation_memory {where} GROUP BY status",
                params,
            ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}
