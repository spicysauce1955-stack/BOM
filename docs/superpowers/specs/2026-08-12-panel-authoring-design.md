# Choosing, seeing and authoring a panel

Status: design · 2026-08-12 · supersedes the "Model authoring UI" out-of-scope line in
`2026-08-12-fence-model-design.md:780`

## The complaint, and why it is correct

> "I don't see an option to see the Panel spec and choose a model before the strategy —
> the Model affects the Panel and the Panel affects the materials, sizes and structure.
> What if the user wants to edit, change or add a panel? variant?"

Every clause of that is a true statement about the code as it stands.

- **No choice.** `strategy/generator.py:582-590` hard-codes `legacy_model(...)` per topology
  run, under a comment that says "M-LEGACY until a `fence_model` event exists to pick
  another". No such event exists in `topology/model.py`. There is no `/api/fence-models`
  route, and `variant` and `preset` return **zero hits** across the entire frontend.
- **No sight.** A `PanelSpec` reaches the user only after generation, as two numbers on a
  BOM line. The side view draws a bay as a plain rectangle. Nothing shows what a panel is
  made of before you commit to it.
- **No authoring.** `FenceModel` is not persisted anywhere: `store/db.py:20-38` has no
  `fence_models` table, `Catalog` is `{products, substitutions}`, and the single instance
  in the system is minted per call by `legacy_model()`. Models exist only as Python.
- **No variants.** `Variant` and `Axis` are fully specified types that `validate_model`
  **rejects on sight** (`model.py:259-269`), deliberately: phase 1's rule is that a
  deferral must not read as a working feature.

The causal chain the user names — model → panel → materials, sizes and structure — is
already real in the code (`Span.panel` → `derive_requirements` → `resolve_supply` →
BOM/structure). What is missing is every surface at which a human meets it.

## Decomposition

This is too large for one spec. Six waves, each independently shippable, each ending at a
green suite and a merge. The dependency order is forced, not chosen:

| Wave | Delivers | Why it must come here |
|---|---|---|
| **W1** | Models are persisted, versioned, selectable data | Nothing can be shown or edited that does not exist as data |
| **W2** | The panel is visible *before* generation | Needs W1's selection to have something to show |
| **W3** | Variants, option axes, height support resolve | Editing a variant is theatre while `validate_model` rejects variants |
| **W4** | Authoring: edit, add, duplicate, vary | Needs W1 (persistence) and W3 (the features being edited must work) |
| **W5** | `select_supply` explanation, multi-member groups, pricing | The documented phase-2 blocker; independent of the UI |
| **W6** | The phase-2/3 tail | Everything left |

W1–W4 answer the user's question. W5–W6 are the project's remaining backlog
(`plan/current-status.md:350-353`, `docs/v1-known-limitations.md`).

---

## W1 — Models become choosable data

### Persistence

A new table, mirroring `knowledge_versions` exactly, because a `FenceModel` has the same
lifecycle as a knowledge object even though it is not one:

```sql
CREATE TABLE IF NOT EXISTS fence_models (
    model_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    doc TEXT NOT NULL, PRIMARY KEY (model_id, version));
```

`status` is the model's own `draft | active | retired`. The invariant matches knowledge:
**an `active` version's `doc` is immutable**; only the status may change, through a method
that audits the transition. A `draft` may be overwritten in place — that is what makes
authoring bearable — and *cannot be selected by a project that is not the one editing it*
(see W4). Publishing a draft mints the next version number and freezes it.

`M-LEGACY@v1` is seeded at store creation, exactly as the demo catalog is, so a fresh
database is never empty and the compatibility path is data rather than a special case in
the generator. `legacy_model()`'s parameterisation by resolved demand SKUs
(`demo.py:19-21`) is the one thing that cannot become static data — a knowledge
`DefaultComponent` change must still reach the BOM. Resolution therefore keeps a documented
seam: when the selected model is `M-LEGACY`, its eligibility members are re-seeded from the
run's resolved demand SKUs. This is recorded as a deliberate exception, not generalised.

### Selection

Two levels, per the phase-1 spec (`2026-08-12-fence-model-design.md:553-564`):

1. **Project default** — a typed field, `Project.fence_model: FenceModelChoice | None`,
   replacing the relevant part of `Project.policy`'s bare dict. `None` means `M-LEGACY`.
2. **Per-interval override** — a `fence_model` interval event on a run, so a fence may
   change model partway along, exactly as it changes base or height.

```python
FenceModelPayload(kind="fence_model", model_id: str, version_pin: int | None = None,
                  options: dict[str, str | int] = {})
```

`version_pin=None` means "the newest `active` version at generation time"; the resolved
`(id, version)` is stamped on the run either way, so a run is always reproducible.

**Model-change stations become boundary stations.** `generator.py:620-621` builds the fixed
set from `{0, length} | corners | base transitions | pinned | gate edges | step stations`.
Span properties are sampled at the mid-point (`_interval_at`, `generator.py:929`). Without
this, a 5000 mm run carrying M-SLAT to 2500 and M-LEGACY beyond lays out 1667/1667/1666,
and the middle bay straddles the boundary — it samples mid = 2500 and silently becomes one
model's panel at a place where the fence visibly changes. Model-change stations join
`fixed`, exactly as base transitions do.

The consequence is stated in the phase-1 spec and is real work: `max_span_mm` and its
siblings are resolved **once** at `generator.py:490`, before any segmentation. A per-interval
model cannot be honoured at all until that resolution moves inside the segment loop. W1 does
that move, and pins it with a scenario where two models with different `max_span_mm` meet on
one run.

### Explanation

`select_model` is a decision node per segment: inputs are the interval event (or the project
default, or the M-LEGACY fallback), the resolved `(id, version)`, and the option values.
`decisions/explain.py` TEMPLATES gain key-identical `en`/`he` entries.

### Run identity

`model_snapshot` is already in the digest (`generator.py:172-180`). Two gaps W1 closes:

- **Option values are not in the digest.** Change a colour, regenerate, and `INSERT OR
  IGNORE` serves the old document under a reused id. Options join the digest.
- **`model_snapshot` is `(id, version)`, not a content hash**, and a `draft` version's
  content can change under a fixed `(id, version)`. Now that models are stored documents,
  the snapshot becomes `(id, version, sha256(doc)[:12])`. This closes the weakness recorded
  at `docs/v1-known-limitations.md:79-92` as a side effect of persistence, so it is done
  here rather than deferred again.

### API

```
GET    /api/fence-models                     list (id, latest version, name_i18n, status)
GET    /api/fence-models/{id}/{version}      one full model
POST   /api/fence-models                     create draft
PUT    /api/fence-models/{id}/draft          overwrite draft
POST   /api/fence-models/{id}/publish        draft → next active version
POST   /api/fence-models/{id}/{version}/status  active ↔ retired
PUT    /api/projects/{id}/fence-model        set the project default
```

Every write runs `validate_model` against the live catalog and returns 422 with
`code + params` on failure — the same shape `fence_model_unknown_sku` already uses.

### UI (minimal in W1)

A model row in the canvas tab's aside: the project's default model, its name in the active
locale, a `<select>` of active models, and its version. Plus a `fence_model` tool on the
event rail, following the base/height popover pattern exactly (`editor.js:498-527`) so an
interval override is authored the way every other interval event is.

### Demo data

`M-SLAT@v1`: horizontal slat infill on a two-rail frame — a vertical-orientation pattern of
one member with a gap, `justification: spread_to_fit`, `excess: space`, screws
`per_member_crossing`. Every feature it uses is **already honoured** by `resolve_panel` and
`fit_pattern` today; it needs no phase-2 work. It is what makes "choose a model" mean
something in W1 rather than in W3, and it exercises the infill path end to end for the first
time in a shipped model. New catalog products (slat, U-channel) and new golden scenarios go
through the `golden-scenarios` skill.

### The acceptance gate

Unchanged in kind from phase 1: **with no `fence_model` event and no project default, every
existing fixture produces byte-identical requirement lines and BOM.** The committed
compatibility artifact (`tests/.../fence_model_compat/*.json`) is the check.

---

## W2 — See the panel before you generate

### The read model

`resolve_panel` already returns a `ResolvedPanel` carrying aggregate quantities plus fit
parameters. Geometry is a pure function of those parameters, so it stays derived, never
stored (foundation §15).

**It is computed on the server**, not mirrored in JS. The codebase has mirrored maths across
that boundary before (`geom.anchorFor` mirrors `make_anchor`), but that is a two-line formula
and this is a fit algorithm with a justification × excess matrix. One implementation, one set
of tests.

`PanelElevation` is a **field on `StructureReport`**, not a second endpoint —
`structure-data.js` is already the shared run-keyed cache with the in-flight guard built to
fix finding A7, and `profile.js` reads it rather than fetching. A second endpoint fetched by
`profile.js` would reintroduce exactly the stale-fetch bug A7 closed. It also inherits the
`topology_changed` and `catalog_changed` 409s for free.

```python
PanelElevation   bay_tag: str, width_mm, height_mm, members: [ElevationMember]
ElevationMember  slot_key, role, x_mm, y_mm, w_mm, h_mm, face: front|back, swatch: str|None
```

Rectangles in the panel's own frame (x: 0 → clear width, y: 0 → panel height, origin at the
opening's bottom-left), as the phase-1 spec defines it. The renderer positions them; it never
computes them.

### The preview endpoint

The user's actual ask is *before the strategy*, which means before a run exists.

```
POST /api/fence-models/{id}/{version}/preview
     { height_mm, width_mm, options: {}, vertical: "level", context: {} }
  -> { panel: ResolvedPanel, elevation: PanelElevation,
       parts: [PreviewPart], warnings: [code+params] }
```

This is `resolve_panel` on a synthetic `PanelContext` plus `resolve_supply` against the live
catalog and an empty inventory. It is explicitly **not** a run: it has no id, is not stored,
is not quotable, and says so in the UI. What it answers is "if I build this model at this
height and width, what is in one panel and roughly what does it cost" — which is exactly the
question a picker needs to answer to be a picker rather than a dropdown.

### The Panel tab

A new tab between Structure and BOM. Two states:

- **No run**: the preview. Model select, height and width fields (display units, via
  `toDisplayValue`/`toMm`), option controls, and the elevation drawn beside a slot table
  (slot key, role, qty, length, eligible items, chosen item, unit price).
- **A run exists**: a bay picker over the run's real bays, showing the *actual* resolved
  panel and its real parts, with the elevation drawn from `StructureReport.elevations`.
  Clicking a drawn member selects its part row — the browser check the phase-1 spec asked
  for (`:726`).

Frontend contracts, none optional: strings through `t()`/`data-i18n` with he/en key parity;
lengths through `tu()` with `{u}`, never a literal unit; **the elevation SVG is never
mirrored in RTL** (it joins the plan canvas and profile in that standing rule, or Hebrew
reverses slat order relative to the plan); user text through `esc()`; and a `swatch` reaching
an SVG `fill` is a **style context where `esc()` is not sufficient** — it is validated
against `^#[0-9a-fA-F]{6}$` at model load (`model.py:367-371`) and rejected there, which is
the existing defence and must not be weakened.

---

## W3 — Variants, option axes and height support resolve

Delete entries 1, 2, 3, 4 and 9 from `_unsupported_features` (`model.py:257-332`) and make
each one work, in that order. The table's own comment states the rule: "Deleting an entry
from this table is how phase 2 turns each feature on."

- **Variants**: `select_variant` gains its production caller. Precedence is authored order,
  first satisfied condition wins — never specificity, for the reason the phase-1 spec gives
  (a `Variant` has a bare `Expr` and no scope dict, so "specificity" would mean counting AST
  nodes and two implementers would choose differently). A decision node per span records the
  winning index and the conditions that failed. There is **no `defeated` edge**: this is
  product structure evaluated outside the knowledge evaluator, not a defeasible rule, and the
  distinction has to be visible or someone will hunt for an edge that was never going to
  exist.
- **Option axes**: `PanelContext.options` is read. `sku_by_option[chosen]` names a preferred
  member **of the requirement's own eligibility set** — a value naming a non-member is
  already a load-time validation error (`model.py:412-417`), so a colour choice can never
  smuggle in a product the slot disallows. `select_product` per slot records the option that
  governed it.
- **`height_support`**: checked at resolution; `height_not_supported` **aggregates per
  section, not per bay**, because `top_line: level` on a slope makes every span a different
  height (S06) and a discrete-height model would otherwise emit one warning per bay and drown
  the list.
- **`layout_policy`**: contributions emitted as knowledge-shaped objects scoped to
  `series=<model_id>`, each declaring **its own `knowledge_type`**. Not one authority for the
  whole model: `DEFAULT_AUTHORITY` puts `hard_constraint` at 1 and `company_rule` at 3, so
  lumping a manufacturer's maximum span together with a nominal panel width guarantees either
  an unbeatable preference or a beatable safety limit.

`bind_scope()` gains `series` — closing the blocked dimension recorded at
`plan/current-status.md:105`.

**The locale-bundle guard must be extended first.** `tests/web/test_locale_bundles.py:60-70`
regexes `code="..."` out of exactly two files, `strategy/generator.py` and `ai/stub.py`.
Every code this wave adds originates in `fencemodel/` or fulfillment, so all of them would
ship untranslated with the test green. Extending the scanner is part of this slice, verified
by adding a code and watching the test fail.

---

## W4 — Authoring

The editor lives in a new Models tab and copies the knowledge rule builder's proven shape
(`tabs.js:492-651`): **sentence-style rows over the live data structure, plus an
Advanced-JSON escape hatch** whose exit is never gated on the JSON being valid — the rule
recorded at `tabs.js:93-95`, learned the hard way when the rule editor trapped users.

Four nested editors, each a row list with add/remove and a kind select:

- **Frame slots** — key, orientation, placement (the four-arm `Placement` union, where
  choosing `distributed` reveals `count_param` — a knowledge param, not an integer, because
  rail count must stay defeasible), length rule, role, qty, eligibility.
- **Infill** — orientation, justification, excess, edge margin, and a member pattern list
  (width, gap-after **which may be negative**, face offset, base/top ref).
- **Fixings** — key, basis (the closed six-value vocabulary), qty per basis, qty param.
- **Eligibility** — an ordered member list of catalog SKUs with priority and
  `auto | suggest_only`, using the existing `skuSelect` helper so names localise.

Variants are a list of `(condition, spec)`; the condition is an `Expr` and the AST builder is
**out of scope for W4** — the knowledge tab has the same limitation today and says so
(`knowledge.builder.conditions_hint`). Variant conditions get the same hint and the JSON
box. Building a general AST editor is its own design round; pretending otherwise would ship
a half one.

**Editing semantics**: an `active` version is never mutated. "Edit" on an active model
creates a draft copy at `version + 1`; the draft is saved in place as often as you like;
"Publish" freezes it. Duplicate creates a new `model_id` from any version.

**Impact preview is not optional.** `FenceModel` is catalog-side, so it does not inherit
`/api/knowledge/preview-impact` for free, and editing a model's slat gap is a portfolio-wide
change that foundation §11 requires to be exposed before it is made. `learning/impact.py`
gains model-version cases — pure regenerate-and-diff, as the knowledge case already is — and
the publish button shows "this would affect N of your projects" with per-project BOM deltas,
including deltas against **accepted quotes**, which the existing impact code already reports.

---

## W5 — Supply choice explained, and pricing

`resolve_supply` records chosen, rejected, preset and per-requirement reasoning in
`SupplyResolution.decisions`, and **nothing consumes it**. It reaches no decision-graph node,
so `/explain` cannot say why POLE-3000 was bought instead of POLE-2000. Today every shipped
group has exactly one member so the gap is invisible; W1 ships M-SLAT and W4 lets users
author multi-member groups, at which point the system makes a priced choice it cannot account
for — contradicting foundation §15 for exactly the decision most worth explaining.

The blocker is structural: selection is coupled to the cut plan and runs in fulfillment,
which has no graph builder. The resolution: `fulfill()` returns its decision records, and
`/api/runs/{id}/bom` and `/structure` attach them to the run's graph as `select_supply` nodes
**at read time**, keyed by requirement — a derived read model over a pure function of the
stored run, which is what `report/` already is. The graph is not mutated; reading never
mutates the graph, and there is a test that pins that.

Then `Eligibility.group` and `Eligibility.predicate` (with the predicate **frozen into the
run's snapshot** — property-based eligibility is dynamic by nature and a new catalog product
silently changing what an accepted quote meant is finding A2 happening again), and the
pricing union: `FlatPrice` and `LinearPrice` only. `AreaPrice` and `BandPrice` have a stated
prerequisite — `fulfill()` grouping per `(sku, price_basis, size)` rather than per SKU — and
shipping them without it produces a line whose single `unit_price_cents` cannot give the
right total.

---

## W6 — The tail

`excess: trim_last | extension_clip`; `InfillSpec.supply: assembly`; the panel safety codes
(`clear_gap_exceeded` on `max(gaps_mm)` — not on a single rounded gap, which is the sphere
test defeated by a return type — `rail_separation_insufficient`, `pattern_residual_large`);
`exact_span_mm` and `span_not_exact`; narrowing `catalog_hash` to the products a run actually
resolved, so that editing one price stops 409-ing every prior run. Then phase 3: arc-flow
over multiple stock lengths and sources with remnants, via OR-Tools, as ADR-0007 anticipated.

---

## Testing, throughout

Beyond each wave's own tests, four properties hold across all of them:

- **The compatibility gate**: no `fence_model` selection ⇒ identical requirement lines and
  BOM, against the committed artifact.
- **Σ(parts) ≡ BOM in both directions** per `(sku, unit)` — finding A3's property, now over a
  panel with dozens of members rather than two rails.
- **Reproducibility**: editing a model, publishing a version, adding a catalog product or
  flipping a preset changes `run.id` and cannot alter a stored run's `/bom` or an accepted
  quote.
- **Determinism**: `resolve_panel` and `fit_pattern` have no clock, no RNG and no dependence
  on dict order.

Every wave ends at `uv run pytest -q`, `uv run pytest tests/scenarios -q` and
`tools/ui_smoke.py` all green, an `architecture-critic` and `test-reviewer` pass, and a
merge to `main`.
