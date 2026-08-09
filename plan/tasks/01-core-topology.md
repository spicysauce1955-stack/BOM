# Task 01 — Core + topology
Goal: units/ids/tolerances; Node/Run/events model; stationing; ground(s); corner classification; anchors + re-anchoring transform.
Rationale: physical source of truth all else depends on. Dependencies: 00.
Inputs: ADR-0002/0003, domain-model.md. Outputs: fenceai/core, fenceai/topology + tests.
Interfaces: Topology/Run/PointEvent/IntervalEvent/Anchor Pydantic models; station math functions.
Acceptance: station math exact in int mm; events survive vertex edits proportionally; corner classification with override event; ground interpolation.
Tests: unit + property (station roundtrip, anchor invariance). Non-goals: arcs, Shapely.
Validation: uv run pytest tests/topology -q
