from __future__ import annotations

import pytest

from app.profiles.calculator_profile import CalculatorProfile


class TestSafeEval:
    def setup_method(self):
        self.profile = CalculatorProfile()

    def test_simple_addition(self):
        assert self.profile._safe_eval("2+3") == 5

    def test_multiplication(self):
        assert self.profile._safe_eval("125*4") == 500

    def test_subtraction(self):
        assert self.profile._safe_eval("10-3") == 7

    def test_division_returns_float(self):
        result = self.profile._safe_eval("7/2")
        assert result == 3.5

    def test_whole_number_division_returns_int(self):
        result = self.profile._safe_eval("10/2")
        assert result == 5
        assert isinstance(result, int)

    def test_parentheses(self):
        assert self.profile._safe_eval("(2+3)*4") == 20

    def test_unary_negative(self):
        result = self.profile._safe_eval("0-5")
        assert result == -5

    def test_rejects_non_arithmetic(self):
        with pytest.raises(ValueError):
            self.profile._safe_eval("__import__('os')")

    def test_rejects_invalid_syntax(self):
        with pytest.raises(ValueError):
            self.profile._safe_eval("2 + + +")  # trailing operator — SyntaxError


class TestCalculatorProfileBuildPlan:
    def setup_method(self):
        self.profile = CalculatorProfile()

    def test_simple_expression(self, tmp_path):
        plan = self.profile.build_plan("compute 2+3", tmp_path)
        assert any(a.name == "press_equals" for a in plan)

    def test_unsupported_task_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported calculator task"):
            self.profile.build_plan("do something else", tmp_path)

    def test_expected_result_in_metadata(self, tmp_path):
        plan = self.profile.build_plan("compute 125*4", tmp_path)
        equals_action = next(a for a in plan if a.name == "press_equals")
        assert equals_action.metadata.get("expected_result") == "500"
