from __future__ import annotations

import requests
from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class FetchPageInput(BaseModel):
    url: str
    timeout_sec: int = Field(default=20, ge=1, le=120)
    max_chars: int = Field(default=200_000, ge=1, le=2_000_000)


class FetchPageTool(BaseTool):
    name = "fetch_page"
    description = "Fetch a web page by URL"
    input_model = FetchPageInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        response = requests.get(input_data["url"], timeout=input_data["timeout_sec"])
        response.raise_for_status()
        text = response.text
        max_chars = input_data["max_chars"]
        return ToolResult(
            ok=True,
            data={
                "url": input_data["url"],
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "content": text[:max_chars],
                "truncated": len(text) > max_chars,
            },
        )

