from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlanStep:
    id: str
    title: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskDefinition:
    id: str
    title: str
    prompt: str
    goal: dict[str, Any]


@dataclass(slots=True)
class ExecutionRecord:
    step_id: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Lesson:
    category: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
