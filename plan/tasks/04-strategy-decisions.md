# Task 04 — Strategy + decisions
Goal: generate() pipeline (fixed posts, sub-run span layout, vertical behavior, mounting, selection), GraphBuilder, warnings, Tier-1 explanations.
Rationale: the reasoning engine. Dependencies: 01,02,03.
Acceptance: S01–S06 + S13 scenario tests pass with pinned numbers and citation assertions; every element traced; determinism test.
Non-goals: overrides (06), AI (07). Validation: uv run pytest tests/strategy tests/scenarios -q
