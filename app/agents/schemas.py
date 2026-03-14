from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.storage.models import ProjectRecord, TaskRecord, TaskRunRecord
from app.workflows.models import WorkflowStepDefinition


class ToolCallModel(BaseModel):
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ArtifactModel(BaseModel):
    name: str
    kind: str = "markdown"
    content: Any
    relative_path: str | None = None


class BaseAgentResult(BaseModel):
    status: Literal["success", "failed", "needs_debug", "needs_revision"] = "success"
    summary: str
    findings: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallModel] = Field(default_factory=list)
    artifacts: list[ArtifactModel] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerResult(BaseAgentResult):
    plan: list[str] = Field(default_factory=list)
    requires_architecture: bool = False


class ArchitectResult(BaseAgentResult):
    modules: list[str] = Field(default_factory=list)
    apis: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class CoderResult(BaseAgentResult):
    implementation_notes: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)


class TestResult(BaseAgentResult):
    passed: bool = True
    test_commands: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class DebuggerResult(BaseAgentResult):
    root_cause: str = ""
    proposed_fixes: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)


class ReviewResult(BaseAgentResult):
    approved: bool = True


class DevOpsResult(BaseAgentResult):
    deployment_steps: list[str] = Field(default_factory=list)
    docker_commands: list[str] = Field(default_factory=list)


class AgentExecutionContext(BaseModel):
    project: ProjectRecord
    task: TaskRecord
    run: TaskRunRecord
    workflow_step: WorkflowStepDefinition
    run_workspace: str
    retry_count: int = 0
    review_cycles: int = 0
