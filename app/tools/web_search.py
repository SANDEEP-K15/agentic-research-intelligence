"""Web search tool. The third-party search client stays inside this module."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from app.errors import (
    EmptySearchError,
    MalformedSearchError,
    SearchNetworkError,
    SearchProviderError,
    SimulatedTimeoutError,
    ToolInputError,
)
from app.models import SearchResult

SearchFn = Callable[[str, str | None, int, str], list[object]]

_ALLOWED_TIMELIMITS = {"d", "w", "m", "y"}


class FailureSimulator:
    """Fails the first web-search invocation, then allows later calls."""

    def __init__(self) -> None:
        self.triggered = False

    def check(self) -> None:
        if not self.triggered:
            self.triggered = True
            raise SimulatedTimeoutError("simulated timeout on the first web search")


def _is_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    name = type(exc).__name__.lower()
    return any(token in name for token in ("timeout", "network", "connection", "ratelimit"))


def _search_once(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
    """One ddgs call. An empty provider response is a failure, not an empty success."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise SearchProviderError("ddgs is not installed") from exc

    kwargs: dict[str, object] = {
        "query": query,
        "region": "us-en",
        "safesearch": "moderate",
        "max_results": max_results,
        "backend": backend,
    }
    if timelimit:
        kwargs["timelimit"] = timelimit
    try:
        results = DDGS(timeout=20).text(**kwargs)
    except Exception as exc:
        message = str(exc).lower()
        if "no results found" in message:
            raise EmptySearchError(str(exc)) from exc
        if _is_network_error(exc):
            raise SearchNetworkError(str(exc)) from exc
        raise SearchProviderError(str(exc)) from exc
    if results is None or results == []:
        raise EmptySearchError(f"{backend} returned no results")
    if not isinstance(results, list):
        raise MalformedSearchError("search response was not a list")
    return results


def default_search(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
    """Call ddgs. If the chosen backend has no results, try the library auto backend once."""
    try:
        return _search_once(query, timelimit, max_results, backend)
    except EmptySearchError:
        if backend == "auto":
            raise
        return _search_once(query, timelimit, max_results, "auto")


def _domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_results(raw: list[object]) -> list[SearchResult]:
    """Keep well-formed http(s) results. Skip malformed items. Never invent URLs."""
    normalized: list[SearchResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("href") or item.get("url") or "").strip()
        snippet = str(item.get("body") or item.get("snippet") or "").strip()
        if not title or not url.startswith(("http://", "https://")):
            continue
        domain = _domain(url)
        if not domain:
            continue
        normalized.append(
            SearchResult(
                title=title[:300],
                url=url[:1000],
                snippet=snippet[:500],
                domain=domain[:200],
            )
        )
    return normalized


class WebSearchTool:
    name = "web_search"

    def __init__(
        self,
        *,
        search_fn: SearchFn | None = None,
        simulator: FailureSimulator | None = None,
        max_results: int = 8,
        backend: str = "duckduckgo",
    ) -> None:
        self._search_fn = search_fn or default_search
        self._simulator = simulator
        self._max_results = max_results
        self._backend = backend

    def run(self, payload: dict[str, object]) -> list[SearchResult]:
        if self._simulator is not None:
            self._simulator.check()

        query = payload.get("query")
        timelimit = payload.get("timelimit")
        if not isinstance(query, str) or not query.strip():
            raise ToolInputError("query must be a non-empty string")
        if timelimit is not None and timelimit not in _ALLOWED_TIMELIMITS:
            raise ToolInputError("timelimit must be d, w, m, y, or omitted")
        if not isinstance(timelimit, str):
            timelimit = None

        try:
            raw = self._search_fn(query.strip(), timelimit, self._max_results, self._backend)
        except (SearchNetworkError, SearchProviderError, MalformedSearchError, SimulatedTimeoutError):
            raise
        except Exception as exc:
            if _is_network_error(exc):
                raise SearchNetworkError(str(exc)) from exc
            raise SearchProviderError(str(exc)) from exc
        if not isinstance(raw, list):
            raise MalformedSearchError("search function did not return a list")
        results = normalize_results(raw)
        if not results:
            raise EmptySearchError("search provider returned no usable results")
        return results
