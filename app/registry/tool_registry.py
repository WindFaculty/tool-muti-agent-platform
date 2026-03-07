from __future__ import annotations

import threading
from dataclasses import dataclass

from app.core.errors import ToolNotFoundError
from app.registry.base_tool import BaseTool


@dataclass
class RegisteredTool:
    tool: BaseTool
    required_permissions: list[str]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._lock = threading.Lock()

    def register(self, tool: BaseTool, required_permissions: list[str] | None = None) -> None:
        with self._lock:
            self._tools[tool.name] = RegisteredTool(
                tool=tool,
                required_permissions=required_permissions or [],
            )

    def get(self, tool_name: str) -> RegisteredTool:
        with self._lock:
            if tool_name not in self._tools:
                raise ToolNotFoundError(tool_name)
            return self._tools[tool_name]

    def list_tools(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "name": registered.tool.name,
                    "description": registered.tool.description,
                    "input_schema": registered.tool.input_schema(),
                    "required_permissions": registered.required_permissions,
                }
                for registered in self._tools.values()
            ]

