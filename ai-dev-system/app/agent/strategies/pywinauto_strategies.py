from __future__ import annotations

from app.agent.strategies.base_strategy import ExecutionContext


class PywinautoClickStrategy:
    """Click a control via pywinauto structured automation."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_click"

    def execute(self, ctx: ExecutionContext) -> None:
        if ctx.action.target is None:
            raise RuntimeError(f"Action {ctx.action.name} has no selector for pywinauto_click")
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.click(root, ctx.action.target)


class PywinautoInvokeStrategy:
    """Invoke (accessibility action) a control via pywinauto."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_invoke"

    def execute(self, ctx: ExecutionContext) -> None:
        if ctx.action.target is None:
            raise RuntimeError(f"Action {ctx.action.name} has no selector for pywinauto_invoke")
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.invoke(root, ctx.action.target)


class PywinautoSelectStrategy:
    """Select a control (list item, tab, etc.) via pywinauto."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_select"

    def execute(self, ctx: ExecutionContext) -> None:
        if ctx.action.target is None:
            raise RuntimeError(f"Action {ctx.action.name} has no selector for pywinauto_select")
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.select(root, ctx.action.target)


class PywinautoTypeStrategy:
    """Type text into a control via clipboard-paste (pywinauto + pyperclip)."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_type"

    def execute(self, ctx: ExecutionContext) -> None:
        if ctx.action.target is None:
            raise RuntimeError(f"Action {ctx.action.name} has no selector for pywinauto_type")
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.type_text(root, ctx.action.target, str(ctx.action.value))


class PywinautoSetTextStrategy:
    """Directly set the text of an edit control via pywinauto."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_set_text"

    def execute(self, ctx: ExecutionContext) -> None:
        if ctx.action.target is None:
            raise RuntimeError(f"Action {ctx.action.name} has no selector for pywinauto_set_text")
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.set_text(root, ctx.action.target, str(ctx.action.value))


class PywinautoHotkeyStrategy:
    """Send a hotkey sequence via pywinauto type_keys."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_hotkey"

    def execute(self, ctx: ExecutionContext) -> None:
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.send_hotkey(root, str(ctx.action.value))


class PywinautoMenuSelectStrategy:
    """Select a menu path via pywinauto's native menu_select helper."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "pywinauto_menu_select"

    def execute(self, ctx: ExecutionContext) -> None:
        root = ctx.pywinauto.resolve_window(ctx.window_selector, backend=_backend(ctx))
        _set_focus(root)
        ctx.guard.ensure_safe(expected_handle=ctx.window_selector.handle)
        ctx.pywinauto.menu_select(root, str(ctx.action.value))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _backend(ctx: ExecutionContext) -> str:
    selector = ctx.action.target
    if selector is not None and selector.backend is not None:
        return selector.backend
    return ctx.window_selector.backend or "uia"


def _set_focus(root) -> None:
    try:
        root.set_focus()
    except Exception:
        pass
