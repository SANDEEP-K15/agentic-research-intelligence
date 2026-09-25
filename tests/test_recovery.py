import pytest

from app.errors import CalculatorError, RecoveryExhausted, SearchNetworkError, SimulatedTimeoutError
from app.execution.recovery import RecoveryManager, is_retryable_tool_error


def test_retries_then_succeeds() -> None:
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            raise SimulatedTimeoutError("down")
        return "ok"

    seen: list[int] = []
    result = RecoveryManager(max_retries=2).run(
        operation,
        on_retry=lambda attempt, exc: seen.append(attempt),
    )
    assert result.value == "ok"
    assert result.retry_count == 1
    assert result.recovered is True
    assert seen == [1]
    assert calls["count"] == 2


def test_stops_at_max_retries_and_preserves_error() -> None:
    def operation() -> str:
        raise SearchNetworkError("timeout")

    with pytest.raises(RecoveryExhausted) as caught:
        RecoveryManager(max_retries=2).run(operation)
    assert isinstance(caught.value.original, SearchNetworkError)
    assert caught.value.retry_count == 2
    assert "timeout" in str(caught.value.original)


def test_does_not_retry_calculator_errors() -> None:
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        raise CalculatorError("bad expression")

    with pytest.raises(RecoveryExhausted) as caught:
        RecoveryManager(max_retries=2).run(operation)
    assert calls["count"] == 1
    assert caught.value.retry_count == 0
    assert isinstance(caught.value.original, CalculatorError)


def test_retryable_classification() -> None:
    assert is_retryable_tool_error(SimulatedTimeoutError("x"))
    assert is_retryable_tool_error(SearchNetworkError("x"))
    assert not is_retryable_tool_error(CalculatorError("x"))
    assert not is_retryable_tool_error(ValueError("x"))


def test_negative_budget_rejected() -> None:
    with pytest.raises(ValueError):
        RecoveryManager(max_retries=-1)
