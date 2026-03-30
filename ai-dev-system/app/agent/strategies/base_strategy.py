from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.agent.state import ActionRequest, SelectorSpec, WindowTarget
    from app.automation.input_guard import InputGuard
    from app.config.settings import Settings
    from app.platform.base import PointerKeyboardAdapter, ScreenCaptureAdapter, StructuredUiAdapter
    from app.profiles.base_profile import BaseProfile


@dataclass(slots=True)
class ExecutionContext:
    """All runtime dependencies available to a strategy during execution."""

    action: "ActionRequest"
    profile: "BaseProfile"
    active_window: "WindowTarget | None"
    window_selector: "SelectorSpec"
    pywinauto: "StructuredUiAdapter"
    pyautogui: "PointerKeyboardAdapter"
    screen_capture: "ScreenCaptureAdapter"
    guard: "InputGuard"
    settings: "Settings"
    artifact_dir: Path
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class ActionStrategy(Protocol):
    """Contract that every action strategy must fulfil."""

    def can_handle(self, strategy_name: str) -> bool:
        """Return True when this object handles the given strategy name."""
        ...

    def execute(self, ctx: ExecutionContext) -> None:
        """Execute the strategy. Raise on failure."""
        ...
