# V1 runbook

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/).

## Install & test

```bash
uv sync                    # creates .venv with pinned deps
uv run pytest -q           # full suite (~140 tests, all offline)
uv run pytest tests/scenarios -q   # golden scenarios S01-S14 + invariants (release gate)
```

## Run

```bash
uv run uvicorn fenceai.api.app:app --reload
# open http://localhost:8000
```

Environment:

| Var | Default | Meaning |
|---|---|---|
| `FENCEAI_DB` | `fenceai.db` | SQLite path (`:memory:` for throwaway) |
| `FENCEAI_AI` | `stub` | `claude` opts into the live interpreter (needs `ANTHROPIC_API_KEY`); anything else = deterministic stub |
| `FENCEAI_AI_MODEL` | `claude-opus-5` | model for the Claude adapter |

First start seeds the demo catalog and knowledge base automatically.

## 10-minute walkthrough (exercises most of V1)

1. **Draw**: on *Topology & Strategy*, click twice on the canvas ~5 m apart,
   double-click to finish → a run appears. (Click more times before finishing for
   corners — each click is a shared node.)
2. **Gate**: in *Run editing → Gate*, station `2000`, width `1000`, Add gate.
3. **Mixed base**: *Base interval* start `4000` end `5000` surface `masonry wall`.
4. **Generate strategy** → overlay shows posts (cyan = reinforced gate posts,
   red ring = masonry mount, red = base-transition post), spans, warnings below.
5. **Explain**: click any post → Inspector shows the decision trail with the
   governing knowledge versions.
6. **Override**: *Pin post* at station `1000`, Generate again → pinned post (amber
   ring), layout re-flows around it.
7. **BOM tab** → purchase lines with engineering vs purchase quantities, cut plans
   per bar with kerf and reusable remnants, total price.
8. **Inventory tab** → add
   `{"items":[{"id":"rem1","sku":"RAIL-3000","kind":"remnant","length_mm":1250,"qty":1}]}`,
   save, Generate → BOM allocates the remnant (one fewer new bar).
9. **Annotate**: *Annotations* tab → target the run, text
   `keep the top aligned with the neighbour (approx. 1750)` → *Interpret with AI* →
   confirm the proposed `top_line` intent → Generate → span heights become 1750 and
   cite the confirmed event.
10. **Teach**: click a post → record a correction with comment
    `always use existing foundations when within 300 mm` → *Review queue* →
    *Propose knowledge from corrections* → approve (or approve-narrower/reject).
    Approved knowledge appears versioned in the *Knowledge* tab.

## Troubleshooting

- `422 generation failed: no max_span_mm knowledge...` — the hard span constraint was
  retired; add a version via the Knowledge tab (`set_param max_span_mm`).
- Empty UI project list: the app auto-creates `demo project` on first load; check the
  server log if not.
- Delete the `FENCEAI_DB` file to reset all state (it reseeds on next start).
