# Task 03 — Knowledge
Goal: condition AST, action types, evaluator with trace, precedence (authority→specificity→recency), conflicts, immutable versions, snapshot sets, demo KB, example-tests runner.
Rationale: ADR-0005/0006; knowledge-system.md. Dependencies: 00.
Acceptance: firing trace with defeated_by; tie → Conflict object; hard-violation → failure path; version insert-only; examples executed as tests; S13 core semantics.
Non-goals: authoring UI, static conflict UI (function only). Validation: uv run pytest tests/knowledge -q
