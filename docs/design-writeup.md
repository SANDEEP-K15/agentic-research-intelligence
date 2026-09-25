# Technical write-up

## Problem

Researchers and engineers often start from a vague question (“top developments in X from the last week”) and need a **sourced, structured brief**, not a chat transcript. The assignment asks for an agent that **plans**, **calls tools**, **shows its work**, **recovers from failures**, and returns a **validated report**—without hiding orchestration inside a framework.

## Architecture

A thin **CLI** loads settings and wires `AgentController` to Gemini (`LLMClient`) and a **tool registry**. The controller runs four phases in order: **goal analysis** (structured `GoalAnalysis`), **planning** (structured `PlanDraft`, then canonicalization to five execution steps), **execution** (engine + recovery), and **reporting** (`ResearchReport`).

The execution engine is sequential. Stages `normalize`, `select`, and `synthesize` are implemented in `app/research/` and invoked by name from the plan. The model never calls tools directly; it only fills schemas.

## Orchestration

1. Print `[GOAL]` from analysis.
2. Print `[PLAN]` (possibly adjusted; limitations note repairs).
3. For each step, emit `[STEP n/5]`, tool or `[STAGE]` lines, and `[SUCCESS]` / `[ERROR]` / `[SKIPPED]`.
4. Emit `[REPORT]` with status, findings, sources, limitations.

Time-bounded goals trigger **five** focused `web_search` queries (merged and deduped). `normalize` enriches promising URLs with lightweight HTML evidence (publication meta, excerpt). `select` applies topic, recency, event, and source heuristics. `synthesize` asks the model for findings, then **drops any citation not in the shortlist**.

## Tools

| Tool | Role |
| --- | --- |
| **Web search** | `ddgs` (`duckduckgo` backend, optional `auto` fallback). Normalizes title, URL, snippet, domain. Passes recency as `timelimit` (`d`/`w`/`m`/`y`). |
| **Calculator** | Parses arithmetic via `ast` (no `eval`). Computes source-domain diversity: `(unique domains / normalized count) × 100` for transparency, not ranking. |

Registry operations: `register`, `get`, `list_tools`.

## Error handling and recovery

- **Simulated failure:** first search raises `SimulatedTimeoutError` when `--simulate-failure` is set.
- **Retryable:** search timeouts, network errors, empty provider results (`EmptySearchError`), simulated timeout—up to `MAX_RETRIES` (default 2).
- **Not retryable:** bad calculator input, exhausted recovery, non-retryable LLM errors.
- **Synthesis:** provider errors surface with type and message in the trace; grounding removes uncited URLs.
- **Partial / failed status:** fewer grounded findings than requested → `partial`; no candidates or critical step failure → `failed`.

## Limitations

- Evidence is **public search results** plus **partial page HTML** for selected URLs—not full browser rendering or paywalled content.
- Recency uses search `timelimit`, extracted `publication_date`, and event-linked dates in text; strict rules can yield **no** qualifying candidates even when many URLs are retrieved.
- Ranking is heuristic (topic tokens, event wording, source lists), not an objective “top N.”
- Live runs depend on Gemini quota and DuckDuckGo availability; outcomes vary by day.
- The pytest suite mocks LLM and search; it does not prove live search quality.

## Future improvements

- Structured trace/event log alongside terminal text.
- Optional caching of page evidence and search results for reproducible demos.
- Richer news APIs where licensing allows.
- Human-in-the-loop approval before synthesis for high-stakes use.
