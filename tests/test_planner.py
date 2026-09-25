import pytest
from pydantic import ValidationError

from app.models import GoalAnalysis, PlanDraft, PlanStep
from app.planning.planner import Planner, canonicalize_plan
from tests.fakes import ScriptedLLM, sample_plan


def _analysis() -> GoalAnalysis:
    return GoalAnalysis(
        topic="cloud computing",
        time_range="last month",
        recency="month",
        requested_items=3,
        output_type="summary",
    )


def test_valid_plan_is_unchanged() -> None:
    draft = sample_plan("cloud computing")
    plan, note = canonicalize_plan(draft, _analysis())
    assert note is None
    assert [step.tool for step in plan.steps] == [
        "web_search",
        "normalize",
        "select",
        "calculator",
        "synthesize",
    ]
    assert plan.steps[0].description.startswith("Search for recent developments")


def test_missing_step_is_added_and_recorded() -> None:
    draft = PlanDraft(steps=sample_plan().steps[:3])
    plan, note = canonicalize_plan(draft, _analysis())
    assert note is not None
    assert "calculator" in note
    assert [step.tool for step in plan.steps][-2:] == ["calculator", "synthesize"]
    assert plan.steps[3].description.startswith("Compute a descriptive")


def test_steps_are_reordered() -> None:
    steps = list(reversed(sample_plan().steps))
    draft = PlanDraft(steps=steps)
    plan, note = canonicalize_plan(draft, _analysis())
    assert note is not None
    assert [step.id for step in plan.steps] == [1, 2, 3, 4, 5]
    assert plan.steps[0].tool == "web_search"


def test_unknown_tool_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        PlanStep(
            id=1,
            description="Do something unsupported",
            tool="shell",  # type: ignore[arg-type]
            expected_output="Nothing safe",
        )


def test_planner_uses_the_goal() -> None:
    llm = ScriptedLLM(topic="cybersecurity")
    plan, note = Planner(llm).create("Research recent cybersecurity developments.", _analysis())
    assert "cybersecurity" in llm.goals[0]
    assert note is None
    assert plan.steps[0].tool == "web_search"
