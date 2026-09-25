from datetime import date

import pytest

_INTEGRATION_PAGE_HTML = """
<html><head>
  <meta property="article:published_time" content="2026-09-22T10:00:00Z" />
</head><body>
  <p>The organization announced a launch and product release this week.</p>
</body></html>
"""


def mock_fetch_page(_url: str) -> str:
    return _INTEGRATION_PAGE_HTML


@pytest.fixture
def integration_page_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.research.page_evidence.default_fetch_page", mock_fetch_page)
    monkeypatch.setattr("app.research.selection._today", lambda: date(2026, 9, 25))
