from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.state import ActionRequest, SelectorSpec, WindowTarget
from app.profiles.base_profile import BaseProfile


@dataclass(slots=True)
class HealingStep:
    strategy: str
    description: str
    metadata: dict[str, Any]


class UiHealingPlanner:
    """Plan tightly scoped recovery steps without abandoning fail-closed safety."""

    def plan(
        self,
        *,
        action: ActionRequest,
        profile: BaseProfile,
        active_window: WindowTarget | None,
    ) -> HealingStep | None:
        del profile, active_window
        hints = dict(action.metadata.get("heal_hints") or {})
        retry_selector = self._normalize_selector(hints.get("retry_selector"))
        configured_modes = [
            key
            for key in ("focus_surface", "open_window", "expand_container")
            if hints.get(key) not in (None, "", {})
        ]
        if len(configured_modes) > 1:
            return None

        focus_surface = hints.get("focus_surface")
        if isinstance(focus_surface, str) and focus_surface.strip():
            return HealingStep(
                strategy="ui_heal",
                description=f"Focus Unity surface '{focus_surface}'.",
                metadata={
                    "mode": "focus_surface",
                    "surface": focus_surface.strip(),
                    "retry_selector": retry_selector,
                },
            )

        open_window = hints.get("open_window")
        if isinstance(open_window, str) and open_window.strip():
            return HealingStep(
                strategy="ui_heal",
                description=f"Open Unity window '{open_window}'.",
                metadata={
                    "mode": "open_window",
                    "window": open_window.strip(),
                    "retry_selector": retry_selector,
                },
            )

        expand_container = self._normalize_selector(hints.get("expand_container"))
        if expand_container is not None:
            return HealingStep(
                strategy="ui_heal",
                description="Expand the hinted container and retry.",
                metadata={
                    "mode": "expand_container",
                    "selector": expand_container,
                    "retry_selector": retry_selector,
                },
            )

        return None

    @staticmethod
    def _normalize_selector(raw: Any) -> SelectorSpec | None:
        if isinstance(raw, SelectorSpec):
            return raw
        if isinstance(raw, dict):
            return SelectorSpec(**raw)
        return None
