from __future__ import annotations

import re
from pathlib import Path

from app.agent.state import ActionRequest, SelectorSpec, VerificationCheck
from app.profiles.base_profile import BaseProfile
from app.profiles.registry import ProfileRegistry


@ProfileRegistry.register("notepad")
class NotepadProfile(BaseProfile):
    """Profile for the modern Windows Notepad app."""

    def __init__(self) -> None:
        super().__init__(
            name="notepad",
            executable="notepad.exe",
            window_selector=SelectorSpec(title_re=".*Notepad", class_name="Notepad", backend="uia"),
            region_hints={
                "editor": (0.04, 0.18, 0.96, 0.82),
                "title": (0.0, 0.0, 1.0, 0.14),
            },
        )

    # Named regex constants — kept at class level for readability and reuse
    _PATTERN_TYPE_AND_SAVE = re.compile(
        r"type\s+(?P<text>.+?)(?:\s+and\s+save|\s+save)", re.IGNORECASE
    )
    _PATTERN_SAVE_PATH = re.compile(
        r"(?:save\s+(?:to|as)\s+)(?P<path>[A-Za-z]:\\[^\"\r\n]+|[^\"\r\n]+\.txt)", re.IGNORECASE
    )
    _PATTERN_CLEAR_AND_TYPE = re.compile(
        r"(?:clear\s+and\s+type|clear\s+then\s+type)\s+(?P<text>.+?)(?:\s+and\s+save|\s+save|$)",
        re.IGNORECASE,
    )
    _PATTERN_APPEND = re.compile(
        r"append\s+(?P<text>.+?)(?:\s+and\s+save|\s+save|$)", re.IGNORECASE
    )
    _PATTERN_OPEN_NEW = re.compile(r"open\s+new|new\s+document", re.IGNORECASE)

    def build_plan(self, task: str, working_directory: Path) -> list[ActionRequest]:
        # Dispatch to the appropriate sub-plan builder based on detected intent
        if self._PATTERN_CLEAR_AND_TYPE.search(task):
            return self._plan_clear_and_type(task, working_directory)
        if self._PATTERN_APPEND.search(task):
            return self._plan_append(task, working_directory)
        if self._PATTERN_TYPE_AND_SAVE.search(task):
            return self._plan_type_and_save(task, working_directory)
        if self._PATTERN_OPEN_NEW.search(task):
            return self._plan_open_new()

        raise ValueError(
            "Unsupported notepad task. Supported forms:\n"
            "  'type <text> and save'\n"
            "  'type <text> and save to <path>'\n"
            "  'clear and type <text> and save'\n"
            "  'append <text> and save'\n"
            "  'open new'"
        )

    # ------------------------------------------------------------------
    # Sub-plan builders
    # ------------------------------------------------------------------

    def _plan_type_and_save(self, task: str, working_directory: Path) -> list[ActionRequest]:
        text_match = self._PATTERN_TYPE_AND_SAVE.search(task)
        if text_match is None:
            raise ValueError("Could not extract the text to type for Notepad.")
        content = text_match.group("text").strip()
        if not content:
            raise ValueError("The Notepad task did not include any text to type.")
        save_path = self._resolve_save_path(task, working_directory)
        save_dialog_selector = SelectorSpec(title_re="(?i)save as", class_name="#32770", backend="win32")
        return [
            self._action_open_new_document(),
            ActionRequest(
                name="type_in_editor",
                action_type="type_text",
                target=SelectorSpec(control_type="Document", backend="uia"),
                value=content,
                allowed_strategies=["pywinauto_type", "pywinauto_set_text", "image_type", "coordinate_click"],
                postconditions=[
                    VerificationCheck(kind="window_title_contains", expected="Notepad", timeout_seconds=4.0),
                ],
            ),
            *self._actions_save_as(save_path, save_dialog_selector),
        ]

    def _plan_clear_and_type(self, task: str, working_directory: Path) -> list[ActionRequest]:
        text_match = self._PATTERN_CLEAR_AND_TYPE.search(task)
        if text_match is None:
            raise ValueError("Could not extract the text to type for 'clear and type'.")
        content = text_match.group("text").strip()
        save_path = self._resolve_save_path(task, working_directory)
        save_dialog_selector = SelectorSpec(title_re="(?i)save as", class_name="#32770", backend="win32")
        return [
            ActionRequest(
                name="select_all",
                action_type="hotkey",
                value="^a",
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[],
            ),
            ActionRequest(
                name="delete_selection",
                action_type="hotkey",
                value="{DELETE}",
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[],
            ),
            ActionRequest(
                name="type_in_editor",
                action_type="type_text",
                target=SelectorSpec(control_type="Document", backend="uia"),
                value=content,
                allowed_strategies=["pywinauto_type", "pywinauto_set_text", "image_type"],
                postconditions=[
                    VerificationCheck(kind="window_title_contains", expected="Notepad", timeout_seconds=4.0),
                ],
            ),
            *self._actions_save_as(save_path, save_dialog_selector),
        ]

    def _plan_append(self, task: str, working_directory: Path) -> list[ActionRequest]:
        text_match = self._PATTERN_APPEND.search(task)
        if text_match is None:
            raise ValueError("Could not extract the text to append for Notepad.")
        content = text_match.group("text").strip()
        save_path = self._resolve_save_path(task, working_directory)
        save_dialog_selector = SelectorSpec(title_re="(?i)save as", class_name="#32770", backend="win32")
        return [
            ActionRequest(
                name="move_to_end",
                action_type="hotkey",
                value="^{END}",
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                postconditions=[],
            ),
            ActionRequest(
                name="type_append",
                action_type="type_text",
                target=SelectorSpec(control_type="Document", backend="uia"),
                value=content,
                allowed_strategies=["pywinauto_type", "pywinauto_set_text", "image_type"],
                postconditions=[
                    VerificationCheck(kind="window_title_contains", expected="Notepad", timeout_seconds=4.0),
                ],
            ),
            *self._actions_save_as(save_path, save_dialog_selector),
        ]

    def _plan_open_new(self) -> list[ActionRequest]:
        return [self._action_open_new_document()]

    # ------------------------------------------------------------------
    # Shared action builders
    # ------------------------------------------------------------------

    @staticmethod
    def _action_open_new_document() -> ActionRequest:
        return ActionRequest(
            name="open_new_document",
            action_type="hotkey",
            value="^n",
            allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
            postconditions=[
                VerificationCheck(kind="window_title_contains", expected="Notepad", timeout_seconds=4.0),
            ],
        )

    @staticmethod
    def _actions_save_as(save_path: Path, save_dialog_selector: SelectorSpec) -> list[ActionRequest]:
        return [
            ActionRequest(
                name="open_file_menu",
                action_type="click",
                target=SelectorSpec(title="File", automation_id="File", control_type="MenuItem", backend="uia"),
                allowed_strategies=["pywinauto_click", "pywinauto_invoke"],
                postconditions=[
                    VerificationCheck(
                        kind="control_exists",
                        selector=SelectorSpec(title="Save as", control_type="MenuItem", backend="uia"),
                        timeout_seconds=4.0,
                    ),
                ],
            ),
            ActionRequest(
                name="open_save_dialog",
                action_type="click",
                target=SelectorSpec(title="Save as", control_type="MenuItem", backend="uia"),
                allowed_strategies=["pywinauto_click", "pywinauto_invoke"],
                postconditions=[
                    VerificationCheck(kind="window_exists", selector=save_dialog_selector, timeout_seconds=6.0),
                ],
            ),
            ActionRequest(
                name="set_save_path",
                action_type="set_text",
                target=SelectorSpec(class_name="Edit", backend="win32", found_index=0),
                value=str(save_path),
                allowed_strategies=["pywinauto_set_text", "pywinauto_type", "image_type", "coordinate_click"],
                postconditions=[
                    VerificationCheck(
                        kind="control_text_contains",
                        selector=SelectorSpec(class_name="Edit", backend="win32", found_index=0),
                        expected=save_path.name,
                        timeout_seconds=3.0,
                    ),
                ],
            ),
            ActionRequest(
                name="confirm_save",
                action_type="click",
                target=SelectorSpec(title="&Save", class_name="Button", backend="win32"),
                allowed_strategies=["pywinauto_click", "pywinauto_invoke", "image_click", "coordinate_click"],
                metadata={"save_path": str(save_path)},
                postconditions=[
                    VerificationCheck(kind="file_exists", expected=str(save_path), timeout_seconds=8.0),
                    VerificationCheck(
                        kind="window_title_contains",
                        selector=SelectorSpec(title_re=".*Notepad", class_name="Notepad", backend="uia"),
                        expected=save_path.name,
                        timeout_seconds=6.0,
                    ),
                ],
            ),
        ]

    def _resolve_save_path(self, task: str, working_directory: Path) -> Path:
        path_match = self._PATTERN_SAVE_PATH.search(task)
        if path_match:
            return Path(path_match.group("path")).expanduser()
        return working_directory / "notepad-output.txt"
