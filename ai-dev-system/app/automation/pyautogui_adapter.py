from __future__ import annotations

from pathlib import Path
from typing import Any

import pyautogui


class PyAutoGuiAdapter:
    """Vision-backed fallback input layer using PyAutoGUI."""

    def __init__(self, pause_seconds: float) -> None:
        pyautogui.PAUSE = pause_seconds
        # Keep FAILSAFE enabled: moving cursor to top-left corner triggers an emergency stop.
        # This is intentional — do NOT disable it.
        pyautogui.FAILSAFE = True

    def locate_on_screen(
        self,
        image_path: Path,
        *,
        region: tuple[int, int, int, int] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any] | None:
        match = pyautogui.locateOnScreen(str(image_path), region=region, confidence=confidence)
        if match is None:
            return None
        return {
            "left": match.left,
            "top": match.top,
            "width": match.width,
            "height": match.height,
            "center": pyautogui.center(match),
        }

    def click_image(
        self,
        image_path: Path,
        *,
        region: tuple[int, int, int, int] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        match = self.locate_on_screen(image_path, region=region, confidence=confidence)
        if match is None:
            raise LookupError(f"Could not locate image on screen: {image_path}")
        center = match["center"]
        pyautogui.click(center.x, center.y)
        return match

    def click_point(self, x: int, y: int) -> None:
        pyautogui.click(x, y)

    def type_text(self, text: str) -> None:
        pyautogui.write(text, interval=0.02)

    def hotkey(self, *keys: str) -> None:
        pyautogui.hotkey(*keys)
