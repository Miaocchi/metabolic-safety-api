from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_mobile_seed_files(out_dir: Path, dataset: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "init_substances.json", dataset["substances_core"])
    write_json(out_dir / "init_interactions.json", dataset["interactions_core"])
    write_json(out_dir / "init_dose_rules.json", dataset.get("dose_rules_core", []))
    write_json(out_dir / "evidence_facts.json", dataset["evidence_facts"])
    write_json(
        out_dir / "manifest.json",
        {
            "dataset_version": dataset["dataset_version"],
            "substances_count": len(dataset["substances_core"]),
            "interactions_count": len(dataset["interactions_core"]),
            "dose_rules_count": len(dataset.get("dose_rules_core", [])),
            "facts_count": len(dataset["evidence_facts"]),
            "warning": "Prototype data. Do not use as clinical decision support without source review and validation.",
        },
    )


def write_sqlite(path: Path, dataset: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE substances_core (
                id TEXT PRIMARY KEY,
                name_zh TEXT,
                name_en TEXT NOT NULL,
                category TEXT,
                solubility TEXT,
                base_half_life REAL,
                base_onset REAL,
                base_duration REAL,
                identifiers_json TEXT NOT NULL,
                cyp_tags_json TEXT NOT NULL,
                source_summary_json TEXT NOT NULL,
                dataset_version TEXT NOT NULL
            );
            CREATE TABLE interactions_core (
                interaction_id TEXT PRIMARY KEY,
                substance_a_id TEXT NOT NULL,
                substance_b_id TEXT NOT NULL,
                interaction_type TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                confidence TEXT NOT NULL,
                source_tier TEXT NOT NULL,
                action TEXT NOT NULL,
                mechanism TEXT,
                note TEXT,
                evidence_refs_json TEXT NOT NULL,
                conflict_status TEXT NOT NULL,
                dataset_version TEXT NOT NULL
            );
            CREATE INDEX idx_substances_name_en ON substances_core(name_en);
            CREATE INDEX idx_substances_name_zh ON substances_core(name_zh);
            CREATE INDEX idx_interactions_a_b ON interactions_core(substance_a_id, substance_b_id);
            CREATE INDEX idx_interactions_b_a ON interactions_core(substance_b_id, substance_a_id);
            CREATE INDEX idx_interactions_risk ON interactions_core(risk_level);
            CREATE TABLE dose_rules_core (
                rule_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                match_terms_json TEXT NOT NULL,
                unit TEXT NOT NULL,
                route TEXT,
                window_hours REAL NOT NULL,
                thresholds_json TEXT NOT NULL,
                note TEXT,
                source_name TEXT,
                source_tier TEXT NOT NULL,
                source_url TEXT,
                confidence TEXT NOT NULL,
                review_status TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL,
                dataset_version TEXT NOT NULL
            );
            CREATE INDEX idx_dose_rules_subject ON dose_rules_core(subject_id);
            CREATE TABLE evidence_facts (
                fact_id TEXT PRIMARY KEY,
                fact_type TEXT NOT NULL,
                subject_ids_json TEXT NOT NULL,
                claim_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                confidence TEXT NOT NULL,
                source_tier TEXT NOT NULL,
                source_name TEXT,
                source_url TEXT,
                evidence_quote TEXT,
                extraction_method TEXT NOT NULL,
                review_status TEXT NOT NULL,
                use_policy TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        for row in dataset["substances_core"]:
            conn.execute(
                """
                INSERT INTO substances_core VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row.get("name_zh"),
                    row.get("name_en") or row["id"],
                    row.get("category"),
                    row.get("solubility"),
                    row.get("base_half_life"),
                    row.get("base_onset"),
                    row.get("base_duration"),
                    json.dumps(row.get("identifiers", {}), ensure_ascii=False),
                    json.dumps(row.get("cyp_tags", []), ensure_ascii=False),
                    json.dumps(row.get("source_summary", []), ensure_ascii=False),
                    row["dataset_version"],
                ),
            )
        for row in dataset["interactions_core"]:
            conn.execute(
                """
                INSERT INTO interactions_core VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["interaction_id"],
                    row["substance_a_id"],
                    row["substance_b_id"],
                    row["interaction_type"],
                    row["risk_level"],
                    row["confidence"],
                    row["source_tier"],
                    row["action"],
                    row.get("mechanism"),
                    row.get("note"),
                    json.dumps(row.get("evidence_refs", []), ensure_ascii=False),
                    row["conflict_status"],
                    row["dataset_version"],
                ),
            )
        for row in dataset.get("dose_rules_core", []):
            conn.execute(
                """
                INSERT INTO dose_rules_core VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["rule_id"],
                    row["subject_id"],
                    json.dumps(row.get("match_terms", []), ensure_ascii=False),
                    row.get("unit") or "mg",
                    row.get("route"),
                    row.get("window_hours") or 24,
                    json.dumps(row.get("thresholds", []), ensure_ascii=False),
                    row.get("note"),
                    row.get("source_name"),
                    row.get("source_tier") or "Label",
                    row.get("source_url"),
                    row.get("confidence") or "Unknown",
                    row.get("review_status") or "unreviewed",
                    json.dumps(row.get("evidence_refs", []), ensure_ascii=False),
                    row["dataset_version"],
                ),
            )
        for row in dataset["evidence_facts"]:
            conn.execute(
                """
                INSERT INTO evidence_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["fact_id"],
                    row["fact_type"],
                    json.dumps(row["subject_ids"], ensure_ascii=False),
                    json.dumps(row["claim"], ensure_ascii=False),
                    row["risk_level"],
                    row["confidence"],
                    row["source_tier"],
                    row.get("source_name"),
                    row.get("source_url"),
                    row.get("evidence_quote"),
                    row["extraction_method"],
                    row["review_status"],
                    row["use_policy"],
                    row["updated_at"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


