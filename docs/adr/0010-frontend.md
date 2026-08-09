# ADR-0010: Static vanilla-JS + SVG frontend served by FastAPI; no build step

Status: accepted · 2026-08-09

## Decision
V1 UI is a static ES-module page served by FastAPI StaticFiles: SVG canvas for topology
drawing (click-place vertices, polyline runs, interval/point event editing) with the
generated strategy rendered as an overlay; side panels for decisions/explanations, knowledge,
BOM, review queue. Server-authoritative: frontend renders JSON the engine computed; no domain
logic in JS. No React/bundler; Konva (MIT) is the fallback if overlay density demands it;
tldraw rejected (proprietary license).

## Rationale
Research D: fence-scale object counts are far below SVG limits; all complexity budget goes to
the domain; mission §13 allows pragmatic visuals. Revisit trigger: genuinely complex UI state
(collaborative editing, heavy review filtering).
