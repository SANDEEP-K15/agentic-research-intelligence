"""Assemble and render the structured research result."""

from __future__ import annotations

import json
from pathlib import Path

from app.models import RECENCY_TIMELIMIT, PlanStep, ResearchReport, StepSummary
from app.research.context import ResearchContext
from app.research.process import sources_for

_BASE_LIMITATIONS = [
    "Search coverage is limited to the public results returned for a few focused queries.",
    "Candidate selection scores topic overlap, extracted publication dates, event wording in page evidence, and source quality. It is a heuristic, not an objective ranking.",
    "The calculator output is the percentage of normalized results that come from distinct domains. It does not measure importance.",
]


def build_report(
    context: ResearchContext,
    records: list[StepSummary],
    plan: list[PlanStep],
) -> ResearchReport:
    tools_used: list[str] = []
    for record in records:
        if record.tool in {"web_search", "calculator"} and record.state in {"success", "recovered"}:
            if record.tool not in tools_used:
                tools_used.append(record.tool)

    limitations = list(_BASE_LIMITATIONS)
    if RECENCY_TIMELIMIT[context.analysis.recency] is None:
        limitations.append("The request did not set a time window, so search results were not filtered by recency.")
    else:
        limitations.append(
            f"Recency was requested as {context.analysis.time_range} and passed to search as a time filter."
        )
    if context.plan_note:
        limitations.append(context.plan_note)
    limitations.extend(context.warnings)
    limitations.extend(context.synthesis_notes)

    failed = any(record.state == "failed" for record in records)
    if not context.findings or any(
        record.state == "failed" and record.tool in {"web_search", "synthesize"} for record in records
    ):
        status = "failed"
    elif failed or len(context.findings) < context.analysis.requested_items:
        status = "partial"
    else:
        status = "success"

    if not context.findings and not any("no search results" in note.lower() for note in limitations):
        limitations.append("The run did not produce findings grounded in retrieved sources.")

    return ResearchReport(
        goal=context.goal,
        plan=plan,
        execution_summary=records,
        tools_used=tools_used,
        retry_count=sum(record.retry_count for record in records),
        failures_recovered=sum(1 for record in records if record.recovery_status == "recovered"),
        findings=context.findings,
        sources=sources_for(context.findings, context.selected),
        limitations=limitations,
        status=status,
    )


def write_report(report: ResearchReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
