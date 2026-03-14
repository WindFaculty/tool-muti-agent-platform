from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMGenerateContext(BaseModel):
    agent_name: str
    project_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    name: str
    base_url: str | None = None
    chat_model: str
    embedding_model: str | None = None
    timeout_sec: int = 60
