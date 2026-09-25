"""Small LLM interface so the agent does not depend on a vendor SDK."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMClient(Protocol):
    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[ModelT],
    ) -> ModelT:
        """Return a validated model instance."""
