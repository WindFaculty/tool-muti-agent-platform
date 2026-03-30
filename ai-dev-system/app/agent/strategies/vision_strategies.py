from __future__ import annotations

from app.agent.strategies.base_strategy import ExecutionContext
from app.vision.locator import VisionLlmLocator


class VisionLlmClickStrategy:
    def __init__(self, locator: VisionLlmLocator) -> None:
        self._locator = locator

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "vision_llm_click"

    def execute(self, ctx: ExecutionContext) -> None:
        self._execute_click(ctx)

    def _execute_click(self, ctx: ExecutionContext) -> None:
        region = _resolve_region(ctx)
        image = ctx.screen_capture.capture_image(region=region)
        hints = dict(ctx.action.metadata.get("heal_hints") or {})
        target_description = str(
            hints.get("expected_visual_target")
            or ctx.action.metadata.get("visual_target")
            or ctx.action.name
        )
        prediction = self._locator.locate(
            image=image,
            target_description=target_description,
            region_hint=region,
            candidate_actions=[
                {
                    "name": ctx.action.name,
                    "action_type": ctx.action.action_type,
                    "target_description": target_description,
                }
            ],
        )
        left, top, right, bottom = prediction.bounding_box
        offset_x = region[0] if region is not None else 0
        offset_y = region[1] if region is not None else 0
        center_x = offset_x + left + ((right - left) // 2)
        center_y = offset_y + top + ((bottom - top) // 2)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pyautogui.click_point(center_x, center_y)
        ctx.metadata["vision"] = {
            **prediction.to_dict(),
            "screen_click_point": [center_x, center_y],
        }


class VisionLlmTypeStrategy(VisionLlmClickStrategy):
    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "vision_llm_type"

    def execute(self, ctx: ExecutionContext) -> None:
        self._execute_click(ctx)
        ctx.pyautogui.type_text(str(ctx.action.value))


def _resolve_region(ctx: ExecutionContext) -> tuple[int, int, int, int] | None:
    if ctx.active_window is None or ctx.active_window.bounds is None:
        return None
    hint = ctx.profile.region_hints.get(ctx.action.name) or ctx.profile.region_hints.get("results")
    if hint is None:
        return None
    left, top, right, bottom = ctx.active_window.bounds
    width = right - left
    height = bottom - top
    rx, ry, rw, rh = hint
    return (
        int(left + rx * width),
        int(top + ry * height),
        int(rw * width),
        int(rh * height),
    )
