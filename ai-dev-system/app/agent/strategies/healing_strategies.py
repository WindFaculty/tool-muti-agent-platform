from __future__ import annotations

from app.agent.strategies.base_strategy import ExecutionContext
from app.unity.surfaces import UnitySurfaceMap


class UiHealStrategy:
    """Execute a tightly scoped self-healing step before retrying the primary action."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "ui_heal"

    def execute(self, ctx: ExecutionContext) -> None:
        hints = dict(ctx.action.metadata.get("active_healing_step") or {})
        mode = str(hints.get("mode") or "").strip().lower()
        if not mode:
            raise RuntimeError(f"Action {ctx.action.name} has no active healing step.")

        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=ctx.window_selector.backend or "uia")
        if mode == "focus_surface":
            surface = UnitySurfaceMap.surface(str(hints.get("surface") or ""))
            if surface.focus_hotkey:
                ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
                ctx.pywinauto.send_hotkey(root, surface.focus_hotkey)
            elif surface.menu_path:
                ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
                ctx.pywinauto.menu_select(root, surface.menu_path)
            else:
                raise RuntimeError(f"Unity surface '{surface.key}' does not provide a safe focus path.")
        elif mode == "open_window":
            surface = UnitySurfaceMap.resolve_window_alias(str(hints.get("window") or ""))
            if not surface.menu_path:
                raise RuntimeError(f"Unity window '{surface.display_name}' cannot be opened from the menu.")
            ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
            ctx.pywinauto.menu_select(root, surface.menu_path)
        elif mode == "expand_container":
            selector = hints.get("selector")
            if selector is None:
                raise RuntimeError("expand_container healing step is missing a selector.")
            ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
            try:
                ctx.pywinauto.invoke(root, selector)
            except Exception:
                ctx.pywinauto.click(root, selector)
        else:
            raise RuntimeError(f"Unsupported healing mode '{mode}'.")

        retry_selector = hints.get("retry_selector")
        healed = {"mode": mode}
        if mode == "focus_surface":
            healed["surface"] = hints.get("surface")
        if mode == "open_window":
            healed["window"] = hints.get("window")
        if retry_selector is not None:
            healed["retry_selector"] = {
                "title": retry_selector.title,
                "title_re": retry_selector.title_re,
                "automation_id": retry_selector.automation_id,
                "control_type": retry_selector.control_type,
                "class_name": retry_selector.class_name,
                "found_index": retry_selector.found_index,
                "backend": retry_selector.backend,
                "visible_only": retry_selector.visible_only,
            }
            healed["retry_selector_found"] = ctx.pywinauto.exists(root, retry_selector)
        ctx.metadata["healing"] = healed
