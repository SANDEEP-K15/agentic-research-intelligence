"""Sequential plan execution. Tool calls go through the registry and recovery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

from app.errors import EmptySearchError, PipelineError, RecoveryExhausted, ToolNotFoundError
from app.execution.recovery import RecoveryManager, is_retryable_tool_error
from app.models import (
    RECENCY_TIMELIMIT,
    Calculation,
    PlanStep,
    RecoveryStatus,
    StepState,
    StepSummary,
)
from app.research.context import ResearchContext
from app.research.process import (
    build_search_queries,
    diversity_expression,
    prepare_candidates,
    select_candidates,
)
from app.tools.registry import ToolRegistry
from app.trace import Trace

StageHandler = Callable[[ResearchContext], str]
_CRITICAL = {"web_search", "normalize", "select", "synthesize"}
_REGISTRY_TOOLS = {"web_search", "calculator"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _public_error(tool_name: str, exc: Exception) -> str:
    """Keep the original failure visible. Truncate so traces stay readable."""
    origin = exc.__cause__ or exc
    detail = f"{type(origin).__name__}: {origin}"
    if len(detail) > 500:
        detail = detail[:500] + "..."
    if tool_name == "synthesize":
        return f"Synthesis failed: {detail}"
    return detail


class ExecutionEngine:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        recovery: RecoveryManager,
        trace: Trace,
        synthesize: StageHandler,
    ) -> None:
        self._registry = registry
        self._recovery = recovery
        self._trace = trace
        self._synthesize = synthesize

    def execute(self, context: ResearchContext, steps: list[PlanStep]) -> list[StepSummary]:
        records: list[StepSummary] = []
        aborted = False
        total = len(steps)
        for position, step in enumerate(steps, start=1):
            self._trace.emit(f"[STEP {position}/{total}]")
            started = _now()
            if aborted:
                records.append(self._record(step, "skipped", started, "Skipped because an earlier step failed"))
                label = "TOOL" if step.tool in _REGISTRY_TOOLS else "STAGE"
                self._trace.emit(f"[{label}] {step.tool}")
                self._trace.emit("[SKIPPED] earlier step failed")
                self._trace.emit("")
                continue
            try:
                if step.tool in _REGISTRY_TOOLS:
                    summary, retries, recovered = self._run_tool(step.tool, context)
                else:
                    self._trace.emit(f"[STAGE] {step.tool}")
                    summary = self._run_stage(step.tool, context)
                    retries, recovered = 0, False
            except RecoveryExhausted as exc:
                original = exc.original
                summary = ""
                records.append(
                    self._record(
                        step,
                        "failed",
                        started,
                        summary,
                        error=f"{type(original).__name__}: {original}",
                        retry_count=exc.retry_count,
                        recovery_status="failed",
                    )
                )
                self._trace.emit(f"[ERROR] {type(original).__name__}: {original}")
                self._trace.emit("")
                if step.tool in _CRITICAL:
                    aborted = True
                continue
            except (PipelineError, ToolNotFoundError) as exc:
                message = _public_error(step.tool, exc)
                records.append(
                    self._record(
                        step,
                        "failed",
                        started,
                        "",
                        error=message,
                        recovery_status="failed",
                    )
                )
                self._trace.emit(f"[ERROR] {message}")
                self._trace.emit("")
                if step.tool in _CRITICAL:
                    aborted = True
                continue

            state = "recovered" if recovered else "success"
            records.append(
                self._record(
                    step,
                    state,
                    started,
                    summary,
                    retry_count=retries,
                    recovery_status="recovered" if recovered else "none",
                )
            )
            self._trace.emit(f"[SUCCESS] {summary}")
            self._trace.emit("")
        return records

    def _run_tool(self, tool_name: str, context: ResearchContext) -> tuple[str, int, bool]:
        if tool_name == "web_search":
            return self._search_queries(context)
        tool = self._registry.get(tool_name)
        payload = self._payload(tool_name, context)

        def operation() -> str:
            self._trace.emit(f"[TOOL] {tool_name}")
            result = tool.run(payload)
            return self._store(tool_name, context, result, payload)

        outcome = self._recovery.run(
            operation,
            retryable=is_retryable_tool_error,
            on_retry=self._on_retry,
        )
        return outcome.value, outcome.retry_count, outcome.recovered

    def _search_queries(self, context: ResearchContext) -> tuple[str, int, bool]:
        """Run focused searches (up to five for time-bounded goals) through the tool registry."""
        tool = self._registry.get("web_search")
        timelimit = RECENCY_TIMELIMIT[context.analysis.recency]
        queries = build_search_queries(context.analysis)
        collected: list[object] = []
        retry_count = 0
        recovered = False
        failures: list[RecoveryExhausted] = []

        for query in queries:
            payload = {"query": query, "timelimit": timelimit}

            def operation(current: dict[str, object] = payload) -> list[object]:
                self._trace.emit("[TOOL] web_search")
                if self._trace.verbose:
                    self._trace.emit(f"  query: {current['query']}")
                result = tool.run(current)
                return result if isinstance(result, list) else []

            try:
                outcome = self._recovery.run(
                    operation,
                    retryable=is_retryable_tool_error,
                    on_retry=self._on_retry,
                )
            except RecoveryExhausted as exc:
                failures.append(exc)
                continue
            retry_count += outcome.retry_count
            recovered = recovered or outcome.recovered
            collected.extend(outcome.value)

        if not collected:
            if failures:
                raise failures[-1]
            raise EmptySearchError("search provider returned no usable results")
        context.search_results = collected
        if self._trace.verbose:
            for item in collected[:5]:
                title = getattr(item, "title", "")
                if title:
                    self._trace.emit(f"  - {title}")
        return (
            f"{len(collected)} results retrieved from {len(queries)} queries",
            retry_count,
            recovered,
        )

    def _on_retry(self, attempt: int, exc: BaseException) -> None:
        self._trace.emit(f"[ERROR] {type(exc).__name__}")
        self._trace.emit("[RECOVERY] Attempting recovery...")
        self._trace.emit(f"[RECOVERY] Retry {attempt}/{self._recovery.max_retries}")

    def _payload(self, tool_name: str, context: ResearchContext) -> dict[str, object]:
        unique_domains = len({result.domain for result in context.normalized})
        return {
            "expression": diversity_expression(len(context.normalized), unique_domains),
        }

    def _store(
        self,
        tool_name: str,
        context: ResearchContext,
        result: object,
        payload: dict[str, object],
    ) -> str:
        value = float(result) if isinstance(result, (int, float)) else 0.0
        expression = str(payload.get("expression"))
        context.calculation = Calculation(
            expression=expression,
            value=value,
            summary=(
                "Share of normalized results whose domains are distinct, "
                "as a percentage of the retrieved set. This is not a quality score."
            ),
        )
        rendered = str(int(value)) if float(value).is_integer() else f"{value:.2f}"
        return f"source diversity {rendered} from `{expression}`"

    def _run_stage(self, tool_name: str, context: ResearchContext) -> str:
        if tool_name == "normalize":
            context.normalized = prepare_candidates(context.search_results, context.analysis)
            return f"{len(context.normalized)} unique results with page evidence"
        if tool_name == "select":
            context.selected = select_candidates(context.normalized, context.analysis)
            if not context.selected:
                raise PipelineError(
                    "insufficient evidence: retrieved pages did not describe a concrete recent development"
                )
            if len(context.selected) < context.analysis.requested_items:
                context.warnings.append(
                    f"Only {len(context.selected)} of {context.analysis.requested_items} "
                    "requested developments had sufficient recent evidence in retrieved sources."
                )
            return (
                f"{len(context.selected)} candidates selected "
                "by topic, recency, event, and source signals"
            )
        if tool_name == "synthesize":
            return self._synthesize(context)
        raise ToolNotFoundError(f"unknown stage: {tool_name}")

    def _record(
        self,
        step,
        state: str,
        started: str,
        summary: str,
        *,
        error: str | None = None,
        retry_count: int = 0,
        recovery_status: str = "none",
    ) -> StepSummary:
        return StepSummary(
            id=step.id,
            description=step.description,
            tool=step.tool,
            state=cast(StepState, state),
            started_at=started,
            ended_at=_now(),
            result_summary=summary,
            error=error,
            retry_count=retry_count,
            recovery_status=cast(RecoveryStatus, recovery_status),
        )
