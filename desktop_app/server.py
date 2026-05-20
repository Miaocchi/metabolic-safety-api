"""Desktop local-first metabolic safety HTTP server.

This module provides the ``Handler`` (a ``SimpleHTTPRequestHandler`` subclass)
and the ``main()`` entry-point.  Heavy logic is delegated to:

- ``desktop_app.config``        – shared path constants and source configs
- ``desktop_app.services.security``   – URL/path policy & input validation
- ``desktop_app.services.job_manager`` – background job state management
- ``desktop_app.services.source_ops``  – fetching, sync, and rebuild
"""
from __future__ import annotations

import json
import socket
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# -- bootstrap: ensure repo root on sys.path for direct invocation ----------
# When launched as ``python3 desktop_app/server.py`` (not ``-m``), Python
# puts ``desktop_app/`` on sys.path instead of the repo root, which breaks
# ``from desktop_app.config import …``.  Insert the repo root early.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
del _REPO_ROOT

# -- config & shared constants (also sets sys.path for ETL imports) ---------
from desktop_app.config import (
    BUILD,
    BULK_SOURCE_CONFIG,
    BULK_SOURCE_ORDER,
    DIRECT_PUBLIC_SOURCES,
    REMOTE_STATIC_API,
    SEVERE_FAERS_REACTIONS,
    SOURCE_NAME_TO_KEY,
    SOURCE_UPDATE_META,
    STATIC,
)

# -- service imports --------------------------------------------------------
from desktop_app.services.security import (
    _int_param,
    active_seed_db,
    stable_text_hash,
    validate_path_within_base,
)
from desktop_app.services.job_manager import (
    JOBS,
    REBUILD_LOCK,
    get_job_status,
    start_job,
)
from desktop_app.services.source_ops import (
    append_optional_facts,
    faers_query_terms,
    fetch_direct_public_facts,
    fetch_faers_signal_facts_cached,
    optional_fact_counts_by_source,
    run_bulk_sync_job,
    run_public_sync_job,
    run_rebuild_job,
    update_source_meta,
)

# -- ETL adapter imports ----------------------------------------------------
from metabolic_safety_etl.adapters.label_bulk import (              # noqa: E402
    fetch_dailymed_label_manifest,
    fetch_openfda_label_manifest,
)
from metabolic_safety_etl.source_catalog import source_status_dicts  # noqa: E402


# ============================================================================
# HTTP request handler
# ============================================================================

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

    # -- routing -------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/remote-api" or parsed.path.startswith("/remote-api/"):
            self._serve_remote_static(parsed.path)
            return
        if parsed.path == "/api/seed":
            self._send_json(self._read_seed())
            return
        if parsed.path == "/api/interactions":
            self._send_json(self._query_interactions(params))
            return
        if parsed.path == "/api/check":
            self._send_json(self._check_interactions(params))
            return
        if parsed.path == "/api/adverse-signals":
            self._send_json(self._adverse_signals(params))
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

    # -- database helpers ----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(active_seed_db())
        conn.row_factory = sqlite3.Row
        return conn

    # -- route implementations -----------------------------------------------

    def _read_seed(self) -> dict:
        manifest = self._read_json(BUILD / "manifest.json")
        if not active_seed_db().exists():
            return {
                "manifest": manifest,
                "substances": self._read_json(BUILD / "init_substances.json"),
                "interactionsLoaded": False,
                "doseRules": (
                    self._read_json(BUILD / "init_dose_rules.json")
                    if (BUILD / "init_dose_rules.json").exists()
                    else []
                ),
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
        from desktop_app.config import RISK_ORDER_SQL

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
            "query": query, "limit": limit, "offset": offset, "total": total,
            "items": [self._interaction_row(row) for row in rows],
        }

    def _check_interactions(self, params: dict[str, list[str]]) -> dict:
        from desktop_app.config import RISK_ORDER_SQL

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

    def _adverse_signals(self, params: dict[str, list[str]]) -> dict:
        raw_ids = []
        for value in params.get("ids", []):
            raw_ids.extend(part for part in value.split(",") if part)
        ids = sorted({item.strip() for item in raw_ids if item.strip()})
        if not ids:
            return {"items": [], "errors": []}
        limit = min(max(_int_param(params, "limit", 3), 1), 8)
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, name_zh, name_en, category, identifiers_json
                FROM substances_core
                WHERE id IN ({placeholders})
                ORDER BY COALESCE(name_zh, name_en), id
                """,
                ids,
            ).fetchall()

        items = []
        errors = []
        for row in rows:
            try:
                item = self._faers_signal_for_substance(row, limit)
                if item:
                    items.append(item)
            except Exception as exc:
                errors.append({"id": row["id"], "error": type(exc).__name__, "message": str(exc)})
        return {"items": items, "errors": errors}

    def _faers_signal_for_substance(self, row: sqlite3.Row, limit: int) -> dict | None:
        substance_id = row["id"]
        substance_name = row["name_zh"] or row["name_en"] or substance_id
        for term in faers_query_terms(row):
            facts = fetch_faers_signal_facts_cached(term, limit)
            if not facts:
                continue
            reactions = []
            for fact in facts[:limit]:
                claim = fact.claim
                reactions.append(
                    {
                        "reaction": claim.get("reaction"),
                        "label": claim.get("reaction_label_zh") or claim.get("reaction"),
                        "count": claim.get("count", 0),
                    }
                )
            readable = "\uff1b".join(
                f"{reaction['label']}\uff08{reaction['reaction']}\uff09{int(reaction.get('count') or 0):,} \u4f8b"
                for reaction in reactions
            )
            risk_level = (
                "Moderate"
                if any(str(reaction.get("reaction") or "").upper() in SEVERE_FAERS_REACTIONS for reaction in reactions)
                else "Minor"
            )
            return {
                "risk_kind": "signal",
                "signal_id": f"faers_{substance_id}_{stable_text_hash(term)}",
                "substance_id": substance_id,
                "substance_name": substance_name,
                "query_term": term,
                "reactions": reactions,
                "risk_level": risk_level,
                "confidence": "Low",
                "source_tier": "Signal",
                "interaction_type": "adverse_event_signal",
                "source_name": "openFDA FAERS adverse event",
                "source_url": facts[0].source_url,
                "note": (
                    f"FAERS \u81ea\u53d1\u4e0d\u826f\u4e8b\u4ef6\u62a5\u544a\u4e2d\uff0c"
                    f"{substance_name}\uff08\u6309 {term} \u68c0\u7d22\uff09\u5e38\u89c1\u5171\u62a5\u544a\u4e8b\u4ef6\uff1a"
                    f"{readable}\u3002\u8fd9\u662f\u836f\u7269\u8b66\u6212\u5019\u9009\u4fe1\u53f7\uff0c"
                    "\u4e0d\u4ee3\u8868\u56e0\u679c\u5173\u7cfb\u3001\u53d1\u751f\u7387\u6216\u5df2\u786e\u8ba4\u8054\u7528\u51b2\u7a81\uff1b"
                    "\u7528\u4e8e\u63d0\u9192\u8bb0\u5f55\u75c7\u72b6\u5e76\u5fc5\u8981\u65f6\u54a8\u8be2\u533b\u751f/\u836f\u5e08\u3002"
                ),
            }
        return None

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
            row["can_update"] = row["status"] in {
                "connected_api", "connected_api_and_local_bulk",
                "connected_local_csv", "connected_local_json",
                "connected_local_bulk",
            }
            row["can_bulk_update"] = row["key"] in BULK_SOURCE_CONFIG
            row["bulk_update_label"] = BULK_SOURCE_CONFIG.get(row["key"], {}).get("label")
            row["bulk_update_mode"] = BULK_SOURCE_CONFIG.get(row["key"], {}).get("mode")
            row["bulk_update_large"] = bool(BULK_SOURCE_CONFIG.get(row["key"], {}).get("large"))
            row["last_update"] = meta.get(row["key"])
            row["optional_facts_count"] = (
                optional_counts.get(row["key"], 0) if row["key"] in direct_keys else None
            )
            items.append(row)
        return {"items": items, "optionalFactsCount": optional_count, "updateMeta": meta}

    def _source_update(self, params: dict[str, list[str]]) -> dict:
        key = (params.get("key", [""])[0] or "").strip()
        if key not in DIRECT_PUBLIC_SOURCES:
            return {"ok": False, "error": "unsupported_source", "message": "\u53ea\u80fd\u76f4\u63a5\u66f4\u65b0\u975e\u5546\u4e1a\u516c\u5f00 API \u6e90\u3002"}
        config = DIRECT_PUBLIC_SOURCES[key]
        term = (params.get("term", [""])[0] or "").strip()
        if config["requires_term"] and not term:
            return {"ok": False, "error": "term_required", "message": "\u8be5\u6570\u636e\u6e90\u9700\u8981\u8f93\u5165\u836f\u7269/\u7269\u8d28\u5173\u952e\u8bcd\u3002"}
        limit = min(
            max(_int_param(params, "limit", int(config["default_limit"])), 1),
            int(config["max_limit"]),
        )
        try:
            facts = fetch_direct_public_facts(key, term, limit)
            stored = append_optional_facts(facts)
            meta = update_source_meta(key, {"term": term, "limit": limit, "facts": len(facts)})
            return {
                "ok": True, "key": key, "label": config["label"],
                "factsFetched": len(facts), "optionalFactsCount": stored,
                "lastUpdate": meta.get(key),
                "message": f"\u5df2\u83b7\u53d6 {len(facts)} \u6761\u5019\u9009\u4e8b\u5b9e\u3002\u70b9\u51fb\u91cd\u5efa\u672c\u5730\u5e93\u540e\u5e76\u5165\u684c\u9762\u79cd\u5b50\u5e93\u3002",
            }
        except Exception as exc:
            return {"ok": False, "key": key, "error": type(exc).__name__, "message": str(exc)}

    # -- job management routes -----------------------------------------------

    def _start_rebuild_job(self) -> dict:
        job, already = start_job(run_rebuild_job, "\u51c6\u5907\u5168\u91cf\u91cd\u5efa...")
        return {"ok": True, "jobId": job.get("id") if job else None, "alreadyRunning": already}

    def _start_public_sync_job(self, params: dict[str, list[str]]) -> dict:
        max_terms = _int_param(params, "maxTerms", 0)

        def _target(job_id: str) -> None:
            run_public_sync_job(job_id, max_terms or None)

        job, already = start_job(_target, "\u51c6\u5907\u8054\u7f51\u540c\u6b65\u516c\u5f00\u6e90...")
        return {"ok": True, "jobId": job.get("id") if job else None, "alreadyRunning": already}

    def _start_bulk_sync_job(self, params: dict[str, list[str]]) -> dict:
        key = (params.get("key", ["all"])[0] or "all").strip()
        if key != "all" and key not in BULK_SOURCE_CONFIG:
            return {"ok": False, "error": "unsupported_source", "message": "\u8fd9\u4e2a\u6e90\u6ca1\u6709\u53ef\u6267\u884c\u7684\u5168\u91cf\u62c9\u53d6\u9002\u914d\u5668\u3002"}
        label = "\u6240\u6709\u53ef\u7528\u975e\u5546\u4e1a\u6e90" if key == "all" else BULK_SOURCE_CONFIG[key]["label"]

        def _target(job_id: str) -> None:
            run_bulk_sync_job(job_id, key)

        job, already = start_job(_target, f"\u51c6\u5907\u5168\u91cf\u62c9\u53d6\uff1a{label}...")
        return {"ok": True, "jobId": job.get("id") if job else None, "alreadyRunning": already}

    def _rebuild_status(self, params: dict[str, list[str]]) -> dict:
        job_id = (params.get("job", [""])[0] or "").strip()
        job = get_job_status(job_id)
        if not job:
            return {"ok": False, "error": "job_not_found", "message": "\u6ca1\u6709\u627e\u5230\u8fd9\u4e2a\u91cd\u5efa\u4efb\u52a1\u3002"}
        return {"ok": True, **job}

    def _label_bulk_manifest(self) -> dict:
        payload: dict = {"ok": True, "items": []}
        try:
            payload["items"].append(fetch_openfda_label_manifest())
        except Exception as exc:
            payload["items"].append({"source": "openfda_label", "error": type(exc).__name__, "message": str(exc)})
        try:
            payload["items"].append(fetch_dailymed_label_manifest())
        except Exception as exc:
            payload["items"].append({"source": "dailymed", "error": type(exc).__name__, "message": str(exc)})
        return payload

    # -- row formatters ------------------------------------------------------

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

    # -- I/O helpers ---------------------------------------------------------

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

    def _serve_remote_static(self, request_path: str) -> None:
        relative = request_path.removeprefix("/remote-api").lstrip("/") or "manifest.json"
        target = REMOTE_STATIC_API / relative
        try:
            target = validate_path_within_base(target, REMOTE_STATIC_API)
        except ValueError:
            self.send_error(404)
            return
        if not target.exists() or not target.is_file():
            if relative.startswith((
                "interactions/by-substance/", "dose-rules/by-substance/",
                "dose-candidates/by-substance/", "overdose-warnings/by-substance/",
            )):
                self._send_json([])
                return
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(target)))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ============================================================================
# Server startup
# ============================================================================

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
