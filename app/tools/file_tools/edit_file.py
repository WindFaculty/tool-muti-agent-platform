from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class EditFileInput(BaseModel):
    path: str
    search: str
    replace: str
    replace_all: bool = False
    encoding: str = "utf-8"


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Replace text in a file"
    input_model = EditFileInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        path = Path(input_data["path"])
        if not path.is_absolute():
            path = context.workspace_root / path
        resolved = path.resolve(strict=False)

        content = resolved.read_text(encoding=input_data["encoding"])
        search = input_data["search"]
        replace = input_data["replace"]
        replace_all = bool(input_data["replace_all"])

        if replace_all:
            updated = content.replace(search, replace)
            replacements = content.count(search)
        else:
            updated = content.replace(search, replace, 1)
            replacements = 1 if search in content else 0

        resolved.write_text(updated, encoding=input_data["encoding"])
        return ToolResult(
            ok=True,
            data={
                "path": str(resolved),
                "replacements": replacements,
            },
        )

