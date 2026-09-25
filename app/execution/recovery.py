"""Bounded retry for retryable tool failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.errors import RecoveryExhausted, SearchNetworkError, SimulatedToolError

T = TypeVar("T")


def is_retryable_tool_error(exc: BaseException) -> bool:
    """Retry simulated outages and network failures only."""
    return isinstance(exc, (SimulatedToolError, SearchNetworkError))


@dataclass(frozen=True)
class RecoveryResult(Generic[T]):
    value: T
    retry_count: int
    recovered: bool


class RecoveryManager:
    def __init__(self, max_retries: int) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be zero or greater")
        self.max_retries = max_retries

    def run(
        self,
        operation: Callable[[], T],
        *,
        retryable: Callable[[BaseException], bool] = is_retryable_tool_error,
        on_retry: Callable[[int, BaseException], None] | None = None,
    ) -> RecoveryResult[T]:
        """Run operation. Never retry more than max_retries times."""
        retries = 0
        while True:
            try:
                value = operation()
            except Exception as exc:
                if not retryable(exc) or retries >= self.max_retries:
                    raise RecoveryExhausted(exc, retries) from exc
                retries += 1
                if on_retry is not None:
                    on_retry(retries, exc)
                continue
            return RecoveryResult(value=value, retry_count=retries, recovered=retries > 0)
