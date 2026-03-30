from __future__ import annotations

import pytest

from app.agent.task_spec import TaskSpec
from app.unity.macros import UnityMacroRegistry


def test_unity_macro_registry_contains_expected_v1_macros() -> None:
    names = UnityMacroRegistry.names()

    for name in [
        "launch_editor",
        "attach_editor",
        "assert_layout_ready",
        "focus_hierarchy",
        "focus_project",
        "focus_inspector",
        "focus_scene_view",
        "focus_game_view",
        "focus_console",
        "open_window",
        "select_gameobject",
        "select_asset",
        "play_mode",
        "stop_mode",
        "pause_mode",
        "open_scene",
        "create_gameobject",
        "duplicate_selection",
        "delete_selection",
        "rename_selection",
        "add_component",
        "create_folder",
        "create_material",
        "capture_view",
        "dump_control_tree",
        "snapshot_console",
    ]:
        assert name in names


def test_unity_open_scene_plan_is_dialog_driven() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        macro="open_scene",
        args={"scene_path": "Assets/Scenes/SampleScene.unity"},
        requires_layout="default-6000",
    )

    plan = UnityMacroRegistry.build_plan(spec)

    assert [step.name for step in plan] == ["open_scene_menu", "set_scene_path", "confirm_open_scene"]
    assert plan[0].action_type == "menu_select"
    assert plan[1].action_type == "set_text"
    assert plan[2].action_type == "click"
    assert plan[2].postconditions[0].expected == "SampleScene"


def test_unity_play_mode_plan_uses_ctrl_p() -> None:
    spec = TaskSpec(profile="unity-editor", macro="play_mode", requires_layout="default-6000")

    plan = UnityMacroRegistry.build_plan(spec)

    assert len(plan) == 1
    assert plan[0].action_type == "hotkey"
    assert plan[0].value == "^p"


def test_unity_add_component_maps_path_to_menu_select() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        macro="add_component",
        args={"component_path": "Rendering/Light"},
        confirm_destructive=True,
        requires_layout="default-6000",
    )

    plan = UnityMacroRegistry.build_plan(spec)

    assert len(plan) == 1
    assert plan[0].action_type == "menu_select"
    assert plan[0].value == "Component->Rendering->Light"
    assert plan[0].destructive is True


def test_unity_open_window_rejects_unknown_window() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        macro="open_window",
        args={"window": "Profiler"},
        requires_layout="default-6000",
    )

    with pytest.raises(ValueError, match="Unsupported Unity window"):
        UnityMacroRegistry.build_plan(spec)
