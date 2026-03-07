from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class ReadFileInput(BaseModel):
    path: str
    encoding: str = "utf-8"
    max_chars: int = Field(default=200_000, ge=1, le=2_000_000)


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read text content from a file"
    input_model = ReadFileInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        path = Path(input_data["path"])
        if not path.is_absolute():
            path = context.workspace_root / path
        resolved = path.resolve(strict=False)

        content = resolved.read_text(encoding=input_data["encoding"])
        max_chars = int(input_data["max_chars"])
        truncated = content[:max_chars]
        return ToolResult(
            ok=True,
            data={
                "path": str(resolved),
                "content": truncated,
                "truncated": len(content) > max_chars,
            },
        )

