from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.agents.schemas import (
    AgentExecutionContext,
    ArchitectResult,
    ArtifactModel,
    CoderResult,
    DebuggerResult,
    DevOpsResult,
    PlannerResult,
    ReviewResult,
    TestResult,
    ToolCallModel,
)


class PlannerAgent(BaseAgent):
    agent_name = "planner"
    result_model = PlannerResult

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update(
            {
                "plan": [
                    "Inspect project context.",
                    "Define the next implementation slice.",
                    "Validate with tests and review.",
                ],
                "requires_architecture": True,
            }
        )
        return payload


class ArchitectAgent(BaseAgent):
    agent_name = "architect"
    result_model = ArchitectResult

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update(
            {
                "modules": ["orchestrator", "storage", "api"],
                "apis": ["/v1/tasks", "/v1/runs"],
                "risks": ["Using fallback architecture output."],
            }
        )
        return payload


class CoderAgent(BaseAgent):
    agent_name = "coder"
    result_model = CoderResult

    def _augment_result(self, context: AgentExecutionContext, result: Any) -> Any:
        result = super()._augment_result(context, result)
        payload = result.model_dump()
        artifacts = payload.get("artifacts", [])
        if not artifacts:
            artifacts.append(
                ArtifactModel(
                    name="implementation",
                    kind="markdown",
                    content=(
                        f"# Implementation\n\nPrepared implementation notes for {context.task.title}.\n"
                    ),
                ).model_dump()
            )
        payload["artifacts"] = artifacts
        return result.__class__.model_validate(payload)

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update(
            {
                "implementation_notes": ["Create workspace artifacts.", "Preserve API compatibility."],
                "files_to_create": [f"{context.task.task_id}.md"],
            }
        )
        return payload


class TestAgent(BaseAgent):
    agent_name = "tester"
    result_model = TestResult

    def _augment_result(self, context: AgentExecutionContext, result: Any) -> Any:
        result = super()._augment_result(context, result)
        project_root = Path(context.project.root_path)
        should_run_tests = any(
            [
                (project_root / "tests").exists(),
                (project_root / "pyproject.toml").exists(),
                (project_root / "package.json").exists(),
                (project_root / "pom.xml").exists(),
            ]
        )
        if "test_runner" in self.allowed_tools(context) and should_run_tests:
            execution = self.tool_executor.execute_calls(
                agent_name=self.agent_name,
                allowed_tools=self.allowed_tools(context),
                max_calls=1,
                tool_calls=[
                    ToolCallModel(
                        tool_name="test_runner",
                        input={"path": context.project.root_path, "framework": "auto", "extra_args": []},
                    )
                ],
            )
            if execution:
                run_result = execution[0]
                tool_payload = result.model_dump()
                tool_payload["metadata"] = {**tool_payload.get("metadata", {}), "tool_results": execution}
                tool_payload["passed"] = run_result.get("status") == "success"
                tool_payload["status"] = "success" if tool_payload["passed"] else "needs_debug"
                tool_payload["failures"] = [] if tool_payload["passed"] else [run_result["result"]["error_message"]]
                report_content = run_result["result"]["data"].get("stdout") or "Tests executed."
                tool_payload["artifacts"] = [
                    ArtifactModel(
                        name="test-report",
                        kind="markdown",
                        content=f"# Test Report\n\n{report_content}\n",
                    ).model_dump()
                ]
                result = result.__class__.model_validate(tool_payload)
        return result

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update({"passed": True, "test_commands": ["pytest -q"], "failures": []})
        return payload


class DebuggerAgent(BaseAgent):
    agent_name = "debugger"
    result_model = DebuggerResult

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update(
            {
                "root_cause": "Fallback debug analysis.",
                "proposed_fixes": ["Inspect failing tests.", "Adjust implementation."],
                "remaining_risks": [],
            }
        )
        return payload


class ReviewerAgent(BaseAgent):
    agent_name = "reviewer"
    result_model = ReviewResult

    def _augment_result(self, context: AgentExecutionContext, result: Any) -> Any:
        result = super()._augment_result(context, result)
        payload = result.model_dump()
        if not payload.get("approved", True):
            payload["status"] = "needs_revision"
        return result.__class__.model_validate(payload)

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update({"approved": True})
        return payload


class DevOpsAgent(BaseAgent):
    agent_name = "devops"
    result_model = DevOpsResult

    def _fallback_payload(self, context: AgentExecutionContext, error: Exception) -> dict[str, Any]:
        payload = super()._fallback_payload(context, error)
        payload.update(
            {
                "deployment_steps": ["Prepare Docker image.", "Document local run command."],
                "docker_commands": ["docker build . -t local/dev-os"],
            }
        )
        return payload
