from __future__ import annotations

from typing import Sequence

from app.agent.strategies.base_strategy import ActionStrategy, ExecutionContext
from app.agent.strategies.coordinate_strategy import CoordinateClickStrategy
from app.agent.strategies.healing_strategies import UiHealStrategy
from app.agent.strategies.mcp_strategies import MpcBatchStrategy, MpcToolStrategy
from app.agent.strategies.pyautogui_strategies import (
    ImageClickStrategy,
    ImageTypeStrategy,
    PyAutoGuiHotkeyStrategy,
)
from app.agent.strategies.pywinauto_strategies import (
    PywinautoClickStrategy,
    PywinautoHotkeyStrategy,
    PywinautoInvokeStrategy,
    PywinautoMenuSelectStrategy,
    PywinautoSelectStrategy,
    PywinautoSetTextStrategy,
    PywinautoTypeStrategy,
)
from app.agent.strategies.vision_strategies import VisionLlmClickStrategy, VisionLlmTypeStrategy
from app.vision.locator import VisionLlmLocator


class StrategyRegistry:
    """Registry of all action strategies. Supports plugin-style registration."""

    def __init__(self) -> None:
        self._strategies: list[ActionStrategy] = []

    def register(self, strategy: ActionStrategy) -> None:
        """Add a strategy to the registry."""
        self._strategies.append(strategy)

    def execute(self, strategy_name: str, ctx: ExecutionContext) -> None:
        """Dispatch execution to the first registered strategy that handles the name."""
        for strategy in self._strategies:
            if strategy.can_handle(strategy_name):
                strategy.execute(ctx)
                return
        raise ValueError(f"No registered strategy handles '{strategy_name}'")

    def registered_names(self, strategies: Sequence[ActionStrategy] | None = None) -> list[str]:
        """Return the list of all strategy names this registry knows about."""
        source = strategies if strategies is not None else self._strategies
        names: list[str] = []
        for s in source:
            for candidate in _ALL_KNOWN_NAMES:
                if s.can_handle(candidate) and candidate not in names:
                    names.append(candidate)
        return names

    @classmethod
    def default(cls, *, vision_locator: VisionLlmLocator | None = None) -> "StrategyRegistry":
        """Build a registry pre-loaded with all built-in strategies."""
        registry = cls()
        for strategy in _built_in_strategies(vision_locator=vision_locator):
            registry.register(strategy)
        return registry


def _built_in_strategies(*, vision_locator: VisionLlmLocator | None = None) -> list[ActionStrategy]:
    locator = vision_locator or VisionLlmLocator()
    return [
        MpcToolStrategy(),
        MpcBatchStrategy(),
        PywinautoClickStrategy(),
        PywinautoInvokeStrategy(),
        PywinautoSelectStrategy(),
        PywinautoTypeStrategy(),
        PywinautoSetTextStrategy(),
        PywinautoHotkeyStrategy(),
        PywinautoMenuSelectStrategy(),
        UiHealStrategy(),
        VisionLlmClickStrategy(locator),
        VisionLlmTypeStrategy(locator),
        PyAutoGuiHotkeyStrategy(),
        ImageClickStrategy(),
        ImageTypeStrategy(),
        CoordinateClickStrategy(),
    ]

_ALL_KNOWN_NAMES = [
    "mcp_tool",
    "mcp_batch",
    "pywinauto_click",
    "pywinauto_invoke",
    "pywinauto_select",
    "pywinauto_type",
    "pywinauto_set_text",
    "pywinauto_hotkey",
    "pywinauto_menu_select",
    "ui_heal",
    "vision_llm_click",
    "vision_llm_type",
    "pyautogui_hotkey",
    "image_click",
    "image_type",
    "coordinate_click",
]

__all__ = [
    "ActionStrategy",
    "ExecutionContext",
    "StrategyRegistry",
]
