"""Background job state management for the desktop app.

Centralises the ``JOBS`` registry, the ``REBUILD_LOCK`` (serialising all
heavy background tasks), and helper functions for starting / querying jobs.
"""
from __future__ import annotations

import threading
import uuid

__all__ = [
    "JOBS",
    "REBUILD_LOCK",
    "get_job_status",
    "start_job",
    "update_job",
]

# A single lock that serialises all heavy rebuild / sync jobs.
REBUILD_LOCK = threading.Lock()

# Protects the check-and-start sequence in ``start_job`` so that two
# concurrent callers cannot both create a new job.
_START_LOCK = threading.Lock()

# In-memory job registry keyed by hex job-id.
JOBS: dict[str, dict] = {}


def update_job(job_id: str, progress: int, message: str, **extra) -> None:
    """Update an existing job's progress/message.  No-op if *job_id* unknown."""
    job = JOBS.get(job_id)
    if not job:
        return
    job.update({"progress": max(0, min(progress, 100)), "message": message, **extra})


def start_job(target_fn, initial_message: str = "\u51c6\u5907\u4e2d...") -> tuple[dict | None, bool]:
    """Start a background job thread.

    Parameters
    ----------
    target_fn:
        ``target_fn(job_id: str)`` -- will be called in a daemon thread.
    initial_message:
        Human-readable status shown before the first progress callback.

    Returns
    -------
    ``(job_dict, already_running)`` -- *job_dict* is either the newly
    created job record or the currently running one (if *already_running*
    is ``True``).
    """
    with _START_LOCK:
        # Check JOBS state (not REBUILD_LOCK.locked()) to avoid TOCTOU
        # races between the check and the thread acquiring REBUILD_LOCK.
        active = next(
            (j for j in JOBS.values() if j.get("status") in ("running", "queued")),
            None,
        )
        if active:
            return active, True
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "message": initial_message,
        }

    # Thread starts outside _START_LOCK; the job is already recorded as
    # "queued" so concurrent callers will see it.
    def _wrapper(jid: str) -> None:
        JOBS[jid]["status"] = "running"
        target_fn(jid)

    thread = threading.Thread(target=_wrapper, args=(job_id,), daemon=True)
    thread.start()
    return JOBS[job_id], False


def get_job_status(job_id: str) -> dict | None:
    """Return the job record for *job_id*, or ``None``."""
    return JOBS.get(job_id)
