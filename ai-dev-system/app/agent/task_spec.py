from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TaskActionSpec:
    """One structured operation requested by the caller."""

    capability: str
    params: dict[str, Any] = field(default_factory=dict)
    backend: str = "auto"
    allow_fallback: bool = True
    heal_hints: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "params": self.params,
            "backend": self.backend,
            "allow_fallback": self.allow_fallback,
            "heal_hints": self.heal_hints,
            "execution": self.execution,
        }


@dataclass
class TaskVerifySpec:
    """One structured verification requested after actions complete."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "params": self.params,
        }


@dataclass
class TaskSpec:
    """Structured task specification — can be loaded from a YAML file or built inline."""

    profile: str
    task: str | None = None
    macro: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    actions: list[TaskActionSpec] = field(default_factory=list)
    verify: list[TaskVerifySpec] = field(default_factory=list)
    confirm_destructive: bool = False
    dry_run: bool = False
    requires_layout: str | None = None
    layout_policy: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_macro(self) -> bool:
        return bool(self.macro)

    @property
    def is_actions(self) -> bool:
        return bool(self.actions)

    @property
    def display_text(self) -> str:
        if self.task:
            return self.task
        if self.macro:
            return self.macro
        if self.actions:
            return ", ".join(action.capability for action in self.actions)
        return ""

    @classmethod
    def from_file(cls, path: str | Path) -> "TaskSpec":
        """Load a TaskSpec from a YAML file.

        Example YAML:
            profile: notepad
            task: "type hello and save to C:\\output.txt"
            confirm_destructive: false
        """
        import yaml  # type: ignore[import-untyped]

        raw = Path(path).read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(raw) or {}

        profile = data.get("profile")
        task = data.get("task")
        macro = data.get("macro")
        if not profile:
            raise ValueError(f"Task spec file '{path}' is missing required field 'profile'.")
        actions = [TaskActionSpec(**item) for item in list(data.get("actions") or [])]
        verify = [TaskVerifySpec(**item) for item in list(data.get("verify") or [])]
        if not task and not macro and not actions:
            raise ValueError(f"Task spec file '{path}' must include either 'task', 'macro', or 'actions'.")

        return cls(
            profile=str(profile),
            task=str(task) if task else None,
            macro=str(macro) if macro else None,
            args=dict(data.get("args") or {}),
            actions=actions,
            verify=verify,
            confirm_destructive=bool(data.get("confirm_destructive", False)),
            dry_run=bool(data.get("dry_run", False)),
            requires_layout=str(data["requires_layout"]) if data.get("requires_layout") else None,
            layout_policy=dict(data.get("layout_policy") or {}),
            execution=dict(data.get("execution") or {}),
            evidence=dict(data.get("evidence") or {}),
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "profile",
                    "task",
                    "macro",
                    "args",
                    "actions",
                    "verify",
                    "confirm_destructive",
                    "dry_run",
                    "requires_layout",
                    "layout_policy",
                    "execution",
                    "evidence",
                }
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "task": self.task,
            "macro": self.macro,
            "args": self.args,
            "actions": [action.to_dict() for action in self.actions],
            "verify": [check.to_dict() for check in self.verify],
            "confirm_destructive": self.confirm_destructive,
            "dry_run": self.dry_run,
            "requires_layout": self.requires_layout,
            "layout_policy": self.layout_policy,
            "execution": self.execution,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }
