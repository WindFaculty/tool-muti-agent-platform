from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class WriteFileInput(BaseModel):
    path: str
    content: str
    mode: str = Field(default="w")
    encoding: str = "utf-8"


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write text content to a file"
    input_model = WriteFileInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        mode = input_data["mode"]
        if mode not in {"w", "a", "x"}:
            raise ValidationError("mode must be one of: w, a, x")

        path = Path(input_data["path"])
        if not path.is_absolute():
            path = context.workspace_root / path
        resolved = path.resolve(strict=False)
        resolved.parent.mkdir(parents=True, exist_ok=True)

        with resolved.open(mode, encoding=input_data["encoding"]) as file:
            file.write(input_data["content"])

        return ToolResult(
            ok=True,
            data={
                "path": str(resolved),
                "bytes_written": len(input_data["content"].encode(input_data["encoding"])),
            },
        )

