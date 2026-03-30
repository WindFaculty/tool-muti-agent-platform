from __future__ import annotations

from app.agent.jobs import JobTracker


def test_job_tracker_lifecycle() -> None:
    tracker = JobTracker()

    tracker.start(
        job_key="tests",
        tool_name="run_tests",
        status_tool="get_test_job",
        job_id="job-123",
        params={"mode": "EditMode"},
    )
    tracker.update("tests", status="completed", result={"structured_content": {"data": {"status": "completed"}}})

    snapshot = tracker.snapshot()

    assert snapshot["tests"]["job_id"] == "job-123"
    assert snapshot["tests"]["status"] == "completed"
