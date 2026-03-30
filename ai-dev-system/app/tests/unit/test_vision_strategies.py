from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.agent.state import ActionRequest, SelectorSpec, WindowTarget
from app.agent.strategies.base_strategy import ExecutionContext
from app.agent.strategies.vision_strategies import VisionLlmClickStrategy
from app.config.settings import Settings
from app.vision.locator import VisionLlmLocator


class _FakePyAutoGui:
    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []

    def click_point(self, x: int, y: int) -> None:
        self.points.append((x, y))

    def type_text(self, text: str) -> None:
        raise AssertionError("type_text should not be called in this test")


class _FakeScreens:
    def capture(self, path: Path, region=None) -> Path:
        return path

    def capture_image(self, region=None):
        return Image.new("RGB", (100, 100))


class _FakeGuard:
    def ensure_safe(self, expected_handle=None) -> None:
        return None


def test_vision_strategy_offsets_click_by_region_origin() -> None:
    locator = VisionLlmLocator(
        resolver=lambda payload: {
            "bounding_box": [10, 20, 30, 40],
            "confidence": 0.9,
            "target_description": payload["target_description"],
            "reason": "offset-test",
        }
    )
    ctx = ExecutionContext(
        action=ActionRequest(name="click_console", action_type="click"),
        profile=type("Profile", (), {"region_hints": {"results": (0.1, 0.2, 0.5, 0.5)}})(),
        active_window=WindowTarget(handle=1, title="Window", class_name="Window", pid=1, bounds=(100, 200, 300, 500)),
        window_selector=SelectorSpec(handle=1, backend="uia"),
        pywinauto=type("Pywinauto", (), {})(),
        pyautogui=_FakePyAutoGui(),
        screen_capture=_FakeScreens(),
        guard=_FakeGuard(),
        settings=Settings.default(),
        artifact_dir=Path("."),
        metadata={},
    )

    VisionLlmClickStrategy(locator).execute(ctx)

    assert ctx.pyautogui.points == [(140, 290)]
    assert ctx.metadata["vision"]["screen_click_point"] == [140, 290]
