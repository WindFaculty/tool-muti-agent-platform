from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.agent.state import ActionRequest, SelectorSpec

if TYPE_CHECKING:
    from app.agent.state import RunState, WindowTarget
    from app.agent.task_spec import TaskSpec
    from app.automation.pywinauto_adapter import PywinautoAdapter
    from app.automation.windows_driver import WindowsDriver
    from app.config.settings import Settings
    from app.logging.artifacts import ArtifactManager
    from app.logging.logger import GuiAgentLogger
    from app.vision.screenshot import ScreenshotService


@dataclass(slots=True)
class BaseProfile:
    """Base profile contract for one target Windows app."""

    name: str
    executable: str | list[str]
    window_selector: SelectorSpec
    launch_delay_seconds: float = 3.0
    coordinate_fallbacks: dict[str, tuple[int, int]] = field(default_factory=dict)
    region_hints: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)

    def build_plan(self, task: str, working_directory: Path) -> list[ActionRequest]:
        raise NotImplementedError

    def build_plan_from_task_spec(self, task_spec: "TaskSpec", working_directory: Path) -> list[ActionRequest]:
        if not task_spec.task:
            raise ValueError(f"Profile '{self.name}' requires a free-form task string.")
        return self.build_plan(task_spec.task, working_directory)

    def task_spec_from_alias(self, task: str) -> "TaskSpec | None":
        return None

    def run_preflight(
        self,
        *,
        task_input: str | "TaskSpec",
        settings: "Settings",
        driver: "WindowsDriver",
        pywinauto: "PywinautoAdapter",
        artifacts: "ArtifactManager",
        logger: "GuiAgentLogger",
        active_window: "WindowTarget",
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {}

    def prepare_run_context(
        self,
        *,
        task_input: str | "TaskSpec",
        settings: "Settings",
        driver: "WindowsDriver",
        pywinauto: "PywinautoAdapter",
        artifacts: "ArtifactManager",
        logger: "GuiAgentLogger",
        active_window: "WindowTarget | None",
    ) -> dict[str, Any]:
        return {}

    def cleanup_run_context(
        self,
        *,
        task_input: str | "TaskSpec",
        settings: "Settings",
        artifacts: "ArtifactManager",
        logger: "GuiAgentLogger",
        run_context: dict[str, Any] | None,
    ) -> None:
        return None

    def inspect_extras(
        self,
        *,
        settings: "Settings",
        driver: "WindowsDriver",
        pywinauto: "PywinautoAdapter",
        screenshots: "ScreenshotService",
        artifacts: "ArtifactManager",
        logger: "GuiAgentLogger",
        target_window: "WindowTarget",
    ) -> dict[str, Any]:
        return {}

    def summary_file_name(self) -> str | None:
        return None

    def build_run_summary(
        self,
        *,
        task_input: str | "TaskSpec",
        settings: "Settings",
        driver: "WindowsDriver",
        pywinauto: "PywinautoAdapter",
        screenshots: "ScreenshotService",
        artifacts: "ArtifactManager",
        logger: "GuiAgentLogger",
        state: "RunState",
        preflight: dict[str, Any],
        error: str | None,
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return None

    def run_task_verification(
        self,
        *,
        task_input: str | "TaskSpec",
        settings: "Settings",
        artifacts: "ArtifactManager",
        logger: "GuiAgentLogger",
        state: "RunState",
        run_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {"passed": True, "checks": []}

    def inspect_selector(self) -> SelectorSpec:
        return self.window_selector

    def list_capabilities(
        self,
        *,
        settings: "Settings",
    ) -> dict[str, Any]:
        return {"profile": self.name, "capabilities": []}

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "executable": self.executable,
            "window_selector": self.window_selector.to_window_criteria(),
            "coordinate_fallbacks": self.coordinate_fallbacks,
            "region_hints": self.region_hints,
        }
