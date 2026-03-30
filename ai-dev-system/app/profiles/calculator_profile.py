from __future__ import annotations

import ast
import operator
import re
from pathlib import Path

from app.agent.state import ActionRequest, SelectorSpec, VerificationCheck
from app.profiles.base_profile import BaseProfile
from app.profiles.registry import ProfileRegistry


@ProfileRegistry.register("calculator")
class CalculatorProfile(BaseProfile):
    """Profile for the Windows Calculator app."""

    _BUTTONS = {
        "0": "num0Button",
        "1": "num1Button",
        "2": "num2Button",
        "3": "num3Button",
        "4": "num4Button",
        "5": "num5Button",
        "6": "num6Button",
        "7": "num7Button",
        "8": "num8Button",
        "9": "num9Button",
        "+": "plusButton",
        "-": "minusButton",
        "*": "multiplyButton",
        "/": "divideButton",
        ".": "decimalSeparatorButton",
        "(": "openParenthesisButton",
        ")": "closeParenthesisButton",
    }

    def __init__(self) -> None:
        super().__init__(
            name="calculator",
            executable="calc.exe",
            window_selector=SelectorSpec(title="Calculator", class_name="ApplicationFrameWindow", backend="uia"),
            launch_delay_seconds=5.0,
            region_hints={"results": (0.5, 0.12, 0.96, 0.28)},
        )

    def build_plan(self, task: str, working_directory: Path) -> list[ActionRequest]:
        del working_directory
        match = re.search(r"compute\s+(?P<expression>[0-9+\-*/.() ]+)", task, re.IGNORECASE)
        if match is None:
            raise ValueError("Unsupported calculator task. Use a task like 'compute 125*4'.")

        expression = match.group("expression").replace(" ", "")
        if not expression or any(char not in self._BUTTONS for char in expression):
            raise ValueError(f"Unsupported calculator expression: {expression!r}")

        steps: list[ActionRequest] = [
            ActionRequest(
                name="clear_calculator",
                action_type="click",
                target=SelectorSpec(automation_id="clearButton", control_type="Button", backend="uia"),
                allowed_strategies=["pywinauto_click", "pywinauto_invoke", "image_click", "coordinate_click"],
                postconditions=[
                    VerificationCheck(
                        kind="control_text_contains",
                        selector=SelectorSpec(automation_id="CalculatorResults", control_type="Text", backend="uia"),
                        expected="Display is 0",
                        timeout_seconds=3.0,
                    ),
                ],
            )
        ]

        running_digits = ""
        for index, token in enumerate(expression):
            automation_id = self._BUTTONS[token]
            selector = SelectorSpec(automation_id=automation_id, control_type="Button", backend="uia")
            if token.isdigit():
                running_digits = f"{running_digits}{token}" if running_digits.isdigit() else token
                check = VerificationCheck(
                    kind="control_text_contains",
                    selector=SelectorSpec(automation_id="CalculatorResults", control_type="Text", backend="uia"),
                    expected=f"Display is {running_digits}",
                    timeout_seconds=3.0,
                )
            else:
                display_expression = expression[: index + 1].replace("*", "×").replace("/", "÷")
                running_digits = ""
                check = VerificationCheck(
                    kind="control_text_contains",
                    selector=SelectorSpec(automation_id="CalculatorExpression", control_type="Text", backend="uia"),
                    expected=display_expression[:-1],
                    timeout_seconds=3.0,
                )
            steps.append(
                ActionRequest(
                    name=f"press_{index}_{token}",
                    action_type="click",
                    target=selector,
                    allowed_strategies=["pywinauto_click", "pywinauto_invoke", "image_click", "coordinate_click"],
                    postconditions=[check],
                )
            )

        expected_result = str(self._safe_eval(expression))
        steps.append(
            ActionRequest(
                name="press_equals",
                action_type="click",
                target=SelectorSpec(automation_id="equalButton", control_type="Button", backend="uia"),
                allowed_strategies=["pywinauto_click", "pywinauto_invoke", "image_click", "coordinate_click"],
                postconditions=[
                    VerificationCheck(
                        kind="control_text_contains",
                        selector=SelectorSpec(automation_id="CalculatorResults", control_type="Text", backend="uia"),
                        expected=f"Display is {expected_result}",
                        timeout_seconds=4.0,
                    ),
                ],
                metadata={"expected_result": expected_result},
            )
        )
        return steps

    @staticmethod
    def _safe_eval(expression: str) -> int | float:
        """Evaluate a basic arithmetic expression without using eval().

        Supports: integers, floats, +, -, *, /, parentheses.
        Raises ValueError for any unsupported construct.
        """
        _ALLOWED_OPS = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        def _eval_node(node: ast.AST) -> int | float:
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp):
                op_type = type(node.op)
                if op_type not in _ALLOWED_OPS:
                    raise ValueError(f"Unsupported operator: {op_type.__name__}")
                return _ALLOWED_OPS[op_type](_eval_node(node.left), _eval_node(node.right))
            if isinstance(node, ast.UnaryOp):
                op_type = type(node.op)
                if op_type not in _ALLOWED_OPS:
                    raise ValueError(f"Unsupported operator: {op_type.__name__}")
                return _ALLOWED_OPS[op_type](_eval_node(node.operand))
            raise ValueError(f"Unsupported expression node: {type(node).__name__}")

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid expression: {expression!r}") from exc
        result = _eval_node(tree.body)
        # Return int if the result is a whole number
        if isinstance(result, float) and result.is_integer():
            return int(result)
        return result
