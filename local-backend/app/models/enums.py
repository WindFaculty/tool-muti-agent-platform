from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    INBOX = "inbox"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RepeatRule(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AssistantEmotion(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SERIOUS = "serious"
    WARNING = "warning"
    THINKING = "thinking"


class AnimationHint(str, Enum):
    IDLE = "idle"
    GREET = "greet"
    NOD = "nod"
    LISTEN = "listen"
    THINK = "think"
    EXPLAIN = "explain"
    CONFIRM = "confirm"
    ALERT = "alert"
