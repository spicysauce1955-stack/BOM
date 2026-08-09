# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Fence AI** — visual fence-construction topology → explainable strategy generation → BOM
optimization, with expert-in-the-loop learning. Python 3.12 modular monolith
(`src/fenceai/`), FastAPI + Pydantic v2, SQLite, static SVG/JS frontend.

## Commands

- `uv sync` — install deps (creates `.venv`)
- `uv run pytest -q` — full test suite; single test: `uv run pytest tests/path/test_x.py::test_name -q`
- `uv run pytest tests/scenarios -q` — golden scenarios S01–S14 + invariants (the release gate)
- `uv run uvicorn fenceai.api.app:app --reload` — run the app (UI at http://localhost:8000)

## Where truth lives

- `docs/product/architecture-foundation-v0.1.md` — the product foundation; §15 lists the
  non-negotiable properties every change must respect.
- `docs/architecture/` — system/domain/knowledge/decision/AI/fulfillment design; `docs/adr/` —
  decisions with rationale. Change code and these docs together, or not at all.
- `docs/scenarios/golden-scenarios.md` — the behavioral contract; `tests/scenarios/` mirrors
  it. Never silently reconcile a disagreement between them (use the `golden-scenarios` skill).
- `plan/current-status.md` — live progress; update at each checkpoint.

## Durable principles (short form of foundation §15 + ADRs)

- **Integer millimeters and cents at rest; float only transient** (ADR-0002). Exactly two
  named tolerances live in `fenceai/core/units.py`.
- **`generate()` is pure and deterministic**; overrides are patches anchored to
  `(run_id, station, kind)`, never to generated element identity (ADR-0004).
- **Hard constraint ≠ preference ≠ objective ≠ override** — distinct types, distinct handling;
  conflation is an architecture bug.
- **Rules are data** (typed ASTs + owned evaluator, ADR-0005); no rule may exist only in a
  prompt. Knowledge versions are immutable; runs stamp their snapshot set.
- **The decision graph is the explanation**; prose is rendered from it. Every strategy
  element, requirement, and BOM line must trace back through it.
- **Verbatim human text is immutable** wherever it appears; AI interpretations are proposals
  until a human confirms; knowledge candidates are inert until approved.
- **No AI inside deterministic computation** — AI sits behind the ports in `fenceai/ai/`;
  the stub implementation must keep the whole system working offline.

## Project agents & skills

- `architecture-critic` / `test-reviewer` agents: run after the spike, after slices touching
  domain abstractions, and before declaring milestones done.
- `golden-scenarios` skill: procedure for adding/validating scenarios and converting expert
  corrections into regression scenarios.
