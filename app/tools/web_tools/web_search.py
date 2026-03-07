from __future__ import annotations

import requests
from pydantic import BaseModel, Field

from app.core.errors import ExecutionError
from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1)
    num_results: int = Field(default=5, ge=1, le=10)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web via SerpAPI"
    input_model = WebSearchInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        api_key = context.settings.serpapi_api_key
        if not api_key:
            raise ExecutionError("SERPAPI key is missing. Set AGENT_PLATFORM_SERPAPI_API_KEY.")

        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": input_data["query"],
                "num": input_data["num_results"],
                "api_key": api_key,
            },
            timeout=context.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        organic = payload.get("organic_results", [])

        results = []
        for item in organic[: input_data["num_results"]]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "snippet": item.get("snippet"),
                }
            )
        return ToolResult(ok=True, data={"query": input_data["query"], "results": results})

