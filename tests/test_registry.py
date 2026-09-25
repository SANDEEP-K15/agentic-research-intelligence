import pytest

from app.errors import ToolAlreadyRegisteredError, ToolNotFoundError
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool


def test_register_get_and_list() -> None:
    registry = ToolRegistry()
    registry.register(WebSearchTool(search_fn=lambda *args: []))
    registry.register(CalculatorTool())
    assert registry.list_tools() == ["calculator", "web_search"]
    assert registry.get("calculator").name == "calculator"


def test_unknown_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")


def test_duplicate_registration() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    with pytest.raises(ToolAlreadyRegisteredError):
        registry.register(CalculatorTool())
