from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.agent.state import ActionRequest, SelectorSpec, VerificationCheck, VerificationResult
from app.automation.pywinauto_adapter import PywinautoAdapter
from app.automation.windows_driver import WindowsDriver
from app.vision.screenshot import ScreenshotService
from app.vision.template_match import TemplateMatcher

# Maximum cumulative wall-clock seconds allowed for all postconditions in one action.
_DEFAULT_TOTAL_CAP_SECONDS = 30.0


class Verifier:
    """Verify postconditions after each action."""

    def __init__(
        self,
        driver: WindowsDriver,
        pywinauto_adapter: PywinautoAdapter,
        screenshots: ScreenshotService,
        matcher: TemplateMatcher,
        total_timeout_cap_seconds: float = _DEFAULT_TOTAL_CAP_SECONDS,
    ) -> None:
        self._driver = driver
        self._pywinauto = pywinauto_adapter
        self._screenshots = screenshots
        self._matcher = matcher
        self._total_timeout_cap = total_timeout_cap_seconds

    def verify(
        self,
        action: ActionRequest,
        *,
        default_window_selector: SelectorSpec,
        screenshot_path: Path | None = None,
        execution_details: dict[str, Any] | None = None,
    ) -> VerificationResult:
        failed_checks: list[str] = []
        details: dict[str, Any] = {}
        run_deadline = time.time() + self._total_timeout_cap

        for check in action.postconditions:
            # Cap individual check timeout to whatever time budget remains
            remaining = max(0.0, run_deadline - time.time())
            effective_timeout = min(check.timeout_seconds, remaining)
            passed, detail = self._run_check(
                check,
                default_window_selector=default_window_selector,
                screenshot_path=screenshot_path,
                execution_details=execution_details or {},
                effective_timeout=effective_timeout,
            )
            details[check.kind] = detail
            if not passed:
                failed_checks.append(f"{check.kind}: {detail}")

        return VerificationResult(
            passed=not failed_checks,
            strategy="verification",
            details=details,
            failed_checks=failed_checks,
        )

    def _run_check(
        self,
        check: VerificationCheck,
        *,
        default_window_selector: SelectorSpec,
        screenshot_path: Path | None,
        execution_details: dict[str, Any],
        effective_timeout: float,
    ) -> tuple[bool, Any]:
        deadline = time.time() + effective_timeout
        last_detail: Any = None
        while time.time() < deadline:
            last_detail = self._evaluate_once(
                check,
                default_window_selector=default_window_selector,
                screenshot_path=screenshot_path,
                execution_details=execution_details,
            )
            if bool(last_detail.get("passed")):
                return True, last_detail
            time.sleep(0.2)
        return False, last_detail

    def _evaluate_once(
        self,
        check: VerificationCheck,
        *,
        default_window_selector: SelectorSpec,
        screenshot_path: Path | None,
        execution_details: dict[str, Any],
    ) -> dict[str, Any]:
        selector = check.selector or default_window_selector
        kind = check.kind

        if kind == "window_title_contains":
            window = self._pywinauto.resolve_window(selector, backend=selector.backend or "uia")
            actual = window.window_text()
            passed = str(check.expected) in actual
            return {"passed": not passed if check.negate else passed, "actual": actual}

        if kind == "window_exists":
            try:
                self._pywinauto.resolve_window(selector, backend=selector.backend or "uia")
                passed = True
            except Exception as exc:
                passed = False
                return {"passed": not passed if check.negate else passed, "error": str(exc)}
            return {"passed": not passed if check.negate else passed}

        if kind == "control_exists":
            window_selector = _resolve_window_selector(check, default_window_selector)
            backend = selector.backend or window_selector.backend or "uia"
            window = self._pywinauto.resolve_window(window_selector, backend=backend)
            passed = self._pywinauto.exists(window, selector)
            return {"passed": not passed if check.negate else passed}

        if kind == "control_text_contains":
            window_selector = _resolve_window_selector(check, default_window_selector)
            backend = selector.backend or window_selector.backend or "uia"
            window = self._pywinauto.resolve_window(window_selector, backend=backend)
            actual = self._pywinauto.get_text(window, selector)
            passed = str(check.expected) in actual
            return {"passed": not passed if check.negate else passed, "actual": actual}

        if kind == "file_exists":
            path = Path(str(check.expected))
            passed = path.exists()
            return {"passed": not passed if check.negate else passed, "actual": str(path)}

        if kind == "screenshot_match":
            if screenshot_path is None:
                return {"passed": False, "error": "No screenshot was captured for template verification."}
            image = self._screenshots.capture_image()
            match = self._matcher.match(image, Path(str(check.expected)), float(check.metadata.get("confidence", 0.9)))
            return {"passed": match is not None, "match": match}

        if kind == "process_running":
            # check.expected should be a PID (int) or process name (str)
            import psutil
            expected = check.expected
            if isinstance(expected, int):
                passed = psutil.pid_exists(expected)
            else:
                passed = any(p.name().lower() == str(expected).lower() for p in psutil.process_iter(["name"]))
            return {"passed": not passed if check.negate else passed, "expected": expected}

        if kind == "window_has_focus":
            active = self._driver.get_active_window()
            if active is None:
                return {"passed": False if not check.negate else True, "actual": None}
            expected_handle = check.expected
            if expected_handle is None and selector.handle is not None:
                expected_handle = selector.handle
            passed = active.handle == expected_handle
            return {"passed": not passed if check.negate else passed, "actual": active.handle}

        if kind == "mcp_result_success":
            mcp_result = execution_details.get("mcp_result")
            if not isinstance(mcp_result, dict):
                return {"passed": False, "error": "No MCP result is attached to the action attempt."}
            structured = mcp_result.get("structured_content") or {}
            success = bool(structured.get("success")) and not bool(mcp_result.get("is_error"))
            detail = {
                "is_error": bool(mcp_result.get("is_error")),
                "message": structured.get("message") or structured.get("error"),
                "code": structured.get("code"),
            }
            return {"passed": not success if check.negate else success, "result": detail}

        if kind == "mcp_job_started":
            background_job = execution_details.get("background_job")
            if not isinstance(background_job, dict):
                return {"passed": False, "error": "No background job metadata is attached to the action attempt."}
            passed = bool(background_job.get("job_id"))
            return {"passed": not passed if check.negate else passed, "job": background_job}

        if kind == "mcp_job_completed":
            background_job = execution_details.get("background_job")
            if not isinstance(background_job, dict):
                return {"passed": False, "error": "No background job metadata is attached to the action attempt."}
            status = str(background_job.get("status") or "").lower()
            passed = status in {"completed", "succeeded", "success"}
            return {"passed": not passed if check.negate else passed, "job": background_job}

        if kind == "mcp_batch_success":
            batch_result = execution_details.get("mcp_batch_result")
            if not isinstance(batch_result, dict):
                return {"passed": False, "error": "No MCP batch result is attached to the action attempt."}
            structured = batch_result.get("structured_content") or {}
            success = bool(structured.get("success")) and not bool(batch_result.get("is_error"))
            detail = {
                "is_error": bool(batch_result.get("is_error")),
                "message": structured.get("message") or structured.get("error"),
                "code": structured.get("code"),
            }
            return {"passed": not success if check.negate else success, "result": detail}

        raise ValueError(f"Unsupported verification kind: {kind}")


def _resolve_window_selector(check: VerificationCheck, default: SelectorSpec) -> SelectorSpec:
    raw = check.metadata.get("window_selector", default)
    if isinstance(raw, dict):
        return SelectorSpec(**raw)
    return raw
