import pytest
from datetime import date

from app.errors import PipelineError
from app.models import FindingDraft, GoalAnalysis, SearchResult, SynthesisDraft
from app.research.context import ResearchContext
from app.research.process import (
    build_search_queries,
    deduplicate,
    ground_findings,
    is_disqualified_for_time_sensitive,
    prepare_candidates,
    select_candidates,
)
from app.research.selection import score_candidate
from app.research.synthesize import Synthesizer
from tests.fakes import ScriptedLLM


def _result(url: str, title: str, domain: str = "example.com") -> SearchResult:
    return SearchResult(title=title, url=url, snippet=title, domain=domain)


def test_deduplicate_by_url_and_title() -> None:
    results = [
        _result("https://example.com/a", "Same"),
        _result("https://example.com/a/", "Same"),
        _result("https://other.example/b", "Same"),
        _result("https://other.example/c", "Different"),
    ]
    unique = deduplicate(results)
    assert [item.url for item in unique] == [
        "https://example.com/a",
        "https://other.example/c",
    ]


def test_selection_uses_page_evidence_not_only_the_snippet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    analysis = GoalAnalysis(
        topic="cloud computing",
        time_range="last week",
        recency="week",
        requested_items=2,
        output_type="summary",
    )
    thin_snippet = SearchResult(
        title="Cloud update",
        url="https://example.com/2",
        snippet="Brief.",
        domain="example.com",
        page_title="Cloud provider announced a new region",
        page_excerpt="The company announced a cloud computing expansion this week.",
        publication_date="2026-09-22",
    )
    unrelated = _result("https://example.com/1", "Weather today")
    selected = select_candidates([unrelated, thin_snippet], analysis)
    assert [item.url for item in selected] == ["https://example.com/2"]


def test_grounding_drops_unknown_urls() -> None:
    selected = [_result("https://example.com/real", "Real source")]
    draft = SynthesisDraft(
        findings=[
            FindingDraft(
                title="Invented claim",
                summary="This cites a page that was not retrieved.",
                why_it_matters="It should be discarded.",
                source_urls=["https://example.com/invented"],
            ),
            FindingDraft(
                title="Grounded claim",
                summary="This cites the retrieved page.",
                why_it_matters="The snippet is the only support.",
                source_urls=["https://example.com/real"],
            ),
        ],
        limitations=[],
    )
    findings, notes = ground_findings(draft, selected, limit=3)
    assert len(findings) == 1
    assert findings[0].source_urls == ["https://example.com/real"]
    assert notes


def test_synthesis_without_sources_does_not_fabricate() -> None:
    context = ResearchContext(
        goal="Research recent robotics developments.",
        analysis=GoalAnalysis(
            topic="robotics",
            time_range="last week",
            recency="week",
            requested_items=3,
            output_type="summary",
        ),
    )
    with pytest.raises(PipelineError, match="no search results"):
        Synthesizer(ScriptedLLM())(context)
    assert context.findings == []


def _analysis() -> GoalAnalysis:
    return GoalAnalysis(
        topic="generative AI",
        time_range="last week",
        recency="week",
        requested_items=2,
        output_type="summary",
    )


def test_unspecified_recency_uses_three_discovery_queries() -> None:
    analysis = GoalAnalysis(
        topic="robotics",
        time_range="unspecified",
        recency="unspecified",
        requested_items=3,
        output_type="summary",
    )
    assert len(build_search_queries(analysis)) == 3


def test_search_queries_cover_five_time_bounded_angles() -> None:
    queries = build_search_queries(_analysis())
    assert len(queries) == 5
    assert len({query.lower() for query in queries}) == len(queries)
    assert all("generative AI" in query for query in queries)
    assert all("last week" in query for query in queries)
    joined = " ".join(queries).lower()
    assert "announcement" in joined or "release" in joined
    assert "model launch" in joined or "launch" in joined
    assert "product" in joined or "company" in joined
    assert "partnership" in joined or "funding" in joined
    assert "breakthrough" in joined or "research" in joined


def test_prepare_candidates_enriches_promising_urls() -> None:
    html = """
    <html><head><meta property="article:published_time" content="2026-09-21T09:00:00Z" /></head>
    <body><p>OpenAI announced a generative AI model release.</p></body></html>
    """
    base = SearchResult(
        title="Generative AI news",
        url="https://openai.com/blog/release",
        snippet="short",
        domain="openai.com",
    )
    prepared = prepare_candidates([base], _analysis(), fetch_fn=lambda _url: html)
    assert prepared[0].publication_date == "2026-09-21"
    assert "announced" in (prepared[0].page_excerpt or "")


def test_scoring_prefers_dated_announcement_over_a_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    analysis = _analysis()
    guide = SearchResult(
        title="What is generative AI: a complete guide",
        url="https://example.com/guide",
        snippet="An introduction and overview of generative AI.",
        domain="example.com",
        publication_date="2026-09-20",
        page_excerpt="An introduction and overview.",
    )
    announcement = SearchResult(
        title="Lab update",
        url="https://www.reuters.com/ai",
        snippet="Short.",
        domain="reuters.com",
        publication_date="2026-09-22",
        page_excerpt="The lab announced and launched a new generative AI model.",
    )
    assert score_candidate(guide, analysis).qualifies(analysis) is False
    assert score_candidate(announcement, analysis).qualifies(analysis) is True
    selected = select_candidates([guide, announcement], analysis)
    assert [item.url for item in selected] == ["https://www.reuters.com/ai"]


def test_wikipedia_and_old_dates_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    wiki = SearchResult(
        title="Generative artificial intelligence",
        url="https://en.wikipedia.org/wiki/Generative_artificial_intelligence",
        snippet="Generative AI is a type of machine learning.",
        domain="en.wikipedia.org",
    )
    stale = SearchResult(
        title="Generative AI study findings",
        url="https://example.com/2025-study",
        snippet="A 2025 study evaluated generative AI adoption trends.",
        domain="example.com",
        publication_date="2025-01-10",
        page_excerpt="A 2025 study evaluated generative AI adoption trends.",
    )
    recent = SearchResult(
        title="Company launch",
        url="https://techcrunch.com/launch",
        snippet="Brief.",
        domain="techcrunch.com",
        publication_date="2026-09-23",
        page_excerpt="The company announced the launch of a generative AI assistant.",
    )
    assert is_disqualified_for_time_sensitive(wiki, _analysis())
    assert is_disqualified_for_time_sensitive(stale, _analysis())
    selected = select_candidates([wiki, stale, recent], _analysis())
    assert [item.url for item in selected] == ["https://techcrunch.com/launch"]


def test_july_2024_event_is_rejected_for_last_week_september_2026(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    canva = SearchResult(
        title="Canva Acquires Leonardo.AI",
        url="https://techcrunch.com/canva-leonardo",
        snippet="Generative AI news.",
        domain="techcrunch.com",
        publication_date="2026-09-24",
        page_excerpt="Canva Acquires Leonardo.AI. In July 2024 the companies announced the acquisition.",
    )
    assert is_disqualified_for_time_sensitive(canva, _analysis())
    assert select_candidates([canva], _analysis()) == []


def test_recent_wording_does_not_override_explicit_old_event_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    stale = SearchResult(
        title="Latest generative AI developments",
        url="https://example.com/latest",
        snippet="Recent generative AI news and the latest updates from last week.",
        domain="example.com",
        publication_date="2026-09-24",
        page_excerpt="In July 2024 the lab announced a generative AI model launch.",
    )
    assert is_disqualified_for_time_sensitive(stale, _analysis())
    assert select_candidates([stale], _analysis()) == []


def test_valid_in_window_2026_event_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    fresh = SearchResult(
        title="Model launch",
        url="https://techcrunch.com/fresh",
        snippet="Brief.",
        domain="techcrunch.com",
        publication_date="2026-09-22",
        page_excerpt="On September 22, 2026 the company announced a generative AI model launch.",
    )
    assert not is_disqualified_for_time_sensitive(fresh, _analysis())
    selected = select_candidates([fresh], _analysis())
    assert [item.url for item in selected] == ["https://techcrunch.com/fresh"]


def test_current_article_with_background_historical_date_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    article = SearchResult(
        title="Agency unveils generative AI safety framework",
        url="https://reuters.com/safety",
        snippet="Brief generative AI update.",
        domain="reuters.com",
        publication_date="2026-09-23",
        page_excerpt=(
            "In July 2024 regulators began reviewing early generative AI tools. "
            "On September 23, 2026 the agency unveiled a new generative AI safety framework."
        ),
    )
    assert not is_disqualified_for_time_sensitive(article, _analysis())
    selected = select_candidates([article], _analysis())
    assert [item.url for item in selected] == ["https://reuters.com/safety"]


def test_old_publication_without_recent_event_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    stale = SearchResult(
        title="Generative AI adoption report",
        url="https://example.com/report",
        snippet="A generative AI adoption report from early 2025.",
        domain="example.com",
        publication_date="2025-01-10",
        page_excerpt="The report summarized generative AI adoption through 2024.",
    )
    assert is_disqualified_for_time_sensitive(stale, _analysis())
    assert select_candidates([stale], _analysis()) == []


def test_old_publication_with_clear_recent_event_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    updated = SearchResult(
        title="Partnership update",
        url="https://techcrunch.com/partnership",
        snippet="Brief.",
        domain="techcrunch.com",
        publication_date="2025-01-10",
        page_excerpt=(
            "On September 22, 2026 the company announced a generative AI partnership "
            "with a major cloud provider."
        ),
    )
    assert not is_disqualified_for_time_sensitive(updated, _analysis())
    selected = select_candidates([updated], _analysis())
    assert [item.url for item in selected] == ["https://techcrunch.com/partnership"]


def test_current_publication_with_concrete_event_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    current = SearchResult(
        title="Generative AI chip launch",
        url="https://nvidia.com/blog/chip",
        snippet="Short.",
        domain="nvidia.com",
        publication_date="2026-09-24",
        page_excerpt="The company announced the launch of a new generative AI accelerator.",
    )
    assert not is_disqualified_for_time_sensitive(current, _analysis())
    selected = select_candidates([current], _analysis())
    assert [item.url for item in selected] == ["https://nvidia.com/blog/chip"]


def test_insufficient_evidence_selects_nothing() -> None:
    generic = SearchResult(
        title="What is generative AI",
        url="https://example.com/explainer",
        snippet="An introduction and overview for beginners.",
        domain="example.com",
        publication_date="2026-09-20",
        page_excerpt="An introduction and overview for beginners.",
    )
    assert select_candidates([generic], _analysis()) == []
