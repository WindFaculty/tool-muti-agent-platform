from __future__ import annotations

from app.agent.strategies.base_strategy import ExecutionContext


class CoordinateClickStrategy:
    """Click a hard-coded (x, y) coordinate pair from the profile's coordinate_fallbacks."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "coordinate_click"

    def execute(self, ctx: ExecutionContext) -> None:
        if ctx.action.name not in ctx.profile.coordinate_fallbacks:
            raise RuntimeError(
                f"No coordinate fallback is configured for action {ctx.action.name}"
            )
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        x, y = ctx.profile.coordinate_fallbacks[ctx.action.name]
        ctx.pyautogui.click_point(x, y)
        if ctx.action.action_type in {"type_text", "set_text"}:
            ctx.pyautogui.type_text(str(ctx.action.value))
