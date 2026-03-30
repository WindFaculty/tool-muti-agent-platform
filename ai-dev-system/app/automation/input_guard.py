from __future__ import annotations

import time
from typing import Callable

import keyboard

from app.platform.base import DesktopDriver


class InputGuard:
    """Enforce safety checks before mutating desktop input."""

    def __init__(
        self,
        driver: DesktopDriver,
        *,
        hotkey: str,
        action_delay_seconds: float,
        require_foreground: bool,
    ) -> None:
        self._driver = driver
        self._hotkey = hotkey
        self._action_delay_seconds = action_delay_seconds
        self._require_foreground = require_foreground
        self._stop_requested = False
        self._registered = False

    def start(self) -> None:
        if not self._driver.is_interactive_desktop_available():
            raise RuntimeError("Interactive desktop is unavailable; refusing to send input.")
        try:
            keyboard.add_hotkey(self._hotkey, self._request_stop)
            self._registered = True
        except Exception as exc:
            raise RuntimeError(f"Could not register emergency stop hotkey {self._hotkey}: {exc}") from exc

    def stop(self) -> None:
        if self._registered:
            keyboard.remove_hotkey(self._hotkey)
            self._registered = False

    def ensure_safe(self, expected_handle: int | None = None) -> None:
        if self._stop_requested:
            raise RuntimeError("Emergency stop was requested.")
        if self._require_foreground and expected_handle is not None:
            active = None
            for _ in range(10):
                active = self._driver.get_active_window()
                if active is not None and active.handle == expected_handle:
                    return
                time.sleep(0.1)
            raise RuntimeError(
                f"Foreground window mismatch. Expected handle {expected_handle}, got {getattr(active, 'handle', None)}."
            )

    def require_destructive_confirmation(self, confirmed: bool, action_name: str) -> None:
        if not confirmed:
            raise RuntimeError(f"Destructive action '{action_name}' requires explicit confirmation.")

    def delay(self) -> None:
        time.sleep(self._action_delay_seconds)

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    def _request_stop(self) -> None:
        self._stop_requested = True
