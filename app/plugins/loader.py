from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


class PluginLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def discover_workflow_files(self) -> list[Path]:
        files: list[Path] = []
        plugin_root = self.settings.resolve_path(self.settings.plugins_root)
        external_root = self.settings.resolve_path(Path("tools"))
        if plugin_root.exists():
            files.extend(sorted(plugin_root.rglob("*.yaml")))
        workflows_root = external_root / "workflows"
        if workflows_root.exists():
            files.extend(sorted(workflows_root.rglob("*.yaml")))
        return files

    def discover_prompt_files(self) -> list[Path]:
        files: list[Path] = []
        plugin_root = self.settings.resolve_path(self.settings.plugins_root)
        external_root = self.settings.resolve_path(Path("tools"))
        if plugin_root.exists():
            files.extend(sorted(plugin_root.rglob("*_prompt.md")))
        prompts_root = external_root / "prompts"
        if prompts_root.exists():
            files.extend(sorted(prompts_root.rglob("*_prompt.md")))
        return files
