from __future__ import annotations

from agents.contracts import Lesson


class DebugAgent:
    _MCP_PACKAGE_MARKER = "library/packagecache/com.coplaydev.unity-mcp@"
    _NOISE_MESSAGE_MARKERS = (
        "client handler exited",
        "client connected",
        "stdiobridgehost started on port",
        "sending shutdown to client",
    )

    def summarize_console(self, console_payload: dict) -> dict:
        structured = console_payload.get("structured_content") or {}
        entries = structured.get("data") or []
        analysis = {
            "total_entries": len(entries),
            "counts": {
                "app_errors": 0,
                "app_warnings": 0,
                "app_logs": 0,
                "noise_filtered": 0,
            },
            "app_errors": [],
            "app_warnings": [],
            "app_logs": [],
            "noise_filtered": [],
        }

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            if self._is_mcp_noise(entry):
                analysis["noise_filtered"].append(entry)
                analysis["counts"]["noise_filtered"] += 1
                continue

            entry_type = str(entry.get("type", "")).strip().lower()
            if entry_type in {"error", "exception", "assert"}:
                analysis["app_errors"].append(entry)
                analysis["counts"]["app_errors"] += 1
            elif entry_type == "warning":
                analysis["app_warnings"].append(entry)
                analysis["counts"]["app_warnings"] += 1
            else:
                analysis["app_logs"].append(entry)
                analysis["counts"]["app_logs"] += 1

        return analysis

    def analyze_console(self, analysis: dict) -> Lesson | None:
        counts = analysis.get("counts", {})
        app_error_count = counts.get("app_errors", 0)
        app_warning_count = counts.get("app_warnings", 0)
        app_log_count = counts.get("app_logs", 0)
        filtered_noise_count = counts.get("noise_filtered", 0)

        if app_error_count == 0 and app_warning_count == 0 and app_log_count == 0 and filtered_noise_count == 0:
            return Lesson(
                category="verification",
                summary="Unity console was clean during verification.",
                evidence={"console_entries": 0},
            )

        if app_error_count == 0 and app_warning_count == 0 and app_log_count == 0:
            return Lesson(
                category="verification",
                summary="Unity console only produced filtered MCP bridge lifecycle noise during verification.",
                evidence={"noise_filtered": filtered_noise_count},
            )

        return Lesson(
            category="console",
            summary=(
                "Unity console produced application-visible output during verification "
                f"(errors={app_error_count}, warnings={app_warning_count}, logs={app_log_count})."
            ),
            evidence={
                "counts": counts,
                "app_errors": analysis.get("app_errors", [])[:5],
                "app_warnings": analysis.get("app_warnings", [])[:5],
            },
        )

    def _is_mcp_noise(self, entry: dict) -> bool:
        message = str(entry.get("message", "")).strip().lower()
        file_path = str(entry.get("file", "")).strip().replace("\\", "/").lower()

        is_transport_source = self._MCP_PACKAGE_MARKER in file_path or "mcp-for-unity" in message or "stdiobridgehost" in message
        if not is_transport_source:
            return False

        if "closing" in message and "stale client" in message:
            return True

        return any(marker in message for marker in self._NOISE_MESSAGE_MARKERS)
