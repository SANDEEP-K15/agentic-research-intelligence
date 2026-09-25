# Sample run transcripts

These files are **verbatim terminal captures** from live runs on this project (Windows, project root). They are not edited for outcome.

| File | Command | Exit code | Report `status` |
| --- | --- | ---: | --- |
| [partial_run_generative_ai.md](partial_run_generative_ai.md) | `python -m app "Research the top 3 developments in generative AI from the last week."` | 1 | `partial` |
| [simulate_failure_recovery.md](simulate_failure_recovery.md) | Same goal with `--simulate-failure` | 1 | `failed` (select step; recovery still shown) |
| [failed_run_insufficient_evidence.md](failed_run_insufficient_evidence.md) | Same goal without simulation (later run) | 1 | `failed` |

**Note:** During submission prep, no live run produced report status `success` (three grounded in-window findings). That depends on public search results and strict recency/event selection on the day of the run. End-to-end `success` is covered by the pytest suite (mocked LLM and search).

Each transcript header records when the capture was taken and the shell exit code.
