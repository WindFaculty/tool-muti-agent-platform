from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ExecutionError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class GitPushInput(BaseModel):
    path: str = "."
    remote: str = "origin"
    branch: str | None = None
    set_upstream: bool = False
    timeout_sec: int = Field(default=60, ge=1, le=600)


class GitPushTool(BaseTool):
    name = "git_push"
    description = "Push git changes to a remote repository"
    input_model = GitPushInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        repo_path = Path(input_data["path"])
        if not repo_path.is_absolute():
            repo_path = context.workspace_root / repo_path
        repo_path = repo_path.resolve(strict=False)

        verify = context.sandbox.run(
            ["git", "-C", str(repo_path), "rev-parse", "--is-inside-work-tree"],
            timeout_sec=input_data["timeout_sec"],
        )
        if verify["exit_code"] != 0:
            raise ExecutionError("Target path is not a git repository")

        command = ["git", "-C", str(repo_path), "push"]
        if input_data["set_upstream"]:
            command.append("-u")
        command.append(input_data["remote"])
        if input_data.get("branch"):
            command.append(input_data["branch"])

        push_result = context.sandbox.run(
            command,
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=push_result["exit_code"] == 0, data=push_result)
