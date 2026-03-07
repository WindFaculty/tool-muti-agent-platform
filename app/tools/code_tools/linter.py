from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class LinterInput(BaseModel):
    path: str = "."
    tool: str = "flake8"
    extra_args: list[str] = Field(default_factory=list)
    timeout_sec: int = Field(default=120, ge=1, le=1800)


class LinterTool(BaseTool):
    name = "linter"
    description = "Run source code linter"
    input_model = LinterInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        project_path = Path(input_data["path"])
        if not project_path.is_absolute():
            project_path = context.workspace_root / project_path
        project_path = project_path.resolve(strict=False)

        command = self._build_command(input_data["tool"].lower(), input_data["extra_args"])
        result = context.sandbox.run(
            command,
            cwd=str(project_path),
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=result["exit_code"] == 0, data={"tool": input_data["tool"], **result})

    @staticmethod
    def _build_command(tool: str, extra_args: list[str]) -> list[str]:
        if tool == "flake8":
            return ["flake8", *extra_args]
        if tool == "ruff":
            return ["ruff", "check", *extra_args]
        if tool == "pylint":
            return ["pylint", *extra_args]
        raise ValidationError(f"Unsupported linter: {tool}")

