import pytest

from app.errors import CalculatorError, ToolInputError
from app.tools.calculator import CalculatorTool, evaluate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 2", 4),
        ("(3 + 4) * 2", 14),
        ("-5 + 2", -3),
        ("10 / 4", 2.5),
        ("7 // 2", 3),
        ("10 % 3", 1),
        ("2 ** 8", 256),
        ("1.5 * 2", 3),
        ("+4", 4),
    ],
)
def test_evaluate_arithmetic(expression: str, expected: float) -> None:
    assert evaluate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "__import__('os')",
        "a + 1",
        "eval('1')",
        "(1 + 2",
        "1; 2",
        "[1, 2]",
        "1 and 2",
        "2 ** 100",
        "9 ** 99",
        "'ab' + 'c'",
        "1 / 0",
        "1 % 0",
    ],
)
def test_evaluate_rejects_unsafe_or_invalid(expression: str) -> None:
    with pytest.raises(CalculatorError):
        evaluate(expression)


def test_expression_length_limit() -> None:
    with pytest.raises(CalculatorError):
        evaluate("1+" * 200 + "1")


def test_calculator_tool_payload() -> None:
    assert CalculatorTool().run({"expression": "6 * 7"}) == 42
    with pytest.raises(ToolInputError):
        CalculatorTool().run({"expression": 1})
