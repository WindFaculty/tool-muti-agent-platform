from __future__ import annotations

from typing import Any


def build_workflow_report(summary: dict[str, Any]) -> dict[str, Any]:
    steps = summary.get("steps") or []
    failed_steps: list[dict[str, Any]] = []
    verification_reports: list[dict[str, Any]] = []

    for step in steps:
        if not isinstance(step, dict):
            continue

        step_id = str(step.get("step_id", ""))
        status = str(step.get("status", "unknown"))
        details = step.get("details") or {}

        if status != "completed":
            failure = _classify_failure(details)
            failed_steps.append(
                {
                    "step_id": step_id,
                    "status": status,
                    "category": failure["category"],
                    "retryable": failure["retryable"],
                    "reason_codes": failure["reason_codes"],
                    "messages": failure["messages"],
                }
            )

        console_analysis = details.get("console_analysis")
        if isinstance(console_analysis, dict):
            missing_objects = _extract_missing_objects(details.get("expected_objects") or {})
            verification_reports.append(
                {
                    "step_id": step_id,
                    "status": _classify_verification(console_analysis, missing_objects),
                    "counts": console_analysis.get("counts") or {},
                    "top_errors": _summarize_entries(console_analysis.get("app_errors") or []),
                    "top_warnings": _summarize_entries(console_analysis.get("app_warnings") or []),
                    "top_logs": _summarize_entries(console_analysis.get("app_logs") or [], limit=3),
                    "screenshot": _extract_screenshot_path(details.get("screenshot") or {}),
                    "missing_objects": missing_objects,
                }
            )

    return {
        "task_id": summary.get("task_id"),
        "task_title": summary.get("task_title"),
        "step_count": len([step for step in steps if isinstance(step, dict)]),
        "failed_step_count": len(failed_steps),
        "failed_steps": failed_steps,
        "verification_reports": verification_reports,
        "stopped_after_step": summary.get("stopped_after_step"),
        "overall_status": summary.get("workflow_status") or ("failed" if failed_steps else "completed"),
    }


def format_workflow_report(report: dict[str, Any]) -> str:
    lines = [
        f"Task: {report.get('task_title') or report.get('task_id') or 'unknown task'}",
        f"Overall status: {report.get('overall_status', 'unknown')}",
        f"Steps: {report.get('step_count', 0)}",
    ]

    failed_steps = report.get("failed_steps") or []
    if failed_steps:
        lines.append(f"Failed steps: {len(failed_steps)}")
        for failed_step in failed_steps:
            retryable = "yes" if failed_step.get("retryable") else "no"
            reason_codes = failed_step.get("reason_codes") or []
            reason_suffix = f"; reasons={','.join(reason_codes)}" if reason_codes else ""
            lines.append(
                f"- {failed_step.get('step_id', 'unknown')}: "
                f"[{failed_step.get('category', 'execution_failure')}; retryable={retryable}{reason_suffix}] "
                f"{'; '.join(failed_step.get('messages') or ['No detail message'])}"
            )
        stopped_after_step = report.get("stopped_after_step")
        if stopped_after_step:
            lines.append(f"Stopped after step: {stopped_after_step}")
    else:
        lines.append("Failed steps: 0")

    verification_reports = report.get("verification_reports") or []
    if not verification_reports:
        lines.append("Verification: no verification steps recorded")
        return "\n".join(lines)

    for verification in verification_reports:
        counts = verification.get("counts") or {}
        lines.append(
            "Verification "
            f"{verification.get('step_id', 'unknown')} "
            f"[{verification.get('status', 'unknown')}]: "
            f"errors={counts.get('app_errors', 0)}, "
            f"warnings={counts.get('app_warnings', 0)}, "
            f"logs={counts.get('app_logs', 0)}, "
            f"noise_filtered={counts.get('noise_filtered', 0)}"
        )

        screenshot = verification.get("screenshot")
        if screenshot:
            lines.append(f"Screenshot: {screenshot}")

        missing_objects = verification.get("missing_objects") or []
        if missing_objects:
            lines.append(f"Missing objects: {', '.join(missing_objects)}")

        for label, entries in (
            ("Errors", verification.get("top_errors") or []),
            ("Warnings", verification.get("top_warnings") or []),
            ("Logs", verification.get("top_logs") or []),
        ):
            if not entries:
                continue
            lines.append(f"{label}:")
            for entry in entries:
                lines.append(f"- {entry}")

    return "\n".join(lines)


def _extract_detail_messages(details: dict[str, Any]) -> list[str]:
    signals = _collect_failure_signals(details)
    return signals["messages"][:5]


def _classify_failure(details: dict[str, Any]) -> dict[str, Any]:
    signals = _collect_failure_signals(details)
    messages = signals["messages"][:5]
    reason_codes = signals["reason_codes"]
    haystack = " ".join(message.lower() for message in messages)
    reason_set = {code.lower() for code in reason_codes}

    if "unsaved changes" in haystack:
        category = "editor_unsaved_changes"
        retryable = False
    elif (
        "reloading" in reason_set
        or "transport_exception" in reason_set
        or "please retry" in haystack
        or "hint='retry'" in haystack
        or 'hint="retry"' in haystack
    ):
        category = "transport_retryable"
        retryable = True
    elif "timed out" in haystack or "timeout" in haystack:
        category = "timeout"
        retryable = True
    elif (
        "does not exist" in haystack
        or "not found" in haystack
        or "cannot find" in haystack
        or "missing" in haystack
    ):
        category = "missing_resource"
        retryable = False
    else:
        category = "execution_failure"
        retryable = False

    return {
        "category": category,
        "retryable": retryable,
        "reason_codes": reason_codes,
        "messages": messages,
    }


def _classify_verification(console_analysis: dict[str, Any], missing_objects: list[str]) -> str:
    counts = console_analysis.get("counts") or {}
    error_count = int(counts.get("app_errors", 0) or 0)
    warning_count = int(counts.get("app_warnings", 0) or 0)
    log_count = int(counts.get("app_logs", 0) or 0)
    noise_count = int(counts.get("noise_filtered", 0) or 0)

    if error_count > 0 and missing_objects:
        return "console-errors-and-missing-objects"
    if error_count > 0:
        return "console-errors"
    if missing_objects:
        return "missing-objects"
    if warning_count > 0:
        return "warnings"
    if log_count > 0:
        return "logs-only"
    if noise_count > 0:
        return "noise-only"
    return "clean"


def _collect_failure_signals(value: Any) -> dict[str, list[str]]:
    messages: list[str] = []
    reason_codes: list[str] = []
    _walk_failure_signals(value, messages, reason_codes)
    return {"messages": messages, "reason_codes": reason_codes}


def _walk_failure_signals(value: Any, messages: list[str], reason_codes: list[str]) -> None:
    if isinstance(value, dict):
        structured = value.get("structured_content")
        if isinstance(structured, dict):
            for key in ("error", "code", "message"):
                message = structured.get(key)
                if message:
                    _append_unique(messages, str(message).strip())

            data = structured.get("data")
            if isinstance(data, dict):
                reason = data.get("reason")
                if reason:
                    _append_unique(reason_codes, str(reason).strip())

        for item in value.get("content") or []:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if text:
                _append_unique(messages, str(text).strip())

        extracted_message = _extract_message(value)
        if extracted_message:
            _append_unique(messages, extracted_message)

        for nested in value.values():
            _walk_failure_signals(nested, messages, reason_codes)
        return

    if isinstance(value, list):
        for item in value:
            _walk_failure_signals(item, messages, reason_codes)


def _append_unique(items: list[str], value: str) -> None:
    if not value or value in items:
        return
    items.append(value)


def _extract_message(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    structured = value.get("structured_content") or {}
    for key in ("error", "code", "message"):
        message = structured.get(key)
        if message:
            return str(message)

    for item in value.get("content") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if text:
            return str(text).strip()

    return None


def _extract_screenshot_path(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None

    structured = payload.get("structured_content") or {}
    data = structured.get("data") or {}
    path = data.get("fullPath") or data.get("path")
    if path:
        return str(path)
    return None


def _summarize_entries(entries: list[dict[str, Any]], limit: int = 5) -> list[str]:
    summarized: list[str] = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type", "entry")).strip()
        message = str(entry.get("message", "")).strip()
        if not message:
            continue
        summarized.append(f"{entry_type}: {message}")
    return summarized


def _extract_missing_objects(expected_objects: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for object_name, lookup_result in expected_objects.items():
        if not isinstance(lookup_result, dict):
            missing.append(str(object_name))
            continue

        structured = lookup_result.get("structured_content") or {}
        data = structured.get("data") or {}
        items = data.get("items") or []
        instance_ids = data.get("instanceIDs") or []
        total_count = data.get("totalCount")
        if len(items) == 0 and len(instance_ids) == 0 and total_count in (None, 0):
            missing.append(str(object_name))

    return missing
