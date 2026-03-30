from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    """Report agent progress events during a run."""

    def report(self, event: str, **kwargs: Any) -> None:
        """Emit a progress event."""
        ...


class SilentProgressReporter:
    """No-op reporter — used in tests and non-verbose mode."""

    def report(self, event: str, **kwargs: Any) -> None:
        pass


class ConsoleProgressReporter:
    """Writes human-friendly progress lines to stdout."""

    _ICONS: dict[str, str] = {
        "run_started": "▶",
        "action_started": "⟳",
        "action_done": "✓",
        "action_failed": "✗",
        "recovery_attempted": "↺",
        "verification_failed": "⚠",
        "run_finished": "■",
        "run_failed": "✗",
    }

    def report(self, event: str, **kwargs: Any) -> None:
        icon = self._ICONS.get(event, "·")
        parts: list[str] = [f" {icon} [{event}]"]

        if event == "run_started":
            parts.append(f"profile={kwargs.get('profile', '?')}  task={kwargs.get('task', '?')!r}")
        elif event == "action_started":
            idx = kwargs.get("index", "?")
            total = kwargs.get("total", "?")
            name = kwargs.get("name", "?")
            strategy = kwargs.get("strategy", "?")
            parts.append(f"[{idx}/{total}] {name}  strategy={strategy}")
        elif event == "action_done":
            name = kwargs.get("name", "?")
            elapsed = kwargs.get("elapsed_ms", "?")
            parts.append(f"{name}  ({elapsed}ms)")
        elif event in {"action_failed", "run_failed"}:
            parts.append(str(kwargs.get("error", "")))
        elif event == "recovery_attempted":
            parts.append(
                f"current={kwargs.get('current_strategy', '?')}  "
                f"next={kwargs.get('next_strategy', 'stop')}  "
                f"reason={kwargs.get('reason', '?')!r}"
            )
        elif event == "run_finished":
            parts.append(
                f"status={kwargs.get('status', '?')}  "
                f"actions={kwargs.get('action_count', '?')}  "
                f"elapsed={kwargs.get('elapsed_seconds', '?'):.1f}s"
                if isinstance(kwargs.get("elapsed_seconds"), float) else
                f"status={kwargs.get('status', '?')}"
            )

        print("  ".join(parts))
