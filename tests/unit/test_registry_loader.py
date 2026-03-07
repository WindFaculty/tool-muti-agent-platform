from __future__ import annotations

from pathlib import Path

from app.registry.tool_loader import ToolLoader
from app.registry.tool_registry import ToolRegistry


def test_tool_loader_registers_18_tools() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "config" / "tools.yaml"

    registry = ToolRegistry()
    count = ToolLoader(config_path).load_into_registry(registry)

    assert count == 18
    assert registry.get("read_file").tool.name == "read_file"
    assert registry.get("docker_build").tool.name == "docker_build"

