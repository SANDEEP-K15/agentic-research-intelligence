"""Terminal trace. This prints execution events, not private reasoning."""

from __future__ import annotations

import sys
from typing import TextIO

from app.models import GoalAnalysis, Plan, ResearchReport


class Trace:
    def __init__(self, stream: TextIO | None = None, *, verbose: bool = False) -> None:
        self.stream = stream or sys.stdout
        self.verbose = verbose

    def emit(self, line: str = "") -> None:
        print(line, file=self.stream)

    def goal(self, analysis: GoalAnalysis) -> None:
        self.emit("[GOAL]")
        self.emit(f"Topic: {analysis.topic}")
        self.emit(f"Time range: {analysis.time_range}")
        self.emit(f"Requested items: {analysis.requested_items}")
        self.emit(f"Output: {analysis.output_type}")
        self.emit("")

    def plan(self, plan: Plan) -> None:
        self.emit("[PLAN]")
        self.emit("")
        for step in plan.steps:
            self.emit(f"{step.id}. {step.description}")
        self.emit("")

    def report(self, report: ResearchReport) -> None:
        self.emit("[REPORT]")
        self.emit(f"Status: {report.status}")
        self.emit(f"Goal: {report.goal}")
        self.emit("")
        self.emit("Findings:")
        if not report.findings:
            self.emit("  None.")
        for index, finding in enumerate(report.findings, start=1):
            self.emit(f"{index}. {finding.title}")
            self.emit(f"   {finding.summary}")
            self.emit(f"   Why it matters: {finding.why_it_matters}")
            self.emit("   Sources: " + ", ".join(finding.source_urls))
        self.emit("")
        self.emit("Sources:")
        if not report.sources:
            self.emit("  None.")
        for source in report.sources:
            self.emit(f"- {source.title} ({source.domain})")
            self.emit(f"  {source.url}")
        self.emit("")
        self.emit(f"Tools used: {', '.join(report.tools_used) if report.tools_used else 'none'}")
        self.emit(f"Retries: {report.retry_count}")
        self.emit(f"Failures recovered: {report.failures_recovered}")
        self.emit("Limitations:")
        for note in report.limitations:
            self.emit(f"- {note}")
        self.emit("")
