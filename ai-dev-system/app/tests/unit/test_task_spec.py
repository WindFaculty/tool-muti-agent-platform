from __future__ import annotations

import textwrap

import pytest

from app.agent.task_spec import TaskSpec


def test_task_spec_from_file_supports_macro_payload(tmp_path) -> None:
    spec_path = tmp_path / "unity-task.yaml"
    spec_path.write_text(
        textwrap.dedent(
            """
            profile: unity-editor
            macro: open_scene
            args:
              scene_path: Assets/Scenes/SampleScene.unity
            confirm_destructive: false
            requires_layout: default-6000
            evidence:
              screenshot: true
              control_tree: false
              console_snapshot: false
            """
        ).strip(),
        encoding="utf-8",
    )

    spec = TaskSpec.from_file(spec_path)

    assert spec.profile == "unity-editor"
    assert spec.task is None
    assert spec.macro == "open_scene"
    assert spec.args["scene_path"] == "Assets/Scenes/SampleScene.unity"
    assert spec.requires_layout == "default-6000"
    assert spec.evidence["screenshot"] is True


def test_task_spec_from_file_supports_actions_and_verify(tmp_path) -> None:
    spec_path = tmp_path / "unity-actions.yaml"
    spec_path.write_text(
        textwrap.dedent(
            """
            profile: unity-editor
            actions:
              - capability: scene.manage
                params:
                  action: load
                  path: Assets/Scenes/AIDemoBasic3D.unity
                heal_hints:
                  focus_surface: project
                execution:
                  mode: blocking
              - capability: editor.layout.assert
                backend: gui
                allow_fallback: false
            layout_policy:
              required: default-6000
              normalize_if_needed: true
              strict_after_normalize: true
            execution:
              mode: blocking
            verify:
              - kind: active_scene_path_is
                params:
                  path: Assets/Scenes/AIDemoBasic3D.unity
            """
        ).strip(),
        encoding="utf-8",
    )

    spec = TaskSpec.from_file(spec_path)

    assert spec.profile == "unity-editor"
    assert len(spec.actions) == 2
    assert spec.actions[0].capability == "scene.manage"
    assert spec.actions[0].heal_hints["focus_surface"] == "project"
    assert spec.actions[0].execution["mode"] == "blocking"
    assert spec.actions[1].backend == "gui"
    assert spec.actions[1].allow_fallback is False
    assert spec.layout_policy["normalize_if_needed"] is True
    assert spec.execution["mode"] == "blocking"
    assert spec.verify[0].kind == "active_scene_path_is"


def test_task_spec_requires_task_or_macro(tmp_path) -> None:
    spec_path = tmp_path / "invalid.yaml"
    spec_path.write_text("profile: unity-editor\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must include either 'task', 'macro', or 'actions'"):
        TaskSpec.from_file(spec_path)
