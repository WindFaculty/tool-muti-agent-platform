from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.registry.base_tool import BaseTool, ToolContext, ToolResult


class ScraperInput(BaseModel):
    url: str
    selector: str | None = None
    timeout_sec: int = Field(default=20, ge=1, le=120)
    max_items: int = Field(default=100, ge=1, le=1000)


class ScraperTool(BaseTool):
    name = "scraper"
    description = "Extract text and links from HTML pages"
    input_model = ScraperInput

    def execute(self, context: ToolContext, input_data: dict) -> ToolResult:
        response = requests.get(input_data["url"], timeout=input_data["timeout_sec"])
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        selector = input_data.get("selector")
        if selector:
            elements = soup.select(selector)[: input_data["max_items"]]
            text_items = [element.get_text(" ", strip=True) for element in elements]
        else:
            elements = soup.find_all(["p", "li"])[: input_data["max_items"]]
            text_items = [element.get_text(" ", strip=True) for element in elements]

        links = []
        for link in soup.find_all("a", href=True)[: input_data["max_items"]]:
            links.append(link.get("href"))

        return ToolResult(
            ok=True,
            data={
                "url": input_data["url"],
                "selector": selector,
                "texts": text_items,
                "links": links,
            },
        )

