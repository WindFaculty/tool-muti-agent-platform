from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from app.agent.state import RecoveryDecision


class ErrorCategory(str, Enum):
    ELEMENT_NOT_FOUND = "element_not_found"
    TIMEOUT = "timeout"
    FOREGROUND_LOST = "foreground_lost"
    EMERGENCY_STOP = "emergency_stop"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RecoveryPolicy:
    """Per-category recovery behaviour."""

    retry_same_first: bool = False        # retry the same strategy once before advancing
    backoff_seconds: float = 0.0          # wait before retrying
    refocus_before_retry: bool = False    # regain focus before the retry
    stop_immediately: bool = False        # stop the run without any retry


# Default policies per error category
_POLICIES: dict[ErrorCategory, RecoveryPolicy] = {
    ErrorCategory.ELEMENT_NOT_FOUND: RecoveryPolicy(retry_same_first=False, backoff_seconds=0.0),
    ErrorCategory.TIMEOUT: RecoveryPolicy(retry_same_first=True, backoff_seconds=0.5),
    ErrorCategory.FOREGROUND_LOST: RecoveryPolicy(retry_same_first=True, backoff_seconds=0.3, refocus_before_retry=True),
    ErrorCategory.EMERGENCY_STOP: RecoveryPolicy(stop_immediately=True),
    ErrorCategory.UNKNOWN: RecoveryPolicy(retry_same_first=False, backoff_seconds=0.0),
}

# Keywords used to classify error messages
_CATEGORY_KEYWORDS: dict[ErrorCategory, list[str]] = {
    ErrorCategory.EMERGENCY_STOP: ["emergency stop", "failsafe"],
    ErrorCategory.FOREGROUND_LOST: ["foreground", "focus", "foreground window mismatch"],
    ErrorCategory.TIMEOUT: ["timed out", "timeout", "wait"],
    ErrorCategory.ELEMENT_NOT_FOUND: ["no control", "no window", "lookuperror", "not found", "could not locate"],
}


class ErrorClassifier:
    """Classify a raw error string into an ErrorCategory."""

    def classify(self, error_message: str) -> ErrorCategory:
        lower = error_message.lower()
        for category, keywords in _CATEGORY_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return category
        return ErrorCategory.UNKNOWN


class RecoveryPlanner:
    """Choose the next fallback strategy with context-aware policy after a failed attempt."""

    def __init__(self, classifier: ErrorClassifier | None = None) -> None:
        self._classifier = classifier or ErrorClassifier()

    def next_strategy(
        self,
        strategies: list[str],
        current_strategy: str,
        failure_reason: str,
    ) -> RecoveryDecision:
        category = self._classifier.classify(failure_reason)
        policy = _POLICIES.get(category, _POLICIES[ErrorCategory.UNKNOWN])

        if policy.stop_immediately:
            return RecoveryDecision(
                next_strategy=None,
                reason=f"Stopping immediately due to {category.value}: {failure_reason}",
                stop=True,
            )

        try:
            index = strategies.index(current_strategy)
        except ValueError:
            return RecoveryDecision(
                next_strategy=None,
                reason=f"Unknown strategy '{current_strategy}'",
                stop=True,
            )

        # Apply backoff if configured
        if policy.backoff_seconds > 0:
            time.sleep(policy.backoff_seconds)

        # retry_same_first: stay on current strategy once before advancing
        if policy.retry_same_first:
            return RecoveryDecision(
                next_strategy=current_strategy,
                reason=f"Retrying same strategy after {category.value}: {failure_reason}",
                stop=False,
            )

        # Advance to the next strategy
        next_index = index + 1
        if next_index >= len(strategies):
            return RecoveryDecision(
                next_strategy=None,
                reason=f"All strategies exhausted after {current_strategy}: {failure_reason}",
                stop=True,
            )
        return RecoveryDecision(
            next_strategy=strategies[next_index],
            reason=f"Advancing from {current_strategy} after {category.value}: {failure_reason}",
            stop=False,
        )
