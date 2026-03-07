from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class InstallDependencyInput(BaseModel):
    manager: str = Field(default="pip")
    packages: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout_sec: int = Field(default=300, ge=1, le=3600)


class InstallDependencyTool(BaseTool):
    name = "install_dependency"
    description = "Install dependencies via pip, npm, or maven"
    input_model = InstallDependencyInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        cwd = input_data.get("cwd")
        if cwd:
            path = Path(cwd)
            if not path.is_absolute():
                path = context.workspace_root / path
            cwd = str(path.resolve(strict=False))

        manager = input_data["manager"].lower()
        packages = input_data["packages"]
        command = self._build_command(manager, packages)
        result = context.sandbox.run(
            command,
            cwd=cwd,
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=result["exit_code"] == 0, data={"manager": manager, **result})

    @staticmethod
    def _build_command(manager: str, packages: list[str]) -> list[str]:
        if manager == "pip":
            if not packages:
                raise ValidationError("pip manager requires packages")
            return [sys.executable, "-m", "pip", "install", *packages]
        if manager == "npm":
            if not packages:
                raise ValidationError("npm manager requires packages")
            return ["npm", "install", *packages]
        if manager == "maven":
            return ["mvn", "dependency:resolve"]
        raise ValidationError(f"Unsupported manager: {manager}")

