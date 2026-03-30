from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pyperclip
from pywinauto import Desktop
from pywinauto.base_wrapper import BaseWrapper
from pywinauto.controls.uiawrapper import UIAWrapper

from app.agent.state import SelectorSpec


class PywinautoAdapter:
    """Use pywinauto as the primary structured UI automation layer."""

    def resolve_window(self, selector: SelectorSpec, backend: str | None = None) -> BaseWrapper:
        selected_backend = backend or selector.backend or "uia"
        desktop = Desktop(backend=selected_backend)
        candidates = desktop.windows(**selector.to_window_criteria())
        unique = self._dedupe_by_handle(candidates)
        visible = [window for window in unique if not selector.visible_only or window.is_visible()]
        if not visible:
            raise LookupError(f"No window matched selector {selector} using backend {selected_backend}")
        index = min(selector.found_index, len(visible) - 1)
        return visible[index]

    def resolve_control(self, root: BaseWrapper, selector: SelectorSpec) -> BaseWrapper:
        descendants = root.descendants()
        matches: list[BaseWrapper] = []
        for item in descendants:
            info = item.element_info
            if selector.visible_only and not item.is_visible():
                continue
            if selector.title is not None and info.name != selector.title:
                continue
            if selector.title_re is not None:
                import re

                if re.search(selector.title_re, info.name or "") is None:
                    continue
            if selector.automation_id is not None and info.automation_id != selector.automation_id:
                continue
            if selector.class_name is not None and info.class_name != selector.class_name:
                continue
            if selector.control_type is not None and info.control_type != selector.control_type:
                continue
            matches.append(item)
        if not matches:
            raise LookupError(f"No control matched selector {selector}")
        index = min(selector.found_index, len(matches) - 1)
        return matches[index]

    def dump_control_tree(self, root: BaseWrapper, max_depth: int = 4, max_nodes: int = 250) -> list[dict[str, Any]]:
        tree: list[dict[str, Any]] = []
        queue: list[tuple[BaseWrapper, int]] = [(root, 0)]
        while queue and len(tree) < max_nodes:
            current, depth = queue.pop(0)
            info = current.element_info
            tree.append(
                {
                    "depth": depth,
                    "name": info.name,
                    "class_name": info.class_name,
                    "control_type": info.control_type,
                    "automation_id": info.automation_id,
                    "handle": getattr(current, "handle", None),
                }
            )
            if depth >= max_depth:
                continue
            try:
                children = current.children()
            except Exception:
                children = []
            for child in children:
                queue.append((child, depth + 1))
        return tree

    def click(self, root: BaseWrapper, selector: SelectorSpec) -> None:
        self.resolve_control(root, selector).click_input()

    def invoke(self, root: BaseWrapper, selector: SelectorSpec) -> None:
        control = self.resolve_control(root, selector)
        if hasattr(control, "invoke"):
            control.invoke()
            return
        control.click_input()

    def select(self, root: BaseWrapper, selector: SelectorSpec) -> None:
        control = self.resolve_control(root, selector)
        if hasattr(control, "select"):
            control.select()
            return
        control.click_input()

    def type_text(self, root: BaseWrapper, selector: SelectorSpec, text: str) -> None:
        control = self.resolve_control(root, selector)
        control.set_focus()
        previous_clipboard = None
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = None
        try:
            pyperclip.copy(text)
            control.type_keys("^v", set_foreground=True)
        finally:
            if previous_clipboard is not None:
                try:
                    pyperclip.copy(previous_clipboard)
                except Exception:
                    pass

    def set_text(self, root: BaseWrapper, selector: SelectorSpec, text: str) -> None:
        control = self.resolve_control(root, selector)
        if hasattr(control, "set_edit_text"):
            control.set_edit_text(text)
            return
        if hasattr(control, "set_text"):
            control.set_text(text)
            return
        control.type_keys("^a{BACKSPACE}" + text, with_spaces=True, set_foreground=True)

    def send_hotkey(self, root: BaseWrapper, keys: str) -> None:
        root.set_focus()
        root.type_keys(keys, set_foreground=True)

    def menu_select(self, root: BaseWrapper, menu_path: str) -> None:
        root.set_focus()
        root.menu_select(menu_path)

    def exists(self, root: BaseWrapper, selector: SelectorSpec) -> bool:
        try:
            self.resolve_control(root, selector)
            return True
        except Exception:
            return False

    def bounds(self, wrapper: BaseWrapper) -> tuple[int, int, int, int]:
        rect = wrapper.rectangle()
        return (rect.left, rect.top, rect.right, rect.bottom)

    def get_text(self, root: BaseWrapper, selector: SelectorSpec) -> str:
        control = self.resolve_control(root, selector)
        text = control.window_text()
        if text:
            return text
        legacy = getattr(control, "texts", None)
        if callable(legacy):
            values = legacy()
            return " ".join(value for value in values if value)
        if isinstance(control, UIAWrapper):
            return control.iface_value.CurrentValue if hasattr(control, "iface_value") else ""
        return ""

    @staticmethod
    def _dedupe_by_handle(candidates: Iterable[BaseWrapper]) -> list[BaseWrapper]:
        deduped: list[BaseWrapper] = []
        seen: set[int] = set()
        for candidate in candidates:
            handle = getattr(candidate, "handle", None)
            if handle in seen:
                continue
            if handle is not None:
                seen.add(handle)
            deduped.append(candidate)
        return deduped
