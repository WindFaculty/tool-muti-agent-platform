from __future__ import annotations

import pytest

from app.agent.task_spec import TaskActionSpec, TaskSpec
from app.unity.capabilities import UnityCapabilityRegistry


def test_capability_matrix_marks_mcp_and_gui_support() -> None:
    matrix = UnityCapabilityRegistry.build_matrix(
        tools=["manage_scene", "manage_editor", "manage_gameobject", "batch_execute", "manage_shader", "manage_vfx", "manage_animation"],
        resources=["editor_state"],
    )
    rows = {row["capability"]: row for row in matrix}

    assert rows["scene.manage"]["status"] == "supported_via_mcp"
    assert rows["editor.layout.assert"]["status"] == "supported_via_gui_fallback"
    assert rows["editor.layout.normalize"]["status"] == "manual_validation_required"
    assert rows["shader.manage"]["status"] == "manual_validation_required"
    assert rows["vfx.manage"]["status"] == "manual_validation_required"
    assert rows["animator.graph.manage"]["status"] == "manual_validation_required"
    assert rows["timeline.manage"]["status"] == "unsupported"


def test_compile_actions_prefers_mcp_when_tool_available() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        actions=[TaskActionSpec(capability="scene.manage", params={"action": "load", "path": "Assets/Scenes/A.unity"})],
    )

    plan = UnityCapabilityRegistry.compile_actions(task_spec=spec, tools=["manage_scene"], resources=[])

    assert len(plan) == 1
    assert plan[0].action_type == "mcp_tool"
    assert plan[0].metadata["resolved_backend"] == "mcp"


def test_compile_actions_falls_back_to_gui_when_mcp_unavailable() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        actions=[TaskActionSpec(capability="editor.play")],
    )

    plan = UnityCapabilityRegistry.compile_actions(task_spec=spec, tools=[], resources=[])

    assert len(plan) == 1
    assert plan[0].action_type == "hotkey"
    assert plan[0].metadata["resolved_backend"] == "gui"


def test_compile_actions_supports_background_job_modes() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        actions=[
            TaskActionSpec(
                capability="tests.run",
                params={"mode": "EditMode"},
                execution={"mode": "background_job_start", "job_key": "tests"},
            )
        ],
    )

    plan = UnityCapabilityRegistry.compile_actions(task_spec=spec, tools=["run_tests"], resources=[])

    assert plan[0].postconditions[0].kind == "mcp_job_started"
    assert plan[0].metadata["execution"]["mode"] == "background_job_start"


def test_compile_actions_rejects_unsupported_capability() -> None:
    spec = TaskSpec(
        profile="unity-editor",
        actions=[TaskActionSpec(capability="scene.manage", params={"action": "load", "path": "Assets/Scenes/A.unity"})],
    )

    with pytest.raises(ValueError, match="unsupported"):
        UnityCapabilityRegistry.compile_actions(task_spec=spec, tools=[], resources=[])
