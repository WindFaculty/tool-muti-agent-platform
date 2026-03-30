from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SelectorSpec:
    """Selector configuration for a top-level window or child control."""

    handle: int | None = None
    title: str | None = None
    title_re: str | None = None
    automation_id: str | None = None
    control_type: str | None = None
    class_name: str | None = None
    found_index: int = 0
    backend: str | None = None
    visible_only: bool = True

    def to_window_criteria(self) -> dict[str, Any]:
        criteria: dict[str, Any] = {}
        if self.handle is not None:
            criteria["handle"] = self.handle
        if self.title is not None:
            criteria["title"] = self.title
        if self.title_re is not None:
            criteria["title_re"] = self.title_re
        if self.class_name is not None:
            criteria["class_name"] = self.class_name
        if self.control_type is not None:
            criteria["control_type"] = self.control_type
        return criteria

    def to_child_criteria(self) -> dict[str, Any]:
        criteria: dict[str, Any] = {}
        if self.title is not None:
            criteria["title"] = self.title
        if self.title_re is not None:
            criteria["title_re"] = self.title_re
        if self.automation_id is not None:
            criteria["auto_id"] = self.automation_id
        if self.class_name is not None:
            criteria["class_name"] = self.class_name
        if self.control_type is not None:
            criteria["control_type"] = self.control_type
        return criteria


@dataclass(slots=True)
class WindowTarget:
    """Observed top-level window metadata."""

    handle: int
    title: str
    class_name: str
    pid: int
    backend: str = "uia"
    bounds: tuple[int, int, int, int] | None = None


@dataclass(slots=True)
class VerificationCheck:
    """One postcondition for an action."""

    kind: str
    selector: SelectorSpec | None = None
    expected: Any = None
    timeout_seconds: float = 5.0
    negate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ActionRequest:
    """A planned action and the verification checks that must pass after it."""

    name: str
    action_type: str
    target: SelectorSpec | None = None
    value: Any = None
    allowed_strategies: list[str] = field(default_factory=list)
    postconditions: list[VerificationCheck] = field(default_factory=list)
    destructive: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ActionAttempt:
    """An execution attempt for one action with one strategy."""

    request_name: str
    strategy: str
    status: str
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class VerificationResult:
    """The final outcome of verification after an action attempt."""

    passed: bool
    strategy: str
    details: dict[str, Any] = field(default_factory=dict)
    failed_checks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RecoveryDecision:
    """Decision returned by recovery logic after a failed attempt."""

    next_strategy: str | None
    reason: str
    stop: bool = False
    error_category: str | None = None


@dataclass(slots=True)
class RunState:
    """Mutable state for a single CLI run."""

    run_id: str
    profile_name: str
    task: str
    artifact_dir: Path
    status: str = "created"
    action_index: int = 0
    attempts: list[ActionAttempt] = field(default_factory=list)
    observed_windows: list[WindowTarget] = field(default_factory=list)
    active_window: WindowTarget | None = None
    details: dict[str, Any] = field(default_factory=dict)
    background_jobs: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact_dir"] = str(self.artifact_dir)
        return payload
