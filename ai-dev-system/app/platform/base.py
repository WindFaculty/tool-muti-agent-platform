from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from app.agent.state import SelectorSpec, WindowTarget


class DesktopDriver(Protocol):
    def list_top_windows(self) -> list[WindowTarget]:
        ...

    def get_active_window(self) -> WindowTarget | None:
        ...

    def launch(self, command: list[str] | str) -> Any:
        ...

    def wait_for_window(
        self,
        selector: SelectorSpec,
        timeout_seconds: float,
        predicate=None,
    ) -> WindowTarget:
        ...

    def is_interactive_desktop_available(self) -> bool:
        ...


class StructuredUiAdapter(Protocol):
    def resolve_window(self, selector: SelectorSpec, backend: str | None = None):
        ...

    def resolve_control(self, root, selector: SelectorSpec):
        ...

    def dump_control_tree(self, root, max_depth: int = 4, max_nodes: int = 250) -> list[dict[str, Any]]:
        ...

    def click(self, root, selector: SelectorSpec) -> None:
        ...

    def invoke(self, root, selector: SelectorSpec) -> None:
        ...

    def select(self, root, selector: SelectorSpec) -> None:
        ...

    def type_text(self, root, selector: SelectorSpec, text: str) -> None:
        ...

    def set_text(self, root, selector: SelectorSpec, text: str) -> None:
        ...

    def send_hotkey(self, root, keys: str) -> None:
        ...

    def menu_select(self, root, menu_path: str) -> None:
        ...

    def exists(self, root, selector: SelectorSpec) -> bool:
        ...

    def bounds(self, wrapper) -> tuple[int, int, int, int]:
        ...

    def get_text(self, root, selector: SelectorSpec) -> str:
        ...


class PointerKeyboardAdapter(Protocol):
    def locate_on_screen(
        self,
        image_path: Path,
        *,
        region: tuple[int, int, int, int] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any] | None:
        ...

    def click_image(
        self,
        image_path: Path,
        *,
        region: tuple[int, int, int, int] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        ...

    def click_point(self, x: int, y: int) -> None:
        ...

    def type_text(self, text: str) -> None:
        ...

    def hotkey(self, *keys: str) -> None:
        ...


class ScreenCaptureAdapter(Protocol):
    def capture(self, path: Path, region: tuple[int, int, int, int] | None = None) -> Path:
        ...

    def capture_image(self, region: tuple[int, int, int, int] | None = None):
        ...
