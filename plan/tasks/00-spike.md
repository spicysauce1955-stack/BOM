# Task 00 — Architecture spike
Goal: smallest executable spine proving topology → rule eval → strategy → decisions → requirements → BOM.
Rationale: validate abstractions (pure generate(), anchored events, typed rules, pegging) before scaling (mission §11).
Dependencies: none. Inputs: docs/architecture/*, golden scenarios S01/S07/S08.
Outputs: package skeleton, minimal models, spike tests. Interfaces: generate(), derive_requirements(), fulfill() signatures per system-design.md.
Acceptance: S01 span layout + post count, S07 cut plan invariants, S08 package rounding pass; decision graph traces S01 posts to K-MAXSPAN/K-EQUAL; determinism double-run test.
Tests: tests/spike/. Docs: none beyond status. Non-goals: API, UI, persistence, AI.
Validation: uv run pytest tests -q
