"""Ask the model to write findings that cite only retrieved sources."""

from __future__ import annotations

import json

from app.errors import LLMProviderError, PipelineError, StructuredOutputError
from app.llm.protocol import LLMClient
from app.models import SynthesisDraft
from app.research.context import ResearchContext
from app.research.process import ground_findings

_SYSTEM = (
    "You write a research brief from supplied sources only. "
    "Every finding must copy source_urls exactly from the provided URLs. "
    "Do not invent publications, numbers, or URLs. "
    "If the sources do not support a claim, leave it out. "
    "Describe only announcements, launches, or events that the snippet states. "
    "Do not turn a general explainer into a dated development. "
    "why_it_matters must follow from the snippet, and you must say when the snippet is thin. "
    "The source-diversity figure is a description of the retrieved set, not a ranking. "
    "Return at most the requested number of findings."
)


def render_sources(context: ResearchContext) -> str:
    payload = [
        {
            "title": result.title,
            "url": result.url,
            "domain": result.domain,
            "snippet": result.snippet,
            "page_title": result.page_title,
            "publication_date": result.publication_date,
            "page_excerpt": result.page_excerpt,
        }
        for result in context.selected
    ]
    return json.dumps(payload, ensure_ascii=False)


class Synthesizer:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def __call__(self, context: ResearchContext) -> str:
        if not context.selected:
            raise PipelineError("no search results were available to synthesize")
        calculation = "not computed"
        if context.calculation is not None:
            calculation = (
                f"{context.calculation.value} from expression {context.calculation.expression}. "
                f"{context.calculation.summary}"
            )
        try:
            draft = self._llm.generate_structured(
                system=_SYSTEM,
                user=(
                    f"Goal: {context.goal}\n"
                    f"Topic: {context.analysis.topic}\n"
                    f"Time range: {context.analysis.time_range}\n"
                    f"Requested findings: {context.analysis.requested_items}\n"
                    f"Source diversity statistic: {calculation}\n"
                    f"Sources:\n{render_sources(context)}"
                ),
                schema=SynthesisDraft,
            )
        except (StructuredOutputError, LLMProviderError) as exc:
            raise PipelineError(f"synthesis failed: {exc}") from exc
        findings, notes = ground_findings(draft, context.selected, context.analysis.requested_items)
        context.findings = findings
        context.synthesis_notes = notes
        if not findings:
            detail = "; ".join(notes) if notes else "model returned no findings that cite a retrieved source"
            raise PipelineError(detail)
        return f"{len(findings)} findings generated"
