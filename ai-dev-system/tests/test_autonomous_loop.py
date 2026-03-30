from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
for child in ("agents", "planner", "executor", "memory", "tools", "workflows", "unity-interface"):
    path = ROOT / child
    if str(path) not in sys.path:
        sys.path.append(str(path))

from autonomous_loop import AutonomousUnityWorkflow
from contracts import ExecutionRecord, PlanStep, TaskDefinition


class _FakeClient:
    instances: list["_FakeClient"] = []

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.reconnect_count = 0
        self.connect_count = 0
        self.close_count = 0
        self.fail_metadata_once = False
        self._metadata_failed = False
        _FakeClient.instances.append(self)

    async def connect(self) -> "_FakeClient":
        self.connect_count += 1
        return self

    async def close(self, exc_type=None, exc=None, tb=None) -> None:
        self.close_count += 1
        return None

    async def list_tools(self) -> list[str]:
        if self.fail_metadata_once and not self._metadata_failed:
            self._metadata_failed = True
            raise RuntimeError("Connection closed while listing tools")
        return ["manage_scene"]

    async def list_resources(self) -> list[str]:
        return ["project_info"]

    async def reconnect(self) -> "_FakeClient":
        self.reconnect_count += 1
        return await self.connect()


class _FakePlanner:
    def build_plan(self, task: TaskDefinition) -> list[PlanStep]:
        return [
            PlanStep(id="load_scene", title="Load scene", kind="scene", payload={}),
            PlanStep(id="verify_scene", title="Verify scene", kind="verify", payload={}),
        ]


class _FakeExecutor:
    async def execute(self, client, step: PlanStep) -> ExecutionRecord:
        if step.id == "load_scene":
            return ExecutionRecord(step_id=step.id, status="failed", details={"reason": {"content": [{"text": "load failed"}]}})
        return ExecutionRecord(step_id=step.id, status="completed", details={})


class _RetryableExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, client, step: PlanStep) -> ExecutionRecord:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Connection closed by remote host")
        return ExecutionRecord(step_id=step.id, status="completed", details={"recovered": True})


class _SuccessfulExecutor:
    async def execute(self, client, step: PlanStep) -> ExecutionRecord:
        return ExecutionRecord(step_id=step.id, status="completed", details={})


class _MetadataRetryClient(_FakeClient):
    def __init__(self, repo_root: Path) -> None:
        super().__init__(repo_root)
        self.fail_metadata_once = True


class _FakeDebugAgent:
    def summarize_console(self, console_payload: dict) -> dict:
        return {"counts": {}}

    def analyze_console(self, analysis: dict):
        return None


class AutonomousLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeClient.instances.clear()

    def test_workflow_stops_after_first_failed_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow = AutonomousUnityWorkflow(Path(temp_dir))
            workflow.planner = _FakePlanner()
            workflow.executor = _FakeExecutor()
            workflow.debugger = _FakeDebugAgent()

            task = TaskDefinition(id="demo", title="Demo", prompt="Prompt", goal={"id": "fake"})

            with patch("autonomous_loop.UnityMcpClient", _FakeClient):
                summary = asyncio.run(workflow.run(Path(temp_dir), task))

        self.assertEqual(summary["workflow_status"], "failed")
        self.assertEqual(summary["stopped_after_step"], "load_scene")
        self.assertEqual(len(summary["steps"]), 1)

    def test_workflow_reconnects_and_retries_step_after_transport_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow = AutonomousUnityWorkflow(Path(temp_dir))
            workflow.planner = _FakePlanner()
            workflow.executor = _RetryableExecutor()
            workflow.debugger = _FakeDebugAgent()

            task = TaskDefinition(id="demo", title="Demo", prompt="Prompt", goal={"id": "fake"})

            with patch("autonomous_loop.UnityMcpClient", _FakeClient):
                summary = asyncio.run(workflow.run(Path(temp_dir), task))

        self.assertEqual(summary["workflow_status"], "completed")
        self.assertEqual(len(summary["steps"]), 2)
        self.assertEqual(_FakeClient.instances[0].reconnect_count, 1)

    def test_workflow_reconnects_when_initial_metadata_fetch_hits_transport_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow = AutonomousUnityWorkflow(Path(temp_dir))
            workflow.planner = _FakePlanner()
            workflow.executor = _SuccessfulExecutor()
            workflow.debugger = _FakeDebugAgent()

            task = TaskDefinition(id="demo", title="Demo", prompt="Prompt", goal={"id": "fake"})

            with patch("autonomous_loop.UnityMcpClient", _MetadataRetryClient):
                summary = asyncio.run(workflow.run(Path(temp_dir), task))

        self.assertEqual(summary["workflow_status"], "completed")
        self.assertEqual(_FakeClient.instances[0].reconnect_count, 1)


if __name__ == "__main__":
    unittest.main()
