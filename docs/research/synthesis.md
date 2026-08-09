# Research synthesis — decisions

*Principal-architect synthesis of Researchers A–D (2026-08-09). Each decision has an ADR.*

The four reports converge with no contradictions. Decisions:

| # | Decision | Source | ADR |
|---|---|---|---|
| 1 | Python 3.12 modular monolith; uv; pytest; FastAPI; Pydantic v2 | D | ADR-0001 |
| 2 | Integer millimeters / integer cents everywhere at rest; float64 transient only; two named tolerances | A, C | ADR-0002 |
| 3 | Topology = shallow graph (nodes + run-edges of int-mm vertex polylines); derived stationing; varying attributes as station point/interval events; horizontal/vertical split with derived top-line | A | ADR-0003 |
| 4 | Strategy generation = pure deterministic function, full regeneration; overrides = patch list anchored (run_id, station, kind); orphaned overrides surfaced, never silently dropped | A | ADR-0004 |
| 5 | Rules as data: typed condition/action ASTs (Pydantic discriminated unions), hand-rolled tree-walking evaluator emitting trace natively; no rule-engine dependency | B | ADR-0005 |
| 6 | Precedence = authority tier → scope specificity → recency; `defeated_by` recorded; ties surface conflict objects; violated hard constraint = generation failure | B | ADR-0005 |
| 7 | Knowledge: immutable version records + append-only audit; generation runs stamp (object, version) snapshot set; PROV vocabulary; no event sourcing; no embeddings in V1 | B | ADR-0006 |
| 8 | Decision graph: append-only node+edge records per generation run, acyclic by ordinal construction; dynamic dependency capture; impact analysis = reverse walk + regenerate-and-diff | B | ADR-0006 |
| 9 | Fulfillment: FFD/BFD cut planner w/ kerf-aware capacity, remnant policy, LP-bound optimality certificate; closed-form span layout; dual-quantity BOM lines w/ int-ratio UoM; pegging; lexicographic objective tiers; no solver dep (CP-SAT behind interface later) | C | ADR-0007 |
| 10 | Persistence: SQLite (stdlib), document-style tables + append-only version/decision tables; no Postgres until a concrete multi-tenant/scale need | B (adapted) | ADR-0008 |
| 11 | AI: capability Protocols speaking domain types; ClaudeInterpreter via messages.parse(); deterministic StubInterpreter default; enum confidence; verbatim source_text; 2-attempt retry; templated explanations first, optional LLM polish with node-citation validation | D | ADR-0009 |
| 12 | Frontend: static vanilla-JS + SVG served by FastAPI; no build step; tldraw rejected (license) | D | ADR-0010 |
| 13 | Geometry deps: Shapely optional-only — V1 fence math (polyline length, interpolation) is trivial in int-mm; avoid the dep until arcs/offsets appear | A (adapted) | ADR-0003 |

Notable adaptations from researcher recommendations, with rationale:
- **SQLite over Postgres** (B assumed Postgres): mission technology discipline forbids
  infrastructure without concrete use case; all patterns (recursive CTEs, JSON columns,
  append-only tables) port unchanged; repository layer isolates the swap.
- **No Shapely in V1 core** (A recommended adopt): our runs are straight polylines in int mm;
  `line_locate/interpolate` are ~10 lines of exact integer math. Shapely enters when plan
  arcs or polygon ops appear. This keeps the deterministic core dependency-free and exact.

Cross-cutting pitfalls adopted as test requirements: re-stationing/event-anchoring semantics
must be explicit; chord vs slope length explicit on every quantity; kerf off-by-one; remnant
threshold boundaries; determinism (double-run tests); no float lengths in persistence.
