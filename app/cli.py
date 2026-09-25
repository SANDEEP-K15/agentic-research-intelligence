"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import Settings, load_settings
from app.controller import AgentController
from app.errors import LLMProviderError, PlanValidationError, StructuredOutputError
from app.llm.gemini import GeminiLLM
from app.llm.protocol import LLMClient
from app.report.builder import write_report
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import FailureSimulator, WebSearchTool
from app.trace import Trace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description=(
            "Research Intelligence Agent. "
            "Turn a natural-language research goal into a sourced report."
        ),
    )
    parser.add_argument("goal", help="Natural-language research goal")
    parser.add_argument(
        "--simulate-failure",
        action="store_true",
        help="Fail the first web-search call, then recover with a bounded retry",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write the JSON report to this path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print plan adjustments and retrieved titles",
    )
    return parser


def build_llm(settings: Settings) -> LLMClient:
    return GeminiLLM(
        api_key=settings.require_api_key(),
        model=settings.gemini_model,
        max_retries=settings.llm_max_retries,
    )


def build_registry(settings: Settings, simulate_failure: bool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        WebSearchTool(
            simulator=FailureSimulator() if simulate_failure else None,
            max_results=settings.search_max_results,
            backend=settings.search_backend,
        )
    )
    registry.register(CalculatorTool())
    return registry


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.goal.strip():
        parser.error("goal must not be empty")

    try:
        settings = load_settings()
        controller = AgentController(
            settings=settings,
            llm=build_llm(settings),
            registry=build_registry(settings, args.simulate_failure),
            trace=Trace(verbose=args.verbose),
        )
        report = controller.run(args.goal)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (StructuredOutputError, LLMProviderError, PlanValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.output:
        try:
            write_report(report, Path(args.output))
        except OSError as exc:
            print(f"Error: could not write report: {exc}", file=sys.stderr)
            return 1
        print(f"[OUTPUT] {args.output}")

    return 0 if report.status == "success" else 1
