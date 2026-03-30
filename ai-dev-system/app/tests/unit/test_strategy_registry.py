from __future__ import annotations

import pytest

from app.agent.strategies import StrategyRegistry
from app.agent.strategies.base_strategy import ExecutionContext


class TestStrategyRegistry:
    def setup_method(self):
        self.registry = StrategyRegistry.default()

    def test_known_strategies_registered(self):
        known = [
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
        for name in known:
            found = any(s.can_handle(name) for s in self.registry._strategies)
            assert found, f"Strategy '{name}' not found in registry"

    def test_execute_unknown_raises_value_error(self):
        ctx = object()  # dummy — execute won't be reached
        with pytest.raises(ValueError, match="No registered strategy handles"):
            self.registry.execute("nonexistent_strategy", ctx)  # type: ignore[arg-type]

    def test_custom_strategy_registered(self):
        class EchoStrategy:
            called = False

            def can_handle(self, name: str) -> bool:
                return name == "echo"

            def execute(self, ctx) -> None:
                EchoStrategy.called = True

        registry = StrategyRegistry()
        strategy = EchoStrategy()
        registry.register(strategy)
        assert registry._strategies == [strategy]
        assert strategy.can_handle("echo")
        assert not strategy.can_handle("other")
