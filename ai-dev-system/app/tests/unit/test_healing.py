from __future__ import annotations

from app.agent.healing import UiHealingPlanner
from app.agent.state import ActionRequest, SelectorSpec


def test_healing_planner_focus_surface_hint() -> None:
    planner = UiHealingPlanner()
    action = ActionRequest(
        name="click_console",
        action_type="click",
        metadata={
            "heal_hints": {
                "focus_surface": "console",
                "retry_selector": {"title": "UnityEditor.ConsoleWindow", "control_type": "Pane", "backend": "uia"},
            }
        },
    )

    step = planner.plan(action=action, profile=None, active_window=None)  # type: ignore[arg-type]

    assert step is not None
    assert step.metadata["mode"] == "focus_surface"
    assert isinstance(step.metadata["retry_selector"], SelectorSpec)


def test_healing_planner_stops_when_multiple_heal_paths_are_possible() -> None:
    planner = UiHealingPlanner()
    action = ActionRequest(
        name="click_console",
        action_type="click",
        metadata={"heal_hints": {"focus_surface": "console", "open_window": "Console"}},
    )

    step = planner.plan(action=action, profile=None, active_window=None)  # type: ignore[arg-type]

    assert step is None
