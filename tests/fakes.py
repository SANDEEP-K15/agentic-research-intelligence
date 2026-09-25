"""Shared test doubles. No network and no Gemini calls."""

from __future__ import annotations

import re

from app.models import (
    FindingDraft,
    GoalAnalysis,
    PlanDraft,
    PlanStep,
    SynthesisDraft,
)


def sample_plan(topic: str = "robotics") -> PlanDraft:
    steps = [
        PlanStep(
            id=1,
            description=f"Search for recent developments in {topic}",
            tool="web_search",
            expected_output="Search results with titles, URLs, and snippets",
        ),
        PlanStep(
            id=2,
            description="Normalize and filter search results",
            tool="normalize",
            expected_output="Deduplicated search results",
        ),
        PlanStep(
            id=3,
            description=f"Identify relevant developments in {topic}",
            tool="select",
            expected_output="A shortlist of candidate developments",
        ),
        PlanStep(
            id=4,
            description="Compute a descriptive source-diversity statistic for the retrieved set",
            tool="calculator",
            expected_output="A numeric source-diversity statistic",
        ),
        PlanStep(
            id=5,
            description="Generate the final summary from cited sources",
            tool="synthesize",
            expected_output="A sourced research report",
        ),
    ]
    return PlanDraft(steps=steps)


class ScriptedLLM:
    def __init__(self, *, topic: str = "robotics", recency: str = "week", items: int = 3) -> None:
        self.topic = topic
        self.recency = recency
        self.items = items
        self.goals: list[str] = []

    def generate_structured(self, *, system: str, user: str, schema: type):
        self.goals.append(user)
        if schema is GoalAnalysis:
            return GoalAnalysis(
                topic=self.topic,
                time_range="last week" if self.recency == "week" else "unspecified",
                recency=self.recency,
                requested_items=self.items,
                output_type="summary",
            )
        if schema is PlanDraft:
            return sample_plan(self.topic)
        if schema is SynthesisDraft:
            urls = re.findall(r"https://[^\s\"\\]+", user)
            findings = []
            for index, url in enumerate(urls[: self.items], start=1):
                findings.append(
                    FindingDraft(
                        title=f"{self.topic.title()} development {index}",
                        summary=f"Retrieved source {index} discusses {self.topic}.",
                        why_it_matters=f"It is one of the sources returned for {self.topic}.",
                        source_urls=[url],
                    )
                )
            return SynthesisDraft(
                findings=findings,
                limitations=["The snippets are short, so the brief stays close to them."],
            )
        raise AssertionError(f"unexpected schema {schema}")
