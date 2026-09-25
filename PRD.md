# PRD — Research Intelligence Agent

## 1. Product Overview

Build a production-quality but appropriately scoped Agentic AI system called **Research Intelligence Agent**.

The system accepts a high-level natural-language research goal, autonomously converts it into a structured execution plan, uses multiple tools to gather and process live information, handles tool failures through recovery, and produces a structured final research report.

The project is being developed as an AI Engineer take-home assignment. The implementation should demonstrate good engineering judgment, clean architecture, reliable tool orchestration, error handling, testing, and documentation.

The system must be a real agentic workflow, not a simple LLM chatbot.

---

# 2. Assignment Goal

The system must be able to:

1. Accept a high-level natural-language goal.
2. Understand and decompose the goal into actionable steps.
3. Display a concise execution plan before acting.
4. Execute the plan step-by-step.
5. Use at least two distinct tools.
6. Detect and recover from a deliberately induced failure.
7. Produce a structured final report.
8. Clearly show what happened during execution.
9. Be testable without requiring live external services.
10. Be easy for another engineer to install and understand.

---

# 3. Selected Use Case

Build a **Research Intelligence Agent**.

Example user request:

> Research the top 3 developments in generative AI from the last week and summarize why each development matters.

The system should not be hard-coded to only generative AI.

Other valid inputs should work, for example:

- Research the latest developments in AI agents.
- Research recent cybersecurity developments.
- Research recent developments in autonomous vehicles.
- Research recent developments in cloud computing.
- Research the top 3 developments in robotics from the last week.

The agent should determine the topic, requested number of findings, and time range from the user's natural-language request when possible.

---

# 4. User Interface

Use a CLI.

Basic usage:

```bash
python -m app "Research the top 3 developments in generative AI from the last week."