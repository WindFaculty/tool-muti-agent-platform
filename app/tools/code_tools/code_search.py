from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class CodeSearchInput(BaseModel):
    query: str = Field(min_length=1)
    path: str = "."
    glob: str | None = None
    max_results: int = Field(default=100, ge=1, le=2000)


class CodeSearchTool(BaseTool):
    name = "code_search"
    description = "Search code content using ripgrep fallback"
    input_model = CodeSearchInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        base_path = Path(input_data["path"])
        if not base_path.is_absolute():
            base_path = context.workspace_root / base_path
        base_path = base_path.resolve(strict=False)

        if self._has_ripgrep():
            return self._search_with_rg(base_path, input_data)
        return self._search_fallback(base_path, input_data)

    @staticmethod
    def _has_ripgrep() -> bool:
        return subprocess.call(
            ["where", "rg"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) == 0

    @staticmethod
    def _search_with_rg(base_path: Path, input_data: dict) -> ToolResult:
        command = ["rg", "-n", "--no-heading"]
        if input_data.get("glob"):
            command.extend(["-g", input_data["glob"]])
        command.extend([input_data["query"], str(base_path)])

        process = subprocess.run(command, capture_output=True, text=True, check=False)
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        return ToolResult(
            ok=True,
            data={
                "engine": "rg",
                "query": input_data["query"],
                "matches": lines[: input_data["max_results"]],
                "count": min(len(lines), input_data["max_results"]),
            },
        )

    @staticmethod
    def _search_fallback(base_path: Path, input_data: dict) -> ToolResult:
        query = input_data["query"]
        matches: list[str] = []
        for path in base_path.rglob("*"):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for index, line in enumerate(content.splitlines(), start=1):
                if query in line:
                    matches.append(f"{path}:{index}:{line.strip()}")
                    if len(matches) >= input_data["max_results"]:
                        return ToolResult(
                            ok=True,
                            data={"engine": "fallback", "query": query, "matches": matches, "count": len(matches)},
                        )
        return ToolResult(
            ok=True,
            data={"engine": "fallback", "query": query, "matches": matches, "count": len(matches)},
        )

