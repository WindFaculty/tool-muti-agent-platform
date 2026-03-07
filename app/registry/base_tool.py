from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import ValidationError


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0


@dataclass
class ToolContext:
    agent_id: str
    request_id: str
    timeout_sec: int
    resource_limits: dict[str, Any]
    policy_snapshot: dict[str, Any]
    workspace_root: Path
    sandbox: Any
    settings: Any
    permissions: Any


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_model: type[BaseModel] | None = None
    output_model: type[BaseModel] | None = None

    def input_schema(self) -> dict[str, Any]:
        if self.input_model is None:
            return {"type": "object", "properties": {}}
        return self.input_model.model_json_schema()

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        if self.input_model is None:
            return input_data
        try:
            model = self.input_model.model_validate(input_data)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        return model.model_dump()

    def run(self, context: ToolContext, input_data: dict[str, Any]) -> ToolResult:
        validated = self.validate_input(input_data)
        return self.execute(context, validated)

    @abstractmethod
    def execute(self, context: ToolContext, input_data: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

