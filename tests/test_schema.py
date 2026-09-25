import json

import pytest
from pydantic import ValidationError

from app.llm.parsing import call_with_schema_retries, parse_structured
from app.models import Finding, GoalAnalysis, ResearchReport, Source


def test_parse_dict_and_json() -> None:
    payload = {
        "topic": "autonomous vehicles",
        "time_range": "last week",
        "recency": "week",
        "requested_items": 3,
        "output_type": "summary",
    }
    assert parse_structured(payload, GoalAnalysis).topic == "autonomous vehicles"
    assert parse_structured(json.dumps(payload), GoalAnalysis).requested_items == 3


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(ValidationError):
        parse_structured("not json", GoalAnalysis)


def test_schema_retry_then_success() -> None:
    calls: list[str] = []

    def invoke(prompt: str) -> object:
        calls.append(prompt)
        if len(calls) == 1:
            return "nope"
        return {
            "topic": "AI agents",
            "time_range": "recent",
            "recency": "unspecified",
            "requested_items": 3,
            "output_type": "brief",
        }

    parsed = call_with_schema_retries(invoke, user="goal", schema=GoalAnalysis, max_retries=2)
    assert parsed.topic == "AI agents"
    assert len(calls) == 2
    assert "invalid" in calls[1]


def test_schema_retry_is_bounded() -> None:
    def invoke(prompt: str) -> object:
        return "still bad"

    with pytest.raises(Exception):
        call_with_schema_retries(invoke, user="goal", schema=GoalAnalysis, max_retries=2)


def test_report_schema_round_trip() -> None:
    report = ResearchReport(
        goal="Research recent robotics developments.",
        plan=[],
        execution_summary=[],
        tools_used=["web_search", "calculator"],
        retry_count=1,
        failures_recovered=1,
        findings=[
            Finding(
                title="Robotics development 1",
                summary="A retrieved source discusses robotics.",
                why_it_matters="The source is part of the retrieved set.",
                source_urls=["https://example.com/robots"],
            )
        ],
        sources=[
            Source(
                title="Robots",
                url="https://example.com/robots",
                domain="example.com",
            )
        ],
        limitations=["Coverage is limited to returned results."],
        status="success",
    )
    restored = ResearchReport.model_validate(json.loads(report.model_dump_json()))
    assert restored == report


def test_report_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        ResearchReport.model_validate(
            {
                "goal": "x",
                "plan": [],
                "execution_summary": [],
                "tools_used": [],
                "retry_count": 0,
                "failures_recovered": 0,
                "findings": [],
                "sources": [],
                "limitations": [],
                "status": "unknown",
            }
        )
