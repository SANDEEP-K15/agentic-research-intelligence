"""Natural-language goal analysis."""

from __future__ import annotations

from app.llm.protocol import LLMClient
from app.models import GoalAnalysis

_SYSTEM = (
    "You extract a structured research request. "
    "Use only what the user asked. Do not add topics they did not mention. "
    "topic is a short noun phrase. "
    "time_range is the user's time window in a few words, or 'unspecified' if they gave none. "
    "recency is day, week, month, year, or unspecified. "
    "Map phrases such as 'last week' or 'past 7 days' to week, 'today' or 'last 24 hours' to day, "
    "'last month' to month, and 'last year' to year. "
    "requested_items is the count the user asked for. If they did not ask for a count, use 3. "
    "output_type is summary, brief, or report."
)


class GoalAnalyzer:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def analyze(self, goal: str) -> GoalAnalysis:
        return self._llm.generate_structured(
            system=_SYSTEM,
            user=f"Research goal:\n{goal.strip()}",
            schema=GoalAnalysis,
        )
