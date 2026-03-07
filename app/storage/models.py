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

