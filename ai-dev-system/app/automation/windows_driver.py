from __future__ import annotations

import ctypes
import subprocess
import time
from pathlib import Path
from typing import Callable

import win32gui
import win32process

from app.agent.state import SelectorSpec, WindowTarget


class WindowsDriver:
    """Observe desktop state and launch Windows desktop apps."""

    def list_top_windows(self) -> list[WindowTarget]:
        windows: list[WindowTarget] = []

        def callback(hwnd: int, _: int) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title.strip():
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            windows.append(
                WindowTarget(
                    handle=hwnd,
                    title=title,
                    class_name=win32gui.GetClassName(hwnd),
                    pid=pid,
                    bounds=rect,
                )
            )

        win32gui.EnumWindows(callback, 0)
        return windows

    def get_active_window(self) -> WindowTarget | None:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return None
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        return WindowTarget(
            handle=hwnd,
            title=title,
            class_name=win32gui.GetClassName(hwnd),
            pid=pid,
            bounds=rect,
        )

    def launch(self, command: list[str] | str) -> subprocess.Popen[bytes]:
        return subprocess.Popen(command if isinstance(command, list) else [command])

    def wait_for_window(
        self,
        selector: SelectorSpec,
        timeout_seconds: float,
        predicate: Callable[[WindowTarget], bool] | None = None,
    ) -> WindowTarget:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            matches = [window for window in self.list_top_windows() if self._matches(window, selector)]
            if predicate is not None:
                matches = [window for window in matches if predicate(window)]
            if matches:
                index = min(selector.found_index, len(matches) - 1)
                return matches[index]
            time.sleep(0.2)
        raise TimeoutError(f"Timed out waiting for window: {selector}")

    def is_interactive_desktop_available(self) -> bool:
        user32 = ctypes.windll.user32
        desktop = user32.OpenInputDesktop(0, False, 0x0100)
        if desktop:
            user32.CloseDesktop(desktop)
            return True
        return False

    @staticmethod
    def _matches(window: WindowTarget, selector: SelectorSpec) -> bool:
        if selector.handle is not None and window.handle != selector.handle:
            return False
        if selector.title is not None and window.title != selector.title:
            return False
        if selector.title_re is not None:
            import re

            if re.search(selector.title_re, window.title) is None:
                return False
        if selector.class_name is not None and window.class_name != selector.class_name:
            return False
        return True
