"""Validate structured model output and retry malformed responses."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.errors import StructuredOutputError

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_structured(payload: object, schema: type[ModelT]) -> ModelT:
    """Accept a model, dict, or JSON string. Reject anything else."""
    if isinstance(payload, schema):
        return payload
    if isinstance(payload, BaseModel):
        return schema.model_validate(payload.model_dump())
    if isinstance(payload, dict):
        return schema.model_validate(payload)
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise StructuredOutputError("model returned an empty response")
        try:
            return schema.model_validate_json(text)
        except (ValidationError, json.JSONDecodeError):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end <= start:
                raise
            return schema.model_validate_json(text[start : end + 1])
    raise StructuredOutputError(f"unsupported model payload: {type(payload).__name__}")


def call_with_schema_retries(
    invoke: Callable[[str], object],
    *,
    user: str,
    schema: type[ModelT],
    max_retries: int,
) -> ModelT:
    """Call the provider and retry only when the payload fails validation."""
    prompt = user
    last_error: Exception | None = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            return parse_structured(invoke(prompt), schema)
        except (ValidationError, StructuredOutputError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            prompt = (
                f"{user}\n\nThe previous response was invalid: {exc}. "
                "Return only JSON that matches the schema."
            )
    raise StructuredOutputError(
        f"model output did not match {schema.__name__} after {attempts} attempts"
    ) from last_error
