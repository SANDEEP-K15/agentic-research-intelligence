"""Research pipeline helpers outside retrieval/selection ranking."""

from __future__ import annotations

from app.models import Finding, SearchResult, SynthesisDraft
from app.research.selection import (
    build_search_queries,
    deduplicate,
    evidence_text,
    is_disqualified_for_time_sensitive,
    prepare_candidates,
    publication_in_window,
    publication_outside_window,
    score_result,
    select_candidates,
)

__all__ = [
    "build_search_queries",
    "deduplicate",
    "evidence_text",
    "ground_findings",
    "is_disqualified_for_time_sensitive",
    "prepare_candidates",
    "publication_in_window",
    "publication_outside_window",
    "score_result",
    "select_candidates",
    "sources_for",
    "diversity_expression",
]


def diversity_expression(result_count: int, unique_domains: int) -> str:
    if result_count <= 0:
        return "0"
    return f"({unique_domains} / {result_count}) * 100"


def _url_key(url: str) -> str:
    return url.strip().rstrip("/").lower()


def ground_findings(
    draft: SynthesisDraft,
    selected: list[SearchResult],
    limit: int,
) -> tuple[list[Finding], list[str]]:
    allowed = {_url_key(result.url): result.url for result in selected}
    findings: list[Finding] = []
    dropped = 0
    for item in draft.findings:
        urls: list[str] = []
        for url in item.source_urls:
            canonical = allowed.get(_url_key(url))
            if canonical and canonical not in urls:
                urls.append(canonical)
        if not urls:
            dropped += 1
            continue
        findings.append(
            Finding(
                title=item.title.strip(),
                summary=item.summary.strip(),
                why_it_matters=item.why_it_matters.strip(),
                source_urls=urls,
            )
        )
        if len(findings) >= limit:
            break

    notes = [note.strip() for note in draft.limitations if note.strip()]
    if dropped:
        notes.append(
            f"{dropped} model finding(s) were dropped because they did not cite a retrieved source."
        )
    return findings, notes


def sources_for(findings: list[Finding], selected: list[SearchResult]) -> list:
    from app.models import Source

    by_url = {result.url: result for result in selected}
    sources: list[Source] = []
    seen: set[str] = set()
    for finding in findings:
        for url in finding.source_urls:
            result = by_url.get(url)
            if result is None or url in seen:
                continue
            seen.add(url)
            sources.append(Source(title=result.title, url=result.url, domain=result.domain))
    return sources
