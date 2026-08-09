# ADR-0001: Python 3.12 modular monolith with uv, FastAPI, Pydantic v2, pytest

Status: accepted · 2026-08-09

## Decision
Single Python 3.12 package `fenceai` structured as a modular monolith (`topology`, `catalog`,
`knowledge`, `strategy`, `decisions`, `demand`, `fulfillment`, `ai`, `store`, `api` modules
with explicit interfaces). Tooling: `uv` for env/deps, `pytest` for tests, FastAPI + uvicorn
for the API, Pydantic v2 for all domain schemas (shared by API and LLM validation).

## Rationale
- Domain is computation-heavy, UI-light; Python maximizes velocity for the deterministic core
  and has first-class Anthropic SDK + Pydantic structured-output support (Research D).
- One schema language end-to-end (domain, API, LLM output) removes a whole class of drift.
- Mission §18: modular monolith, explicit interfaces, no premature services.

## Consequences
Frontend is a static JS page (ADR-0010), so no shared types with a TS codebase — acceptable
because the frontend is a thin view over server-authoritative JSON.
