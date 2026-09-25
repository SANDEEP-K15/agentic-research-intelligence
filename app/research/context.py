"""Mutable research state owned by the execution engine, not the model."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Calculation, Finding, GoalAnalysis, SearchResult


@dataclass
class ResearchContext:
    goal: str
    analysis: GoalAnalysis
    plan_note: str | None = None
    search_results: list[SearchResult] = field(default_factory=list)
    normalized: list[SearchResult] = field(default_factory=list)
    selected: list[SearchResult] = field(default_factory=list)
    calculation: Calculation | None = None
    findings: list[Finding] = field(default_factory=list)
    synthesis_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
