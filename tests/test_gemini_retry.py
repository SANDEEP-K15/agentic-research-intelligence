from app.llm.gemini import GeminiLLM, retryable_provider_delay
from app.models import GoalAnalysis


def test_quota_error_has_a_bounded_delay() -> None:
    exc = RuntimeError(
        "429 RESOURCE_EXHAUSTED. Please retry in 26.35s. Quota exceeded for gemini-2.5-flash"
    )
    assert retryable_provider_delay(exc) == 26.85
    assert retryable_provider_delay(RuntimeError("400 INVALID_ARGUMENT")) is None
    daily = RuntimeError(
        "429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier quotaValue 20"
    )
    assert retryable_provider_delay(daily) is None
    assert retryable_provider_delay(RuntimeError("retry in 120s 429")) == 40.0


def test_gemini_retries_resource_exhausted_then_returns_schema(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.gemini.time.sleep", lambda _seconds: None)
    llm = GeminiLLM(api_key="test-key", model="gemini-2.5-flash", max_retries=2)
    calls = {"count": 0}

    class Response:
        def __init__(self, parsed: object) -> None:
            self.parsed = parsed
            self.text = None

    def generate_content(**kwargs: object) -> Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 1s")
        return Response(
            GoalAnalysis(
                topic="generative AI",
                time_range="last week",
                recency="week",
                requested_items=3,
                output_type="summary",
            )
        )

    llm._client.models.generate_content = generate_content  # type: ignore[method-assign]
    result = llm.generate_structured(system="Extract the request.", user="goal", schema=GoalAnalysis)
    assert calls["count"] == 2
    assert result.topic == "generative AI"
