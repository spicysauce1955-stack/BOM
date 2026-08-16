# Two-tier visualizer — design

Date: 2026-08-14. Status: approved for implementation (autonomous session).

Two synchronized viewports over one fence: a **macro** view of the run as it is set
out, and a **micro** view of one panel as it is assembled — plus the material and
inventory drawer that makes a part on the drawing something you can *change*, and
prices that read in the currency this ships into (₪).

---

## 1. Why this, and what it is not

The app can already draw two things: a **plan** (the canvas, top-down) and a
**panel elevation** (one bay's rectangles, on the Panel and Structure tabs). Two
questions it cannot answer with a picture:

* *How do these pieces actually go together?* The elevation draws every member as a
  rectangle in the panel plane. A slat that seats 12 mm into a bottom channel and a
  slat that butts onto a rail draw identically — and are cut to different lengths.
* *What does the whole line look like standing up?* The plan shows stations from
  above; the profile side view shows ground and post tops. Neither shows a panel
  docked between two posts, a footing under a post, or a step-down as a fence.

The two are one question at two scales, which is why they belong in one tab with a
shared selection: pick a bay in the macro view, the micro view assembles it; pick a
part in the micro view, the macro view shows you every bay that carries it.

**Not in scope, and refused by name rather than half-built:**

* No 3D. Both viewports are orthographic SVG (front elevation), like every other
  drawing in this app. A 3D view is a different renderer with a different set of
  lies available to it, and nothing in the BOM needs it.
* No auto-generation. The macro viewport shows the **last generated run**. A
  dimension change that only a new layout could answer marks the viewport stale and
  offers the button; it never fires `generate()` (project rule: generation stays
  behind the explicit button).
* No new pricing basis. Money is still integer cents at rest, one currency, and the
  BOM is still `fulfill()`'s.
* Material selection in the drawer is **preview-scoped**. Choosing "Cedar" for the
  slats re-prices the panel preview; it does not silently patch a stored run.
  Making it stick is either authoring the model (Models tab) or an override
  anchored to `(run_id, station, kind)` — both existing surfaces, neither bypassed.

---

## 2. The domain work first: a joint has to be worth drawing

A picture of an interlock that no number depends on is decoration, and this codebase
already knows what happens to a field the resolver ignores (`_UNSUPPORTED` in
`fencemodel/model.py`). So joint geometry lands as data that **changes the cut
list**, and the drawing is derived from the same fields.

### 2.1 Schema (`fencemodel/model.py`)

```python
JointKind = Literal["butt", "channel", "groove", "bracket", "overlap"]

class FrameSlot(BaseModel):
    ...
    joint: JointKind = "butt"
    channel_depth_mm: Mm = 0     # how deep this member RECEIVES an infill member
    insertion_margin_mm: Mm = 0  # clearance left at the bottom of that channel

class Member(BaseModel):
    ...
    joint: JointKind = "butt"
    base_engagement_mm: Mm = 0   # how far this member seats into its base_ref
    top_engagement_mm: Mm = 0    # ... and into its top_ref
```

`base_ref` / `top_ref` already exist on `Member` and are **not honoured today** —
`_length_for` says so in a comment. That is the gap this closes.

### 2.2 A new length rule: `between_frame`

```
length = (top_position - base_position)
       - (top_thickness/2 + base_thickness/2)      # face to face
       + base_engagement_mm + top_engagement_mm     # what disappears into the joint
```

Positions come from `placement_positions` for the referenced frame slots — the same
integer arithmetic that places them on the drawing, read once, never re-derived.

Defaults keep every existing model still: no model in the repo declares
`between_frame`, so `tests/scenarios/compatibility_gate/*.json` are byte-identical.
`M-SLAT` gains a *second* published version demonstrating the rule; v1 stays.

### 2.3 Load-time refusals (`validate_model`)

Each of these is a wrong answer the author can still fix:

* `between_frame` with no `base_ref`/`top_ref` — nothing to measure between.
* a ref naming a slot that is not a frame slot of the same spec.
* engagement deeper than the receiving slot's `channel_depth_mm` — a 20 mm seat into
  a 12 mm channel is a member cut 8 mm too long, on every bay.
* `channel_depth_mm > 0` on a slot whose `thickness_mm` is undeclared — a channel
  inside a member of unknown depth is a dimension with no datum.
* `insertion_margin_mm >= channel_depth_mm` — the margin swallows the seat.
* a non-`butt` `joint` with zero engagement AND zero channel depth: the kind claims
  a mechanic the numbers do not have.

### 2.4 The drawing gains the joint (`report/elevation.py`)

`ElevationMember` gains `seat_start_mm` / `seat_end_mm` (the engaged portion, in the
same panel coordinates as the rectangle) and `joint`. `PanelElevation` gains

```python
class JointDetail(BaseModel):
    key: str                  # "<member_slot>@<frame_slot>"
    member_slot: str
    frame_slot: str
    end: Literal["base", "top"]
    kind: JointKind
    member_thickness_mm: Mm   # 0 = undeclared (nominal), as elsewhere
    frame_thickness_mm: Mm
    channel_depth_mm: Mm
    engagement_mm: Mm
    margin_mm: Mm
    declared: bool
```

`details: list[JointDetail]` rides on `PanelElevation`, so the **preview and a stored
run's `Bay.elevation` carry it by the same code path** — no second endpoint, and no
chance of the tab's detail disagreeing with the bay's.

### 2.5 The macro view needs two numbers it cannot see

`Post` gains `embed_mm: Mm = 0`, written by `_check_post_lengths` from the value it
already resolves (`post_embed_mm`), and `report.structure.Station` gains `embed_mm`
and `post_length_mm` (from the post's SKU `attrs.length_mm`). Without them the macro
view would have to invent a footing depth, and an invented dimension on a setting-out
drawing is the worst kind. A post with no resolvable length draws with no embed
dimension rather than a guessed one.

---

## 3. The tab

`index.html` gains one button (`data-tab="assembly"`) and one section:

```html
<section id="tab-assembly" class="tab">
  <div class="panel" id="assembly-bar"></div>     <!-- mode, dimensions, sync state -->
  <div class="assembly-row" id="assembly-row">
    <div class="panel" id="assembly-macro"></div>
    <div class="panel" id="assembly-micro"></div>
  </div>
  <div id="assembly-drawer"></div>                <!-- material & inventory -->
</section>
```

`.assembly-row` follows `.models-row`: flex, `flex: 3 1 …` / `flex: 2 1 …`, wrapping.
Modes: **split** (both), **macro**, **micro** — a segmented control in the bar,
persisted in `localStorage` under `fenceai.assembly.mode`, like the structure detail
level and the display unit.

### 3.1 Modules

| module | owns | pure? |
|---|---|---|
| `js/runview.js` | macro geometry: report → placed rectangles + dimensions | **pure** (node-tested) |
| `js/joint.js` | micro joint detail: `JointDetail` → section rectangles | **pure** (node-tested) |
| `js/assembly.js` | the tab: DOM, mode, selection sync, drawer, live re-price | wiring |

The split mirrors `base-top.js` / `profile.js`: the maths is a point-list transform
with no DOM and no state, so it is testable under node; the wiring only places it.

`runview.js` **places, never computes**: every station, z, height and embed on its
output is a field of `StructureReport`. It owns exactly one transform — world mm to
SVG coordinates with y flipped, one scale for both axes — the same rule
`elevation.js` states.

### 3.2 The macro drawing

Per section, walking order, x = station along the run, y = elevation:

* **ground line** from the stations' `ground_z_mm`, with the built-base band where a
  section declares one (tones reused from `profile.js`: masonry `#dc2626`, concrete
  `#64748b`);
* **posts**: a rectangle from `base_z_mm` to `base_z_mm + height`, plus the embedded
  portion below ground drawn hatched to `-embed_mm`, plus a footing bell where the
  station's parts carry a `concrete` role;
* **bays**: the panel between two posts, drawn as its own members when the bay
  carries an elevation (scaled into the opening), else as a hatched block. This is
  what "how individual panels dock into structural posts" means: the bay rectangle
  is bounded by the post faces, not by the post centres;
* **gates**: the opening, its kit tag, and a swing arc;
* **steps**: where two adjacent bays' `bottom_z_*` differ, the step riser is drawn
  and dimensioned.

Dimension annotations (toggleable, on by default): total run length, each bay's
clear width, height per bay (or one height when a section has a single height),
embed depth, step rise. Every one of them is a field, rendered through `tu()`.

### 3.3 The micro drawing

The existing `renderElevation` gains an options object rather than a fork:

```js
renderElevation(elev, { onSelect, annotations = true, joints = true, scale })
```

* `joints` overlays, on each member that has one, the seated portion (hatched, with a
  leader to the engagement dimension) — read from `seat_start_mm` / `seat_end_mm`;
* `annotations` toggles the dimension group (width, height, fitted gap) plus two new
  ones this request names: **slat pitch** (member width + gap, dimensioned once
  across two consecutive members) and **edge margin** (`fit.edge_margin_start_mm`);
* a **joint detail inset** — the selected member's `JointDetail` drawn as a section at
  its own scale, so a 12 mm engagement is legible on a 1800 mm panel. This is
  `joint.js`'s output and it appears beside the panel, never on top of it.

The Panel and Structure tabs keep calling `renderElevation` with defaults, so their
drawings do not change.

### 3.4 Selection sync

One selection, both directions, through `state.js` — no module reaches into
another's DOM:

* macro bay click → `setSelection({ runId, elementId })` (the existing event the
  Structure tab and inspector already speak) → micro view assembles that bay;
* micro member click → local slot selection → macro view highlights every bay whose
  parts carry that slot, and the drawer opens for the part;
* the Structure tab's own selection already emits the same event, so selecting a bay
  there and switching to Assembly lands on the same bay.

### 3.5 Real-time synchronization, honestly

| change | macro | micro | BOM strip |
|---|---|---|---|
| panel height / bay width in the bar | unchanged (see below) | re-previews (debounced 250 ms) | preview total, live |
| material swap in the drawer | unchanged | re-previews with `slot_skus` | preview total, live |
| model swap | stale badge | re-previews | preview total, live |
| a new run generated | redraws | redraws from the run | run BOM total |
| units mm↔cm, locale | redraws | redraws | redraws |

**Correction, made during the review pass rather than left as a disagreement.**
The first version of this table said a dimension what-if marks the macro viewport
stale and offers a Generate button. The implementation does not, and the
implementation is right: the macro viewport is showing the RUN, which a
hypothetical panel height has not made wrong. Calling it stale would claim the
drawing is inaccurate when it is exactly accurate, and a Generate button there
would be worse — a what-if height lives nowhere the generator could read it, so
the button would either do nothing or silently generate the OLD height. What the
what-if actually needs is what it has: a badge on the panel that is hypothetical,
and one button back.

Staleness in the real sense — the topology moved, the catalog moved, the run
predates fence models — is still handled, by the same `structure-data.js` refusal
branches the Structure tab uses. Those branches are now ONE function
(`refusalKey`) in the module that owns the refusal state rather than a copy per
tab, because two copies is how one surface comes to say "generate a strategy"
about a run whose catalog moved while the surface beside it says the truth.

The cost strip states which of the two it is showing — *preview of one panel* or
*this run's BOM* — because a number that silently changes meaning is worse than two
numbers.

---

## 4. The material & inventory drawer

Opened by clicking a part in either viewport (or a row in the parts table). It shows,
for that slot:

* **the chosen product** — name (localized), SKU, unit price, how it is bought
  (`consumption.kind` rendered as a sentence), cut length if it has one;
* **compatible stock profiles** — the slot's `eligible_skus`, each with material,
  finish/colour swatch, price, and *why it is or is not the chosen one* (priority,
  `suggest_only` approval) — the narrowing rule is already recorded on the resolved
  slot (`option_axis` / `option_value`), so this is read, not re-derived;
* **inventory availability** — on-hand quantity and reusable remnants for that SKU
  from the project's inventory, with the "no warehouse scope" caveat the app already
  documents;
* **select** — sets a preview-scoped `slot_skus[slot_key] = sku`, re-prices, and shows
  the delta against the current choice. A sku that is not a member of that slot's own
  eligibility is refused by the API with a coded 422 (`sku_not_eligible`).

Material and finish are **catalog data**, not code: `Product.attrs` gains
`material`, `finish`, `colour` (a `#rrggbb` swatch, validated like `OptionValue.swatch`)
on the demo products, and the words are locale keys (`material.aluminium`,
`material.composite`, `material.cedar`, `material.steel`, `material.concrete`).
A product with no `material` attr shows no material row — never a guessed one.

Backend: `PreviewRequest` gains `slot_skus: dict[str, str] = {}`, narrowing that
slot's eligibility exactly as an option axis does (`_chosen_option`'s discipline:
narrowing only ever removes candidates, and carries priority/approval through
untouched). One new API refusal code, `sku_not_eligible`, with entries in both locale
bundles.

---

## 5. Prices in ₪

Currency is hardcoded `€` in five places, three smoke checks and two locale bundles.
It becomes one function and one locale key:

```js
// units.js
export function money(cents)        // "₪1,234.56", grouped, always 2 decimals
export function moneyDelta(cents)   // "+₪12.00" / "−₪12.00"
```

* `units.currency` = `"₪"` in both bundles; `bom.unit_price` / `bom.line_total` /
  `impact.vs_accepted` carry `{c}` the way lengths carry `{u}` — no literal symbol in
  any string;
* the two duplicated `money` definitions (`panel.js`, `model-editor.js`) and the three
  inline ones (`tabs.js`, `impact.js`, `editor.js`) all import it;
* `tests/web/test_locale_bundles.py` gains the single-owner rule for `money`
  (the same rule that already guards `localizedByCode`) and a "no literal currency
  symbol in a bundle value" rule (the mirror of the no-literal-units rule);
* the three `€` smoke assertions become `₪`.

RTL: `money()` output is a number plus a symbol, so it is rendered inside `.num`
(`direction: ltr; unicode-bidi: isolate`) exactly like every other figure, and the
`‎`-prefixed hack in `editor.js` goes away with it.

Scope: one currency, ILS. Multi-currency is a `Money(amount, currency)` type through
the whole cost tier and a rate source with an as-of date — a different project, and a
half-done version of it (a symbol swap that pretends) is worse than this.

---

## 6. Testing

Per wave, all three tiers:

* **pytest** — schema refusals, the `between_frame` arithmetic (hand-derived, not
  self-consistent), joint details on both the preview and a stored bay, `embed_mm`
  reaching `Station`, `slot_skus` narrowing and its 422, and the compatibility gate
  **unchanged** (proof that defaults move nothing);
* **node module tests** — `runview.js` (a report in, placed rectangles out: post
  embed below the ground line, a bay bounded by post faces not centres, a step
  dimensioned at the right riser), `joint.js` (a 12 mm engagement into a 20 mm
  channel with a 2 mm margin comes out as three measurable bands), `units.money`
  (grouping, negative, zero, and that it is defined in exactly one module);
* **browser smoke** — new checks in `tools/ui_smoke.py`: the tab opens in split and
  toggles; a macro bay click drives the micro view; a micro member click opens the
  drawer with eligible products; a material swap re-prices without a run; the stale
  badge appears on a dimension change and no run is generated behind it; every price
  on screen reads ₪. Screenshots at each state.

The release gate (`uv run pytest tests/scenarios -q`) and the full suite must pass at
every wave boundary, and the browser suite must be run — three of the last session's
defects were invisible to `TestClient` by construction.

---

## 7. Waves

Each wave is a branch, merged `--no-ff`, tagged and pushed.

1. **W1 — ₪.** `money()` + bundles + all sites + tests. Independent of everything else.
2. **W2 — joint schema + `between_frame`** + refusals + the second `M-SLAT` version.
3. **W3 — joint details on the elevation** (`seat_*`, `JointDetail`).
4. **W4 — `embed_mm` through to `Station`.**
5. **W5 — `runview.js` + the macro viewport.**
6. **W6 — `joint.js` + micro annotations, pitch, edge margin, detail inset.**
7. **W7 — the drawer**, `slot_skus`, catalog material attrs, `sku_not_eligible`.
8. **W8 — sync, modes, stale badge, cost strip.**
9. **W9 — smoke suite, screenshots, docs, status, adversarial review pass.**

W1–W4 are backend-shaped and independent of W5–W8's frontend except through the wire
schema, so W1/W2/W4 can run in parallel; W3 depends on W2, W6 on W3, W8 on W5–W7.
