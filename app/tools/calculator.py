"""Safe arithmetic evaluator. It does not call eval or execute Python."""

from __future__ import annotations

import ast

from app.errors import CalculatorError, ToolInputError

_MAX_EXPRESSION_LENGTH = 200
_MAX_NODES = 40
_MAX_ABS_VALUE = 1_000_000_000_000
_MAX_EXPONENT = 12
_BINARY_OPS: tuple[type[ast.operator], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)


def _check_magnitude(value: float) -> float:
    if abs(value) > _MAX_ABS_VALUE:
        raise CalculatorError("result is too large")
    return value


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CalculatorError("only numeric constants are allowed")
        return _check_magnitude(float(value))

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _eval_node(node.operand)
        return _check_magnitude(inner if isinstance(node.op, ast.UAdd) else -inner)

    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINARY_OPS):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _check_magnitude(_apply(node.op, left, right))

    raise CalculatorError("expression contains unsupported syntax")


def _apply(op: ast.operator, left: float, right: float) -> float:
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        if right == 0:
            raise CalculatorError("division by zero")
        return left / right
    if isinstance(op, ast.FloorDiv):
        if right == 0:
            raise CalculatorError("division by zero")
        return float(left // right)
    if isinstance(op, ast.Mod):
        if right == 0:
            raise CalculatorError("division by zero")
        return float(left % right)
    if isinstance(op, ast.Pow):
        if not float(right).is_integer() or right < 0 or right > _MAX_EXPONENT:
            raise CalculatorError("exponent must be an integer from 0 to 12")
        return float(left**int(right))
    raise CalculatorError("unsupported operator")


def evaluate(expression: str) -> float:
    """Evaluate a numeric expression containing only arithmetic."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalculatorError("expression is empty")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise CalculatorError("expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError("expression syntax is invalid") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise CalculatorError("expression is too complex")
    return _eval_node(tree.body)


class CalculatorTool:
    name = "calculator"

    def run(self, payload: dict[str, object]) -> float:
        expression = payload.get("expression")
        if not isinstance(expression, str):
            raise ToolInputError("expression must be a string")
        return evaluate(expression)
