# Task 06 — Overrides
Goal: anchored Override model, pin/suppress/force directives honored by generate(), orphan detection on topology change.
Dependencies: 04. Acceptance: S11 passes; orphaned override produces warning not silent drop; override cited as decision input.
Validation: uv run pytest tests/strategy/test_overrides.py tests/scenarios/test_s11* -q
