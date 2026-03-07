from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class ListFilesInput(BaseModel):
    path: str = "."
    pattern: str = "*"
    recursive: bool = False
    limit: int = Field(default=200, ge=1, le=5000)


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files in a directory"
    input_model = ListFilesInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        base = Path(input_data["path"])
        if not base.is_absolute():
            base = context.workspace_root / base
        base = base.resolve(strict=False)

        pattern = input_data["pattern"]
        iterator = base.rglob(pattern) if input_data["recursive"] else base.glob(pattern)

        files: list[str] = []
        for item in iterator:
            files.append(str(item))
            if len(files) >= input_data["limit"]:
                break

        return ToolResult(ok=True, data={"path": str(base), "files": files, "count": len(files)})

