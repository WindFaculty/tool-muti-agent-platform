from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class FormatterInput(BaseModel):
    path: str = "."
    tool: str = "isort"
    check: bool = False
    extra_args: list[str] = Field(default_factory=list)
    timeout_sec: int = Field(default=120, ge=1, le=1800)


class FormatterTool(BaseTool):
    name = "formatter"
    description = "Run source code formatter"
    input_model = FormatterInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        project_path = Path(input_data["path"])
        if not project_path.is_absolute():
            project_path = context.workspace_root / project_path
        project_path = project_path.resolve(strict=False)

        command = self._build_command(
            tool=input_data["tool"].lower(),
            check=input_data["check"],
            extra_args=input_data["extra_args"],
        )
        result = context.sandbox.run(
            command,
            cwd=str(project_path),
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=result["exit_code"] == 0, data={"tool": input_data["tool"], **result})

    @staticmethod
    def _build_command(tool: str, check: bool, extra_args: list[str]) -> list[str]:
        if tool == "isort":
            args = ["isort"]
            if check:
                args.append("--check-only")
            return [*args, *extra_args]
        if tool == "black":
            args = ["black"]
            if check:
                args.append("--check")
            return [*args, *extra_args]
        if tool == "ruff-format":
            args = ["ruff", "format"]
            if check:
                args.append("--check")
            return [*args, *extra_args]
        raise ValidationError(f"Unsupported formatter: {tool}")

