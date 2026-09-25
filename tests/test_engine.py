import pytest

from app.config import Settings
from app.controller import AgentController
from app.errors import EmptySearchError, LLMProviderError, SimulatedTimeoutError
from app.execution.engine import ExecutionEngine
from app.execution.recovery import RecoveryManager
from app.models import GoalAnalysis, PlanStep, SearchResult
from app.research.context import ResearchContext
from app.research.process import build_search_queries
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import FailureSimulator, WebSearchTool
from app.trace import Trace
from tests.fakes import ScriptedLLM


def _results(count: int = 5) -> list[SearchResult]:
    return [
        SearchResult(
            title=f"Robotics update {index}",
            url=f"https://example.com/robots-{index}",
            snippet=f"A robotics note {index}",
            domain="example.com" if index < 4 else "news.example.org",
        )
        for index in range(1, count + 1)
    ]


class _FlakySearch:
    name = "web_search"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, payload: dict[str, object]) -> list[SearchResult]:
        self.calls += 1
        if self.calls == 1:
            raise SimulatedTimeoutError("simulated timeout")
        return _results()


def test_engine_recovers_and_records_retry(capsys, integration_page_evidence: None) -> None:
    registry = ToolRegistry()
    search = _FlakySearch()
    registry.register(search)
    registry.register(CalculatorTool())
    analysis = GoalAnalysis(
        topic="robotics",
        time_range="last week",
        recency="week",
        requested_items=3,
        output_type="summary",
    )
    context = ResearchContext(goal="Research robotics.", analysis=analysis)
    steps = [
        PlanStep(id=1, description="Search", tool="web_search", expected_output="results"),
        PlanStep(id=2, description="Normalize", tool="normalize", expected_output="unique"),
        PlanStep(id=3, description="Select", tool="select", expected_output="shortlist"),
        PlanStep(id=4, description="Calculate", tool="calculator", expected_output="statistic"),
        PlanStep(
            id=5,
            description="Synthesize",
            tool="synthesize",
            expected_output="report",
        ),
    ]

    def synthesize(ctx: ResearchContext) -> str:
        ctx.findings = []
        from app.models import Finding

        ctx.findings = [
            Finding(
                title="Robotics update",
                summary="A retrieved source discusses robotics.",
                why_it_matters="It was in the shortlist.",
                source_urls=[ctx.selected[0].url],
            )
        ]
        return "1 findings generated"

    records = ExecutionEngine(
        registry=registry,
        recovery=RecoveryManager(2),
        trace=Trace(),
        synthesize=synthesize,
    ).execute(context, steps)

    output = capsys.readouterr().out
    assert "[ERROR] SimulatedTimeoutError" in output
    assert "[RECOVERY] Attempting recovery..." in output
    assert "[RECOVERY] Retry 1/2" in output
    assert "[SUCCESS] 25 results retrieved from 5 queries" in output
    assert records[0].state == "recovered"
    assert records[0].retry_count == 1
    assert records[3].tool == "calculator"
    assert records[3].state == "success"
    assert context.calculation is not None
    assert search.calls == 6


def test_controller_prints_plan_before_search(capsys, integration_page_evidence: None) -> None:
    calls: list[str] = []

    def search(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
        calls.append(query)
        return [
            {
                "title": "Cloud computing update",
                "href": "https://example.com/cloud",
                "body": "A cloud computing note",
            }
        ]

    registry = ToolRegistry()
    registry.register(WebSearchTool(search_fn=search, simulator=FailureSimulator()))
    registry.register(CalculatorTool())
    settings = Settings(
        gemini_api_key=None,
        gemini_model="test",
        max_retries=2,
        llm_max_retries=1,
        search_max_results=5,
        search_backend="duckduckgo",
    )
    report = AgentController(
        settings=settings,
        llm=ScriptedLLM(topic="cloud computing", items=1),
        registry=registry,
        trace=Trace(),
    ).run("Research the latest developments in cloud computing.")

    output = capsys.readouterr().out
    assert output.index("[PLAN]") < output.index("[TOOL] web_search")
    assert "SimulatedTimeoutError" in output
    assert report.status == "success"
    assert report.failures_recovered == 1
    assert report.sources[0].url == "https://example.com/cloud"
    assert calls == build_search_queries(
        GoalAnalysis(
            topic="cloud computing",
            time_range="last week",
            recency="week",
            requested_items=1,
            output_type="summary",
        )
    )


def test_empty_search_is_not_successful_recovery(capsys) -> None:
    def search(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
        return []

    registry = ToolRegistry()
    registry.register(WebSearchTool(search_fn=search))
    registry.register(CalculatorTool())
    analysis = GoalAnalysis(
        topic="generative AI",
        time_range="last week",
        recency="week",
        requested_items=3,
        output_type="summary",
    )
    context = ResearchContext(goal="Research generative AI.", analysis=analysis)
    steps = [
        PlanStep(id=1, description="Search", tool="web_search", expected_output="results"),
        PlanStep(id=2, description="Synthesize", tool="synthesize", expected_output="report"),
    ]

    def synthesize(ctx: ResearchContext) -> str:
        raise AssertionError("synthesis must not run without sources")

    records = ExecutionEngine(
        registry=registry,
        recovery=RecoveryManager(2),
        trace=Trace(),
        synthesize=synthesize,
    ).execute(context, steps)
    output = capsys.readouterr().out
    assert records[0].state == "failed"
    assert records[0].recovery_status == "failed"
    assert isinstance(records[0].error, str) and "EmptySearchError" in records[0].error
    assert records[1].state == "skipped"
    assert context.findings == []
    assert "[SUCCESS] 0 results retrieved" not in output
    assert "EmptySearchError" in output
    with pytest.raises(EmptySearchError):
        WebSearchTool(search_fn=search).run({"query": "generative AI developments", "timelimit": "w"})


def test_synthesis_provider_failure_still_returns_a_report(capsys, integration_page_evidence: None) -> None:
    class FailingSynthesis(ScriptedLLM):
        def generate_structured(self, *, system: str, user: str, schema: type):
            if schema.__name__ == "SynthesisDraft":
                raise LLMProviderError("provider unavailable")
            return super().generate_structured(system=system, user=user, schema=schema)

    def search(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
        return [
            {
                "title": "Cloud computing update",
                "href": "https://example.com/cloud",
                "body": "A cloud computing note",
            }
        ]

    registry = ToolRegistry()
    registry.register(WebSearchTool(search_fn=search))
    registry.register(CalculatorTool())
    settings = Settings(
        gemini_api_key=None,
        gemini_model="test",
        max_retries=2,
        llm_max_retries=1,
        search_max_results=5,
        search_backend="duckduckgo",
    )
    report = AgentController(
        settings=settings,
        llm=FailingSynthesis(topic="cloud computing", items=1),
        registry=registry,
        trace=Trace(),
    ).run("Research recent cloud computing developments.")
    assert report.status == "failed"
    assert report.execution_summary[-1].state == "failed"
    assert "provider unavailable" in (report.execution_summary[-1].error or "")
    assert "Synthesis failed: LLMProviderError: provider unavailable" in capsys.readouterr().out
    assert report.findings == []
