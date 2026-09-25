"""Agent controller. The model proposes structure; this module owns execution."""

from __future__ import annotations

from app.analysis.goal import GoalAnalyzer
from app.config import Settings
from app.execution.engine import ExecutionEngine
from app.execution.recovery import RecoveryManager
from app.llm.protocol import LLMClient
from app.models import ResearchReport
from app.planning.planner import Planner
from app.report.builder import build_report
from app.research.context import ResearchContext
from app.research.synthesize import Synthesizer
from app.tools.registry import ToolRegistry
from app.trace import Trace


class AgentController:
    def __init__(
        self,
        *,
        settings: Settings,
        llm: LLMClient,
        registry: ToolRegistry,
        trace: Trace,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._registry = registry
        self._trace = trace

    def run(self, goal: str) -> ResearchReport:
        analysis = GoalAnalyzer(self._llm).analyze(goal)
        self._trace.goal(analysis)
        plan, plan_note = Planner(self._llm).create(goal, analysis)
        self._trace.plan(plan)
        if plan_note and self._trace.verbose:
            self._trace.emit(f"[PLAN] {plan_note}")
            self._trace.emit("")

        context = ResearchContext(goal=goal.strip(), analysis=analysis, plan_note=plan_note)
        engine = ExecutionEngine(
            registry=self._registry,
            recovery=RecoveryManager(self._settings.max_retries),
            trace=self._trace,
            synthesize=Synthesizer(self._llm),
        )
        records = engine.execute(context, plan.steps)
        report = build_report(context, records, plan.steps)
        self._trace.report(report)
        return report
