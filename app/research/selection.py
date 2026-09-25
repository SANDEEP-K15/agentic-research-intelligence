"""Research retrieval: queries, deduplication, page evidence, and candidate ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.models import GoalAnalysis, SearchResult
from app.research.page_evidence import FetchFn, enrich_search_result

_STOPWORDS = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "that",
    "this",
    "into",
    "recent",
    "latest",
    "developments",
    "development",
}

_EVENT_PATTERNS = (
    r"\bannounc\w*",
    r"\blaunch\w*",
    r"\breleas\w*",
    r"\bunveil\w*",
    r"\bacquir\w*",
    r"\bpublish\w*",
    r"\bregulat\w*",
    r"\bapprov\w*",
    r"\bpartner\w*",
    r"\bdebut\w*",
    r"\bintroduced\b",
    r"\bintroduces\b",
    r"\bintroducing\b",
    r"\bfunding\b",
    r"\braised\b",
    r"\blawsuit\b",
    r"\bshipped\b",
    r"\bbreakthrough\b",
    r"\bupdates?\b",
)

_GENERIC_PHRASES = (
    "what is",
    "introduction to",
    "guide to",
    "explained",
    "overview",
    "beginner",
    "tutorial",
    "top companies",
    "best tools",
    "ultimate guide",
)

_GENERIC_REFERENCE_SUFFIXES = (
    "wikipedia.org",
    "wikimedia.org",
    "britannica.com",
    "investopedia.com",
)

_NEWS_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "nature.com",
    "arxiv.org",
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "nytimes.com",
    "wsj.com",
    "bloomberg.com",
    "ft.com",
    "cnbc.com",
    "venturebeat.com",
    "arstechnica.com",
    "semianalysis.com",
}

_PRIMARY_SOURCE_SUFFIXES = (
    "openai.com",
    "anthropic.com",
    "deepmind.com",
    "googleblog.com",
    "blog.google",
    "research.google",
    "ai.google",
    "microsoft.com",
    "meta.com",
    "ai.meta.com",
    "nvidia.com",
    "huggingface.co",
)

_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_YEAR = re.compile(
    r"\b(?:in\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d{2})\b",
    re.IGNORECASE,
)
_MONTH_DAY_YEAR = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(20\d{2})\b",
    re.IGNORECASE,
)
_MONTH_NAME_ALT = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
)
_EVENT_VERB_RE = (
    r"announc\w*|launch\w*|releas\w*|unveil\w*|acquir\w*|publish\w*|regulat\w*|approv\w*|"
    r"partner\w*|debut\w*|introduced|introduces|introducing|funding|raised|lawsuit|shipped|"
    r"breakthrough|updates?"
)
_EVENT_DATE_WINDOW_CHARS = 120
_DATE_IN_EVENT_CONTEXT = (
    rf"(?:{_ISO_DATE.pattern}|"
    rf"(?:(?:in\s+)?(?:{_MONTH_NAME_ALT})\s+(?:\d{{1,2}},?\s+)?(20\d{{2}}))|"
    rf"(?:{_MONTH_NAME_ALT})\s+\d{{1,2}},?\s+(20\d{{2}}))"
)
_EVENT_DATE_BEFORE_VERB = re.compile(
    rf"{_DATE_IN_EVENT_CONTEXT}\s+.{{0,{_EVENT_DATE_WINDOW_CHARS}}}?\b(?:{_EVENT_VERB_RE})\b",
    re.IGNORECASE,
)
_EVENT_VERB_BEFORE_DATE = re.compile(
    rf"\b(?:{_EVENT_VERB_RE})\b\s+.{{0,{_EVENT_DATE_WINDOW_CHARS}}}?{_DATE_IN_EVENT_CONTEXT}",
    re.IGNORECASE,
)


def _today() -> date:
    return date.today()


def build_search_queries(analysis: GoalAnalysis) -> list[str]:
    topic = " ".join(analysis.topic.split())[:140]
    window = "" if analysis.recency == "unspecified" else analysis.time_range.strip()
    if analysis.recency != "unspecified":
        drafts = [
            f"{topic} major announcement OR release {window}",
            f"{topic} new model launch OR unveils {window}",
            f"{topic} product OR company development {window}",
            f"{topic} partnership OR acquisition OR funding {window}",
            f"{topic} research breakthrough OR paper {window}",
        ]
        return _unique_queries(drafts, limit=5)
    drafts = [
        f"{topic} announced OR released",
        f"{topic} model OR product launch",
        f"{topic} acquisition OR partnership OR funding",
    ]
    return _unique_queries(drafts, limit=3)


def _unique_queries(drafts: list[str], limit: int) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for draft in drafts:
        query = " ".join(draft.split())[:300]
        key = query.lower()
        if not query or key in seen:
            continue
        seen.add(key)
        queries.append(query)
    return queries[:limit]


def _canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ]
    )
    path = parsed.path.rstrip("/") or "/"
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urlunparse((parsed.scheme.lower(), host, path, "", query, ""))


def deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[SearchResult] = []
    for result in results:
        url_key = _canonical_url(result.url)
        title_key = re.sub(r"\s+", " ", result.title).strip().lower()
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(result)
    return unique


def evidence_text(result: SearchResult) -> str:
    parts = [result.title, result.snippet]
    if result.page_title:
        parts.append(result.page_title)
    if result.page_excerpt:
        parts.append(result.page_excerpt)
    if result.publication_date:
        parts.append(result.publication_date)
    return " ".join(parts)


def _tokens(topic: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", topic.lower())
        if len(token) > 2 and token not in _STOPWORDS
    ]


def _is_generic_reference(result: SearchResult) -> bool:
    domain = result.domain.lower()
    return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in _GENERIC_REFERENCE_SUFFIXES)


def _is_primary_source(domain: str) -> bool:
    lowered = domain.lower()
    return any(lowered == suffix or lowered.endswith(f".{suffix}") for suffix in _PRIMARY_SOURCE_SUFFIXES)


def _is_reputable_source(domain: str) -> bool:
    return domain in _NEWS_DOMAINS or domain.endswith(".gov") or _is_primary_source(domain)


def _window_start(analysis: GoalAnalysis, today: date) -> date | None:
    if analysis.recency == "day":
        return today - timedelta(days=1)
    if analysis.recency == "week":
        return today - timedelta(days=7)
    if analysis.recency == "month":
        return today - timedelta(days=31)
    if analysis.recency == "year":
        return today - timedelta(days=366)
    return None


def _append_date(dates: list[date], candidate: date) -> None:
    if candidate not in dates:
        dates.append(candidate)


def _parse_all_evidence_dates(text: str) -> list[date]:
    dates: list[date] = []
    for year, month, day in _ISO_DATE.findall(text):
        try:
            _append_date(dates, date(int(year), int(month), int(day)))
        except ValueError:
            continue
    for month_name, year in _MONTH_YEAR.findall(text):
        month = _MONTH_NAMES[month_name.lower()]
        _append_date(dates, date(int(year), month, 1))
    for month_name, day, year in _MONTH_DAY_YEAR.findall(text):
        month = _MONTH_NAMES[month_name.lower()]
        try:
            _append_date(dates, date(int(year), month, int(day)))
        except ValueError:
            continue
    return dates


def _parsed_publication_date(result: SearchResult) -> date | None:
    if not result.publication_date:
        return None
    try:
        return date.fromisoformat(result.publication_date[:10])
    except ValueError:
        return None


def evidence_dates(result: SearchResult) -> list[date]:
    return _parse_all_evidence_dates(evidence_text(result))


def event_associated_dates_in_text(text: str) -> list[date]:
    """Dates that appear near event verbs (reported development), not background mentions."""
    dates: list[date] = []
    for pattern in (_EVENT_DATE_BEFORE_VERB, _EVENT_VERB_BEFORE_DATE):
        for match in pattern.finditer(text):
            for parsed in _parse_all_evidence_dates(match.group(0)):
                _append_date(dates, parsed)
    return dates


def event_associated_dates(result: SearchResult) -> list[date]:
    dates: list[date] = []
    for part in (result.title, result.snippet, result.page_excerpt):
        if not part:
            continue
        for parsed in event_associated_dates_in_text(part):
            _append_date(dates, parsed)
    return dates


def _date_window(analysis: GoalAnalysis) -> tuple[date, date] | None:
    if analysis.recency == "unspecified":
        return None
    today = _today()
    window_start = _window_start(analysis, today)
    if window_start is None:
        return None
    return window_start, today


def _is_outside_window(candidate: date, window_start: date, today: date) -> bool:
    return candidate < window_start or candidate > today


def has_out_of_window_evidence_date(result: SearchResult, analysis: GoalAnalysis) -> bool:
    """True when extracted publication or event timing fails the requested window."""
    window = _date_window(analysis)
    if window is None:
        return False
    window_start, today = window
    pub = _parsed_publication_date(result)
    if pub is not None and not _is_outside_window(pub, window_start, today):
        event_dates = event_associated_dates(result)
        in_window_events = [
            item for item in event_dates if not _is_outside_window(item, window_start, today)
        ]
        out_window_events = [
            item for item in event_dates if _is_outside_window(item, window_start, today)
        ]
        if in_window_events:
            return False
        if out_window_events:
            return True
        return False
    in_window_events = [
        item
        for item in event_associated_dates(result)
        if not _is_outside_window(item, window_start, today)
    ]
    if in_window_events:
        return False
    if pub is not None and _is_outside_window(pub, window_start, today):
        return True
    out_window_events = [
        item
        for item in event_associated_dates(result)
        if _is_outside_window(item, window_start, today)
    ]
    return bool(out_window_events)


def publication_in_window(result: SearchResult, analysis: GoalAnalysis) -> bool:
    window = _date_window(analysis)
    if window is None:
        return False
    window_start, today = window
    pub = _parsed_publication_date(result)
    if pub is not None and not _is_outside_window(pub, window_start, today):
        return True
    return any(
        not _is_outside_window(item, window_start, today) for item in event_associated_dates(result)
    )


def publication_outside_window(result: SearchResult, analysis: GoalAnalysis) -> bool:
    return has_out_of_window_evidence_date(result, analysis)


def _explicit_years(text: str) -> set[int]:
    return {int(match.group(1)) for match in re.finditer(r"\b(20[12]\d)\b", text)}


def is_disqualified(result: SearchResult, analysis: GoalAnalysis) -> bool:
    if _is_generic_reference(result):
        return True
    if analysis.recency == "unspecified":
        return False
    if has_out_of_window_evidence_date(result, analysis):
        return True
    pub = _parsed_publication_date(result)
    window = _date_window(analysis)
    if window is None:
        return False
    window_start, today = window
    if pub is not None and not _is_outside_window(pub, window_start, today):
        return False
    if event_associated_dates(result):
        return False
    text = f"{result.title} {result.snippet}"
    years = _explicit_years(text)
    if not years:
        return False
    if analysis.recency in ("day", "week", "month") and all(year < today.year for year in years):
        return True
    if analysis.recency == "year" and all(year < today.year - 1 for year in years):
        return True
    if all(year < window_start.year for year in years):
        return True
    return False


def is_promising_for_enrichment(result: SearchResult, analysis: GoalAnalysis) -> bool:
    if _is_generic_reference(result):
        return False
    if _is_reputable_source(result.domain):
        return True
    tokens = _tokens(analysis.topic)
    blob = f"{result.title} {result.snippet}".lower()
    return any(token in blob for token in tokens)


def prepare_candidates(
    results: list[SearchResult],
    analysis: GoalAnalysis,
    *,
    fetch_fn: FetchFn | None = None,
) -> list[SearchResult]:
    """Deduplicate, enrich promising URLs, return evidence-ready rows."""
    unique = deduplicate(results)
    if fetch_fn is None:
        from app.research.page_evidence import default_fetch_page

        fetch_fn = default_fetch_page
    prepared: list[SearchResult] = []
    for result in unique:
        if is_promising_for_enrichment(result, analysis):
            prepared.append(enrich_search_result(result, fetch_fn))
        else:
            prepared.append(result)
    return prepared


@dataclass(frozen=True)
class CandidateScore:
    topic: int
    recency: int
    event: int
    source: int

    @property
    def total(self) -> int:
        return self.topic + self.recency + self.event + self.source

    def qualifies(self, analysis: GoalAnalysis) -> bool:
        if self.topic <= 0 or self.event <= 0:
            return False
        if analysis.recency != "unspecified" and self.recency <= 0:
            return False
        return True


def score_candidate(result: SearchResult, analysis: GoalAnalysis) -> CandidateScore:
    title = f"{result.title} {result.page_title or ''}".lower()
    body = f"{result.snippet} {result.page_excerpt or ''}".lower()
    text = evidence_text(result).lower()
    tokens = _tokens(analysis.topic)
    topic = sum(3 for token in tokens if token in title) + sum(1 for token in tokens if token in body)
    recency = 0
    if analysis.recency == "unspecified":
        recency = 1
    elif publication_in_window(result, analysis):
        recency = 10  # in-window publication_date or clearly identified recent event date
    event = 4 if any(re.search(pattern, text) for pattern in _EVENT_PATTERNS) else 0
    source = 0
    if result.domain in _NEWS_DOMAINS or result.domain.endswith(".gov"):
        source += 3
    if _is_primary_source(result.domain):
        source += 4
    if any(phrase in text for phrase in _GENERIC_PHRASES):
        source -= 3
    return CandidateScore(topic=topic, recency=recency, event=event, source=source)


def select_candidates(
    results: list[SearchResult],
    analysis: GoalAnalysis,
) -> list[SearchResult]:
    ranked: list[tuple[int, SearchResult, CandidateScore]] = []
    for index, result in enumerate(results):
        if is_disqualified(result, analysis):
            continue
        score = score_candidate(result, analysis)
        if not score.qualifies(analysis):
            continue
        ranked.append((index, result, score))
    ranked.sort(key=lambda item: (-item[2].total, item[0]))

    chosen: list[SearchResult] = []
    seen_domains: set[str] = set()
    deferred: list[SearchResult] = []
    for _, result, _score in ranked:
        if result.domain in seen_domains:
            deferred.append(result)
            continue
        chosen.append(result)
        seen_domains.add(result.domain)
        if len(chosen) >= analysis.requested_items:
            break
    if len(chosen) < analysis.requested_items:
        chosen.extend(deferred[: analysis.requested_items - len(chosen)])
    return chosen[: analysis.requested_items]


# Backward-compatible aliases used in tests and page_evidence.
is_disqualified_for_time_sensitive = is_disqualified
score_result = score_candidate
