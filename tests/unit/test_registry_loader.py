from __future__ import annotations

from pathlib import Path

from app.registry.tool_loader import ToolLoader
from app.registry.tool_registry import ToolRegistry


def test_tool_loader_registers_expected_tools() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "config" / "tools.yaml"

    registry = ToolRegistry()
    count = ToolLoader(config_path).load_into_registry(registry)

    assert count >= 27
    assert registry.get("read_file").tool.name == "read_file"
    assert registry.get("docker_build").tool.name == "docker_build"
    assert registry.get("git_push").tool.name == "git_push"
    assert registry.get("terminal_runner").tool.name == "terminal_runner"
    assert registry.get("submit_multiview_reconstruction").tool.name == "submit_multiview_reconstruction"
