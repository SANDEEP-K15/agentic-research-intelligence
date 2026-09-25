from datetime import date

import pytest

from app.models import GoalAnalysis, SearchResult
from app.research.page_evidence import (
    enrich_search_result,
    extract_page_fields,
    extract_publication_dates,
    normalize_date_string,
)
from app.research.process import is_disqualified_for_time_sensitive, publication_in_window, select_candidates


def _analysis() -> GoalAnalysis:
    return GoalAnalysis(
        topic="generative AI",
        time_range="last week",
        recency="week",
        requested_items=2,
        output_type="summary",
    )


def test_extract_publication_date_from_page_meta() -> None:
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-09-20T14:00:00Z" />
    </head><body><p>Company announced a new generative AI model.</p></body></html>
    """
    assert extract_publication_dates(html) == ["2026-09-20"]
    title, published, excerpt = extract_page_fields(html)
    assert title is None
    assert published == "2026-09-20"
    assert "announced" in excerpt


def test_page_publication_date_qualifies_a_thin_snippet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-09-22T10:00:00Z" />
    </head><body><p>OpenAI announced a generative AI release for enterprise customers.</p></body></html>
    """
    base = SearchResult(
        title="Generative AI update",
        url="https://openai.com/blog/release",
        snippet="Short search snippet with little detail.",
        domain="openai.com",
    )
    enriched = enrich_search_result(base, lambda _url: html)
    assert publication_in_window(enriched, _analysis())
    assert not is_disqualified_for_time_sensitive(enriched, _analysis())
    selected = select_candidates([enriched], _analysis())
    assert selected[0].url == "https://openai.com/blog/release"


def test_page_publication_date_outside_window_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
    html = """
    <html><head>
      <meta property="article:published_time" content="2025-01-10T10:00:00Z" />
    </head><body><p>A generative AI study from last year.</p></body></html>
    """
    result = enrich_search_result(
        SearchResult(
            title="Generative AI study",
            url="https://example.com/study",
            snippet="A generative AI study.",
            domain="example.com",
        ),
        lambda _url: html,
    )
    assert is_disqualified_for_time_sensitive(result, _analysis())


def test_normalize_date_string_accepts_iso_prefix() -> None:
    assert normalize_date_string("2026-09-20T08:00:00Z") == "2026-09-20"
