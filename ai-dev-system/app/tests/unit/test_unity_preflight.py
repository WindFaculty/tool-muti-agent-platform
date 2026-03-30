from __future__ import annotations

from app.agent.state import WindowTarget
from app.agent.task_spec import TaskSpec
from app.unity.preflight import UnityPreflight


class _FakeDriver:
    def __init__(self, windows, *, interactive: bool = True) -> None:
        self._windows = windows
        self._interactive = interactive

    def list_top_windows(self):
        return list(self._windows)

    def is_interactive_desktop_available(self) -> bool:
        return self._interactive


class _FakePywinauto:
    def __init__(self, visible_names):
        self._visible_names = visible_names

    def resolve_window(self, selector, backend=None):
        return object()

    def dump_control_tree(self, root, max_depth=2, max_nodes=120):
        return [{"name": name} for name in self._visible_names]


class _MutableFakePywinauto:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self.dump_calls = 0

    def resolve_window(self, selector, backend=None):
        return object()

    def dump_control_tree(self, root, max_depth=2, max_nodes=120):
        index = min(self.dump_calls, len(self._snapshots) - 1)
        self.dump_calls += 1
        return [{"name": name} for name in self._snapshots[index]]


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict):
        self.calls.append((name, dict(arguments)))
        return {"structured_content": {"success": True, "data": {"status": "completed"}}}


def _unity_window() -> WindowTarget:
    return WindowTarget(
        handle=100,
        title="unity-client - SampleScene - Windows, Mac, Linux - Unity 6.3 LTS (6000.3.11f1) <DX12>",
        class_name="UnityContainerWndClass",
        pid=42,
        bounds=(0, 0, 1920, 1080),
    )


def test_unity_preflight_passes_for_expected_layout() -> None:
    window = _unity_window()
    driver = _FakeDriver([window])
    pywinauto = _FakePywinauto(
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

    result = UnityPreflight().evaluate(
        task_input=TaskSpec(profile="unity-editor", macro="assert_layout_ready", requires_layout="default-6000"),
        driver=driver,
        pywinauto=pywinauto,
        active_window=window,
        run_context={"mcp_connected": True, "available_tools": ["manage_scene"], "capability_matrix": []},
    )

    assert result["blocked_reason"] is None
    assert result["checks"]["layout_ready"] is True


def test_unity_preflight_blocks_on_modal_window() -> None:
    window = _unity_window()
    modal = WindowTarget(handle=200, title="Importing Package", class_name="#32770", pid=42, bounds=(10, 10, 500, 300))
    driver = _FakeDriver([window, modal])
    pywinauto = _FakePywinauto(
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

    result = UnityPreflight().evaluate(
        task_input=TaskSpec(profile="unity-editor", macro="assert_no_modal", requires_layout="default-6000"),
        driver=driver,
        pywinauto=pywinauto,
        active_window=window,
        run_context={"mcp_connected": True, "available_tools": ["manage_scene"], "capability_matrix": []},
    )

    assert result["checks"]["modal_absent"] is False
    assert result["blocked_reason"] == "Unity has blocking modal or popup windows open."


def test_unity_preflight_normalizes_layout_when_surfaces_are_missing() -> None:
    window = _unity_window()
    runtime = _FakeRuntime()
    driver = _FakeDriver([window])
    pywinauto = _MutableFakePywinauto(
        [
            [
                "Application",
                "UnityEditor.MainToolbarWindow",
                "File",
                "Edit",
                "Assets",
                "GameObject",
                "Window",
                "Help",
                "Project",
                "Scene",
            ],
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
            ],
        ]
    )

    result = UnityPreflight().evaluate(
        task_input=TaskSpec(
            profile="unity-editor",
            actions=[],
            requires_layout="default-6000",
            layout_policy={"required": "default-6000", "normalize_if_needed": True, "strict_after_normalize": True},
        ),
        driver=driver,
        pywinauto=pywinauto,
        active_window=window,
        run_context={
            "unity_runtime": runtime,
            "mcp_connected": True,
            "available_tools": ["batch_execute"],
            "capability_matrix": [{"capability": "editor.layout.normalize", "status": "manual_validation_required"}],
        },
        require_gui=True,
        require_mcp=False,
    )

    assert result["blocked_reason"] is None
    assert result["checks"]["layout_normalize_attempted"] is True
    assert result["checks"]["layout_normalize_succeeded"] is True
    assert runtime.calls[0][0] == "batch_execute"
