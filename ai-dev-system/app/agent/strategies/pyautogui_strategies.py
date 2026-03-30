from __future__ import annotations

from pathlib import Path

from app.agent.strategies.base_strategy import ExecutionContext


class PyAutoGuiHotkeyStrategy:
    """Send a hotkey using PyAutoGUI (vision-layer fallback)."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pyautogui_hotkey"

    def execute(self, ctx: ExecutionContext) -> None:
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        keys = _expand_hotkey(str(ctx.action.value))
        ctx.pyautogui.hotkey(*keys)


class ImageClickStrategy:
    """Locate and click a UI element via template image matching (PyAutoGUI)."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "image_click"

    def execute(self, ctx: ExecutionContext) -> None:
        template_path = ctx.action.metadata.get("template_path")
        if not template_path:
            raise RuntimeError(
                f"Action {ctx.action.name} did not provide a template_path for image_click."
            )
        region = _resolve_region(ctx)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pyautogui.click_image(
            Path(str(template_path)),
            region=region,
            confidence=ctx.settings.screenshot_confidence,
        )


class ImageTypeStrategy:
    """Click an image region (optional) then type via PyAutoGUI character-by-character."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "image_type"

    def execute(self, ctx: ExecutionContext) -> None:
        # Attempt to click the target control first with pywinauto if we have a selector
        if ctx.action.target is not None:
            try:
                root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=ctx.window_selector.backend or "uia")
                ctx.pywinauto.click(root, ctx.action.target)
            except Exception:
                pass
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pyautogui.type_text(str(ctx.action.value))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expand_hotkey(keys: str) -> tuple[str, ...]:
    mapping = {"^": "ctrl", "%": "alt", "+": "shift"}
    expanded: list[str] = []
    for char in keys:
        if char in mapping:
            expanded.append(mapping[char])
        else:
            expanded.append(char.lower())
    return tuple(expanded)


def _resolve_region(ctx: ExecutionContext) -> tuple[int, int, int, int] | None:
    """Derive a screen region from window bounds + profile hint (same logic as before)."""
    if ctx.active_window is None or ctx.active_window.bounds is None:
        return None
    hint = ctx.profile.region_hints.get(ctx.action.name) or ctx.profile.region_hints.get("results")
    if hint is None:
        return None
    left, top, right, bottom = ctx.active_window.bounds
    w = right - left
    h = bottom - top
    rx, ry, rw, rh = hint
    return (
        int(left + rx * w),
        int(top + ry * h),
        int(rw * w),
        int(rh * h),
    )
