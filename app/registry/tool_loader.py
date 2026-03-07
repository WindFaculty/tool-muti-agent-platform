from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

from app.core.errors import ConfigurationError
from app.registry.base_tool import BaseTool
from app.registry.tool_registry import ToolRegistry


class ToolLoader:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def load_into_registry(self, registry: ToolRegistry) -> int:
        config = self._read_config()
        tools = config.get("tools", [])
        loaded = 0

        for entry in tools:
            tool = self._build_tool(entry)
            required_permissions = entry.get("required_permissions", [])
            registry.register(tool, required_permissions=required_permissions)
            loaded += 1
        return loaded

    def _read_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise ConfigurationError(f"Tool config file not found: {self.config_path}")
        try:
            return yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise ConfigurationError(f"Failed to parse tool config: {exc}") from exc

    def _build_tool(self, entry: dict[str, Any]) -> BaseTool:
        module_name = entry.get("module")
        class_name = entry.get("class")
        if not module_name or not class_name:
            raise ConfigurationError("Each tool config entry must define module and class")

        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except Exception as exc:
            raise ConfigurationError(
                f"Unable to load tool '{entry.get('name', class_name)}': {exc}"
            ) from exc

        tool = cls()
        if not isinstance(tool, BaseTool):
            raise ConfigurationError(f"{class_name} does not inherit from BaseTool")

        if entry.get("name"):
            tool.name = entry["name"]
        if entry.get("description"):
            tool.description = entry["description"]
        return tool

