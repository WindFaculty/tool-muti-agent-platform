from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.agent.state import ActionRequest, SelectorSpec, VerificationCheck
from app.agent.task_spec import TaskSpec
from app.unity.surfaces import UnitySurfaceMap, UnitySurfaceSpec


@dataclass(frozen=True, slots=True)
class UnityMacroSpec:
    name: str
    destructive: bool
    builder: Callable[[TaskSpec], list[ActionRequest]]


class UnityMacroRegistry:
    _MENU_ONLY_WINDOWS = {"console", "animator", "package-manager", "ui-builder"}

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._SPECS)

    @classmethod
    def get(cls, name: str) -> UnityMacroSpec:
        if name not in cls._SPECS:
            known = ", ".join(sorted(cls._SPECS))
            raise ValueError(f"Unknown Unity macro '{name}'. Known macros: {known}")
        return cls._SPECS[name]

    @classmethod
    def build_plan(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        if not task_spec.macro:
            raise ValueError("Unity macro tasks require 'macro'.")
        return cls.get(task_spec.macro).builder(cls, task_spec)

    @classmethod
    def _no_actions(cls, _: TaskSpec) -> list[ActionRequest]:
        return []

    @classmethod
    def _focus_surface(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        surface_name = task_spec.args.get("surface") or task_spec.macro.removeprefix("focus_").replace("_view", "")
        surface = UnitySurfaceMap.surface(str(surface_name).replace("_", "-"))
        return [cls._open_or_focus_action(surface, destructive=False)]

    @classmethod
    def _open_window(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        window_name = str(task_spec.args.get("window") or "")
        if not window_name:
            raise ValueError("open_window requires args.window")
        surface = UnitySurfaceMap.resolve_window_alias(window_name)
        return [cls._open_or_focus_action(surface, destructive=False)]

    @classmethod
    def _save_project(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._menu_action("save_project", "File->Save Project", destructive=False)]

    @classmethod
    def _save_scene(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._menu_action("save_scene", "File->Save", destructive=False)]

    @classmethod
    def _play_mode(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._hotkey_action("play_mode", "^p", destructive=False)]

    @classmethod
    def _stop_mode(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._hotkey_action("stop_mode", "^p", destructive=False)]

    @classmethod
    def _pause_mode(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._hotkey_action("pause_mode", "^+p", destructive=False)]

    @classmethod
    def _open_scene(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        scene_path = str(task_spec.args.get("scene_path") or "")
        if not scene_path:
            raise ValueError("open_scene requires args.scene_path")
        scene_name = Path(scene_path).stem
        dialog_selector = SelectorSpec(title_re=r"(?i).*open.*", class_name="#32770", backend="win32")
        return [
            cls._menu_action("open_scene_menu", "File->Open Scene...", destructive=False),
            ActionRequest(
                name="set_scene_path",
                action_type="set_text",
                target=SelectorSpec(class_name="Edit", backend="win32", found_index=0),
                value=str(UnitySurfaceMap.project_root() / scene_path),
                allowed_strategies=["pywinauto_set_text", "pywinauto_type"],
                metadata={"window_selector": dialog_selector},
                postconditions=[
                    VerificationCheck(
                        kind="control_text_contains",
                        selector=SelectorSpec(class_name="Edit", backend="win32", found_index=0),
                        expected=Path(scene_path).name,
                        timeout_seconds=3.0,
                        metadata={"window_selector": dialog_selector},
                    )
                ],
            ),
            ActionRequest(
                name="confirm_open_scene",
                action_type="click",
                target=SelectorSpec(title_re=r"(?i)&?open", class_name="Button", backend="win32"),
                allowed_strategies=["pywinauto_click", "pywinauto_invoke"],
                metadata={"window_selector": dialog_selector},
                postconditions=[VerificationCheck(kind="window_title_contains", expected=scene_name, timeout_seconds=8.0)],
            ),
        ]

    @classmethod
    def _create_folder(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        name = str(task_spec.args.get("name") or "").strip()
        if not name:
            raise ValueError("create_folder requires args.name")
        expected_path = UnitySurfaceMap.project_root() / "Assets" / name
        return [
            cls._menu_action("create_folder_menu", "Assets->Create->Folder", destructive=True),
            cls._hotkey_action("rename_new_folder", name, destructive=True),
            cls._hotkey_action("confirm_new_folder_name", "{ENTER}", destructive=True),
            ActionRequest(
                name="verify_new_folder_exists",
                action_type="hotkey",
                value="",
                allowed_strategies=["pywinauto_hotkey"],
                postconditions=[VerificationCheck(kind="file_exists", expected=str(expected_path), timeout_seconds=5.0)],
            ),
        ]

    @classmethod
    def _create_material(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        name = str(task_spec.args.get("name") or "").strip()
        if not name:
            raise ValueError("create_material requires args.name")
        expected_path = UnitySurfaceMap.project_root() / "Assets" / f"{name}.mat"
        return [
            cls._menu_action("create_material_menu", "Assets->Create->Material", destructive=True),
            cls._hotkey_action("rename_new_material", name, destructive=True),
            cls._hotkey_action("confirm_new_material_name", "{ENTER}", destructive=True),
            ActionRequest(
                name="verify_new_material_exists",
                action_type="hotkey",
                value="",
                allowed_strategies=["pywinauto_hotkey"],
                postconditions=[VerificationCheck(kind="file_exists", expected=str(expected_path), timeout_seconds=5.0)],
            ),
        ]

    @classmethod
    def _create_gameobject(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        primitive_type = str(task_spec.args.get("primitive_type") or task_spec.args.get("kind") or "empty").strip().lower()
        menu_path = {
            "empty": "GameObject->Create Empty",
            "cube": "GameObject->3D Object->Cube",
            "sphere": "GameObject->3D Object->Sphere",
            "capsule": "GameObject->3D Object->Capsule",
            "plane": "GameObject->3D Object->Plane",
            "quad": "GameObject->3D Object->Quad",
        }.get(primitive_type)
        if menu_path is None:
            raise ValueError("create_gameobject only supports empty, cube, sphere, capsule, plane, or quad")
        actions = [cls._menu_action("create_gameobject_menu", menu_path, destructive=True)]
        name = str(task_spec.args.get("name") or "").strip()
        if name:
            actions.extend(
                [
                    cls._hotkey_action("rename_created_gameobject", "{F2}", destructive=True),
                    cls._hotkey_action("type_created_gameobject_name", name, destructive=True),
                    cls._hotkey_action("confirm_created_gameobject_name", "{ENTER}", destructive=True),
                ]
            )
        return actions

    @classmethod
    def _duplicate_selection(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._hotkey_action("duplicate_selection", "^d", destructive=True)]

    @classmethod
    def _delete_selection(cls, _: TaskSpec) -> list[ActionRequest]:
        return [cls._hotkey_action("delete_selection", "{DELETE}", destructive=True)]

    @classmethod
    def _rename_selection(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        name = str(task_spec.args.get("name") or "").strip()
        if not name:
            raise ValueError("rename_selection requires args.name")
        return [
            cls._hotkey_action("start_rename_selection", "{F2}", destructive=True),
            cls._hotkey_action("type_selection_name", name, destructive=True),
            cls._hotkey_action("confirm_selection_name", "{ENTER}", destructive=True),
        ]

    @classmethod
    def _add_component(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        component_path = str(task_spec.args.get("component_path") or "").strip()
        if not component_path:
            raise ValueError("add_component requires args.component_path")
        return [cls._menu_action("add_component_menu", "Component->" + component_path.replace("/", "->"), destructive=True)]

    @classmethod
    def _search_hierarchy(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        query = str(task_spec.args.get("query") or task_spec.args.get("name") or "").strip()
        if not query:
            raise ValueError("search_hierarchy requires args.query or args.name")
        return [
            cls._open_or_focus_action(UnitySurfaceMap.surface("hierarchy"), destructive=False),
            cls._hotkey_action("open_hierarchy_search", "^f", destructive=False),
            cls._hotkey_action("type_hierarchy_search", query, destructive=False),
            cls._hotkey_action("confirm_hierarchy_search", "{ENTER}", destructive=False),
        ]

    @classmethod
    def _search_project(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        query = str(task_spec.args.get("query") or task_spec.args.get("name") or "").strip()
        if not query:
            raise ValueError("search_project requires args.query or args.name")
        return [
            cls._open_or_focus_action(UnitySurfaceMap.surface("project"), destructive=False),
            cls._hotkey_action("open_project_search", "^f", destructive=False),
            cls._hotkey_action("type_project_search", query, destructive=False),
            cls._hotkey_action("confirm_project_search", "{ENTER}", destructive=False),
        ]

    @classmethod
    def _select_gameobject(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        return cls._search_hierarchy(task_spec)

    @classmethod
    def _select_asset(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        return cls._search_project(task_spec)

    @classmethod
    def _capture_view(cls, task_spec: TaskSpec) -> list[ActionRequest]:
        surface_name = str(task_spec.args.get("surface") or "game")
        return [cls._open_or_focus_action(UnitySurfaceMap.surface(surface_name), destructive=False)]

    @classmethod
    def _dump_control_tree(cls, _: TaskSpec) -> list[ActionRequest]:
        return []

    @classmethod
    def _snapshot_console(cls, _: TaskSpec) -> list[ActionRequest]:
        return [
            cls._open_or_focus_action(UnitySurfaceMap.surface("console"), destructive=False),
            cls._hotkey_action("select_console_text", "^a", destructive=False),
            cls._hotkey_action("copy_console_text", "^c", destructive=False),
        ]

    @classmethod
    def _menu_action(cls, name: str, menu_path: str, *, destructive: bool) -> ActionRequest:
        return ActionRequest(
            name=name,
            action_type="menu_select",
            value=menu_path,
            allowed_strategies=["pywinauto_menu_select"],
            destructive=destructive,
            metadata={"window_selector": UnitySurfaceMap.editor_selector()},
            postconditions=[VerificationCheck(kind="window_title_contains", expected="unity-client", timeout_seconds=5.0)],
        )

    @classmethod
    def _hotkey_action(cls, name: str, keys: str, *, destructive: bool) -> ActionRequest:
        return ActionRequest(
            name=name,
            action_type="hotkey",
            value=keys,
            allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
            destructive=destructive,
            metadata={"window_selector": UnitySurfaceMap.editor_selector()},
            postconditions=[VerificationCheck(kind="window_title_contains", expected="unity-client", timeout_seconds=5.0)],
        )

    @classmethod
    def _open_or_focus_action(cls, surface: UnitySurfaceSpec, *, destructive: bool) -> ActionRequest:
        if surface.focus_hotkey and surface.key not in cls._MENU_ONLY_WINDOWS:
            return ActionRequest(
                name=f"focus_{surface.key}",
                action_type="hotkey",
                value=surface.focus_hotkey,
                allowed_strategies=["pywinauto_hotkey", "pyautogui_hotkey"],
                destructive=destructive,
                metadata={"window_selector": UnitySurfaceMap.editor_selector()},
                postconditions=[VerificationCheck(kind="control_exists", selector=surface.selector, timeout_seconds=5.0)],
            )
        if surface.menu_path:
            return ActionRequest(
                name=f"open_{surface.key}",
                action_type="menu_select",
                value=surface.menu_path,
                allowed_strategies=["pywinauto_menu_select"],
                destructive=destructive,
                metadata={"window_selector": UnitySurfaceMap.editor_selector()},
                postconditions=[VerificationCheck(kind="control_exists", selector=surface.selector, timeout_seconds=5.0)],
            )
        raise ValueError(f"Unity surface '{surface.key}' does not define a focus path.")

    _SPECS: dict[str, UnityMacroSpec] = {
        "launch_editor": UnityMacroSpec("launch_editor", False, _no_actions.__func__),
        "attach_editor": UnityMacroSpec("attach_editor", False, _no_actions.__func__),
        "ensure_project_open": UnityMacroSpec("ensure_project_open", False, _no_actions.__func__),
        "assert_no_modal": UnityMacroSpec("assert_no_modal", False, _no_actions.__func__),
        "assert_layout_ready": UnityMacroSpec("assert_layout_ready", False, _no_actions.__func__),
        "save_project": UnityMacroSpec("save_project", False, _save_project.__func__),
        "save_scene": UnityMacroSpec("save_scene", False, _save_scene.__func__),
        "focus_hierarchy": UnityMacroSpec("focus_hierarchy", False, _focus_surface.__func__),
        "focus_project": UnityMacroSpec("focus_project", False, _focus_surface.__func__),
        "focus_inspector": UnityMacroSpec("focus_inspector", False, _focus_surface.__func__),
        "focus_scene_view": UnityMacroSpec("focus_scene_view", False, _focus_surface.__func__),
        "focus_game_view": UnityMacroSpec("focus_game_view", False, _focus_surface.__func__),
        "focus_console": UnityMacroSpec("focus_console", False, _focus_surface.__func__),
        "open_window": UnityMacroSpec("open_window", False, _open_window.__func__),
        "select_gameobject": UnityMacroSpec("select_gameobject", False, _select_gameobject.__func__),
        "select_asset": UnityMacroSpec("select_asset", False, _select_asset.__func__),
        "search_hierarchy": UnityMacroSpec("search_hierarchy", False, _search_hierarchy.__func__),
        "search_project": UnityMacroSpec("search_project", False, _search_project.__func__),
        "play_mode": UnityMacroSpec("play_mode", False, _play_mode.__func__),
        "stop_mode": UnityMacroSpec("stop_mode", False, _stop_mode.__func__),
        "pause_mode": UnityMacroSpec("pause_mode", False, _pause_mode.__func__),
        "open_scene": UnityMacroSpec("open_scene", False, _open_scene.__func__),
        "create_gameobject": UnityMacroSpec("create_gameobject", True, _create_gameobject.__func__),
        "duplicate_selection": UnityMacroSpec("duplicate_selection", True, _duplicate_selection.__func__),
        "delete_selection": UnityMacroSpec("delete_selection", True, _delete_selection.__func__),
        "rename_selection": UnityMacroSpec("rename_selection", True, _rename_selection.__func__),
        "add_component": UnityMacroSpec("add_component", True, _add_component.__func__),
        "create_folder": UnityMacroSpec("create_folder", True, _create_folder.__func__),
        "create_material": UnityMacroSpec("create_material", True, _create_material.__func__),
        "capture_view": UnityMacroSpec("capture_view", False, _capture_view.__func__),
        "dump_control_tree": UnityMacroSpec("dump_control_tree", False, _dump_control_tree.__func__),
        "snapshot_console": UnityMacroSpec("snapshot_console", False, _snapshot_console.__func__),
    }
