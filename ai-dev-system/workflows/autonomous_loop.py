from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agents.contracts import ExecutionRecord, Lesson, PlanStep, TaskDefinition
from debugger_agent import DebugAgent
from executor_agent import ExecutorAgent
from lesson_store import LessonStore
from json_logger import JsonLogger
from mcp_client import UnityMcpClient
from planner_agent import PlannerAgent


class AutonomousUnityWorkflow:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.logger = JsonLogger(root / "logs" / "run-log.jsonl")
        self.lesson_store = LessonStore(root / "logs" / "lessons.jsonl")
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()
        self.debugger = DebugAgent()

    def load_task(self, path: Path) -> TaskDefinition:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TaskDefinition(
            id=payload["id"],
            title=payload["title"],
            prompt=payload["prompt"],
            goal=payload["goal"],
        )

    async def run(self, repo_root: Path, task: TaskDefinition) -> dict:
        plan = self.planner.build_plan(task)
        self.logger.log("plan_created", task_id=task.id, steps=[asdict(step) for step in plan])

        client = UnityMcpClient(repo_root)
        await client.connect()
        try:
            tools, resources = await self._fetch_connection_metadata(client)
            self.logger.log("mcp_connected", tools=tools, resources=resources)

            records = []
            workflow_status = "completed"
            stopped_after_step: str | None = None
            for step in plan:
                self.logger.log("step_started", step=asdict(step))
                record, client = await self._execute_step_with_recovery(client, step)

                if step.kind == "verify":
                    console_analysis = self.debugger.summarize_console(record.details.get("console", {}))
                    record.details["console_analysis"] = console_analysis
                    lesson = self.debugger.analyze_console(console_analysis)
                    if lesson is not None:
                        self.lesson_store.append(lesson)

                records.append(record)
                self.logger.log("step_finished", record=asdict(record))
                if record.status != "completed":
                    workflow_status = "failed"
                    stopped_after_step = step.id
                    self.logger.log("workflow_stopped", failed_step_id=step.id, failed_status=record.status)
                    break

            summary = {
                "task_id": task.id,
                "task_title": task.title,
                "workflow_status": workflow_status,
                "stopped_after_step": stopped_after_step,
                "steps": [asdict(record) for record in records],
            }
            self.logger.log("workflow_completed", summary=summary)
            if workflow_status == "completed":
                self.lesson_store.append(
                    Lesson(
                        category="workflow",
                        summary="Autonomous Unity workflow completed an end-to-end pass.",
                        evidence={"task_id": task.id, "step_count": len(records)},
                    )
                )
            else:
                self.lesson_store.append(
                    Lesson(
                        category="workflow",
                        summary="Autonomous Unity workflow stopped after a failed step.",
                        evidence={"task_id": task.id, "failed_step_id": stopped_after_step, "step_count": len(records)},
                    )
                )
            return summary
        finally:
            await client.close()

    async def _fetch_connection_metadata(self, client: UnityMcpClient) -> tuple[list[str], list[str]]:
        try:
            return await client.list_tools(), await client.list_resources()
        except Exception as exc:
            if not self._is_retryable_transport_exception(exc):
                raise

            self.logger.log("mcp_reconnect_requested", phase="metadata", error=self._stringify_exception(exc))
            await client.reconnect()
            tools = await client.list_tools()
            resources = await client.list_resources()
            self.logger.log("mcp_reconnected", phase="metadata", tools=tools, resources=resources)
            return tools, resources

    async def _execute_step_with_recovery(
        self, client: UnityMcpClient, step: PlanStep
    ) -> tuple[ExecutionRecord, UnityMcpClient]:
        try:
            return await self.executor.execute(client, step), client
        except Exception as exc:
            if not self._is_retryable_transport_exception(exc):
                return self._build_failed_record(step.id, exc, reason="executor_exception", retryable=False), client

            self.logger.log("mcp_reconnect_requested", phase="step", step_id=step.id, error=self._stringify_exception(exc))
            try:
                await client.reconnect()
                self.logger.log("mcp_reconnected", phase="step", step_id=step.id)
                return await self.executor.execute(client, step), client
            except Exception as retry_exc:
                reason = "transport_exception" if self._is_retryable_transport_exception(retry_exc) else "executor_exception"
                retryable = reason == "transport_exception"
                return self._build_failed_record(step.id, retry_exc, reason=reason, retryable=retryable), client

    @staticmethod
    def _is_retryable_transport_exception(exc: Exception) -> bool:
        message = str(exc).strip().lower()
        combined = f"{exc.__class__.__name__} {message}".lower()
        markers = (
            "connection closed",
            "stream closed",
            "closedresourceerror",
            "endofstream",
            "broken pipe",
            "connection reset",
            "pipe is being closed",
            "transport",
            "stdio",
            "stdiobridge",
            "reloading",
            "please retry",
            "hint='retry'",
            'hint="retry"',
            "eof",
        )
        return any(marker in combined for marker in markers)

    @classmethod
    def _build_failed_record(cls, step_id: str, exc: Exception, *, reason: str, retryable: bool) -> ExecutionRecord:
        message = cls._stringify_exception(exc)
        return ExecutionRecord(
            step_id=step_id,
            status="failed",
            details={
                "exception": {
                    "structured_content": {
                        "success": False,
                        "error": message,
                        "message": message,
                        "data": {
                            "reason": reason,
                            "retryable": retryable,
                            "exception_type": exc.__class__.__name__,
                        },
                    },
                    "content": [{"type": "text", "text": message}],
                    "is_error": True,
                }
            },
        )

    @staticmethod
    def _stringify_exception(exc: Exception) -> str:
        return f"{exc.__class__.__name__}: {exc}".strip()
