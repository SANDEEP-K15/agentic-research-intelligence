"""Tool registry. Callers retrieve tools by name."""

from __future__ import annotations

from typing import Protocol

from app.errors import ToolAlreadyRegisteredError, ToolNotFoundError


class Tool(Protocol):
    @property
    def name(self) -> str:
        """Stable tool name."""

    def run(self, payload: dict[str, object]) -> object:
        """Execute the tool with a validated payload."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolAlreadyRegisteredError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"unknown tool: {name}") from exc

    def list_tools(self) -> list[str]:
        return sorted(self._tools)
