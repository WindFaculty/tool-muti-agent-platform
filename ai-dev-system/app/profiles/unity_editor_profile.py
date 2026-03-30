from __future__ import annotations

from pathlib import Path
from typing import Any

import pyperclip

from app.agent.state import RunState
from app.agent.task_spec import TaskActionSpec, TaskSpec
from app.config.settings import Settings
from app.logging.artifacts import ArtifactManager
from app.logging.logger import GuiAgentLogger
from app.profiles.base_profile import BaseProfile
from app.profiles.registry import ProfileRegistry
from app.unity.assertions import UnityAssertionRunner
from app.unity.capabilities import UnityCapabilityRegistry
from app.unity.macros import UnityMacroRegistry
from app.unity.mcp_runtime import UnityMcpRuntime
from app.unity.preflight import UnityPreflight
from app.unity.surfaces import UnitySurfaceMap, UnitySurfaceSpec
from app.unity.task_planner import UnityTaskPlanner
from app.vision.screenshot import ScreenshotService


@ProfileRegistry.register("unity-editor")
class UnityEditorProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="unity-editor",
            executable=[
                str(UnitySurfaceMap.editor_path()),
                "-projectPath",
                str(UnitySurfaceMap.project_root()),
            ],
            window_selector=UnitySurfaceMap.editor_selector(),
            launch_delay_seconds=8.0,
        )
        self._preflight = UnityPreflight()
        self._planner = UnityTaskPlanner()
        self._assertions = UnityAssertionRunner()
        self._last_run_context: dict[str, Any] = {}

    def build_plan(self, task: str, working_directory: Path):
        task_spec = self._resolve_task_input(task)
        return self.build_plan_from_task_spec(task_spec, working_directory)

    def build_plan_from_task_spec(self, task_spec: TaskSpec, working_directory: Path):
        del working_directory
        resolved = self._resolve_task_input(task_spec)
        if resolved.actions:
            tools = list(self._last_run_context.get("available_tools") or [])
            resources = list(self._last_run_context.get("available_resources") or [])
            return UnityCapabilityRegistry.compile_actions(task_spec=resolved, tools=tools, resources=resources)
        if resolved.macro:
            return UnityMacroRegistry.build_plan(resolved)
        raise ValueError("Unity Editor automation requires structured actions, a supported task alias, or a legacy macro.")

    def task_spec_from_alias(self, task: str) -> TaskSpec | None:
        try:
            actions = self._planner.build_actions(task)
        except ValueError:
            return None
        return TaskSpec(
            profile=self.name,
            task=task,
            actions=actions,
            requires_layout="default-6000",
            layout_policy=self._default_layout_policy(),
            evidence={"screenshot": True},
        )

    def prepare_run_context(
        self,
        *,
        task_input: str | TaskSpec,
        settings: Settings,
        driver,
        pywinauto,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        active_window,
    ) -> dict[str, Any]:
        del task_input, settings, driver, pywinauto, artifacts, active_window
        context: dict[str, Any] = {
            "mcp_connected": False,
            "available_tools": [],
            "available_resources": [],
            "tool_groups": [],
            "capability_matrix": [],
        }
        runtime = UnityMcpRuntime(UnitySurfaceMap.project_root().parent)
        try:
            runtime.connect()
            snapshot = runtime.capability_snapshot()
            tool_groups_result = runtime.call_tool("manage_tools", {"action": "list_groups"})
            context.update(
                {
                    "unity_runtime": runtime,
                    "mcp_connected": True,
                    "available_tools": list(snapshot.get("tools") or []),
                    "available_resources": list(snapshot.get("resources") or []),
                    "tool_groups": (tool_groups_result.get("structured_content") or {}).get("groups") or [],
                }
            )
            context["capability_matrix"] = UnityCapabilityRegistry.build_matrix(
                tools=context["available_tools"],
                resources=context["available_resources"],
            )
        except Exception as exc:
            logger.log("unity_mcp_connect_failed", error=str(exc))
            context["mcp_error"] = str(exc)
            context["capability_matrix"] = UnityCapabilityRegistry.build_matrix(tools=[], resources=[])
            runtime.close()
        self._last_run_context = context
        return context

    def cleanup_run_context(
        self,
        *,
        task_input: str | TaskSpec,
        settings: Settings,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        run_context: dict[str, Any] | None,
    ) -> None:
        del task_input, settings, artifacts, logger
        runtime = (run_context or {}).get("unity_runtime")
        if runtime is not None:
            runtime.close()
        self._last_run_context = {}

    def run_preflight(
        self,
        *,
        task_input: str | TaskSpec,
        settings: Settings,
        driver,
        pywinauto,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        active_window,
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del artifacts
        resolved = self._resolve_task_input(task_input)
        if not settings.layout_normalize_enabled:
            resolved.layout_policy["normalize_if_needed"] = False
        required_capabilities = [action.capability for action in resolved.actions]
        require_gui = self._task_requires_gui(resolved, run_context or {})
        require_mcp = self._task_requires_mcp(resolved, run_context or {})
        preflight = self._preflight.evaluate(
            task_input=resolved,
            driver=driver,
            pywinauto=pywinauto,
            active_window=active_window,
            run_context=run_context,
            require_gui=require_gui,
            require_mcp=require_mcp,
            required_capabilities=required_capabilities,
        )
        logger.log("unity_preflight", preflight=preflight)
        if preflight.get("blocked_reason"):
            raise RuntimeError(str(preflight["blocked_reason"]))
        return preflight

    def inspect_extras(
        self,
        *,
        settings: Settings,
        driver,
        pywinauto,
        screenshots: ScreenshotService,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        target_window,
    ) -> dict[str, Any]:
        root = pywinauto.resolve_window(UnitySurfaceMap.editor_selector(), backend="uia")
        visible_names = {
            str(item.get("name") or "")
            for item in pywinauto.dump_control_tree(root, max_depth=2, max_nodes=120)
        }
        surface_shots: dict[str, str] = {}
        for key, surface in UnitySurfaceMap.all_surfaces().items():
            selector_title = surface.selector.title
            bounds = None
            if selector_title and selector_title in visible_names:
                try:
                    wrapper = pywinauto.resolve_window(
                        UnitySurfaceMap.surface(key).selector.__class__(
                            title=selector_title,
                            class_name="UnityGUIViewWndClass",
                            backend="uia",
                        ),
                        backend="uia",
                    )
                    bounds = pywinauto.bounds(wrapper)
                except Exception:
                    bounds = None
            if bounds is None:
                bounds = self._fallback_bounds(target_window.bounds, surface)
            if bounds is None:
                continue
            shot_path = artifacts.screenshot_path(f"surface-{key}")
            screenshots.capture(shot_path, region=bounds)
            surface_shots[key] = str(shot_path)
        if surface_shots:
            artifacts.write_json("unity-surfaces.json", surface_shots)
        logger.log("unity_inspect_surfaces", surfaces=surface_shots)
        return {"surface_screenshots": surface_shots}

    def run_task_verification(
        self,
        *,
        task_input: str | TaskSpec,
        settings: Settings,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        state: RunState,
        run_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        del settings, artifacts, logger, state
        resolved = self._resolve_task_input(task_input)
        if not resolved.verify:
            return {"passed": True, "checks": []}
        runtime = (run_context or {}).get("unity_runtime")
        if runtime is None:
            return {"passed": False, "checks": [{"kind": "mcp_runtime", "passed": False, "error": "Unity MCP runtime is unavailable."}]}
        return self._assertions.run(resolved.verify, runtime=runtime)

    def list_capabilities(
        self,
        *,
        settings: Settings,
    ) -> dict[str, Any]:
        del settings
        runtime = UnityMcpRuntime(UnitySurfaceMap.project_root().parent)
        try:
            runtime.connect()
            snapshot = runtime.capability_snapshot()
            tool_groups = (runtime.call_tool("manage_tools", {"action": "list_groups"}).get("structured_content") or {}).get("groups") or []
            return {
                "profile": self.name,
                "project_root": str(UnitySurfaceMap.project_root()),
                "available_tools": snapshot.get("tools") or [],
                "available_resources": snapshot.get("resources") or [],
                "tool_groups": tool_groups,
                "capabilities": UnityCapabilityRegistry.build_matrix(
                    tools=list(snapshot.get("tools") or []),
                    resources=list(snapshot.get("resources") or []),
                ),
            }
        finally:
            runtime.close()

    def summary_file_name(self) -> str | None:
        return "unity-summary.json"

    def build_run_summary(
        self,
        *,
        task_input: str | TaskSpec,
        settings: Settings,
        driver,
        pywinauto,
        screenshots: ScreenshotService,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        state: RunState,
        preflight: dict[str, Any],
        error: str | None,
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        del settings
        try:
            task_spec = self._resolve_task_input(task_input)
        except Exception:
            task_spec = TaskSpec(profile=self.name, task=task_input if isinstance(task_input, str) else task_input.display_text)
        artifacts_map: dict[str, str] = {}
        if task_spec.macro:
            if task_spec.macro == "capture_view":
                surface_name = str(task_spec.args.get("surface") or "game")
                surface = UnitySurfaceMap.surface(surface_name)
                captured = self._capture_surface(surface, driver, pywinauto, screenshots, artifacts)
                if captured is not None:
                    artifacts_map["surface_screenshot"] = captured
            elif task_spec.macro == "dump_control_tree":
                root_uia = pywinauto.resolve_window(UnitySurfaceMap.editor_selector(), backend="uia")
                root_win32 = pywinauto.resolve_window(UnitySurfaceMap.editor_selector(), backend="win32")
                uia_path = artifacts.write_json("unity-control-tree-uia.json", pywinauto.dump_control_tree(root_uia, max_depth=3, max_nodes=250))
                win32_path = artifacts.write_json("unity-control-tree-win32.json", pywinauto.dump_control_tree(root_win32, max_depth=3, max_nodes=250))
                artifacts_map["control_tree_uia"] = str(uia_path)
                artifacts_map["control_tree_win32"] = str(win32_path)
            elif task_spec.macro == "snapshot_console":
                console_text = pyperclip.paste()
                console_path = artifacts.write_text("console-snapshot.txt", console_text)
                artifacts_map["console_snapshot"] = str(console_path)

        verification_attempts = []
        verification_passed = error is None
        for attempt in state.attempts:
            verification_attempts.append(
                {
                    "action": attempt.request_name,
                    "strategy": attempt.strategy,
                    "status": attempt.status,
                    "error": attempt.error,
                    "details": attempt.details,
                }
            )
            if attempt.status not in {"completed", "healed"}:
                verification_passed = False

        task_verification = state.details.get("task_verification") or {"passed": True, "checks": []}
        if not task_verification.get("passed", True):
            verification_passed = False

        unity_state_wait = state.details.get("unity_editor_state_wait") or {}
        for artifact_name, artifact_path in (unity_state_wait.get("artifacts") or {}).items():
            artifacts_map[f"editor_state_{artifact_name}"] = artifact_path
        if unity_state_wait.get("timed_out"):
            verification_passed = False

        summary = {
            "profile": self.name,
            "task": task_spec.to_dict(),
            "status": state.status,
            "blocked_reason": preflight.get("blocked_reason") or error,
            "preflight": preflight,
            "capability_matrix": list((run_context or {}).get("capability_matrix") or []),
            "background_jobs": dict(state.background_jobs),
            "editor_state_wait": unity_state_wait,
            "verification_result": {
                "passed": verification_passed,
                "attempts": verification_attempts,
                "task_verification": task_verification,
                "artifacts": artifacts_map,
            },
        }
        logger.log("unity_run_summary", summary=summary)
        return summary

    def _resolve_task_input(self, task_input: str | TaskSpec) -> TaskSpec:
        if isinstance(task_input, str):
            alias = self.task_spec_from_alias(task_input)
            if alias is not None:
                return self._with_defaults(alias)
            actions = self._planner.build_actions(task_input)
            return self._with_defaults(
                TaskSpec(
                    profile=self.name,
                    task=task_input,
                    actions=actions,
                    requires_layout="default-6000",
                )
            )

        if task_input.actions:
            return self._with_defaults(task_input)

        if task_input.task:
            actions = self._planner.build_actions(task_input.task)
            return self._with_defaults(
                TaskSpec(
                profile=task_input.profile,
                task=task_input.task,
                args=dict(task_input.args),
                actions=actions,
                verify=list(task_input.verify),
                confirm_destructive=task_input.confirm_destructive,
                dry_run=task_input.dry_run,
                requires_layout=task_input.requires_layout,
                layout_policy=dict(task_input.layout_policy),
                execution=dict(task_input.execution),
                evidence=dict(task_input.evidence),
                metadata=dict(task_input.metadata),
                )
            )

        if task_input.macro:
            translated = self._translate_legacy_macro(task_input)
            return self._with_defaults(translated if translated is not None else task_input)

        raise ValueError("Unity task input must provide a task string, macro, or actions[].")

    def _translate_legacy_macro(self, task_spec: TaskSpec) -> TaskSpec | None:
        macro = task_spec.macro or ""
        if macro == "attach_editor":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.attach", backend="gui", allow_fallback=False)])
        if macro == "assert_layout_ready":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.layout.assert", backend="gui", allow_fallback=False)])
        if macro == "dump_control_tree":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.control_tree.dump", backend="gui", allow_fallback=False)])
        if macro == "snapshot_console":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.console.snapshot", backend="gui", allow_fallback=False)])
        if macro == "play_mode":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.play")])
        if macro == "stop_mode":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.stop")])
        if macro == "pause_mode":
            return self._task_spec_from_actions(task_spec, [TaskActionSpec(capability="editor.pause")])
        if macro == "open_scene":
            scene_path = str(task_spec.args.get("scene_path") or "")
            if scene_path:
                return self._task_spec_from_actions(
                    task_spec,
                    [TaskActionSpec(capability="scene.manage", params={"action": "load", "path": scene_path})],
                )
        return None

    @staticmethod
    def _task_spec_from_actions(task_spec: TaskSpec, actions: list[TaskActionSpec]) -> TaskSpec:
        return TaskSpec(
            profile=task_spec.profile,
            task=task_spec.task,
            macro=task_spec.macro,
            args=dict(task_spec.args),
            actions=actions,
            verify=list(task_spec.verify),
            confirm_destructive=task_spec.confirm_destructive,
            dry_run=task_spec.dry_run,
            requires_layout=task_spec.requires_layout or "default-6000",
            layout_policy=dict(task_spec.layout_policy or {}),
            execution=dict(task_spec.execution or {}),
            evidence=dict(task_spec.evidence),
            metadata=dict(task_spec.metadata),
        )

    @classmethod
    def _default_layout_policy(cls) -> dict[str, Any]:
        return {
            "required": "default-6000",
            "normalize_if_needed": True,
            "strict_after_normalize": True,
        }

    def _with_defaults(self, task_spec: TaskSpec) -> TaskSpec:
        normalized = TaskSpec(
            profile=task_spec.profile,
            task=task_spec.task,
            macro=task_spec.macro,
            args=dict(task_spec.args),
            actions=[
                TaskActionSpec(
                    capability=action.capability,
                    params=dict(action.params),
                    backend=action.backend,
                    allow_fallback=action.allow_fallback,
                    heal_hints=dict(action.heal_hints),
                    execution=dict(action.execution),
                )
                for action in task_spec.actions
            ],
            verify=list(task_spec.verify),
            confirm_destructive=task_spec.confirm_destructive,
            dry_run=task_spec.dry_run,
            requires_layout=task_spec.requires_layout or "default-6000",
            layout_policy=dict(task_spec.layout_policy or {}),
            execution=dict(task_spec.execution or {}),
            evidence=dict(task_spec.evidence),
            metadata=dict(task_spec.metadata),
        )
        for key, value in self._default_layout_policy().items():
            normalized.layout_policy.setdefault(key, value)
        return normalized

    @staticmethod
    def _task_requires_gui(task_spec: TaskSpec, run_context: dict[str, Any]) -> bool:
        if not task_spec.actions:
            return True
        matrix = {row.get("capability"): row for row in list(run_context.get("capability_matrix") or []) if isinstance(row, dict)}
        for action in task_spec.actions:
            if action.backend == "gui":
                return True
            row = matrix.get(action.capability) or {}
            if row.get("resolved_backend") == "gui":
                return True
        return False

    @staticmethod
    def _task_requires_mcp(task_spec: TaskSpec, run_context: dict[str, Any]) -> bool:
        if not task_spec.actions:
            return False
        matrix = {row.get("capability"): row for row in list(run_context.get("capability_matrix") or []) if isinstance(row, dict)}
        for action in task_spec.actions:
            if action.backend == "mcp":
                return True
            row = matrix.get(action.capability) or {}
            if row.get("resolved_backend") == "mcp":
                return True
        return False

    def _capture_surface(
        self,
        surface: UnitySurfaceSpec,
        driver,
        pywinauto,
        screenshots: ScreenshotService,
        artifacts: ArtifactManager,
    ) -> str | None:
        root = pywinauto.resolve_window(UnitySurfaceMap.editor_selector(), backend="uia")
        visible_names = {
            str(item.get("name") or "")
            for item in pywinauto.dump_control_tree(root, max_depth=2, max_nodes=120)
        }
        selector_title = surface.selector.title
        if not selector_title:
            return None
        if selector_title not in visible_names:
            return None
        try:
            wrapper = pywinauto.resolve_window(
                surface.selector.__class__(
                    title=selector_title,
                    class_name="UnityGUIViewWndClass",
                    backend="uia",
                ),
                backend="uia",
            )
            bounds = pywinauto.bounds(wrapper)
        except Exception:
            bounds = None
        if bounds is None:
            try:
                editor_bounds = pywinauto.bounds(root)
            except Exception:
                editor_bounds = None
            if editor_bounds is None:
                return None
            bounds = self._fallback_bounds(editor_bounds, surface)
            if bounds is None:
                return None
        shot_path = artifacts.screenshot_path(f"capture-{surface.key}")
        screenshots.capture(shot_path, region=bounds)
        return str(shot_path)

    @staticmethod
    def _fallback_bounds(
        window_bounds: tuple[int, int, int, int] | None,
        surface: UnitySurfaceSpec,
    ) -> tuple[int, int, int, int] | None:
        if window_bounds is None or surface.fallback_region is None:
            return None
        left, top, right, bottom = window_bounds
        width = right - left
        height = bottom - top
        x0, y0, x1, y1 = surface.fallback_region
        return (
            int(left + width * x0),
            int(top + height * y0),
            int(left + width * x1),
            int(top + height * y1),
        )
