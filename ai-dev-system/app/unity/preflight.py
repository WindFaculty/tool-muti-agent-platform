from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any

from app.agent.task_spec import TaskSpec
from app.agent.state import WindowTarget
from app.automation.pywinauto_adapter import PywinautoAdapter
from app.automation.windows_driver import WindowsDriver
from app.unity.surfaces import UnitySurfaceMap


class UnityPreflight:
    def evaluate(
        self,
        *,
        task_input: str | TaskSpec,
        driver: WindowsDriver,
        pywinauto: PywinautoAdapter,
        active_window: WindowTarget,
        run_context: dict[str, Any] | None = None,
        require_gui: bool = True,
        require_mcp: bool = True,
        required_capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        context = run_context or {}
        visible_names = self._visible_names(require_gui=require_gui, pywinauto=pywinauto)
        layout_policy = self._layout_policy(task_input)
        required_layout = str(layout_policy.get("required") or (task_input.requires_layout if isinstance(task_input, TaskSpec) else "default-6000") or "default-6000")
        required_surface_names = UnitySurfaceMap.layout_surface_names(required_layout)
        missing_surfaces = self._missing_surfaces(required_surface_names, visible_names)

        sibling_windows = [
            window
            for window in driver.list_top_windows()
            if window.pid == active_window.pid and window.handle != active_window.handle
        ]
        modal_windows = [
            asdict(window)
            for window in sibling_windows
            if window.class_name == "#32770" or "popup" in window.class_name.lower() or "dialog" in window.title.lower()
        ]

        selector_blind = require_gui and (len(visible_names) < 10 or "Application" not in visible_names)
        project_ok = "unity-client" in active_window.title
        interactive = driver.is_interactive_desktop_available() if require_gui else True
        layout_file_exists = UnitySurfaceMap.layout_path().exists() if require_gui else True
        mcp_tools = set(context.get("available_tools") or [])
        capability_matrix = list(context.get("capability_matrix") or [])
        capability_statuses = {row.get("capability"): row.get("status") for row in capability_matrix if isinstance(row, dict)}
        missing_capabilities = [
            capability
            for capability in (required_capabilities or [])
            if capability_statuses.get(capability) == "unsupported"
        ]
        tool_group_snapshot = context.get("tool_groups") or []
        mcp_connected = bool(context.get("mcp_connected"))
        layout_normalize_attempted = False
        layout_normalize_succeeded = False
        if (
            require_gui
            and missing_surfaces
            and layout_policy.get("normalize_if_needed", True)
            and context.get("unity_runtime") is not None
            and mcp_connected
            and capability_statuses.get("editor.layout.normalize") != "unsupported"
        ):
            layout_normalize_attempted = True
            self._normalize_layout(context["unity_runtime"], required_layout)
            visible_names = self._visible_names(require_gui=require_gui, pywinauto=pywinauto)
            missing_surfaces = self._missing_surfaces(required_surface_names, visible_names)
            layout_normalize_succeeded = not missing_surfaces

        checks = {
            "mcp_connected": mcp_connected,
            "capabilities_available": not missing_capabilities,
            "interactive_desktop": interactive,
            "layout_file_exists": layout_file_exists,
            "project_window_matches": project_ok,
            "modal_absent": not modal_windows,
            "selector_visible": not selector_blind,
            "layout_ready": not missing_surfaces if require_gui else True,
            "layout_normalize_attempted": layout_normalize_attempted,
            "layout_normalize_succeeded": layout_normalize_succeeded,
        }
        blocked_reason = None
        if require_mcp and not mcp_connected:
            blocked_reason = "Unity MCP connection is unavailable."
        elif missing_capabilities:
            blocked_reason = f"Required Unity capabilities are unavailable: {', '.join(missing_capabilities)}"
        elif not interactive:
            blocked_reason = "Interactive desktop is unavailable."
        elif not layout_file_exists:
            blocked_reason = f"Required layout file is missing: {UnitySurfaceMap.layout_path()}"
        elif not project_ok:
            blocked_reason = f"Unity window is not attached to the expected project: {active_window.title}"
        elif require_gui and modal_windows:
            blocked_reason = "Unity has blocking modal or popup windows open."
        elif require_gui and selector_blind:
            blocked_reason = "Unity editor did not expose enough selectors for safe automation."
        elif require_gui and missing_surfaces and layout_policy.get("strict_after_normalize", True):
            blocked_reason = "Unity default layout is not active."

        return {
            "checks": checks,
            "required_layout": required_layout,
            "expected_layout_surfaces": required_surface_names,
            "missing_surfaces": missing_surfaces,
            "modal_windows": modal_windows,
            "visible_names": sorted(name for name in visible_names if name),
            "available_tools": sorted(mcp_tools),
            "tool_groups": tool_group_snapshot,
            "required_capabilities": list(required_capabilities or []),
            "missing_capabilities": missing_capabilities,
            "require_gui": require_gui,
            "require_mcp": require_mcp,
            "layout_policy": layout_policy,
            "blocked_reason": blocked_reason,
        }

    @staticmethod
    def _visible_names(*, require_gui: bool, pywinauto: PywinautoAdapter) -> set[str]:
        if not require_gui:
            return set()
        root = pywinauto.resolve_window(UnitySurfaceMap.editor_selector(), backend="uia")
        tree = pywinauto.dump_control_tree(root, max_depth=2, max_nodes=120)
        return {str(item.get("name") or "") for item in tree}

    @staticmethod
    def _missing_surfaces(required_surface_names: list[str], visible_names: set[str]) -> list[str]:
        expected_titles = [UnitySurfaceMap.surface(name).selector.title or "" for name in required_surface_names]
        return [
            name for name, expected_title in zip(required_surface_names, expected_titles) if expected_title not in visible_names
        ]

    @staticmethod
    def _layout_policy(task_input: str | TaskSpec) -> dict[str, Any]:
        if not isinstance(task_input, TaskSpec):
            return {
                "required": "default-6000",
                "normalize_if_needed": True,
                "strict_after_normalize": True,
            }
        policy = dict(task_input.layout_policy or {})
        policy.setdefault("required", task_input.requires_layout or "default-6000")
        policy.setdefault("normalize_if_needed", True)
        policy.setdefault("strict_after_normalize", True)
        return policy

    @staticmethod
    def _normalize_layout(runtime, layout_name: str) -> None:
        commands = [
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layouts/{layout_name}"}},
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layout/{layout_name}"}},
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layouts/Load Layout/{layout_name}"}},
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layout/Load Layout/{layout_name}"}},
        ]
        runtime.call_tool(
            "batch_execute",
            {
                "commands": commands,
                "fail_fast": False,
                "parallel": False,
            },
        )
        time.sleep(0.5)
