"""Build a validated execution plan from the goal analysis."""

from __future__ import annotations

from app.errors import PlanValidationError
from app.llm.protocol import LLMClient
from app.models import REQUIRED_TOOLS, GoalAnalysis, Plan, PlanDraft, PlanStep, ToolName

_SYSTEM = (
    "You write a short execution plan for a research agent. "
    "Return steps that use only these tools, in this order: "
    "web_search, normalize, select, calculator, synthesize. "
    "Each step needs an id, a description, a tool, and an expected_output. "
    "Descriptions must mention the user's topic. "
    "Do not include hidden reasoning."
)

_DEFAULT_DESCRIPTIONS: dict[ToolName, str] = {
    "web_search": "Search for recent developments in {topic}",
    "normalize": "Normalize and filter search results",
    "select": "Identify relevant developments in {topic}",
    "calculator": "Compute a descriptive source-diversity statistic for the retrieved set",
    "synthesize": "Generate the final {output_type} from cited sources",
}

_DEFAULT_EXPECTED: dict[ToolName, str] = {
    "web_search": "Search results with titles, URLs, and snippets",
    "normalize": "Deduplicated search results",
    "select": "A shortlist of candidate developments",
    "calculator": "A numeric source-diversity statistic",
    "synthesize": "A sourced research report",
}


def _fill(template: str, analysis: GoalAnalysis) -> str:
    return template.format(topic=analysis.topic, output_type=analysis.output_type)[:240]


def canonicalize_plan(draft: PlanDraft, analysis: GoalAnalysis) -> tuple[Plan, str | None]:
    """Reorder steps to the execution contract and fill any missing stage."""
    if not draft.steps:
        raise PlanValidationError("plan has no steps")

    by_tool: dict[str, PlanStep] = {}
    for step in draft.steps:
        by_tool.setdefault(step.tool, step)

    missing = [tool for tool in REQUIRED_TOOLS if tool not in by_tool]
    order = [step.tool for step in draft.steps]
    reordered = order != list(REQUIRED_TOOLS)

    steps: list[PlanStep] = []
    for index, tool in enumerate(REQUIRED_TOOLS, start=1):
        existing = by_tool.get(tool)
        description = existing.description.strip() if existing else ""
        expected = existing.expected_output.strip() if existing else ""
        if len(description) < 3:
            description = _fill(_DEFAULT_DESCRIPTIONS[tool], analysis)
        if len(expected) < 3:
            expected = _DEFAULT_EXPECTED[tool]
        steps.append(
            PlanStep(
                id=index,
                description=description,
                tool=tool,
                expected_output=expected,
            )
        )

    note = None
    changed = missing or reordered or len(draft.steps) != len(REQUIRED_TOOLS)
    if changed:
        changes: list[str] = []
        if missing:
            changes.append("added missing steps: " + ", ".join(missing))
        if reordered:
            changes.append("reordered steps to the execution contract")
        if len(draft.steps) > len(REQUIRED_TOOLS):
            changes.append("removed duplicate steps")
        if changes:
            note = "Plan adjusted before execution (" + "; ".join(changes) + ")."
    return Plan(steps=steps), note


class Planner:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def create(self, goal: str, analysis: GoalAnalysis) -> tuple[Plan, str | None]:
        draft = self._llm.generate_structured(
            system=_SYSTEM,
            user=(
                f"Goal: {goal.strip()}\n"
                f"Topic: {analysis.topic}\n"
                f"Time range: {analysis.time_range}\n"
                f"Requested items: {analysis.requested_items}\n"
                f"Output type: {analysis.output_type}"
            ),
            schema=PlanDraft,
        )
        return canonicalize_plan(draft, analysis)
