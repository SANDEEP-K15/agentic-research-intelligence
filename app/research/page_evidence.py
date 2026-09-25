"""Fetch lightweight page evidence for recency and event validation."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.models import SearchResult

FetchFn = Callable[[str], str]

_MAX_PAGE_BYTES = 400_000
_FETCH_TIMEOUT_SECONDS = 12
_USER_AGENT = "ResearchIntelligenceAgent/1.0 (+evidence-fetch)"

_META_CONTENT_FIRST = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:published_time|og:published_time|parsely-pub-date|pubdate|date)["\']',
    re.IGNORECASE,
)
_META_PROPERTY_FIRST = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|og:published_time|parsely-pub-date|pubdate|date)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TIME_DATETIME = re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.IGNORECASE)
_JSON_DATE_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.IGNORECASE)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
        else:
            self._chunks.append(text)

    def excerpt(self, limit: int = 2000) -> str:
        collapsed = re.sub(r"\s+", " ", " ".join(self._chunks)).strip()
        return collapsed[:limit]


def normalize_date_string(raw: str) -> str | None:
    """Return an ISO YYYY-MM-DD prefix when the value is recognizable."""
    value = unescape(raw).strip()
    if not value:
        return None
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", value)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def extract_publication_dates(html: str) -> list[str]:
    dates: list[str] = []
    for pattern in (_META_PROPERTY_FIRST, _META_CONTENT_FIRST, _TIME_DATETIME, _JSON_DATE_PUBLISHED):
        for match in pattern.finditer(html):
            normalized = normalize_date_string(match.group(1))
            if normalized and normalized not in dates:
                dates.append(normalized)
    return dates


def extract_page_fields(html: str) -> tuple[str | None, str | None, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return None, None, ""
    page_title = parser.title.strip() or None
    dates = extract_publication_dates(html)
    publication_date = dates[0] if dates else None
    return page_title, publication_date, parser.excerpt()


def default_fetch_page(url: str) -> str:
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(_MAX_PAGE_BYTES + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except (URLError, TimeoutError, OSError, ValueError):
        return ""
    if len(raw) > _MAX_PAGE_BYTES:
        raw = raw[:_MAX_PAGE_BYTES]
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def enrich_search_result(result: SearchResult, fetch_fn: FetchFn) -> SearchResult:
    from app.research.selection import _is_generic_reference

    if _is_generic_reference(result):
        return result
    if not result.url.startswith(("http://", "https://")):
        return result
    html = fetch_fn(result.url)
    if not html.strip():
        return result
    page_title, publication_date, page_excerpt = extract_page_fields(html)
    return result.model_copy(
        update={
            "page_title": page_title,
            "publication_date": publication_date,
            "page_excerpt": page_excerpt or None,
        }
    )


def enrich_search_results(
    results: list[SearchResult],
    *,
    fetch_fn: FetchFn | None = None,
) -> list[SearchResult]:
    """Attach page title, publication date, and excerpt for validation and synthesis."""
    loader = fetch_fn or default_fetch_page
    return [enrich_search_result(result, loader) for result in results]
