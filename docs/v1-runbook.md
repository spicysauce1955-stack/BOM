# V1 runbook

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/).

## Install & test

```bash
uv sync                    # creates .venv with pinned deps
uv run pytest -q           # full suite, all offline (see CLAUDE.md for counts)
uv run pytest tests/scenarios -q   # golden scenarios S01-S14 + invariants (release gate)
```

## Run

```bash
FENCEAI_IDENTITY=dev uv run uvicorn fenceai.api.app:app --reload
# open http://localhost:8000
```

`FENCEAI_IDENTITY` has no default — the app refuses to boot without it. `dev` needs no
Google. With `FENCEAI_DEV_USER` set, the app opens AS that address; with it unset there is
no code default, so the page opens on the persona picker and you choose. `.env.example`
sets it to `admin@example.com`, which is why the step below is worth doing first.

Configuration: copy `.env.example` to `.env` in the repo root and fill in your
values (easiest way to set the Anthropic key). The real `.env` is gitignored;
real environment variables always override it.

Environment:

| Var | Default | Meaning |
|---|---|---|
| `FENCEAI_DB` | `fenceai.db` | SQLite path (`:memory:` for throwaway) |
| `FENCEAI_AI` | `stub` | `claude` opts into the live interpreter (needs `ANTHROPIC_API_KEY`); anything else = deterministic stub |
| `FENCEAI_AI_MODEL` | `claude-opus-5` | model for the Claude adapter |
| `FENCEAI_IDENTITY` | **none** | `dev` \| `iap`. No default on purpose: the app refuses to boot rather than guess who may in |
| `FENCEAI_DEV_USER` | none | `dev` only — the address a bare `uvicorn` opens as. Unset, the page opens on the picker |
| `FENCEAI_IAP_AUDIENCE` | none | `iap` only, and required with it — without it `aud` goes unchecked and an assertion Google minted for another service is accepted |
| `FENCEAI_BOOTSTRAP_ADMIN` | none | admits one named address as admin while NO admin is active. Load-bearing for recovery, not just first deploy: see ADR-0013 |

First start seeds the demo catalog and knowledge base automatically.

## Container and Postgres

```bash
docker compose up -d --build --wait
# open http://localhost:8080
```

The app listens on `http://localhost:8080` by default; set `FENCEAI_COMPOSE_PORT`
to move it. To look inside the database the stack is using:

```bash
docker compose exec db psql -U fenceai fenceai
```

`docker compose down -v` tears down both containers AND the `pgdata` volume,
so the next `up` starts from an empty database rather than one the app, or an
earlier smoke run, has already seeded. Before an attached browser run this is
not merely tidiness — **without it, checks fail.** `tools/ui_smoke.py:2805`
takes a queue job and then `wait_for`s
`document.querySelectorAll('.queue-take').length < 2`; each run leaves one
takeable job behind, so a second run against the same volume never satisfies
that wait, and `wait_for` returns falsy rather than raising, so the failure
surfaces downstream and confusingly. `tools/ui_smoke.py:8944` retires
`K-MAXSPAN/1`, which a second run cannot retire again. A fresh database is a
precondition for an attached run, not an optimization.

To point the 646 browser checks at the container instead of a bare `uvicorn`:

```bash
FENCEAI_SMOKE_BASE_URL=http://localhost:8080 \
  uv run --with websocket-client python tools/ui_smoke.py
```

## 10-minute walkthrough (exercises most of V1)

0. **Language**: the UI opens in Hebrew (RTL). The עב/EN button in the header
   switches languages; the map canvas and side view never mirror.
1. **Draw** (✏️ tool): click on the canvas to place dots (snapped to grid/dots/45°);
   **Enter or double-click finishes, Esc cancels** — Finish/Cancel buttons appear
   while drafting. Multiple clicks before finishing create corners (shared nodes).
2. **Edit** (⬚ Select tool): click a run → drag square handles to move dots, drag
   the ghost midpoint to insert a corner, Delete removes a dot. Click the run's
   length label and type an exact mm value. **Ctrl+Z / Ctrl+Shift+Z undo/redo any
   gesture.**
3. **Events on canvas**: pick the 🚪 gate / 🧱 base / ⛰️ ground / 📏 height / 📍 pin
   tool, click a position on a run, fill the popover. The selected run's events are
   listed (and deletable) in the side panel.
4. **Generate strategy** → overlay shows posts (cyan = reinforced gate posts,
   red ring = masonry mount, red = base-transition post), spans, warnings below —
   localized per the current language.
4b. **Side view**: the panel below the plan shows the selected run unrolled —
   ground line (drag its dots vertically, double-click to add samples), wall tops
   (drag endpoints), dashed height intent, and after generation the actual
   stepped/raked panels and posts. 1×/5× toggles vertical exaggeration.
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

UI smoke suite (drives the real browser; run at milestones):

```bash
uv run --with websocket-client python tools/ui_smoke.py
```

## Troubleshooting

- `422 generation failed: no max_span_mm knowledge...` — the hard span constraint was
  retired; add a version via the Knowledge tab (`set_param max_span_mm`).
- Empty UI project list: the app auto-creates `demo project` on first load; check the
  server log if not.
- Delete the `FENCEAI_DB` file to reset all state (it reseeds on next start).
- A container that exits at boot with a nonzero code and empty **stdout**,
  and `FENCEAI_DB` unset: this is **expected**, not a bug — `docker logs`
  shows a full traceback on **stderr**
  (`sqlite3.OperationalError: unable to open database file`), so the failure
  is loud, just not on the stream you might check first. `/app` is
  root-owned in the image (it is created before the `USER fenceai` switch),
  so the SQLite fallback path has nowhere to write and fails rather than
  succeeding silently into the container's own writable layer — which would
  let a salesperson's fence be lost on the very next revision, since that
  layer does not survive a redeploy. The fix is to set `FENCEAI_DB` to a
  mounted path or a Postgres URL. **Do not "fix" this by making `/app`
  writable** — that is the failure mode this behaviour exists to prevent,
  not an oversight.
- A container that exits at boot naming `admin@example.com` (or the other
  seeded dev addresses) is `identity/dev.py:dev_seed_lockout` refusing to
  serve a dev-seeded database under `FENCEAI_IDENTITY=iap`. The fix is a
  fresh `FENCEAI_DB` or removing those rows, never a code change — see
  ADR-0013's Consequences and `docs/reviews/2026-09-23-slice-2-carried-findings.md`
  finding 3.
