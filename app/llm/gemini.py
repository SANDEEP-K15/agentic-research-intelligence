"""Gemini adapter using the google-genai SDK."""

from __future__ import annotations

import re
import time
from typing import TypeVar

from pydantic import BaseModel

from app.errors import LLMProviderError, StructuredOutputError
from app.llm.parsing import call_with_schema_retries

ModelT = TypeVar("ModelT", bound=BaseModel)


_RETRYABLE_PROVIDER = ("429", "resource_exhausted", "503", "unavailable")
_MAX_PROVIDER_DELAY_SECONDS = 40.0


def retryable_provider_delay(exc: BaseException) -> float | None:
    """Return a bounded wait for a transient Gemini quota or availability error."""
    text = str(exc).lower()
    if "requestsperday" in text or "perday" in text:
        return None
    if not any(token in text for token in _RETRYABLE_PROVIDER):
        return None
    match = re.search(r"retry in (\d+(?:\.\d+)?)", text)
    if match is None:
        return 5.0
    return min(float(match.group(1)) + 0.5, _MAX_PROVIDER_DELAY_SECONDS)


def _response_reason(response: object) -> str:
    """Short provider reason for an empty Gemini payload. Does not include the prompt."""
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None)
    if block_reason:
        return f"block_reason={block_reason}"
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        finish_reason = getattr(candidates[0], "finish_reason", None)
        if finish_reason:
            return f"finish_reason={finish_reason}"
    return "no text and no parsed payload"


class GeminiLLM:
    """Structured-output client. The SDK is imported only when this is constructed."""

    def __init__(self, *, api_key: str, model: str, max_retries: int = 2) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMProviderError(
                "google-genai is not installed. Install dependencies from requirements.txt."
            ) from exc
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._max_retries = max_retries

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[ModelT],
    ) -> ModelT:
        def invoke(prompt: str) -> object:
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=self._types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0,
                    ),
                )
            except Exception as exc:
                raise LLMProviderError(f"Gemini request failed: {exc}") from exc
            parsed = getattr(response, "parsed", None)
            if parsed is not None:
                return parsed
            text = getattr(response, "text", None)
            if not text:
                raise StructuredOutputError(
                    f"model returned an empty response ({_response_reason(response)})"
                )
            return text

        last_error: LLMProviderError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return call_with_schema_retries(
                    invoke,
                    user=user,
                    schema=schema,
                    max_retries=self._max_retries,
                )
            except LLMProviderError as exc:
                delay = retryable_provider_delay(exc)
                last_error = exc
                if delay is None or attempt >= self._max_retries:
                    raise
                time.sleep(delay)
        raise LLMProviderError("Gemini request failed") from last_error
