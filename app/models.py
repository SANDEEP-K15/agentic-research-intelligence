"""Pydantic schemas shared across the agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Recency = Literal["day", "week", "month", "year", "unspecified"]
OutputType = Literal["summary", "brief", "report"]
ToolName = Literal["web_search", "calculator", "normalize", "select", "synthesize"]
StepState = Literal["pending", "running", "success", "failed", "recovered", "skipped"]
RecoveryStatus = Literal["none", "recovered", "failed"]
RunStatus = Literal["success", "partial", "failed"]

REQUIRED_TOOLS: tuple[ToolName, ...] = (
    "web_search",
    "normalize",
    "select",
    "calculator",
    "synthesize",
)

RECENCY_TIMELIMIT: dict[str, str | None] = {
    "day": "d",
    "week": "w",
    "month": "m",
    "year": "y",
    "unspecified": None,
}


class GoalAnalysis(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    time_range: str = Field(min_length=2, max_length=80)
    recency: Recency
    requested_items: int = Field(ge=1, le=10)
    output_type: OutputType


class PlanStep(BaseModel):
    id: int = Field(ge=1)
    description: str = Field(min_length=3, max_length=240)
    tool: ToolName
    expected_output: str = Field(min_length=3, max_length=240)


class PlanDraft(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    domain: str
    page_title: str | None = None
    publication_date: str | None = None
    page_excerpt: str | None = None


class Calculation(BaseModel):
    expression: str
    value: float
    summary: str


class FindingDraft(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=3, max_length=800)
    why_it_matters: str = Field(min_length=3, max_length=500)
    source_urls: list[str] = Field(min_length=1, max_length=5)


class SynthesisDraft(BaseModel):
    findings: list[FindingDraft] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class Finding(BaseModel):
    title: str
    summary: str
    why_it_matters: str
    source_urls: list[str]


class Source(BaseModel):
    title: str
    url: str
    domain: str


class StepSummary(BaseModel):
    id: int
    description: str
    tool: str
    state: StepState
    started_at: str
    ended_at: str
    result_summary: str
    error: str | None = None
    retry_count: int = 0
    recovery_status: RecoveryStatus = "none"


class ResearchReport(BaseModel):
    goal: str
    plan: list[PlanStep]
    execution_summary: list[StepSummary]
    tools_used: list[str]
    retry_count: int
    failures_recovered: int
    findings: list[Finding]
    sources: list[Source]
    limitations: list[str]
    status: RunStatus
