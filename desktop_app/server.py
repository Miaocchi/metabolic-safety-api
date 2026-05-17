from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import sqlite3
import sys
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from metabolic_safety_etl.adapters.chembl import fetch_chembl_facts  # noqa: E402
from metabolic_safety_etl.adapters.dailymed import fetch_dailymed_facts  # noqa: E402
from metabolic_safety_etl.adapters.ddinter import find_ddinter_csvs, load_ddinter_csv_facts  # noqa: E402
from metabolic_safety_etl.adapters.openfda import fetch_label_facts  # noqa: E402
from metabolic_safety_etl.adapters.label_bulk import fetch_dailymed_label_manifest, fetch_openfda_label_manifest  # noqa: E402
from metabolic_safety_etl.adapters.psychonautwiki import fetch_substance_facts  # noqa: E402
from metabolic_safety_etl.adapters.rxnav import fetch_rxnav_facts  # noqa: E402
from metabolic_safety_etl.dose_rules import extract_dose_rule_facts  # noqa: E402
from metabolic_safety_etl.export import write_json, write_mobile_seed_files, write_sqlite  # noqa: E402
from metabolic_safety_etl.fusion import build_dataset, load_facts  # noqa: E402
from metabolic_safety_etl.io import read_json  # noqa: E402
from metabolic_safety_etl.raw_sources import load_raw_source_facts  # noqa: E402
from metabolic_safety_etl.source_catalog import source_status_dicts  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
DATA = ROOT / "data"
BUILD = ROOT / "build"
SEED_DB = BUILD / "app_seed.sqlite"
ACTIVE_DB_POINTER = BUILD / "active_seed_db.txt"
DDINTER_DIR = DATA / "raw" / "ddinter"
ZH_ALIASES = DATA / "overrides" / "drug_zh_aliases.csv"
SUPPLEMENT_FACTS = DATA / "overrides" / "supplemental_facts.json"
DOSE_RULES_FACTS = DATA / "overrides" / "dose_rules.json"
OPTIONAL_DIR = DATA / "optional"
OPTIONAL_FACTS = OPTIONAL_DIR / "public_facts.json"
SOURCE_UPDATE_META = BUILD / "source_update_meta.json"
DATASET_VERSION = "2026-05-17"
REBUILD_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}

RISK_ORDER_SQL = "CASE risk_level WHEN 'Contraindicated' THEN 5 WHEN 'Major' THEN 4 WHEN 'Moderate' THEN 3 WHEN 'Minor' THEN 2 WHEN 'NoKnownClinicalSignificance' THEN 1 ELSE 0 END"

DIRECT_PUBLIC_SOURCES = {
    "openfda_label": {"label": "openFDA Drug Label", "requires_term": True, "default_limit": 3, "max_limit": 10},
    "dailymed": {"label": "DailyMed SPL", "requires_term": True, "default_limit": 5, "max_limit": 20},
    "rxnav": {"label": "RxNav / RxNorm", "requires_term": True, "default_limit": 12, "max_limit": 30},
    "chembl": {"label": "ChEMBL", "requires_term": True, "default_limit": 8, "max_limit": 20},
    "psychonautwiki": {"label": "PsychonautWiki", "requires_term": False, "default_limit": 25, "max_limit": 100},
}
PUBLIC_SYNC_SOURCE_LIMITS = {
    "rxnav": 2,
    "chembl": 2,
    "openfda_label": 1,
    "dailymed": 1,
}
PUBLIC_SYNC_TIMEOUTS = {
    "rxnav": 8,
    "chembl": 8,
    "openfda_label": 6,
    "dailymed": 6,
}
PUBLIC_SYNC_MAX_WORKERS = 8
RAW_DIR = DATA / "raw"

BULK_SOURCE_ORDER = [
    "ddinter",
    "openfda_label",
    "dailymed",
    "rxnav",
    "chembl",
    "psychonautwiki",
    "supplemental",
    "dose_rules",
    "foodrugs",
    "onsides",
    "pharmgkb",
]

BULK_SOURCE_CONFIG = {
    "ddinter": {"label": "\u91cd\u65b0\u7eb3\u5165 DDInter CSV", "mode": "local_rebuild", "out_dir": DDINTER_DIR},
    "openfda_label": {"label": "\u5168\u91cf\u4e0b\u8f7d openFDA \u6807\u7b7e\u5305", "mode": "download_manifest", "out_dir": RAW_DIR / "openfda_label", "large": True},
    "dailymed": {"label": "\u5168\u91cf\u4e0b\u8f7d DailyMed SPL \u5305", "mode": "download_manifest", "out_dir": RAW_DIR / "dailymed_spl", "large": True},
    "rxnav": {"label": "\u8bb0\u5f55 RxNorm \u5168\u91cf\u6765\u6e90\u72b6\u6001", "mode": "licensed_or_external"},
    "chembl": {"label": "\u5168\u91cf\u4e0b\u8f7d ChEMBL SQLite", "mode": "download_manifest", "out_dir": RAW_DIR / "chembl", "large": True},
    "psychonautwiki": {"label": "\u5168\u91cf\u540c\u6b65 PsychonautWiki", "mode": "api_full"},
    "supplemental": {"label": "\u91cd\u65b0\u7eb3\u5165\u672c\u5730\u8865\u5145\u4e8b\u5b9e", "mode": "local_rebuild", "out_dir": SUPPLEMENT_FACTS},
    "dose_rules": {"label": "\u91cd\u65b0\u7eb3\u5165\u5242\u91cf\u89c4\u5219\u5e93", "mode": "local_rebuild", "out_dir": DOSE_RULES_FACTS},
    "foodrugs": {"label": "\u5168\u91cf\u4e0b\u8f7d FooDrugs Zenodo", "mode": "download_manifest", "out_dir": RAW_DIR / "foodrugs", "large": True},
    "onsides": {"label": "\u5168\u91cf\u4e0b\u8f7d OnSIDES Release", "mode": "download_manifest", "out_dir": RAW_DIR / "onsides", "large": True},
    "pharmgkb": {"label": "\u5168\u91cf\u4e0b\u8f7d PharmGKB/ClinPGx \u5305", "mode": "download_manifest", "out_dir": RAW_DIR / "pharmgkb"},
}

PHARMGKB_BULK_FILES = [
    "clinicalAnnotations.zip",
    "clinicalVariants.zip",
    "variantAnnotations.zip",
    "automatedAnnotations.zip",
    "drugLabels.zip",
    "guidelineAnnotations.zip",
    "relationships.zip",
    "drugs.zip",
    "genes.zip",
    "variants.zip",
    "chemicals.zip",
    "diseases.zip",
    "phenotypes.zip",
]

SOURCE_NAME_TO_KEY = {
    "openFDA drug label": "openfda_label",
    "DailyMed SPL": "dailymed",
    "RxNav / RxNorm": "rxnav",
    "ChEMBL": "chembl",
    "PsychonautWiki GraphQL": "psychonautwiki",
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def guess_type(self, path: str) -> str:
        guessed = super().guess_type(path)
        if guessed.startswith("text/") or guessed in {"application/javascript", "text/javascript"}:
            if "charset=" not in guessed:
                return guessed + "; charset=utf-8"
        return guessed

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/api/seed":
            self._send_json(self._read_seed())
            return
        if parsed.path == "/api/interactions":
            self._send_json(self._query_interactions(params))
            return
        if parsed.path == "/api/check":
            self._send_json(self._check_interactions(params))
            return
        if parsed.path == "/api/sources":
            self._send_json(self._sources_payload())
            return
        if parsed.path == "/api/source-update":
            self._send_json(self._source_update(params))
            return
        if parsed.path == "/api/rebuild":
            self._send_json(self._start_rebuild_job())
            return
        if parsed.path == "/api/public-sync":
            self._send_json(self._start_public_sync_job(params))
            return
        if parsed.path == "/api/bulk-sync":
            self._send_json(self._start_bulk_sync_job(params))
            return
        if parsed.path == "/api/rebuild-status":
            self._send_json(self._rebuild_status(params))
            return
        if parsed.path == "/api/label-bulk-manifest":
            self._send_json(self._label_bulk_manifest())
            return
        if parsed.path == "/health":
            self._send_json({"ok": True})
            return
        return super().do_GET()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("desktop-app " + fmt % args + "\n")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(active_seed_db())
        conn.row_factory = sqlite3.Row
        return conn

    def _read_seed(self) -> dict:
        manifest = self._read_json(BUILD / "manifest.json")
        if not active_seed_db().exists():
            return {
                "manifest": manifest,
                "substances": self._read_json(BUILD / "init_substances.json"),
                "interactionsLoaded": False,
                "doseRules": self._read_json(BUILD / "init_dose_rules.json") if (BUILD / "init_dose_rules.json").exists() else [],
            }
        with self._connect() as conn:
            substances = [
                self._substance_row(row)
                for row in conn.execute(
                    """
                    SELECT id, name_zh, name_en, category, solubility, base_half_life,
                           base_onset, base_duration, identifiers_json, cyp_tags_json, dataset_version
                    FROM substances_core
                    ORDER BY COALESCE(name_zh, name_en), name_en
                    """
                )
            ]
            dose_rules = self._read_dose_rules(conn)
        return {
            "manifest": manifest,
            "substances": substances,
            "doseRules": dose_rules,
            "interactions": [],
            "interactionsLoaded": False,
            "evidenceFacts": [],
            "evidenceFactsLoaded": False,
        }

    def _read_dose_rules(self, conn: sqlite3.Connection) -> list[dict]:
        try:
            rows = conn.execute(
                """
                SELECT rule_id, subject_id, match_terms_json, unit, route, window_hours,
                       thresholds_json, note, source_name, source_tier, source_url,
                       confidence, review_status, evidence_refs_json, dataset_version
                FROM dose_rules_core
                ORDER BY subject_id, rule_id
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self._dose_rule_row(row) for row in rows]

    def _dose_rule_row(self, row: sqlite3.Row) -> dict:
        return {
            "rule_id": row["rule_id"],
            "subject_id": row["subject_id"],
            "match_terms": json.loads(row["match_terms_json"]),
            "unit": row["unit"],
            "route": row["route"],
            "window_hours": row["window_hours"],
            "thresholds": json.loads(row["thresholds_json"]),
            "note": row["note"],
            "source_name": row["source_name"],
            "source_tier": row["source_tier"],
            "source_url": row["source_url"],
            "confidence": row["confidence"],
            "review_status": row["review_status"],
            "evidence_refs": json.loads(row["evidence_refs_json"]),
            "dataset_version": row["dataset_version"],
        }

    def _query_interactions(self, params: dict[str, list[str]]) -> dict:
        query = (params.get("q", [""])[0] or "").strip()
        limit = min(max(_int_param(params, "limit", 50), 1), 200)
        offset = max(_int_param(params, "offset", 0), 0)
        with self._connect() as conn:
            values: list[object] = []
            where = ""
            if query:
                like = f"%{query}%"
                id_rows = conn.execute(
                    """
                    SELECT id FROM substances_core
                    WHERE id LIKE ? OR name_en LIKE ? OR COALESCE(name_zh, '') LIKE ? OR identifiers_json LIKE ?
                    ORDER BY COALESCE(name_zh, name_en), name_en
                    LIMIT 250
                    """,
                    [like, like, like, like],
                ).fetchall()
                ids = [row["id"] for row in id_rows]
                if not ids:
                    return {"query": query, "limit": limit, "offset": offset, "total": 0, "items": []}
                placeholders = ",".join("?" for _ in ids)
                where = f"WHERE i.substance_a_id IN ({placeholders}) OR i.substance_b_id IN ({placeholders})"
                values = ids + ids
            sql = f"""
                SELECT i.*, a.name_en AS a_name_en, a.name_zh AS a_name_zh,
                       b.name_en AS b_name_en, b.name_zh AS b_name_zh
                FROM interactions_core i
                JOIN substances_core a ON a.id = i.substance_a_id
                JOIN substances_core b ON b.id = i.substance_b_id
                {where}
                ORDER BY {RISK_ORDER_SQL} DESC, a.name_en, b.name_en
                LIMIT ? OFFSET ?
            """
            count_sql = f"SELECT COUNT(*) FROM interactions_core i {where}"
            total = conn.execute(count_sql, values).fetchone()[0]
            rows = conn.execute(sql, values + [limit, offset]).fetchall()
        return {
            "query": query,
            "limit": limit,
            "offset": offset,
            "total": total,
            "items": [self._interaction_row(row) for row in rows],
        }

    def _check_interactions(self, params: dict[str, list[str]]) -> dict:
        raw_ids = []
        for value in params.get("ids", []):
            raw_ids.extend(part for part in value.split(",") if part)
        ids = sorted({item.strip() for item in raw_ids if item.strip()})
        if len(ids) < 2:
            return {"items": []}
        placeholders = ",".join("?" for _ in ids)
        sql = f"""
            SELECT i.*, a.name_en AS a_name_en, a.name_zh AS a_name_zh,
                   b.name_en AS b_name_en, b.name_zh AS b_name_zh
            FROM interactions_core i
            JOIN substances_core a ON a.id = i.substance_a_id
            JOIN substances_core b ON b.id = i.substance_b_id
            WHERE i.substance_a_id IN ({placeholders}) AND i.substance_b_id IN ({placeholders})
            ORDER BY {RISK_ORDER_SQL} DESC, a.name_en, b.name_en
        """
        with self._connect() as conn:
            rows = conn.execute(sql, ids + ids).fetchall()
        return {"items": [self._interaction_row(row) for row in rows]}

    def _sources_payload(self) -> dict:
        meta = self._read_json(SOURCE_UPDATE_META)
        if not isinstance(meta, dict):
            meta = {}
        optional_counts = optional_fact_counts_by_source()
        optional_count = sum(optional_counts.values())
        items = []
        direct_keys = set(DIRECT_PUBLIC_SOURCES)
        for source in source_status_dicts():
            row = dict(source)
            row["is_direct_public"] = row["key"] in direct_keys
            row["can_update"] = row["status"] in {"connected_api", "connected_api_and_local_bulk", "connected_local_csv", "connected_local_json", "connected_local_bulk"}
            row["can_bulk_update"] = row["key"] in BULK_SOURCE_CONFIG
            row["bulk_update_label"] = BULK_SOURCE_CONFIG.get(row["key"], {}).get("label")
            row["bulk_update_mode"] = BULK_SOURCE_CONFIG.get(row["key"], {}).get("mode")
            row["bulk_update_large"] = bool(BULK_SOURCE_CONFIG.get(row["key"], {}).get("large"))
            row["last_update"] = meta.get(row["key"])
            row["optional_facts_count"] = optional_counts.get(row["key"], 0) if row["key"] in direct_keys else None
            items.append(row)
        return {"items": items, "optionalFactsCount": optional_count, "updateMeta": meta}

    def _source_update(self, params: dict[str, list[str]]) -> dict:
        key = (params.get("key", [""])[0] or "").strip()
        if key not in DIRECT_PUBLIC_SOURCES:
            return {"ok": False, "error": "unsupported_source", "message": "只能直接更新非商业公开 API 源。"}
        config = DIRECT_PUBLIC_SOURCES[key]
        term = (params.get("term", [""])[0] or "").strip()
        if config["requires_term"] and not term:
            return {"ok": False, "error": "term_required", "message": "该数据源需要输入药物/物质关键词。"}
        limit = min(max(_int_param(params, "limit", int(config["default_limit"])), 1), int(config["max_limit"]))
        try:
            facts = fetch_direct_public_facts(key, term, limit)
            stored = append_optional_facts(facts)
            meta = update_source_meta(key, {"term": term, "limit": limit, "facts": len(facts)})
            return {
                "ok": True,
                "key": key,
                "label": config["label"],
                "factsFetched": len(facts),
                "optionalFactsCount": stored,
                "lastUpdate": meta.get(key),
                "message": f"已获取 {len(facts)} 条候选事实。点击重建本地库后并入桌面种子库。",
            }
        except Exception as exc:
            return {"ok": False, "key": key, "error": type(exc).__name__, "message": str(exc)}

    def _start_rebuild_job(self) -> dict:
        if REBUILD_LOCK.locked():
            running = next((job for job in JOBS.values() if job.get("status") == "running"), None)
            return {"ok": True, "jobId": running.get("id") if running else None, "alreadyRunning": True}
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"id": job_id, "status": "running", "progress": 0, "message": "准备全量重建..."}
        thread = threading.Thread(target=run_rebuild_job, args=(job_id,), daemon=True)
        thread.start()
        return {"ok": True, "jobId": job_id, "alreadyRunning": False}

    def _start_public_sync_job(self, params: dict[str, list[str]]) -> dict:
        if REBUILD_LOCK.locked():
            running = next((job for job in JOBS.values() if job.get("status") == "running"), None)
            return {"ok": True, "jobId": running.get("id") if running else None, "alreadyRunning": True}
        max_terms = _int_param(params, "maxTerms", 0)
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"id": job_id, "status": "running", "progress": 0, "message": "准备联网同步公开源..."}
        thread = threading.Thread(target=run_public_sync_job, args=(job_id, max_terms or None), daemon=True)
        thread.start()
        return {"ok": True, "jobId": job_id, "alreadyRunning": False}

    def _start_bulk_sync_job(self, params: dict[str, list[str]]) -> dict:
        if REBUILD_LOCK.locked():
            running = next((job for job in JOBS.values() if job.get("status") == "running"), None)
            return {"ok": True, "jobId": running.get("id") if running else None, "alreadyRunning": True}
        key = (params.get("key", ["all"])[0] or "all").strip()
        if key != "all" and key not in BULK_SOURCE_CONFIG:
            return {"ok": False, "error": "unsupported_source", "message": "\u8fd9\u4e2a\u6e90\u6ca1\u6709\u53ef\u6267\u884c\u7684\u5168\u91cf\u62c9\u53d6\u9002\u914d\u5668\u3002"}
        job_id = uuid.uuid4().hex
        label = "\u6240\u6709\u53ef\u7528\u975e\u5546\u4e1a\u6e90" if key == "all" else BULK_SOURCE_CONFIG[key]["label"]
        JOBS[job_id] = {"id": job_id, "status": "running", "progress": 0, "message": f"\u51c6\u5907\u5168\u91cf\u62c9\u53d6\uff1a{label}..."}
        thread = threading.Thread(target=run_bulk_sync_job, args=(job_id, key), daemon=True)
        thread.start()
        return {"ok": True, "jobId": job_id, "alreadyRunning": False}

    def _rebuild_status(self, params: dict[str, list[str]]) -> dict:
        job_id = (params.get("job", [""])[0] or "").strip()
        job = JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "job_not_found", "message": "没有找到这个重建任务。"}
        return {"ok": True, **job}

    def _label_bulk_manifest(self) -> dict:
        payload = {"ok": True, "items": []}
        try:
            payload["items"].append(fetch_openfda_label_manifest())
        except Exception as exc:
            payload["items"].append({"source": "openfda_label", "error": type(exc).__name__, "message": str(exc)})
        try:
            payload["items"].append(fetch_dailymed_label_manifest())
        except Exception as exc:
            payload["items"].append({"source": "dailymed", "error": type(exc).__name__, "message": str(exc)})
        return payload

    def _substance_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name_zh": row["name_zh"],
            "name_en": row["name_en"],
            "category": row["category"],
            "solubility": row["solubility"],
            "base_half_life": row["base_half_life"],
            "base_onset": row["base_onset"],
            "base_duration": row["base_duration"],
            "identifiers": json.loads(row["identifiers_json"]),
            "cyp_tags": json.loads(row["cyp_tags_json"]),
            "dataset_version": row["dataset_version"],
        }

    def _interaction_row(self, row: sqlite3.Row) -> dict:
        return {
            "interaction_id": row["interaction_id"],
            "substance_a_id": row["substance_a_id"],
            "substance_b_id": row["substance_b_id"],
            "substance_a_name": row["a_name_zh"] or row["a_name_en"],
            "substance_b_name": row["b_name_zh"] or row["b_name_en"],
            "substance_a_name_en": row["a_name_en"],
            "substance_b_name_en": row["b_name_en"],
            "interaction_type": row["interaction_type"],
            "risk_level": row["risk_level"],
            "confidence": row["confidence"],
            "source_tier": row["source_tier"],
            "action": row["action"],
            "mechanism": row["mechanism"],
            "note": row["note"],
            "conflict_status": row["conflict_status"],
        }

    def _read_json(self, path: Path):
        if not path.exists():
            return [] if path.name.endswith(".json") else {}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _send_json(self, payload) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _int_param(params: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(params.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def active_seed_db() -> Path:
    if ACTIVE_DB_POINTER.exists():
        name = ACTIVE_DB_POINTER.read_text(encoding="utf-8").strip()
        candidate = BUILD / name
        if candidate.exists() and candidate.parent == BUILD:
            return candidate
    return SEED_DB


def fetch_direct_public_facts(key: str, term: str, limit: int, timeout: int | None = None):
    timeout_value = timeout or 30
    if key == "openfda_label":
        return fetch_label_facts(term, limit, timeout=timeout_value)
    if key == "dailymed":
        return fetch_dailymed_facts(term, limit, timeout=timeout_value)
    if key == "rxnav":
        return fetch_rxnav_facts(term, limit, timeout=timeout_value)
    if key == "chembl":
        return fetch_chembl_facts(term, limit, timeout=timeout_value)
    if key == "psychonautwiki":
        return fetch_substance_facts(limit=limit, offset=0)
    raise ValueError(f"Unsupported source: {key}")

def append_optional_facts(facts) -> int:
    OPTIONAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if OPTIONAL_FACTS.exists():
        existing = read_json(OPTIONAL_FACTS)
    by_id = {item.get("fact_id"): item for item in existing if item.get("fact_id")}
    for fact in facts:
        item = fact.to_dict()
        by_id[item["fact_id"]] = item
    payload = sorted(by_id.values(), key=lambda item: (item.get("source_name", ""), item.get("fact_id", "")))
    write_json(OPTIONAL_FACTS, payload)
    return len(payload)


def optional_fact_counts_by_source() -> dict[str, int]:
    if not OPTIONAL_FACTS.exists():
        return {}
    counts: dict[str, int] = {}
    try:
        for item in read_json(OPTIONAL_FACTS):
            key = SOURCE_NAME_TO_KEY.get(item.get("source_name", ""))
            if key:
                counts[key] = counts.get(key, 0) + 1
    except Exception:
        return {}
    return counts


def update_source_meta(key: str, detail: dict) -> dict:
    meta = {}
    if SOURCE_UPDATE_META.exists():
        loaded = read_json(SOURCE_UPDATE_META)
        if isinstance(loaded, dict):
            meta = loaded
    from metabolic_safety_etl.schemas import now_utc

    meta[key] = {"updated_at": now_utc(), **detail}
    write_json(SOURCE_UPDATE_META, meta)
    return meta


def update_job(job_id: str, progress: int, message: str, **extra) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    job.update({"progress": max(0, min(progress, 100)), "message": message, **extra})


def run_rebuild_job(job_id: str) -> None:
    with REBUILD_LOCK:
        try:
            result = rebuild_seed_dataset(lambda progress, message: update_job(job_id, progress, message))
            update_job(job_id, 100, "本地库已重建。页面会重新加载数据。", status="done", manifest=result.get("manifest", {}))
        except Exception as exc:
            update_job(job_id, 100, str(exc), status="error", error=type(exc).__name__)


def run_public_sync_job(job_id: str, max_terms: int | None = None) -> None:
    with REBUILD_LOCK:
        try:
            sync_public_sources(lambda progress, message: update_job(job_id, progress, message), max_terms=max_terms)
            result = rebuild_seed_dataset(lambda progress, message: update_job(job_id, 70 + int(progress * 0.3), message))
            update_job(job_id, 100, "公开源同步完成，且本地库已重建。", status="done", manifest=result.get("manifest", {}))
        except Exception as exc:
            update_job(job_id, 100, str(exc), status="error", error=type(exc).__name__)




def run_bulk_sync_job(job_id: str, key: str) -> None:
    with REBUILD_LOCK:
        try:
            result = bulk_sync_sources(key, lambda progress, message: update_job(job_id, progress, message))
            if result.get("needs_rebuild"):
                update_job(job_id, 88, "\u5df2\u62c9\u53d6\u9700\u8981\u5165\u5e93\u7684\u6e90\uff0c\u5f00\u59cb\u91cd\u5efa\u672c\u5730\u68c0\u7d22\u5e93...")
                rebuilt = rebuild_seed_dataset(lambda progress, message: update_job(job_id, 88 + int(progress * 0.11), message))
                result["manifest"] = rebuilt.get("manifest", {})
            update_job(job_id, 100, result.get("message") or "\u5168\u91cf\u62c9\u53d6\u4efb\u52a1\u5b8c\u6210\u3002", status="done", bulk=result)
        except Exception as exc:
            update_job(job_id, 100, str(exc), status="error", error=type(exc).__name__)


def bulk_sync_sources(key: str, progress=None) -> dict:
    keys = BULK_SOURCE_ORDER if key == "all" else [key]
    results = []
    needs_rebuild = False
    downloaded_files = 0
    skipped_files = 0
    errors = 0
    total = max(len(keys), 1)
    for index, source_key in enumerate(keys, start=1):
        start = int((index - 1) / total * 86)
        span = max(1, int(86 / total))

        def step(value: int, message: str) -> None:
            if progress:
                progress(start + int(max(0, min(value, 100)) * span / 100), message)

        config = BULK_SOURCE_CONFIG.get(source_key, {})
        step(0, f"\u5168\u91cf\u5904\u7406 {index}/{total}\uff1a{config.get('label', source_key)}...")
        result = bulk_sync_one_source(source_key, step)
        results.append(result)
        needs_rebuild = needs_rebuild or bool(result.get("needs_rebuild"))
        downloaded_files += int(result.get("downloaded_files") or 0)
        skipped_files += int(result.get("skipped_files") or 0)
        errors += int(result.get("errors") or 0)
    return {
        "key": key,
        "sources": results,
        "needs_rebuild": needs_rebuild,
        "downloaded_files": downloaded_files,
        "skipped_files": skipped_files,
        "errors": errors,
        "message": f"\u5168\u91cf\u62c9\u53d6\u5b8c\u6210\uff1a\u5904\u7406 {len(results)} \u4e2a\u6e90\uff0c\u4e0b\u8f7d {downloaded_files} \u4e2a\u6587\u4ef6\uff0c\u590d\u7528 {skipped_files} \u4e2a\u5df2\u5b58\u5728\u6587\u4ef6\uff0c\u9519\u8bef {errors} \u4e2a\u3002",
    }


def bulk_sync_one_source(key: str, progress=None) -> dict:
    config = BULK_SOURCE_CONFIG[key]
    mode = config.get("mode")
    if mode == "local_rebuild":
        target = config.get("out_dir")
        if isinstance(target, Path) and target.is_dir():
            files = [item for item in target.glob("**/*") if item.is_file()]
            size = sum(item.stat().st_size for item in files)
        elif isinstance(target, Path) and target.exists():
            files = [target]
            size = target.stat().st_size
        else:
            files = []
            size = 0
        update_source_meta(key, {"mode": "local_source_ready", "files": len(files), "bytes": size, "path": str(target.relative_to(ROOT)) if isinstance(target, Path) and target.exists() else str(target)})
        if progress:
            progress(100, f"{config['label']}\uff1a\u53d1\u73b0 {len(files)} \u4e2a\u672c\u5730\u6587\u4ef6\uff0c\u5c06\u5728\u91cd\u5efa\u65f6\u7eb3\u5165\u3002")
        return {"key": key, "mode": mode, "files": len(files), "bytes": size, "needs_rebuild": True, "downloaded_files": 0, "skipped_files": len(files), "errors": 0}

    if mode == "api_full" and key == "psychonautwiki":
        facts = []
        offset = 0
        limit = 100
        max_pages = 40
        for page in range(max_pages):
            if progress:
                progress(int(page / max_pages * 80), f"PsychonautWiki \u5168\u91cf\u9875 {page + 1}/{max_pages}\uff0coffset={offset}...")
            batch = fetch_substance_facts(limit=limit, offset=offset)
            if not batch:
                break
            facts.extend(batch)
            if len(batch) < max(5, limit // 3):
                break
            offset += limit
        stored = append_optional_facts(facts)
        update_source_meta(key, {"mode": "api_full", "facts": len(facts), "optional_total": stored, "pages": (offset // limit) + 1})
        if progress:
            progress(100, f"PsychonautWiki \u5168\u91cf\u5019\u9009\u5df2\u4fdd\u5b58\uff1a{len(facts)} \u6761\u4e8b\u5b9e\uff0c\u7d2f\u8ba1 {stored} \u6761\u3002")
        return {"key": key, "mode": mode, "facts": len(facts), "needs_rebuild": True, "downloaded_files": 0, "skipped_files": 0, "errors": 0}

    if mode == "licensed_or_external":
        note = "RxNorm \u5168\u91cf\u5305\u901a\u5e38\u901a\u8fc7 RxNav-in-a-Box / RxNorm release \u83b7\u53d6\uff0c\u90e8\u5206\u8bcd\u8868\u9700\u8981 UMLS \u8bb8\u53ef\uff1b\u672c\u5730\u53ea\u8bb0\u5f55\u6765\u6e90\u72b6\u6001\uff0c\u4e0d\u81ea\u52a8\u4e0b\u8f7d\u3002"
        update_source_meta(key, {"mode": "external_required", "note": note})
        if progress:
            progress(100, note)
        return {"key": key, "mode": mode, "message": note, "needs_rebuild": False, "downloaded_files": 0, "skipped_files": 0, "errors": 0}

    if mode == "download_manifest":
        manifest = fetch_bulk_manifest(key)
        parts = manifest.get("parts", []) or []
        out_dir = config["out_dir"]
        result = download_manifest_parts(parts, out_dir, progress=progress)
        update_source_meta(key, {
            "mode": "bulk_download",
            "files": result["downloaded_files"] + result["skipped_files"],
            "downloaded_files": result["downloaded_files"],
            "skipped_files": result["skipped_files"],
            "errors": result["errors"],
            "records": manifest.get("total_records"),
            "total_size_mb": manifest.get("total_size_mb"),
            "out_dir": str(out_dir.relative_to(ROOT)),
        })
        result.update({"key": key, "mode": mode, "records": manifest.get("total_records"), "total_size_mb": manifest.get("total_size_mb"), "needs_rebuild": False})
        return result

    raise ValueError(f"Unsupported bulk source mode: {key} / {mode}")


def fetch_bulk_manifest(key: str) -> dict:
    if key == "openfda_label":
        return fetch_openfda_label_manifest()
    if key == "dailymed":
        return fetch_dailymed_label_manifest()
    if key == "chembl":
        return fetch_chembl_bulk_manifest()
    if key == "foodrugs":
        return fetch_zenodo_manifest("8192515", "foodrugs")
    if key == "onsides":
        return fetch_github_release_manifest("tatonetti-lab", "onsides", "onsides")
    if key == "pharmgkb":
        return fetch_pharmgkb_bulk_manifest()
    raise ValueError(f"No bulk manifest adapter for {key}")


def fetch_chembl_bulk_manifest() -> dict:
    url = "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/"
    with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-local"}), timeout=45) as response:
        html = response.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(r'href="([^"]+)"', html)))
    parts = []
    for name in names:
        if re.search(r"chembl_.*_sqlite\.tar\.gz$", name) or re.search(r"chembl_.*_sqlite\.tar\.gz\.sha256sum$", name):
            parts.append({"name": name, "url": urljoin(url, name), "records": None, "size_mb": None})
    return {"source": "chembl", "source_url": url, "parts": parts, "total_records": None, "total_size_mb": None}


def fetch_zenodo_manifest(record_id: str, source: str) -> dict:
    url = f"https://zenodo.org/api/records/{record_id}"
    with urlopen(Request(url, headers={"User-Agent": "metabolic-safety-local"}), timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parts = []
    for item in payload.get("files", []) or []:
        links = item.get("links") or {}
        file_url = links.get("self") or links.get("download")
        if not file_url:
            continue
        size = item.get("size") or 0
        parts.append({"name": item.get("key") or Path(urlparse(file_url).path).name, "url": file_url, "records": None, "size_mb": round(size / 1024 / 1024, 2) if size else None})
    return {"source": source, "source_url": url, "parts": parts, "total_records": None, "total_size_mb": sum(part.get("size_mb") or 0 for part in parts)}


def fetch_github_release_manifest(owner_repo: str, repo_name: str, source: str) -> dict:
    api_url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    try:
        with urlopen(Request(api_url, headers={"User-Agent": "metabolic-safety-local"}), timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts = [
            {"name": asset.get("name"), "url": asset.get("browser_download_url"), "records": None, "size_mb": round((asset.get("size") or 0) / 1024 / 1024, 2)}
            for asset in payload.get("assets", []) or []
            if asset.get("browser_download_url")
        ]
        if parts:
            return {"source": source, "source_url": api_url, "parts": parts, "total_records": None, "total_size_mb": sum(part.get("size_mb") or 0 for part in parts)}
    except Exception:
        pass
    default_branch = "main"
    try:
        repo_api = f"https://api.github.com/repos/{owner_repo}"
        with urlopen(Request(repo_api, headers={"User-Agent": "metabolic-safety-local"}), timeout=20) as response:
            repo_payload = json.loads(response.read().decode("utf-8"))
            default_branch = repo_payload.get("default_branch") or default_branch
    except Exception:
        pass
    archive_url = f"https://github.com/{owner_repo}/archive/refs/heads/{default_branch}.zip"
    return {"source": source, "source_url": f"https://github.com/{owner_repo}", "parts": [{"name": f"{repo_name}-{default_branch}.zip", "url": archive_url, "records": None, "size_mb": None}], "total_records": None, "total_size_mb": None}


def fetch_pharmgkb_bulk_manifest() -> dict:
    base = "https://api.pharmgkb.org/v1/download/file/data/"
    parts = []
    for name in PHARMGKB_BULK_FILES:
        url = base + name
        size_mb = None
        try:
            req = Request(url, headers={"User-Agent": "metabolic-safety-local"}, method="HEAD")
            with urlopen(req, timeout=12) as response:
                size = int(response.headers.get("Content-Length") or 0)
                size_mb = round(size / 1024 / 1024, 2) if size else None
        except Exception:
            continue
        parts.append({"name": name, "url": url, "records": None, "size_mb": size_mb})
    return {"source": "pharmgkb", "source_url": base, "parts": parts, "total_records": None, "total_size_mb": sum(part.get("size_mb") or 0 for part in parts)}


def download_manifest_parts(parts: list[dict], out_dir: Path, progress=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    errors = 0
    total = max(len(parts), 1)
    for index, part in enumerate(parts, start=1):
        url = part.get("url")
        if not url:
            errors += 1
            continue
        name = part.get("name") or Path(urlparse(url).path).name or f"part_{index}.bin"
        target = out_dir / safe_filename(name)
        if progress:
            progress(int((index - 1) / total * 100), f"\u4e0b\u8f7d {index}/{len(parts)}\uff1a{target.name}")
        try:
            status = download_url(url, target)
            if status == "skipped":
                skipped += 1
            else:
                downloaded += 1
        except Exception as exc:
            errors += 1
            if progress:
                progress(int(index / total * 100), f"\u4e0b\u8f7d\u5931\u8d25\uff0c\u5df2\u8df3\u8fc7\uff1a{target.name}\uff08{type(exc).__name__}\uff09")
    if progress:
        progress(100, f"\u4e0b\u8f7d\u5b8c\u6210\uff1a\u65b0\u589e {downloaded} \u4e2a\uff0c\u590d\u7528 {skipped} \u4e2a\uff0c\u9519\u8bef {errors} \u4e2a\u3002")
    return {"downloaded_files": downloaded, "skipped_files": skipped, "errors": errors, "out_dir": str(out_dir)}


def download_url(url: str, target: Path) -> str:
    if target.exists() and target.stat().st_size > 0:
        return "skipped"
    tmp = target.with_name(target.name + ".part")
    req = Request(url, headers={"User-Agent": "metabolic-safety-local"})
    with urlopen(req, timeout=60) as response, tmp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    tmp.replace(target)
    return "downloaded"


def safe_filename(value: str) -> str:
    name = Path(urlparse(value).path).name if "/" in value else value
    name = re.sub(r"[^A-Za-z0-9._+\-()\[\] ]+", "_", name).strip(" .")
    return name or "download.bin"


def sync_public_sources(progress=None, max_terms: int | None = None) -> None:
    def step(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    terms = public_sync_terms(max_terms)
    tasks = [
        (key, term, limit)
        for term in terms
        for key, limit in PUBLIC_SYNC_SOURCE_LIMITS.items()
        if should_query_public_source(key, term)
    ]
    attempted_counts = {key: 0 for key in PUBLIC_SYNC_SOURCE_LIMITS}
    for key, _, _ in tasks:
        attempted_counts[key] = attempted_counts.get(key, 0) + 1

    total_tasks = max(len(tasks), 1)
    fetched: list = []
    errors_by_source = {key: 0 for key in PUBLIC_SYNC_SOURCE_LIMITS}
    step(3, f"准备并发同步公开检索源：{len(terms)} 个核心物质，{len(tasks)} 个 API 请求...")
    with ThreadPoolExecutor(max_workers=PUBLIC_SYNC_MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_direct_public_facts, key, term, limit, PUBLIC_SYNC_TIMEOUTS.get(key, 8)): (key, term)
            for key, term, limit in tasks
        }
        for done, future in enumerate(as_completed(future_map), start=1):
            key, term = future_map[future]
            label = DIRECT_PUBLIC_SOURCES.get(key, {}).get("label", key)
            try:
                batch = future.result()
                fetched.extend(batch)
                message = f"公开源同步 {done}/{total_tasks}：{label} · {term}，命中 {len(batch)} 条"
            except Exception as exc:
                errors_by_source[key] = errors_by_source.get(key, 0) + 1
                message = f"公开源同步 {done}/{total_tasks}：{label} · {term} 超时/无结果，已跳过（{type(exc).__name__}）"
            step(3 + int(done / total_tasks * 62), message)

    step(66, "同步 PsychonautWiki 批量候选...")
    try:
        psychonaut_facts = fetch_substance_facts(limit=50, offset=0)
        fetched.extend(psychonaut_facts)
        attempted_counts["psychonautwiki"] = 1
    except Exception:
        errors_by_source["psychonautwiki"] = errors_by_source.get("psychonautwiki", 0) + 1
    stored = append_optional_facts(fetched)
    record_public_sync_meta(fetched, stored, attempted_counts, errors_by_source)
    step(70, f"公开源候选已保存：新增/更新 {len(fetched)} 条，累计 {stored} 条。")


def public_sync_terms(max_terms: int | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    if ZH_ALIASES.exists():
        with ZH_ALIASES.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                add_public_sync_term(terms, seen, row.get("name_en"))
                for alias in (row.get("aliases") or "").split("|"):
                    if alias.isascii():
                        add_public_sync_term(terms, seen, alias)
                if max_terms and len(terms) >= max_terms:
                    return terms[:max_terms]

    rows = read_json(BUILD / "init_substances.json") if (BUILD / "init_substances.json").exists() else []
    for row in rows:
        name = row.get("name_en") or row.get("id")
        add_public_sync_term(terms, seen, name)
        if max_terms and len(terms) >= max_terms:
            break
    return terms[:max_terms] if max_terms else terms


def add_public_sync_term(terms: list[str], seen: set[str], value: object) -> None:
    term = str(value or "").strip()
    key = term.lower()
    if not term or key in seen or not looks_like_public_api_term(term):
        return
    terms.append(term)
    seen.add(key)


def looks_like_public_api_term(term: str) -> bool:
    if not re.search(r"[A-Za-z]", term):
        return False
    if len(term) < 2 or len(term) > 80:
        return False
    if term[0].isdigit():
        return False
    if re.search(r"[{}\[\]\\]", term):
        return False
    if term.count(" ") > 5:
        return False
    noisy_words = (" oral ", " tablet", " capsule", " pack", " kit", " injection", " solution")
    lowered = f" {term.lower()} "
    return not any(word in lowered for word in noisy_words)


def should_query_public_source(key: str, term: str) -> bool:
    if key in {"openfda_label", "dailymed"}:
        return looks_like_public_api_term(term)
    return True


def record_public_sync_meta(facts, stored: int, attempted_counts: dict[str, int] | None = None, errors_by_source: dict[str, int] | None = None) -> None:
    from metabolic_safety_etl.schemas import now_utc

    counts: dict[str, int] = {}
    for fact in facts:
        key = SOURCE_NAME_TO_KEY.get(fact.source_name)
        if key:
            counts[key] = counts.get(key, 0) + 1
    meta = {}
    if SOURCE_UPDATE_META.exists():
        loaded = read_json(SOURCE_UPDATE_META)
        if isinstance(loaded, dict):
            meta = loaded
    timestamp = now_utc()
    attempted_counts = attempted_counts or {}
    errors_by_source = errors_by_source or {}
    for key in sorted(set(counts) | set(attempted_counts) | set(errors_by_source)):
        meta[key] = {
            "updated_at": timestamp,
            "mode": "public_sync",
            "facts": counts.get(key, 0),
            "attempted": attempted_counts.get(key, 0),
            "errors": errors_by_source.get(key, 0),
            "optional_total": stored,
            "timeout_seconds": PUBLIC_SYNC_TIMEOUTS.get(key),
        }
    write_json(SOURCE_UPDATE_META, meta)

def rebuild_seed_dataset(progress=None) -> dict:
    def step(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    step(5, "扫描 DDInter 全量 CSV...")
    paths = find_ddinter_csvs(DDINTER_DIR)
    if not paths:
        raise RuntimeError(f"No DDInter CSV files found in {DDINTER_DIR}")
    step(15, f"读取 DDInter CSV：{len(paths)} 个文件...")
    facts = load_ddinter_csv_facts(paths, None, ZH_ALIASES if ZH_ALIASES.exists() else None)
    step(45, f"DDInter 已载入：{len(facts)} 条事实，合并本地补充事实...")
    if SUPPLEMENT_FACTS.exists():
        facts.extend(load_facts(read_json(SUPPLEMENT_FACTS)))
    if DOSE_RULES_FACTS.exists():
        facts.extend(load_facts(read_json(DOSE_RULES_FACTS)))
    step(55, "合并已拉取的公开源候选事实...")
    if OPTIONAL_FACTS.exists():
        facts.extend(load_facts(read_json(OPTIONAL_FACTS)))
    step(60, "抽取已下载的 openFDA/DailyMed/ChEMBL/FooDrugs/OnSIDES/PharmGKB 本地全量包...")
    raw_facts, raw_summary = load_raw_source_facts(RAW_DIR, max_records_per_source=100000, max_files_per_source=0)
    facts.extend(raw_facts)
    step(65, f"本地全量包候选已融合：{len(raw_facts)} 条；{raw_summary}")
    step(68, f"执行多源融合：{len(facts)} 条证据事实...")
    dataset = build_dataset(facts, DATASET_VERSION)
    step(78, "写入 JSON 种子文件...")
    write_mobile_seed_files(BUILD, dataset)
    step(86, "写入 SQLite 检索库...")
    next_db = BUILD / f"app_seed.{DATASET_VERSION}.{len(dataset['evidence_facts'])}.{int(time.time())}.sqlite"
    write_sqlite(next_db, dataset)
    step(96, "切换当前活跃 SQLite...")
    ACTIVE_DB_POINTER.write_text(next_db.name, encoding="utf-8")
    manifest = read_json(BUILD / "manifest.json")
    record_rebuild_source_meta(manifest, len(paths))
    return {"manifest": manifest, "dataset": dataset}


def record_rebuild_source_meta(manifest: dict, ddinter_files: int) -> None:
    from metabolic_safety_etl.schemas import now_utc

    meta = {}
    if SOURCE_UPDATE_META.exists():
        loaded = read_json(SOURCE_UPDATE_META)
        if isinstance(loaded, dict):
            meta = loaded
    timestamp = now_utc()
    meta["ddinter"] = {
        "updated_at": timestamp,
        "mode": "included_in_full_rebuild",
        "files": ddinter_files,
        "substances": manifest.get("substances_count"),
        "interactions": manifest.get("interactions_count"),
        "facts": manifest.get("facts_count"),
    }
    if SUPPLEMENT_FACTS.exists():
        meta["supplemental"] = {
            "updated_at": timestamp,
            "mode": "included_in_full_rebuild",
            "file": str(SUPPLEMENT_FACTS.relative_to(ROOT)),
        }
    if DOSE_RULES_FACTS.exists():
        meta["dose_rules"] = {
            "updated_at": timestamp,
            "mode": "included_in_full_rebuild",
            "file": str(DOSE_RULES_FACTS.relative_to(ROOT)),
        }
    write_json(SOURCE_UPDATE_META, meta)


def find_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available port found")


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else find_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Desktop app running at http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
