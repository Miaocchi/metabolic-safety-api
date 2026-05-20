"""Unit tests for desktop_app.services.job_manager – background job state."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

# Ensure the repo root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_app.services.job_manager import (
    JOBS,
    REBUILD_LOCK,
    get_job_status,
    start_job,
    update_job,
)


class _JobManagerTestBase(unittest.TestCase):
    """Shared setup: clears the JOBS dict before each test."""

    def setUp(self):
        JOBS.clear()

    def tearDown(self):
        JOBS.clear()


class UpdateJobTests(_JobManagerTestBase):
    def test_updates_existing_job(self):
        JOBS["abc"] = {"id": "abc", "status": "running", "progress": 0, "message": "init"}
        update_job("abc", 50, "halfway")
        self.assertEqual(JOBS["abc"]["progress"], 50)
        self.assertEqual(JOBS["abc"]["message"], "halfway")

    def test_noop_for_unknown_job(self):
        update_job("nonexistent", 50, "msg")
        self.assertNotIn("nonexistent", JOBS)

    def test_clamps_progress_above_100(self):
        JOBS["x"] = {"id": "x", "status": "running", "progress": 0, "message": ""}
        update_job("x", 150, "overshoot")
        self.assertEqual(JOBS["x"]["progress"], 100)

    def test_clamps_progress_below_0(self):
        JOBS["x"] = {"id": "x", "status": "running", "progress": 0, "message": ""}
        update_job("x", -10, "negative")
        self.assertEqual(JOBS["x"]["progress"], 0)

    def test_extra_kwargs_merged(self):
        JOBS["x"] = {"id": "x", "status": "running", "progress": 0, "message": ""}
        update_job("x", 100, "done", status="done", result={"key": "value"})
        self.assertEqual(JOBS["x"]["status"], "done")
        self.assertEqual(JOBS["x"]["result"], {"key": "value"})


class GetJobStatusTests(_JobManagerTestBase):
    def test_returns_job_dict(self):
        JOBS["abc"] = {"id": "abc", "status": "running", "progress": 10, "message": "hi"}
        result = get_job_status("abc")
        self.assertEqual(result["id"], "abc")

    def test_returns_none_for_unknown(self):
        self.assertIsNone(get_job_status("nonexistent"))


class StartJobTests(_JobManagerTestBase):
    def test_creates_job_and_starts_thread(self):
        entered = threading.Event()
        release = threading.Event()
        def fake_target(job_id):
            entered.set()
            release.wait(timeout=5)
        job, already = start_job(fake_target, "starting...")
        self.assertFalse(already)
        self.assertIsNotNone(job)
        self.assertIn(job["status"], ("queued", "running"))
        self.assertEqual(job["message"], "starting...")
        self.assertIn(job["id"], JOBS)
        entered.wait(timeout=2)
        self.assertTrue(entered.is_set())
        release.set()

    def test_returns_already_running_when_job_active(self):
        """When a job is already in JOBS with running/queued status,
        start_job returns it as already_running."""
        JOBS["existing"] = {"id": "existing", "status": "running", "progress": 0, "message": "busy"}
        job, already = start_job(lambda jid: None)
        self.assertTrue(already)
        self.assertEqual(job["id"], "existing")

    def test_returns_already_running_when_job_queued(self):
        JOBS["existing"] = {"id": "existing", "status": "queued", "progress": 0, "message": "busy"}
        job, already = start_job(lambda jid: None)
        self.assertTrue(already)
        self.assertEqual(job["id"], "existing")

    def test_default_initial_message(self):
        def noop(jid):
            pass
        job, already = start_job(noop)
        self.assertFalse(already)
        self.assertIn("\u51c6\u5907", job["message"])  # "准备"

    def test_concurrent_starts_at_most_one_job(self):
        """When multiple threads race to start_job, exactly one succeeds."""
        target_started = threading.Event()
        target_release = threading.Event()

        def blocking_target(job_id):
            target_started.set()
            target_release.wait(timeout=10)

        results = []
        results_lock = threading.Lock()
        num_threads = 6
        barrier = threading.Barrier(num_threads)

        def attempt():
            barrier.wait(timeout=5)
            job, already = start_job(blocking_target, "test")
            with results_lock:
                results.append((job["id"] if job else None, already))

        threads = [threading.Thread(target=attempt) for _ in range(num_threads)]
        for t in threads:
            t.start()

        # Wait for the blocking target to actually start running.
        target_started.wait(timeout=10)
        target_release.set()

        for t in threads:
            t.join(timeout=10)

        started = [a for _, a in results if not a]
        rejected = [a for _, a in results if a]
        self.assertEqual(len(started), 1, f"Expected exactly 1 new job, got {len(started)}")
        self.assertEqual(len(rejected), num_threads - 1)

    def test_job_transitions_queued_to_running(self):
        """A job starts as 'queued' and transitions to 'running' when
        the target function begins executing."""
        entered = threading.Event()
        release = threading.Event()

        def target(job_id):
            # At this point _wrapper has already set status to 'running'.
            self.assertEqual(JOBS[job_id]["status"], "running")
            entered.set()
            release.wait(timeout=5)

        job, already = start_job(target, "test")
        self.assertFalse(already)
        # Status may be 'queued' or 'running' depending on thread scheduling.
        self.assertIn(job["status"], ("queued", "running"))

        entered.wait(timeout=5)
        # After the target has entered, status must be 'running'.
        self.assertEqual(job["status"], "running")
        release.set()


if __name__ == "__main__":
    unittest.main()
