from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class RunServerInput(BaseModel):
    command: str | list[str] | None = None
    cwd: str = "."
    detach: bool = True
    timeout_sec: int = Field(default=15, ge=1, le=120)


class RunServerTool(BaseTool):
    name = "run_server"
    description = "Start a development server command"
    input_model = RunServerInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        cwd_path = Path(input_data["cwd"])
        if not cwd_path.is_absolute():
            cwd_path = context.workspace_root / cwd_path
        cwd_path = cwd_path.resolve(strict=False)

        command = input_data.get("command") or self._auto_command(cwd_path)
        context.permissions.validate_command(context.agent_id, self.name, command)

        if input_data["detach"]:
            started = context.sandbox.start_background(command, cwd=str(cwd_path))
            return ToolResult(
                ok=True,
                data={"detached": True, "cwd": str(cwd_path), **started},
            )

        result = context.sandbox.run(
            command,
            cwd=str(cwd_path),
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=result["exit_code"] == 0, data={"detached": False, **result})

    @staticmethod
    def _auto_command(cwd_path: Path) -> list[str]:
        if (cwd_path / "app" / "main.py").exists():
            return [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
        if (cwd_path / "pom.xml").exists():
            return ["mvn", "tomcat7:run"]
        raise ValidationError("Cannot auto-detect server command; provide command explicitly")

