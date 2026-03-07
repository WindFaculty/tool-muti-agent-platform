from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class DockerBuildInput(BaseModel):
    context_path: str = "."
    dockerfile: str | None = None
    tag: str | None = None
    timeout_sec: int = Field(default=900, ge=1, le=7200)


class DockerBuildTool(BaseTool):
    name = "docker_build"
    description = "Build docker image from context"
    input_model = DockerBuildInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        context_path = Path(input_data["context_path"])
        if not context_path.is_absolute():
            context_path = context.workspace_root / context_path
        context_path = context_path.resolve(strict=False)

        command = ["docker", "build", str(context_path)]
        if input_data.get("dockerfile"):
            command.extend(["-f", input_data["dockerfile"]])
        if input_data.get("tag"):
            command.extend(["-t", input_data["tag"]])

        result = context.sandbox.run(
            command,
            cwd=str(context_path),
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=result["exit_code"] == 0, data=result)

