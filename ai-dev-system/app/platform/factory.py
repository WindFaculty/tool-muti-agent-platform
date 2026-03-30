from __future__ import annotations

import sys
from dataclasses import dataclass

from app.automation.pyautogui_adapter import PyAutoGuiAdapter
from app.automation.pywinauto_adapter import PywinautoAdapter
from app.automation.windows_driver import WindowsDriver
from app.config.settings import Settings
from app.vision.screenshot import ScreenshotService


@dataclass(slots=True)
class PlatformBundle:
    driver: WindowsDriver
    structured_ui: PywinautoAdapter
    pointer_keyboard: PyAutoGuiAdapter
    screen_capture: ScreenshotService


class PlatformFactory:
    @staticmethod
    def create(settings: Settings) -> PlatformBundle:
        if not sys.platform.startswith("win"):
            raise RuntimeError(
                f"Current implementation only supports Windows desktop automation. Detected platform: {sys.platform}."
            )
        return PlatformBundle(
            driver=WindowsDriver(),
            structured_ui=PywinautoAdapter(),
            pointer_keyboard=PyAutoGuiAdapter(settings.action_delay_seconds),
            screen_capture=ScreenshotService(),
        )
