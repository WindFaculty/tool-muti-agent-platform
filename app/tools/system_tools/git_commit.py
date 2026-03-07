from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ExecutionError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class GitCommitInput(BaseModel):
    message: str = Field(min_length=1)
    path: str = "."
    add_all: bool = True
    timeout_sec: int = Field(default=30, ge=1, le=300)


class GitCommitTool(BaseTool):
    name = "git_commit"
    description = "Commit local git changes"
    input_model = GitCommitInput

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

        if input_data["add_all"]:
            add_result = context.sandbox.run(
                ["git", "-C", str(repo_path), "add", "-A"],
                timeout_sec=input_data["timeout_sec"],
            )
            if add_result["exit_code"] != 0:
                raise ExecutionError(add_result["stderr"] or "git add failed")

        status_result = context.sandbox.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            timeout_sec=input_data["timeout_sec"],
        )
        if not status_result["stdout"].strip():
            raise ExecutionError("No changes to commit")

        commit_result = context.sandbox.run(
            ["git", "-C", str(repo_path), "commit", "-m", input_data["message"]],
            timeout_sec=input_data["timeout_sec"],
            memory_limit_mb=context.resource_limits.get("default_memory_limit_mb"),
        )
        return ToolResult(ok=commit_result["exit_code"] == 0, data=commit_result)

