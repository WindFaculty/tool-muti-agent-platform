from __future__ import annotations

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class ShellExecInput(BaseModel):
    command: str | list[str]
    cwd: str | None = None
    timeout_sec: int = Field(default=30, ge=1, le=600)


class ShellExecTool(BaseTool):
    name = "shell_exec"
    description = "Execute shell command with sandbox controls"
    input_model = ShellExecInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        context.permissions.validate_command(context.agent_id, self.name, input_data["command"])
        result = context.sandbox.run(
            input_data["command"],
            cwd=input_data.get("cwd"),
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=result["exit_code"] == 0, data=result)

