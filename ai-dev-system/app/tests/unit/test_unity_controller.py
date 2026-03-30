from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.controller import AgentController
from app.agent.state import RunState, WindowTarget
from app.agent.task_spec import TaskSpec
from app.config.settings import Settings
from app.logging.artifacts import ArtifactManager
from app.logging.logger import GuiAgentLogger
from app.profiles.unity_editor_profile import UnityEditorProfile
from app.unity.capabilities import UnityCapabilityRegistry
from app.unity.surfaces import UnitySurfaceMap


class _FakePywinauto:
    def __init__(self, visible_names):
        self._visible_names = visible_names

    def resolve_window(self, selector, backend=None):
        return object()

    def dump_control_tree(self, root, max_depth=2, max_nodes=120):
        return [{"name": name} for name in self._visible_names]


def _unity_window() -> WindowTarget:
    return WindowTarget(
        handle=100,
        title="unity-client - SampleScene - Windows, Mac, Linux - Unity 6.3 LTS (6000.3.11f1) <DX12>",
        class_name="UnityContainerWndClass",
        pid=42,
        bounds=(0, 0, 1920, 1080),
    )


def _run_context() -> dict:
    tools = ["manage_scene", "manage_editor", "manage_gameobject"]
    return {
        "mcp_connected": True,
        "available_tools": tools,
        "available_resources": ["editor_state"],
        "tool_groups": [],
        "capability_matrix": UnityCapabilityRegistry.build_matrix(tools=tools, resources=["editor_state"]),
    }


class _FakeUnityRuntime:
    def __init__(self, snapshots: list[dict]) -> None:
        self._snapshots = list(snapshots)
        self.console_reads = 0

    def read_json_resource(self, uri: str) -> dict:
        assert uri == AgentController._UNITY_EDITOR_STATE_URI
        if len(self._snapshots) > 1:
            current = self._snapshots.pop(0)
        else:
            current = self._snapshots[0]
        return {"data": current}

    def call_tool(self, name: str, arguments: dict) -> dict:
        assert name == "read_console"
        self.console_reads += 1
        return {"structured_content": {"success": True, "entries": []}}


def _editor_state(phase: str, *, is_changing: bool) -> dict:
    return {
        "observed_at_unix_ms": 1774796047098,
        "editor": {"play_mode": {"is_playing": False, "is_paused": False, "is_changing": is_changing}},
        "activity": {"phase": phase, "reasons": ["tick"]},
        "advice": {"ready_for_tools": not is_changing, "blocking_reasons": ["playmode_transition"] if is_changing else []},
    }


class _FakeScreenshots:
    def __init__(self) -> None:
        self.regions: list[tuple[int, int, int, int]] = []

    def capture(self, path: Path, region=None) -> Path:
        path.write_bytes(b"shot")
        if region is not None:
            self.regions.append(region)
        return path


class _FakeSurfacePywinauto:
    def resolve_window(self, selector, backend=None):
        if getattr(selector, "class_name", None) == "UnityGUIViewWndClass":
            raise LookupError("surface wrapper missing")
        return object()

    def dump_control_tree(self, root, max_depth=2, max_nodes=120):
        return [{"name": "UnityEditor.GameView"}]

    def bounds(self, wrapper) -> tuple[int, int, int, int]:
        return (100, 200, 1100, 900)


def test_unity_controller_writes_summary_for_dry_run(tmp_path) -> None:
    settings = Settings.default()
    settings.dry_run = True
    settings.artifact_root = tmp_path / "logs"
    controller = AgentController(settings)
    window = _unity_window()
    controller._attach_or_launch = lambda profile: window  # type: ignore[method-assign]
    controller._driver.list_top_windows = lambda: [window]  # type: ignore[method-assign]
    controller._driver.is_interactive_desktop_available = lambda: True  # type: ignore[method-assign]
    controller._pywinauto = _FakePywinauto(
        [
            "Application",
            "UnityEditor.MainToolbarWindow",
            "UnityEditor.SceneHierarchyWindow",
            "UnityEditor.InspectorWindow",
            "UnityEditor.ConsoleWindow",
            "UnityEditor.GameView",
            "File",
            "Edit",
            "Assets",
            "GameObject",
        ]
    )

    profile = UnityEditorProfile()
    task = TaskSpec(profile="unity-editor", macro="assert_layout_ready", requires_layout="default-6000")
    context = _run_context()
    profile.prepare_run_context = lambda **kwargs: context  # type: ignore[method-assign]
    profile.cleanup_run_context = lambda **kwargs: None  # type: ignore[method-assign]
    profile._last_run_context = context

    result = controller.run(profile, task)

    assert result["status"] == "completed"
    summary_path = tmp_path / "logs" / Path(result["artifact_dir"]).name / "unity-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["preflight"]["checks"]["layout_ready"] is True
    assert summary["verification_result"]["passed"] is True


def test_unity_controller_records_preflight_failure(tmp_path) -> None:
    settings = Settings.default()
    settings.dry_run = True
    settings.artifact_root = tmp_path / "logs"
    controller = AgentController(settings)
    window = _unity_window()
    controller._attach_or_launch = lambda profile: window  # type: ignore[method-assign]
    controller._driver.list_top_windows = lambda: [window]  # type: ignore[method-assign]
    controller._driver.is_interactive_desktop_available = lambda: True  # type: ignore[method-assign]
    controller._pywinauto = _FakePywinauto(
        [
            "Application",
            "UnityEditor.MainToolbarWindow",
            "UnityEditor.SceneHierarchyWindow",
            "UnityEditor.InspectorWindow",
            "File",
            "Edit",
            "Assets",
            "GameObject",
            "Window",
            "Help",
        ]
    )

    profile = UnityEditorProfile()
    task = TaskSpec(profile="unity-editor", macro="assert_layout_ready", requires_layout="default-6000")
    context = _run_context()
    profile.prepare_run_context = lambda **kwargs: context  # type: ignore[method-assign]
    profile.cleanup_run_context = lambda **kwargs: None  # type: ignore[method-assign]
    profile._last_run_context = context

    with pytest.raises(RuntimeError, match="Unity default layout is not active"):
        controller.run(profile, task)

    run_dir = next((tmp_path / "logs").iterdir())
    summary = json.loads((run_dir / "unity-summary.json").read_text(encoding="utf-8"))
    assert summary["blocked_reason"] == "Unity default layout is not active."


def test_unity_controller_waits_for_editor_state_before_capture(tmp_path) -> None:
    settings = Settings.default()
    controller = AgentController(settings)
    profile = UnityEditorProfile()
    artifacts = ArtifactManager.create(tmp_path / "logs", "unity-editor")
    logger = GuiAgentLogger(artifacts.run_dir / "run.jsonl")
    state = RunState(
        run_id="run-1",
        profile_name="unity-editor",
        task="capture",
        artifact_dir=artifacts.run_dir,
        active_window=_unity_window(),
    )
    runtime = _FakeUnityRuntime(
        [
            _editor_state("playmode_transition", is_changing=True),
            _editor_state("playmode_transition", is_changing=True),
            _editor_state("idle", is_changing=False),
        ]
    )

    controller._wait_for_unity_editor_stable(  # type: ignore[attr-defined]
        profile,
        artifacts,
        logger,
        state,
        {"unity_runtime": runtime},
        "capture-before",
    )

    assert state.details["unity_editor_state_wait"]["timed_out"] is False
    assert state.details["unity_editor_state_wait"]["latest"]["activity_phase"] == "idle"


def test_unity_controller_times_out_on_playmode_transition_and_records_artifacts(tmp_path, monkeypatch) -> None:
    settings = Settings.default()
    controller = AgentController(settings)
    profile = UnityEditorProfile()
    artifacts = ArtifactManager.create(tmp_path / "logs", "unity-editor")
    logger = GuiAgentLogger(artifacts.run_dir / "run.jsonl")
    state = RunState(
        run_id="run-2",
        profile_name="unity-editor",
        task="capture",
        artifact_dir=artifacts.run_dir,
        active_window=_unity_window(),
    )
    runtime = _FakeUnityRuntime([_editor_state("playmode_transition", is_changing=True)])
    clock = {"value": 0.0}

    monkeypatch.setattr("app.agent.controller.time.time", lambda: clock["value"])
    monkeypatch.setattr("app.agent.controller.time.sleep", lambda seconds: clock.__setitem__("value", clock["value"] + seconds))
    monkeypatch.setattr(controller, "_capture_window", lambda window, path: path.write_bytes(b"fake-shot"))

    with pytest.raises(RuntimeError, match="playmode_transition"):
        controller._wait_for_unity_editor_stable(  # type: ignore[attr-defined]
            profile,
            artifacts,
            logger,
            state,
            {"unity_runtime": runtime},
            "capture-after",
        )

    wait_payload = state.details["unity_editor_state_wait"]
    assert wait_payload["timed_out"] is True
    assert Path(wait_payload["artifacts"]["editor_state_snapshots"]).exists()
    assert Path(wait_payload["artifacts"]["console_snapshot"]).exists()
    assert Path(wait_payload["artifacts"]["last_window_screenshot"]).exists()
    assert runtime.console_reads == 1


def test_unity_controller_only_refreshes_active_window_with_same_pid() -> None:
    current = _unity_window()
    same_process = WindowTarget(handle=101, title="Unity modal", class_name="#32770", pid=42, bounds=(10, 10, 50, 50))
    other_process = WindowTarget(handle=500, title="Visual Studio Code", class_name="Chrome_WidgetWin_1", pid=77)

    assert AgentController._should_refresh_active_window(current, same_process) is True
    assert AgentController._should_refresh_active_window(current, other_process) is False


def test_unity_profile_capture_surface_falls_back_to_attached_editor_bounds(tmp_path) -> None:
    profile = UnityEditorProfile()
    artifacts = ArtifactManager.create(tmp_path / "logs", "unity-editor")
    screenshots = _FakeScreenshots()
    pywinauto = _FakeSurfacePywinauto()

    captured = profile._capture_surface(  # type: ignore[attr-defined]
        UnitySurfaceMap.surface("game"),
        driver=type("Driver", (), {"list_top_windows": lambda self: []})(),
        pywinauto=pywinauto,
        screenshots=screenshots,
        artifacts=artifacts,
    )

    assert captured is not None
    assert Path(captured).exists()
    assert screenshots.regions == [(300, 256, 830, 739)]
