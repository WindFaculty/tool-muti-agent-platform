from __future__ import annotations

import re
from pathlib import Path

from app.agent.state import ActionRequest, SelectorSpec, VerificationCheck
from app.profiles.base_profile import BaseProfile
from app.profiles.registry import ProfileRegistry


@ProfileRegistry.register("explorer")
class ExplorerProfile(BaseProfile):
    """Profile for Windows File Explorer.

    Supported task forms:
      'navigate to <path>'
      'create folder <name>'
      'create folder <name> in <path>'
    """

    _PATTERN_NAVIGATE = re.compile(r"navigate\s+to\s+(?P<path>.+)", re.IGNORECASE)
    _PATTERN_CREATE_FOLDER = re.compile(
        r"create\s+folder\s+(?P<name>[^\s]+)(?:\s+in\s+(?P<path>.+))?", re.IGNORECASE
    )

    def __init__(self) -> None:
        super().__init__(
            name="explorer",
            executable="explorer.exe",
            window_selector=SelectorSpec(
                title_re=r".*",
                class_name="CabinetWClass",
                backend="uia",
            ),
            launch_delay_seconds=2.0,
            region_hints={
                "address_bar": (0.04, 0.05, 0.80, 0.10),
            },
        )

    def build_plan(self, task: str, working_directory: Path) -> list[ActionRequest]:
        match = self._PATTERN_NAVIGATE.search(task)
        if match:
            return self._plan_navigate(match.group("path").strip())

        match = self._PATTERN_CREATE_FOLDER.search(task)
        if match:
            folder_name = match.group("name").strip()
            in_path = match.group("path").strip() if match.group("path") else None
            return self._plan_create_folder(folder_name, in_path)

        raise ValueError(
            "Unsupported Explorer task. Supported forms:\n"
            "  'navigate to <path>'\n"
            "  'create folder <name>'\n"
            "  'create folder <name> in <path>'"
        )

    # ------------------------------------------------------------------
    # Sub-plan builders
    # ------------------------------------------------------------------

    def _plan_navigate(self, path: str) -> list[ActionRequest]:
        return [
            ActionRequest(
                name="focus_address_bar",
                action_type="hotkey",
                value="%d",  # Alt+D focuses the address bar
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[],
            ),
            ActionRequest(
                name="type_path",
                action_type="type_text",
                target=SelectorSpec(control_type="Edit", automation_id="TestNameControlID", backend="uia"),
                value=path,
                allowed_strategies=["pywinauto_type", "pywinauto_set_text", "image_type"],
                postconditions=[],
            ),
            ActionRequest(
                name="confirm_navigation",
                action_type="hotkey",
                value="{ENTER}",
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[
                    VerificationCheck(
                        kind="window_title_contains",
                        expected=Path(path).name or path,
                        timeout_seconds=5.0,
                    ),
                ],
            ),
        ]

    def _plan_create_folder(self, folder_name: str, in_path: str | None) -> list[ActionRequest]:
        steps: list[ActionRequest] = []
        if in_path:
            steps.extend(self._plan_navigate(in_path))
        steps.append(
            ActionRequest(
                name="open_new_folder_menu",
                action_type="hotkey",
                value="^+n",  # Ctrl+Shift+N = New Folder in Explorer
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[],
            )
        )
        steps.append(
            ActionRequest(
                name="type_folder_name",
                action_type="type_text",
                target=SelectorSpec(control_type="Edit", backend="uia"),
                value=folder_name,
                allowed_strategies=["pywinauto_type", "image_type"],
                postconditions=[],
            )
        )
        steps.append(
            ActionRequest(
                name="confirm_folder_name",
                action_type="hotkey",
                value="{ENTER}",
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[
                    VerificationCheck(
                        kind="control_exists",
                        selector=SelectorSpec(title=folder_name, control_type="ListItem", backend="uia"),
                        timeout_seconds=5.0,
                    ),
                ],
            )
        )
        return steps
