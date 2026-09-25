# Failed live run — insufficient recent evidence

- **Captured:** 2026-09-25
- **Command:** `python -m app "Research the top 3 developments in generative AI from the last week."`
- **Exit code:** 1
- **Report status:** `failed`

```text
[GOAL]
Topic: generative AI developments
Time range: last week
Requested items: 3
Output: summary

[PLAN]

1. Search the web for the top developments in generative AI from the last week.
2. Normalize the retrieved web search data about generative AI developments into a consistent format.
3. Select the top 3 most significant developments in generative AI from the normalized data.
4. Calculate the impact metrics or publication frequency statistics for the chosen generative AI developments.
5. Synthesize the final summary report detailing the top 3 developments in generative AI from the last week.

[STEP 1/5]
[TOOL] web_search
[TOOL] web_search
[TOOL] web_search
[ERROR] EmptySearchError
[RECOVERY] Attempting recovery...
[RECOVERY] Retry 1/2
[TOOL] web_search
[ERROR] EmptySearchError
[RECOVERY] Attempting recovery...
[RECOVERY] Retry 2/2
[TOOL] web_search
[TOOL] web_search
[TOOL] web_search
[SUCCESS] 20 results retrieved from 5 queries

[STEP 2/5]
[STAGE] normalize
[SUCCESS] 16 unique results with page evidence

[STEP 3/5]
[STAGE] select
[ERROR] PipelineError: insufficient evidence: retrieved pages did not describe a concrete recent development

[STEP 4/5]
[TOOL] calculator
[SKIPPED] earlier step failed

[STEP 5/5]
[STAGE] synthesize
[SKIPPED] earlier step failed

[REPORT]
Status: failed
Goal: Research the top 3 developments in generative AI from the last week.

Findings:
  None.

Sources:
  None.

Tools used: web_search
Retries: 0
Failures recovered: 0
Limitations:
- Search coverage is limited to the public results returned for a few focused queries.
- Candidate selection scores topic overlap, extracted publication dates, event wording in page evidence, and source quality. It is a heuristic, not an objective ranking.
- The calculator output is the percentage of normalized results that come from distinct domains. It does not measure importance.
- Recency was requested as last week and passed to search as a time filter.
- The run did not produce findings grounded in retrieved sources.
```
