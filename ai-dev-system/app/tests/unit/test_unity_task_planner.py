from __future__ import annotations

import pytest

from app.unity.task_planner import UnityTaskPlanner


def test_unity_task_planner_maps_alias_to_editor_capability() -> None:
    actions = UnityTaskPlanner().build_actions("attach editor")

    assert len(actions) == 1
    assert actions[0].capability == "editor.attach"
    assert actions[0].backend == "gui"


def test_unity_task_planner_maps_scene_command() -> None:
    actions = UnityTaskPlanner().build_actions("open scene Assets/Scenes/AIDemoBasic3D.unity")

    assert len(actions) == 1
    assert actions[0].capability == "scene.manage"
    assert actions[0].params["action"] == "load"


def test_unity_task_planner_rejects_unknown_prompt() -> None:
    with pytest.raises(ValueError, match="Unsupported Unity task"):
        UnityTaskPlanner().build_actions("do literally anything")
