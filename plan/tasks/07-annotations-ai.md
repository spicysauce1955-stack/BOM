# Task 07 — Annotations + AI interpretation
Goal: Annotation records; AI ports; StubInterpreter; confirmation flow (intent → event/knowledge with provenance); Claude adapter behind config; contract tests.
Dependencies: 01,03,04. Acceptance: S14 passes offline via stub; verbatim text preserved; unconfirmed intents don't affect generation; malformed AI output rejected by schema test.
Validation: uv run pytest tests/ai tests/scenarios/test_s14* -q
