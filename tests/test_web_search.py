import pytest

from app.errors import EmptySearchError, MalformedSearchError, SearchNetworkError, SimulatedTimeoutError
from app.tools.web_search import FailureSimulator, WebSearchTool, default_search, normalize_results


def _row(index: int) -> dict[str, str]:
    return {
        "title": f"Result {index}",
        "href": f"https://example.com/item-{index}",
        "body": f"Snippet {index}",
    }


def test_first_search_fails_then_second_succeeds() -> None:
    calls = {"count": 0}

    def search(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
        calls["count"] += 1
        assert query == "robotics developments"
        assert timelimit == "w"
        assert backend == "duckduckgo"
        return [_row(i) for i in range(1, 6)]

    tool = WebSearchTool(search_fn=search, simulator=FailureSimulator())
    payload = {"query": "robotics developments", "timelimit": "w"}

    try:
        tool.run(payload)
        raised = False
    except SimulatedTimeoutError:
        raised = True
    assert raised
    assert calls["count"] == 0

    results = tool.run(payload)
    assert calls["count"] == 1
    assert len(results) == 5
    assert results[0].domain == "example.com"
    assert results[0].url == "https://example.com/item-1"


def test_network_errors_are_preserved() -> None:
    def search(*args: object) -> list[object]:
        raise TimeoutError("timed out")

    tool = WebSearchTool(search_fn=search)
    try:
        tool.run({"query": "cloud computing developments", "timelimit": None})
    except SearchNetworkError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("expected SearchNetworkError")


def test_malformed_items_are_skipped_and_urls_are_not_invented() -> None:
    raw = [
        {"title": "Good", "href": "https://news.example.org/a", "body": "ok"},
        {"title": "", "href": "https://news.example.org/missing-title", "body": "x"},
        {"title": "Relative", "href": "/local", "body": "no"},
        "not-a-dict",
        {"title": "No url", "body": "missing"},
    ]
    results = normalize_results(raw)
    assert len(results) == 1
    assert results[0].url == "https://news.example.org/a"
    assert results[0].domain == "news.example.org"


def test_provider_no_results_is_not_a_successful_empty_search(monkeypatch) -> None:
    class EmptySearch:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def text(self, **kwargs):
            raise RuntimeError("No results found.")

    monkeypatch.setattr("ddgs.DDGS", EmptySearch)
    with pytest.raises(EmptySearchError, match="No results found"):
        default_search("robotics developments", "w", 5, "duckduckgo")


def test_empty_backend_falls_back_to_a_real_second_search(monkeypatch) -> None:
    calls: list[str] = []

    class FlakySearch:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def text(self, **kwargs):
            backend = str(kwargs.get("backend"))
            calls.append(backend)
            if backend == "duckduckgo":
                raise RuntimeError("No results found.")
            return [_row(1)]

    monkeypatch.setattr("ddgs.DDGS", FlakySearch)
    results = normalize_results(default_search("robotics developments", "w", 5, "duckduckgo"))
    assert calls == ["duckduckgo", "auto"]
    assert results[0].url == "https://example.com/item-1"


def test_simulated_failure_is_followed_by_a_real_search(monkeypatch) -> None:
    calls: list[str] = []

    class RecordingSearch:
        def __init__(self, *args, **kwargs) -> None:
            calls.append("client")

        def text(self, **kwargs):
            calls.append(str(kwargs.get("backend")))
            return [_row(1)]

    monkeypatch.setattr("ddgs.DDGS", RecordingSearch)
    tool = WebSearchTool(simulator=FailureSimulator(), backend="duckduckgo")
    payload = {"query": "generative AI developments", "timelimit": "w"}

    with pytest.raises(SimulatedTimeoutError):
        tool.run(payload)
    assert calls == []

    results = tool.run(payload)
    assert calls == ["client", "duckduckgo"]
    assert results[0].url == "https://example.com/item-1"


def test_non_list_response_is_rejected() -> None:
    tool = WebSearchTool(search_fn=lambda *args: {"title": "nope"})  # type: ignore[arg-type, return-value]
    try:
        tool.run({"query": "autonomous vehicles", "timelimit": "m"})
    except MalformedSearchError:
        return
    raise AssertionError("expected MalformedSearchError")
