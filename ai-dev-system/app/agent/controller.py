from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent.healing import UiHealingPlanner
from app.agent.jobs import JobTracker
from app.agent.planner import TaskPlanner
from app.agent.task_spec import TaskSpec
from app.agent.recovery import RecoveryPlanner
from app.agent.state import ActionAttempt, ActionRequest, RunState, SelectorSpec, WindowTarget
from app.agent.strategies import ExecutionContext, StrategyRegistry
from app.agent.verifier import Verifier
from app.automation.input_guard import InputGuard
from app.config.settings import Settings
from app.logging.artifacts import ArtifactManager
from app.logging.logger import GuiAgentLogger
from app.platform.factory import PlatformFactory
from app.profiles.base_profile import BaseProfile
from app.vision.region_locator import RegionLocator
from app.vision.locator import VisionLlmLocator
from app.vision.screenshot import ScreenshotService
from app.vision.template_match import TemplateMatcher


class AgentController:
    """Observe, act, verify, and recover for one Windows GUI automation run."""

    _UNITY_EDITOR_STATE_URI = "mcpforunity://editor/state"
    _UNITY_EDITOR_STATE_POLL_SECONDS = 0.5
    _UNITY_EDITOR_STATE_WARN_AFTER_SECONDS = 10.0
    _UNITY_EDITOR_STATE_TIMEOUT_SECONDS = 20.0

    def __init__(
        self,
        settings: Settings,
        registry: StrategyRegistry | None = None,
        *,
        vision_locator: VisionLlmLocator | None = None,
    ) -> None:
        self._settings = settings
        platform = PlatformFactory.create(settings)
        self._driver = platform.driver
        self._pywinauto = platform.structured_ui
        self._pyautogui = platform.pointer_keyboard
        self._screenshots: ScreenshotService = platform.screen_capture
        self._matcher = TemplateMatcher()
        self._regions = RegionLocator()
        self._verifier = Verifier(self._driver, self._pywinauto, self._screenshots, self._matcher)
        self._planner = TaskPlanner()
        self._recovery = RecoveryPlanner()
        self._healing = UiHealingPlanner()
        self._vision_locator = vision_locator or VisionLlmLocator()
        self._registry = registry or StrategyRegistry.default(vision_locator=self._vision_locator)

    # ------------------------------------------------------------------
    # Public commands
    # ------------------------------------------------------------------

    def list_windows(self) -> dict[str, Any]:
        artifacts = ArtifactManager.create(self._settings.artifact_root, "list-windows")
        logger = GuiAgentLogger(artifacts.run_dir / "run.jsonl")
        windows = [asdict(window) for window in self._driver.list_top_windows()]
        logger.log("run_started", command="list-windows", artifact_dir=str(artifacts.run_dir))
        logger.log("window_observed", windows=windows)
        artifacts.write_json("windows.json", windows)
        logger.log("run_finished", status="completed", window_count=len(windows))
        return {"artifact_dir": str(artifacts.run_dir), "windows": windows}

    def inspect(self, profile: BaseProfile) -> dict[str, Any]:
        artifacts = ArtifactManager.create(self._settings.artifact_root, f"inspect-{profile.name}")
        logger = GuiAgentLogger(artifacts.run_dir / "run.jsonl")
        logger.log("run_started", command="inspect", profile=profile.name, artifact_dir=str(artifacts.run_dir))
        target = self._attach_or_launch(profile)
        root_uia = self._pywinauto.resolve_window(SelectorSpec(handle=target.handle, backend="uia"), backend="uia")
        root_win32 = self._pywinauto.resolve_window(SelectorSpec(handle=target.handle, backend="win32"), backend="win32")
        uia_tree = self._pywinauto.dump_control_tree(root_uia)
        win32_tree = self._pywinauto.dump_control_tree(root_win32)
        screenshot_path = artifacts.screenshot_path("inspect")
        self._capture_window(target, screenshot_path)
        artifacts.write_json("control-tree-uia.json", uia_tree)
        artifacts.write_json("control-tree-win32.json", win32_tree)
        extra_payload = profile.inspect_extras(
            settings=self._settings,
            driver=self._driver,
            pywinauto=self._pywinauto,
            screenshots=self._screenshots,
            artifacts=artifacts,
            logger=logger,
            target_window=target,
        )
        logger.log("window_observed", window=asdict(target))
        logger.log("run_finished", status="completed")
        payload = {
            "artifact_dir": str(artifacts.run_dir),
            "window": asdict(target),
            "control_tree_uia_path": str(artifacts.run_dir / "control-tree-uia.json"),
            "control_tree_win32_path": str(artifacts.run_dir / "control-tree-win32.json"),
        }
        payload.update(extra_payload)
        return payload

    def list_capabilities(self, profile: BaseProfile) -> dict[str, Any]:
        artifacts = ArtifactManager.create(self._settings.artifact_root, f"capabilities-{profile.name}")
        logger = GuiAgentLogger(artifacts.run_dir / "run.jsonl")
        logger.log("run_started", command="list-capabilities", profile=profile.name, artifact_dir=str(artifacts.run_dir))
        payload = profile.list_capabilities(settings=self._settings)
        artifacts.write_json("capabilities.json", payload)
        logger.log("run_finished", status="completed", capability_count=len(payload.get("capabilities", [])))
        return {"artifact_dir": str(artifacts.run_dir), **payload}

    def run(self, profile: BaseProfile, task: str | TaskSpec, *, confirm_destructive: bool = False) -> dict[str, Any]:
        artifacts = ArtifactManager.create(self._settings.artifact_root, profile.name)
        logger = GuiAgentLogger(artifacts.run_dir / "run.jsonl")
        task_label = task.display_text if isinstance(task, TaskSpec) else task
        state = RunState(run_id=artifacts.run_id, profile_name=profile.name, task=task_label, artifact_dir=artifacts.run_dir)
        state.observed_windows = self._driver.list_top_windows()
        logger.log("run_started", command="run", profile=profile.name, task=task_label, artifact_dir=str(artifacts.run_dir))
        logger.log("window_observed", windows=[asdict(window) for window in state.observed_windows])
        preflight: dict[str, Any] = {}
        plan: list[ActionRequest] = []
        run_context: dict[str, Any] = {}
        guard = InputGuard(
            self._driver,
            hotkey=self._settings.emergency_stop_hotkey,
            action_delay_seconds=self._settings.action_delay_seconds,
            require_foreground=self._settings.require_foreground,
        )

        try:
            state.active_window = self._attach_or_launch(profile)
            run_context = profile.prepare_run_context(
                task_input=task,
                settings=self._settings,
                driver=self._driver,
                pywinauto=self._pywinauto,
                artifacts=artifacts,
                logger=logger,
                active_window=state.active_window,
            )
            run_context.setdefault("job_tracker", JobTracker())
            preflight = profile.run_preflight(
                task_input=task,
                settings=self._settings,
                driver=self._driver,
                pywinauto=self._pywinauto,
                artifacts=artifacts,
                logger=logger,
                active_window=state.active_window,
                run_context=run_context,
            )
            state.details["preflight"] = preflight
            plan = self._planner.build_plan(profile, task, artifacts.run_dir)

            if not self._settings.dry_run:
                guard.start()

            if len(plan) > self._settings.max_actions_per_run:
                raise RuntimeError(
                    f"Planned {len(plan)} actions, which exceeds max_actions_per_run={self._settings.max_actions_per_run}."
                )

            for index, action in enumerate(plan):
                state.action_index = index
                logger.log("action_planned", index=index, action=self._serialize_action(action))
                self._execute_with_recovery(
                    action,
                    profile,
                    state,
                    artifacts,
                    logger,
                    guard,
                    run_context=run_context,
                    confirm_destructive=confirm_destructive,
                )

            task_verification = profile.run_task_verification(
                task_input=task,
                settings=self._settings,
                artifacts=artifacts,
                logger=logger,
                state=state,
                run_context=run_context,
            )
            state.details["task_verification"] = task_verification
            if not task_verification.get("passed", True):
                raise RuntimeError("Task-level verification failed.")

            state.status = "completed"
            logger.log("run_finished", state=state.to_record())
            self._write_profile_summary(profile, task, artifacts, logger, state, preflight, error=None, run_context=run_context)
            return {
                "status": state.status,
                "run_id": state.run_id,
                "artifact_dir": str(artifacts.run_dir),
                "attempts": [asdict(attempt) for attempt in state.attempts],
            }
        except Exception as exc:
            state.status = "failed"
            artifacts.write_json(
                "failure-report.json",
                {
                    "error": str(exc),
                    "state": state.to_record(),
                    "attempts": [asdict(attempt) for attempt in state.attempts],
                },
            )
            logger.log("run_failed", error=str(exc), state=state.to_record())
            self._write_profile_summary(profile, task, artifacts, logger, state, preflight, error=str(exc), run_context=run_context)
            raise
        finally:
            if not self._settings.dry_run:
                guard.stop()
            profile.cleanup_run_context(
                task_input=task,
                settings=self._settings,
                artifacts=artifacts,
                logger=logger,
                run_context=run_context,
            )

    # ------------------------------------------------------------------
    # Internal execution loop
    # ------------------------------------------------------------------

    def _execute_with_recovery(
        self,
        action: ActionRequest,
        profile: BaseProfile,
        state: RunState,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        guard: InputGuard,
        run_context: dict[str, Any],
        *,
        confirm_destructive: bool,
    ) -> None:
        strategies = self._applicable_strategies(action, profile)
        default_selector = self._resolve_window_selector(action, state)
        primary_strategy = strategies[0]
        current_strategy = primary_strategy
        attempts = 0
        while True:
            attempts += 1
            if attempts > max(1, len(strategies)):
                raise RuntimeError(f"Max retry count exceeded for action {action.name}")

            self._wait_for_unity_editor_stable(profile, artifacts, logger, state, run_context, f"{action.name}-before")
            before_shot = artifacts.screenshot_path(f"{state.action_index:02d}-{action.name}-before")
            self._capture_window(state.active_window, before_shot)
            logger.log("action_attempted", action=action.name, strategy=current_strategy, screenshot=str(before_shot))
            attempt = ActionAttempt(request_name=action.name, strategy=current_strategy, status="started")
            try:
                if current_strategy == "ui_heal":
                    healing_step = self._healing.plan(action=action, profile=profile, active_window=state.active_window)
                    if healing_step is None:
                        raise RuntimeError("No deterministic healing step could be planned for this action.")
                    action.metadata["active_healing_step"] = healing_step.metadata
                if action.destructive and self._settings.require_destructive_confirmation:
                    guard.require_destructive_confirmation(confirm_destructive, action.name)
                execution_details: dict[str, Any] = {}
                if not self._settings.dry_run:
                    execution_details = self._perform_action(action, current_strategy, profile, state, guard, run_context)
            except Exception as exc:
                attempt.status = "failed"
                attempt.error = str(exc)
                state.attempts.append(attempt)
                decision = self._recovery.next_strategy(strategies, current_strategy, str(exc))
                logger.log("recovery_attempted", action=action.name, strategy=current_strategy, decision=asdict(decision))
                if decision.stop or decision.next_strategy is None:
                    raise RuntimeError(f"Action {action.name} failed during {current_strategy}: {exc}") from exc
                current_strategy = decision.next_strategy
                continue

            if self._settings.dry_run:
                attempt.status = "completed"
                attempt.details = {
                    "execution": {"dry_run": True},
                    "verification": {"passed": True, "strategy": "dry_run_skipped", "details": {}, "failed_checks": []},
                }
                state.attempts.append(attempt)
                return

            if current_strategy == "ui_heal":
                if not self._settings.dry_run:
                    guard.delay()
                heal_after_shot = artifacts.screenshot_path(f"{state.action_index:02d}-{action.name}-heal-after")
                self._capture_window(state.active_window, heal_after_shot)
                attempt.status = "healed"
                attempt.details = {
                    "execution": self._json_safe(execution_details),
                    "healing": self._json_safe(execution_details.get("healing") or {}),
                    "after_screenshot": str(heal_after_shot),
                }
                state.attempts.append(attempt)
                self._record_healing_artifacts(artifacts, state, execution_details)
                action.metadata.pop("active_healing_step", None)
                current_strategy = primary_strategy
                continue

            if not self._settings.dry_run:
                guard.delay()
            self._wait_for_unity_editor_stable(profile, artifacts, logger, state, run_context, f"{action.name}-after")
            after_shot = artifacts.screenshot_path(f"{state.action_index:02d}-{action.name}-after")
            self._capture_window(state.active_window, after_shot)
            verification = self._verifier.verify(
                action,
                default_window_selector=default_selector,
                screenshot_path=after_shot,
                execution_details=execution_details,
            )
            attempt.status = "completed" if verification.passed else "verification_failed"
            attempt.details = {
                "execution": self._json_safe(execution_details),
                "verification": asdict(verification),
                "after_screenshot": str(after_shot),
            }
            if execution_details.get("background_job"):
                state.background_jobs[str(execution_details["background_job"].get("job_key") or action.name)] = self._json_safe(
                    execution_details["background_job"]
                )
            if execution_details.get("healing"):
                attempt.details["healing"] = self._json_safe(execution_details.get("healing"))
                self._record_healing_artifacts(artifacts, state, execution_details)
            if execution_details.get("vision"):
                attempt.details["vision"] = self._json_safe(execution_details.get("vision"))
                self._record_vision_artifacts(artifacts, execution_details)
            state.attempts.append(attempt)

            if verification.passed:
                logger.log("verification_passed", action=action.name, strategy=current_strategy, verification=asdict(verification))
                active = self._driver.get_active_window()
                if self._should_refresh_active_window(state.active_window, active):
                    state.active_window = active
                return

            logger.log("verification_failed", action=action.name, strategy=current_strategy, verification=asdict(verification))
            decision = self._recovery.next_strategy(strategies, current_strategy, "; ".join(verification.failed_checks))
            logger.log("recovery_attempted", action=action.name, strategy=current_strategy, decision=asdict(decision))
            if decision.stop or decision.next_strategy is None:
                raise RuntimeError(f"Verification failed for action {action.name}: {'; '.join(verification.failed_checks)}")
            current_strategy = decision.next_strategy

    def _perform_action(
        self,
        action: ActionRequest,
        strategy_name: str,
        profile: BaseProfile,
        state: RunState,
        guard: InputGuard,
        run_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch to the StrategyRegistry — replaces the former 80-line if/elif chain."""
        window_selector = self._resolve_window_selector(action, state)
        ctx = ExecutionContext(
            action=action,
            profile=profile,
            active_window=state.active_window,
            window_selector=window_selector,
            pywinauto=self._pywinauto,
            pyautogui=self._pyautogui,
            screen_capture=self._screenshots,
            guard=guard,
            settings=self._settings,
            artifact_dir=state.artifact_dir,
            metadata={"run_context": run_context},
        )
        self._registry.execute(strategy_name, ctx)
        result = dict(ctx.metadata)
        result.pop("run_context", None)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_window_selector(self, action: ActionRequest, state: RunState) -> SelectorSpec:
        raw_selector = action.metadata.get("window_selector")
        if isinstance(raw_selector, SelectorSpec):
            return raw_selector
        if isinstance(raw_selector, dict):
            return SelectorSpec(**raw_selector)
        if state.active_window is None:
            raise RuntimeError("No active window is available.")
        return SelectorSpec(handle=state.active_window.handle, backend="uia")

    def _attach_or_launch(self, profile: BaseProfile):
        windows = [w for w in self._driver.list_top_windows() if self._driver._matches(w, profile.window_selector)]
        if windows:
            return windows[profile.window_selector.found_index]
        self._driver.launch(profile.executable)
        window = self._driver.wait_for_window(
            profile.window_selector,
            timeout_seconds=profile.launch_delay_seconds + self._settings.default_window_timeout_seconds,
        )
        time.sleep(profile.launch_delay_seconds)
        return window

    def _capture_window(self, window, path: Path) -> None:
        if window is not None and getattr(window, "bounds", None):
            left, top, right, bottom = window.bounds
            self._screenshots.capture(path, region=(left, top, right, bottom))
            return
        self._screenshots.capture(path)

    @staticmethod
    def _default_strategies(action: ActionRequest) -> list[str]:
        if action.action_type == "mcp_tool":
            return ["mcp_tool"]
        if action.action_type == "mcp_batch":
            return ["mcp_batch"]
        if action.action_type == "menu_select":
            return ["pywinauto_menu_select"]
        if action.action_type == "click":
            return ["pywinauto_click", "pywinauto_invoke", "ui_heal", "vision_llm_click", "image_click", "coordinate_click"]
        if action.action_type in {"type_text", "set_text"}:
            return ["pywinauto_type", "pywinauto_set_text", "ui_heal", "vision_llm_type", "image_type", "coordinate_click"]
        if action.action_type == "hotkey":
            return ["pywinauto_hotkey", "pyautogui_hotkey"]
        return ["pywinauto_click"]

    def _applicable_strategies(self, action: ActionRequest, profile: BaseProfile) -> list[str]:
        strategies = action.allowed_strategies or self._default_strategies(action)
        applicable: list[str] = []
        for strategy in strategies:
            if strategy == "ui_heal" and (
                not self._settings.self_heal_enabled or not action.metadata.get("heal_hints")
            ):
                continue
            if strategy.startswith("vision_llm") and not self._settings.vision_llm_enabled:
                continue
            if strategy == "image_click" and not action.metadata.get("template_path"):
                continue
            if strategy == "coordinate_click" and action.name not in profile.coordinate_fallbacks:
                continue
            applicable.append(strategy)
        if not applicable:
            raise RuntimeError(f"No applicable strategies are configured for action {action.name}")
        return applicable

    @staticmethod
    def _serialize_action(action: ActionRequest) -> dict[str, Any]:
        return {
            "name": action.name,
            "action_type": action.action_type,
            "value": str(action.value) if action.value is not None else None,
            "allowed_strategies": action.allowed_strategies,
            "destructive": action.destructive,
            "metadata": AgentController._json_safe(action.metadata),
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, SelectorSpec):
            return {
                "handle": value.handle,
                "title": value.title,
                "title_re": value.title_re,
                "automation_id": value.automation_id,
                "control_type": value.control_type,
                "class_name": value.class_name,
                "found_index": value.found_index,
                "backend": value.backend,
                "visible_only": value.visible_only,
            }
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: AgentController._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [AgentController._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [AgentController._json_safe(item) for item in value]
        return value

    def _write_profile_summary(
        self,
        profile: BaseProfile,
        task_input: str | TaskSpec,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        state: RunState,
        preflight: dict[str, Any],
        *,
        error: str | None,
        run_context: dict[str, Any],
    ) -> None:
        summary_name = profile.summary_file_name()
        if not summary_name:
            return
        payload = profile.build_run_summary(
            task_input=task_input,
            settings=self._settings,
            driver=self._driver,
            pywinauto=self._pywinauto,
            screenshots=self._screenshots,
            artifacts=artifacts,
            logger=logger,
            state=state,
            preflight=preflight,
            error=error,
            run_context=run_context,
        )
        if payload is not None:
            artifacts.write_json(summary_name, payload)

    @staticmethod
    def _record_healing_artifacts(artifacts: ArtifactManager, state: RunState, execution_details: dict[str, Any]) -> None:
        trace = list(state.details.get("healing_trace") or [])
        trace.append(execution_details.get("healing") or {})
        state.details["healing_trace"] = trace
        artifacts.write_json("healing-trace.json", trace)

    @staticmethod
    def _record_vision_artifacts(artifacts: ArtifactManager, execution_details: dict[str, Any]) -> None:
        artifacts.write_json("vision-locator.json", execution_details.get("vision") or {})

    def _wait_for_unity_editor_stable(
        self,
        profile: BaseProfile,
        artifacts: ArtifactManager,
        logger: GuiAgentLogger,
        state: RunState,
        run_context: dict[str, Any],
        phase_label: str,
    ) -> None:
        if profile.name != "unity-editor":
            return

        runtime = run_context.get("unity_runtime")
        if runtime is None:
            return

        snapshots: list[dict[str, Any]] = []
        started_at = time.time()
        warned = False
        while True:
            snapshot = self._read_unity_editor_state(runtime)
            if snapshot is None:
                return

            snapshots.append(snapshot)
            if not self._unity_editor_state_is_transitioning(snapshot):
                state.details["unity_editor_state_wait"] = {
                    "phase_label": phase_label,
                    "timed_out": False,
                    "latest": snapshot,
                }
                return

            elapsed = time.time() - started_at
            if not warned and elapsed >= self._UNITY_EDITOR_STATE_WARN_AFTER_SECONDS:
                warned = True
                logger.log("unity_editor_state_waiting", phase_label=phase_label, elapsed_seconds=round(elapsed, 2), latest=snapshot)

            if elapsed >= self._UNITY_EDITOR_STATE_TIMEOUT_SECONDS:
                artifacts_map: dict[str, str] = {}
                snapshots_path = artifacts.write_json("unity-editor-state-timeout.json", snapshots)
                artifacts_map["editor_state_snapshots"] = str(snapshots_path)
                active_window_path = artifacts.write_json(
                    "unity-editor-active-window.json",
                    self._json_safe(asdict(state.active_window)) if state.active_window is not None else {},
                )
                artifacts_map["active_window"] = str(active_window_path)

                try:
                    console_payload = runtime.call_tool(
                        "read_console",
                        {"action": "get", "count": "50", "format": "json", "include_stacktrace": True},
                    )
                    console_path = artifacts.write_json("unity-editor-console-timeout.json", console_payload)
                    artifacts_map["console_snapshot"] = str(console_path)
                except Exception as exc:
                    logger.log("unity_editor_console_snapshot_failed", phase_label=phase_label, error=str(exc))

                timeout_shot = artifacts.screenshot_path(f"unity-editor-timeout-{phase_label}")
                self._capture_window(state.active_window, timeout_shot)
                artifacts_map["last_window_screenshot"] = str(timeout_shot)

                state.details["unity_editor_state_wait"] = {
                    "phase_label": phase_label,
                    "timed_out": True,
                    "latest": snapshot,
                    "artifacts": artifacts_map,
                }
                logger.log(
                    "unity_editor_state_timeout",
                    phase_label=phase_label,
                    elapsed_seconds=round(elapsed, 2),
                    latest=snapshot,
                    artifacts=artifacts_map,
                )
                raise RuntimeError(
                    f"Unity editor stayed in playmode_transition for more than {self._UNITY_EDITOR_STATE_TIMEOUT_SECONDS:.0f}s during {phase_label}."
                )

            time.sleep(self._UNITY_EDITOR_STATE_POLL_SECONDS)

    def _read_unity_editor_state(self, runtime) -> dict[str, Any] | None:
        try:
            payload = runtime.read_json_resource(self._UNITY_EDITOR_STATE_URI)
        except Exception:
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None

        play_mode = data.get("editor", {}).get("play_mode", {})
        activity = data.get("activity", {})
        advice = data.get("advice", {})
        return {
            "observed_at_unix_ms": data.get("observed_at_unix_ms"),
            "activity_phase": activity.get("phase"),
            "activity_reasons": activity.get("reasons") or [],
            "is_playing": bool(play_mode.get("is_playing")),
            "is_paused": bool(play_mode.get("is_paused")),
            "is_changing": bool(play_mode.get("is_changing")),
            "ready_for_tools": bool(advice.get("ready_for_tools", True)),
            "blocking_reasons": advice.get("blocking_reasons") or [],
            "recommended_retry_after_ms": advice.get("recommended_retry_after_ms"),
        }

    @staticmethod
    def _unity_editor_state_is_transitioning(snapshot: dict[str, Any]) -> bool:
        phase = str(snapshot.get("activity_phase") or "").lower()
        if phase == "playmode_transition":
            return True
        if bool(snapshot.get("is_changing")):
            return True
        blocking_reasons = [str(item).lower() for item in list(snapshot.get("blocking_reasons") or [])]
        return any("playmode" in item or "play mode" in item for item in blocking_reasons)

    @staticmethod
    def _should_refresh_active_window(current: WindowTarget | None, candidate: WindowTarget | None) -> bool:
        if current is None or candidate is None:
            return False
        return current.pid == candidate.pid
