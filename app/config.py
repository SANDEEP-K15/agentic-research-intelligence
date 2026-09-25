"""Runtime configuration loaded from the environment and the project .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_RETRIES = 2
DEFAULT_LLM_MAX_RETRIES = 2
DEFAULT_SEARCH_MAX_RESULTS = 8
DEFAULT_SEARCH_BACKEND = "duckduckgo"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    max_retries: int
    llm_max_retries: int
    search_max_results: int
    search_backend: str

    def require_api_key(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Export it before running the agent."
            )
        return self.gemini_api_key


def _load_dotenv(path: Path) -> None:
    """Set missing environment variables from a .env file. Existing values win."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return value


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def load_settings() -> Settings:
    """Load settings from the environment, including values supplied by .env."""
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        max_retries=_positive_int("MAX_RETRIES", DEFAULT_MAX_RETRIES),
        llm_max_retries=_positive_int("LLM_MAX_RETRIES", DEFAULT_LLM_MAX_RETRIES),
        search_max_results=max(1, _positive_int("SEARCH_MAX_RESULTS", DEFAULT_SEARCH_MAX_RESULTS)),
        search_backend=os.environ.get("SEARCH_BACKEND", DEFAULT_SEARCH_BACKEND).strip()
        or DEFAULT_SEARCH_BACKEND,
    )
