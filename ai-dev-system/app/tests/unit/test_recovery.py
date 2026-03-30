from __future__ import annotations

import pytest

from app.agent.controller import AgentController
from app.agent.recovery import ErrorCategory, ErrorClassifier, RecoveryPlanner
from app.agent.state import ActionRequest, SelectorSpec
from app.config.settings import Settings
from app.profiles.base_profile import BaseProfile


class _FakeProfile(BaseProfile):
    def __init__(self) -> None:
        super().__init__(
            name="fake",
            executable="fake.exe",
            window_selector=SelectorSpec(title="Fake"),
        )

    def build_plan(self, task: str, working_directory):
        return []


class TestErrorClassifier:
    def setup_method(self):
        self.clf = ErrorClassifier()

    def test_classifies_element_not_found(self):
        assert self.clf.classify("No control matched selector") == ErrorCategory.ELEMENT_NOT_FOUND
        assert self.clf.classify("LookupError: not found") == ErrorCategory.ELEMENT_NOT_FOUND
        assert self.clf.classify("Could not locate image on screen") == ErrorCategory.ELEMENT_NOT_FOUND

    def test_classifies_timeout(self):
        assert self.clf.classify("Timed out waiting for window") == ErrorCategory.TIMEOUT
        assert self.clf.classify("timeout exceeded") == ErrorCategory.TIMEOUT

    def test_classifies_foreground_lost(self):
        assert self.clf.classify("Foreground window mismatch") == ErrorCategory.FOREGROUND_LOST
        assert self.clf.classify("focus was lost") == ErrorCategory.FOREGROUND_LOST

    def test_classifies_emergency_stop(self):
        assert self.clf.classify("Emergency stop was requested") == ErrorCategory.EMERGENCY_STOP
        assert self.clf.classify("FailSafe triggered") == ErrorCategory.EMERGENCY_STOP

    def test_classifies_unknown(self):
        assert self.clf.classify("Something entirely different happened") == ErrorCategory.UNKNOWN


class TestRecoveryPlanner:
    def setup_method(self):
        self.planner = RecoveryPlanner()

    def test_advances_to_next_on_element_not_found(self):
        strategies = ["pywinauto_click", "image_click"]
        decision = self.planner.next_strategy(strategies, "pywinauto_click", "No control matched")
        assert decision.next_strategy == "image_click"
        assert not decision.stop

    def test_retries_same_on_timeout(self):
        strategies = ["pywinauto_click", "image_click"]
        decision = self.planner.next_strategy(strategies, "pywinauto_click", "Timed out waiting")
        # retry_same_first=True for TIMEOUT category
        assert decision.next_strategy == "pywinauto_click"
        assert not decision.stop

    def test_retries_same_on_foreground_lost(self):
        strategies = ["pywinauto_click", "image_click"]
        decision = self.planner.next_strategy(strategies, "pywinauto_click", "Foreground window mismatch")
        assert decision.next_strategy == "pywinauto_click"
        assert not decision.stop

    def test_stops_on_emergency_stop(self):
        strategies = ["pywinauto_click", "image_click"]
        decision = self.planner.next_strategy(strategies, "pywinauto_click", "Emergency stop was requested")
        assert decision.stop
        assert decision.next_strategy is None

    def test_stops_when_all_exhausted(self):
        strategies = ["image_click"]
        decision = self.planner.next_strategy(strategies, "image_click", "No control matched")
        assert decision.stop
        assert decision.next_strategy is None

    def test_stops_on_unknown_strategy(self):
        strategies = ["pywinauto_click"]
        decision = self.planner.next_strategy(strategies, "nonexistent_strategy", "anything")
        assert decision.stop


def test_controller_applicable_strategies_put_heal_and_vision_before_image():
    settings = Settings.default()
    settings.vision_llm_enabled = True
    controller = AgentController(settings)
    action = ActionRequest(
        name="click_console",
        action_type="click",
        metadata={
            "template_path": "console.png",
            "heal_hints": {"focus_surface": "console"},
        },
    )

    strategies = controller._applicable_strategies(action, _FakeProfile())  # type: ignore[attr-defined]

    assert strategies.index("ui_heal") < strategies.index("vision_llm_click") < strategies.index("image_click")
