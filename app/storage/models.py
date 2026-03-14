from __future__ import annotations

from pydantic import BaseModel, Field


class ToolRecord(BaseModel):
    name: str
    description: str
    input_schema: dict
    required_permissions: list[str] = Field(default_factory=list)


class ExecutionRecord(BaseModel):
    execution_id: str
    request_id: str
    agent_id: str
    tool_name: str
    status: str
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int = 0
    created_at: str
    updated_at: str


class ExecutionArtifactRecord(BaseModel):
    execution_id: str
    artifact_type: str
    artifact_path: str | None = None
    artifact_json: dict = Field(default_factory=dict)
    created_at: str


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    root_path: str
    default_workflow_id: str
    status: str
    created_at: str
    updated_at: str


class TaskRecord(BaseModel):
    task_id: str
    project_id: str
    title: str
    description_md: str
    requirements_md: str
    expected_output_md: str
    priority: str
    workflow_id: str
    status: str
    task_path: str
    created_at: str
    updated_at: str


class TaskRunRecord(BaseModel):
    run_id: str
    task_id: str
    project_id: str
    workflow_id: str
    status: str
    current_step_id: str | None = None
    result_summary: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    created_at: str
    updated_at: str


class RunStepRecord(BaseModel):
    run_id: str
    step_id: str
    agent_id: str
    status: str
    retry_count: int = 0
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    started_at: str | None = None
    ended_at: str | None = None
    updated_at: str


class AgentMessageRecord(BaseModel):
    message_id: str
    run_id: str
    task_id: str
    step_id: str | None = None
    agent_id: str
    message_type: str
    content_md: str
    artifacts_json: list[dict] = Field(default_factory=list)
    created_at: str


class KnowledgeDocumentRecord(BaseModel):
    document_id: str
    project_id: str
    title: str
    content_path: str
    content_sha256: str
    tags_json: list[str] = Field(default_factory=list)
    summary_md: str
    source: str
    indexed_at: str


class MemoryEntryRecord(BaseModel):
    entry_id: str
    project_id: str
    kind: str
    title: str
    content_path: str
    content_sha256: str
    tags_json: list[str] = Field(default_factory=list)
    embedding_json: list[float] = Field(default_factory=list)
    source_run_id: str | None = None
    created_at: str


class WorkflowDefinitionRecord(BaseModel):
    workflow_id: str
    version: str
    description: str
    steps_yaml: str
    is_builtin: bool
    updated_at: str


class PromptTemplateRecord(BaseModel):
    prompt_name: str
    role_name: str
    template_body: str
    updated_at: str


class EvaluationRecord(BaseModel):
    run_id: str
    score: float
    metrics_json: dict = Field(default_factory=dict)
    summary_md: str
    created_at: str
    updated_at: str


class DeploymentRecord(BaseModel):
    deployment_id: str
    project_id: str
    run_id: str | None = None
    target: str
    status: str
    log_path: str | None = None
    created_at: str
    updated_at: str
