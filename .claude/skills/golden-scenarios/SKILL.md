---
name: golden-scenarios
description: Procedure for adding, changing, or validating Fence AI golden scenarios (S01–S14 and beyond). Use when implementing a scenario, when an expert correction should become a regression scenario, or when a scenario test disagrees with docs/scenarios/golden-scenarios.md.
---

# Golden scenario workflow

Golden scenarios are the contract between the architecture documents and the code. The doc
(`docs/scenarios/golden-scenarios.md`) is authoritative for *expected behavior*; the tests
(`tests/scenarios/`) are authoritative for *actual behavior*. They must never silently diverge.

## Adding or implementing a scenario

1. Read the scenario definition in `docs/scenarios/golden-scenarios.md`. If it lacks concrete
   numbers, add them to the doc first (integer mm), then implement.
2. Build the fixture with the shared demo catalog/knowledge helpers in
   `tests/scenarios/conftest.py` — never duplicate catalog literals in scenario tests.
3. Write the test as a full-spine walk: topology → generate strategy → decisions →
   requirements → fulfillment → BOM. Assert concrete numbers at each stage, plus the
   decision-graph citations the doc names (e.g. "cites K-MAXSPAN").
4. Run `uv run pytest tests/scenarios -q`. A scenario test may not be marked skip/xfail at
   merge time unless the roadmap explicitly defers that scenario.

## When a test result disagrees with the doc

Do not edit the expected numbers to match the code. Decide which is wrong:
- Code wrong → fix code.
- Doc wrong (expectation was miscalculated) → fix doc **and** record why in the commit message.
- Architecture cannot express the scenario without hacks → stop; raise an architecture finding
  (this is the scenario system doing its job) and fix the model before scaling.

## Converting an expert correction into a regression scenario

When the correction workflow produces a significant correction (S12-style):
1. Add `S<next-number>` to the doc: topology, correction, expected override/candidate behavior.
2. Add the matching test under `tests/scenarios/`.
3. Reference the originating correction ID in both.

## Validation command

`uv run pytest tests/scenarios -q` — all scenarios plus the cross-scenario invariant suite
(`tests/scenarios/test_invariants.py`).
