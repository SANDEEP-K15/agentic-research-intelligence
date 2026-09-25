import json
from pathlib import Path

import pytest

from app.cli import main
from tests.fakes import ScriptedLLM


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cli.build_llm", lambda settings: ScriptedLLM(topic="robotics", items=1))

    def search(query: str, timelimit: str | None, max_results: int, backend: str) -> list[object]:
        return [
            {
                "title": "Robotics development",
                "href": "https://example.com/robotics",
                "body": "A robotics lab published a short update.",
            }
        ]

    monkeypatch.setattr("app.tools.web_search.default_search", search)


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_missing_goal_exits_two() -> None:
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2


def test_blank_goal_exits_two() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["   "])
    assert caught.value.code == 2


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = main(["Research recent developments in cloud computing."])
    assert code == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_cli_success_writes_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    integration_page_evidence: None,
) -> None:
    _install_fakes(monkeypatch)
    destination = tmp_path / "report.json"
    code = main(
        [
            "Research recent robotics developments.",
            "--output",
            str(destination),
            "--simulate-failure",
        ]
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "[PLAN]" in output
    assert "SimulatedTimeoutError" in output
    assert "[RECOVERY] Retry 1/2" in output
    assert destination.exists()
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["tools_used"] == ["web_search", "calculator"]
    assert payload["sources"][0]["url"] == "https://example.com/robotics"
    assert payload["failures_recovered"] == 1
