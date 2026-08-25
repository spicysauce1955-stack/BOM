# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Fence AI** — visual fence-construction topology → explainable strategy generation → BOM
optimization, with expert-in-the-loop learning. Python 3.12 modular monolith
(`src/fenceai/`), FastAPI + Pydantic v2, SQLite. Frontend: vanilla ES modules + SVG
(no build step), Hebrew-first RTL with an EN toggle.

## Commands

- `uv sync` — install deps (creates `.venv`)
- `uv run pytest -q` — full test suite; single test: `uv run pytest tests/path/test_x.py::test_name -q`
- `uv run pytest tests/scenarios -q` — golden scenarios S01–S14 + invariants (the release gate)
- `uv run uvicorn fenceai.api.app:app --reload` — run the app (UI at http://localhost:8000, opens in Hebrew)
- `uv run --with websocket-client python tools/ui_smoke.py` — browser smoke suite (CDP-driven; run at UI milestones; needs google-chrome)

## Where truth lives

- `docs/product/architecture-foundation-v0.1.md` — the product foundation; §15 lists the
  non-negotiable properties every change must respect.
- `docs/architecture/` + `docs/adr/` — design and decisions. Change code and these docs
  together, or not at all.
- `docs/scenarios/golden-scenarios.md` ⇄ `tests/scenarios/` — the behavioral contract.
  Never silently reconcile a disagreement between them (use the `golden-scenarios` skill).
- `docs/superpowers/specs/` + `docs/superpowers/plans/` — feature specs and implementation
  plans (UI v2 lives there). `docs/reviews/` — review verdicts and dispositions.
- `plan/current-status.md` — live progress; update at each checkpoint.

## Durable principles — backend (foundation §15 + ADRs)

- **Integer millimeters and cents at rest; float only transient** (ADR-0002). Exactly two
  named tolerances live in `fenceai/core/units.py`.
- **`generate()` is pure and deterministic**; overrides are patches anchored to
  `(run_id, station, kind)`, never to generated element identity (ADR-0004).
- **Hard constraint ≠ preference ≠ objective ≠ override** — distinct types, distinct handling.
- **Rules are data** (typed ASTs + owned evaluator, ADR-0005); no rule may exist only in a
  prompt. Knowledge versions are immutable; runs stamp their snapshot set.
- **The decision graph is the explanation**; prose is rendered from it via per-language
  templates (`decisions/explain.py` TEMPLATES — en/he must stay key-identical; a `defeated`
  edge cites the LOSING version). Every element, requirement, and BOM line traces through it.
- **Verbatim human text is immutable**; AI interpretations are proposals until confirmed;
  knowledge candidates are inert until approved.
- **No AI inside deterministic computation** — AI sits behind the ports in `fenceai/ai/`;
  the stub keeps the whole system working offline (it understands the demo vocabulary in
  English AND Hebrew; keep it capped — it must not become a second rule engine).
- **Read models are derived, never stored** (`fenceai/report/`): the structure sheet is a
  pure function of `(topology, strategy, requirements, bom)` whose parts come from
  INVERTING pegs — it must never recompute a quantity, and it refuses to lay a run out
  over a topology it was not generated from (409 `topology_changed`).
- User-visible warnings/critiques carry `code + params` (English `message` is fallback only);
  a new code needs `warning.<code>`/`critique.<code>` entries in BOTH locale bundles —
  `tests/web/test_locale_bundles.py` enforces this.

## Durable principles — frontend (`src/fenceai/web/static/`)

- ES modules under `js/` communicate ONLY via `state.js` (events + exports); no module
  touches another's DOM subtree. No framework, no build step, no CDN (fonts are bundled).
- **Mutation discipline, always in this order**: `pushSnapshot(label)` → mutate
  `state.project` → `saveTopology()`. Undo/redo restore locally and PUT a NEW forward
  revision — server revisions never go backwards. Non-user changes never push history;
  use `reloadProject()` (not `openProject`) after non-topology mutations or you wipe the
  user's undo stack.
- **Base-top geometry is pure**: the side view's base actions (height, level,
  match-neighbours, add-step) are point-list transforms in `base-top.js` with no DOM
  or state — `profile.js` only wires them to buttons. Keep new profile math there so it
  stays testable in node (`tests/web/test_base_top_module.py`).
- **Anchors are segment-local**: author with `geom.anchorFor`, resolve with
  `geom.stationOfAnchor` — these mirror backend `make_anchor`/`anchor_station` exactly.
  Never read `anchor.offset_mm` as a station.
- **Display units** (mm | cm) are a presentation preference in `units.js` — convert with
  `toDisplayValue`/`toMm` at the field boundary and render length strings via `tu()`
  (locale strings use `{…_mm}` + `{u}`, never a literal unit). Storage, API payloads, and
  the raw-JSON editors stay int mm; a new length surface must round-trip losslessly.
- **i18n**: every user-visible string goes through `t("key")` (JS) or `data-i18n` (HTML);
  `i18n/he.json` and `en.json` must keep identical key sets. CSS uses logical properties
  only (no left/right); **the plan canvas and profile SVG are NEVER mirrored in RTL**;
  SKUs/ids/dimensions get `.sku`/`.num`/`<bdi>` isolation.
- **XSS**: any user/expert text interpolated into `innerHTML` goes through `esc()`.

## The boundary contract is FROZEN

`docs/integration-contract/contract.md` is a byte-identical copy of the contract in
`fence-rag/docs/integration/`. **Both are frozen at v1.0. Do not edit either.**

- Verify before relying on it: `sha256sum -c docs/integration-contract/contract.sha256`.
  A mismatch means a copy drifted — find the edit, never regenerate the hash.
- Changing a **BINDING** item needs a ratified amendment. The four admissible triggers
  (falsification, unimplementable, scope change, defect) and the five steps are in
  `docs/integration-contract/AMENDING.md`. No `amendments/NNN` file, no change.
- **Registry additions are not amendments** — new part types, warning codes, condition
  dimensions and source classes need no ratification, and routing them through it would
  destroy the property that lets the two teams move at different speeds.
- Internal design — pipeline phases, fact-space layers, read models, extension seams —
  is not the contract's business and changes freely. `docs/superpowers/specs/` owns it.

The failure this prevents does not feel like a violation while it happens: the contract
was revised six times in one session, each time defensibly, and the result was that
neither team could point at a stable document. If you are editing a binding item as a
side effect of other work, that is the thing the freeze exists to stop.

## Project agents & skills

- `architecture-critic` / `test-reviewer` agents: run after slices touching domain
  abstractions or the frontend contracts above, and before declaring milestones done.
- `golden-scenarios` skill: adding/validating scenarios; converting expert corrections
  into regression scenarios.
