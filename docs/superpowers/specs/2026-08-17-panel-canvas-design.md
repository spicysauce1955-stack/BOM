# The Models tab becomes a canvas, not a form

Status: design · 2026-08-17 · supersedes the Authoring UI described in
`2026-08-12-panel-authoring-design.md`'s W4 section and built in `js/model-editor.js`
(~1200 lines, "Panel authoring W4 — the model becomes editable," COMPLETE per
`plan/current-status.md:753`). Everything else that spec's W1–W4 shipped —
persistence, versioning (`draft`/`active`/`retired`), the `/api/fence-models/preview`
route, impact-preview-before-publish, duplicate-creates-a-new-`model_id` — is
unchanged by this doc. Only the authoring *surface* is being replaced.

## The complaint, and why it is correct

> "the whole creating and editing fence panels is really unintuitive and unnecessarily
> complex and nerdish"

W4 was scoped, on the record, as an expert tool: it "copies the knowledge rule
builder's proven shape... sentence-style rows over the live data structure" and
targets, in the file's own words, "the expert who owns it." It delivers exactly
that. The complaint is not a bug in W4 — it is what happens when an expert who knows
fences, not this codebase's internal vocabulary, is handed the internal vocabulary as
the only way to say what they mean. Concretely, today's Models tab requires typing or
selecting, as raw enum values, things like:

- `placement.kind` ∈ `distributed | from_bottom | from_top | fraction`, then depending
  on that, `count` / `count_param` / `bottom_inset_mm` / `top_inset_mm` / `permille` /
  `offset_mm`
- `justification` ∈ `start | end | center | spread_to_fit`, `excess` ∈
  `truncate | space`, `edge_margin_mm`
- `gap_after_mm` accepting a *negative* number to mean "this board overlaps the next
  one" — documented in a hint the user has to read
- `basis` ∈ `per_member_crossing | per_member | per_end_member | per_gap |
  per_frame_member | per_panel` for where fixings go
- a `role`/`length_rule`/ordered-SKU-priority/`approval: auto | suggest_only` block
  repeated per requirement
- a raw JSON AST textarea for a variant's applicability condition, e.g.
  `{"op":"cmp","cmp":">=","left":{"op":"field","path":"panel.height_mm"},"right":{"op":"lit","value":1800}}`

None of this is wrong as a *data model* — every one of those is real structure real
fence systems vary on, and `catalog/model.py`'s own rule (data consumed by
deterministic logic must be typed) is why `basis`, `placement.kind`, etc. are closed,
code-defined enums rather than free text. What's missing is a surface between that
model and a person who thinks in boards, rails and screws, not in `basis` and
`justification`.

## Audience and non-goals

This redesign targets the **internal fence-company expert** — someone who authors
panel types for their own catalog, not a homeowner or a customer-facing salesperson.
That rules out, deliberately, for this round:

- A guided/wizard mode that walks a novice through Frame → Infill → Fixings step by
  step. Explored and rejected during brainstorming: it's the right shape for training
  a brand-new hire, wrong for the day-to-day edits an expert already knows how to
  make. Building it now would pay for a persona this round didn't pick. If onboarding
  turns out to be a real pain point later, it composes cleanly onto the design below
  (same canvas, an optional overlay) rather than requiring a rebuild.
- Photo/AR-anchored placement, in-context editing on a real project span, or any
  change to how a Model relates to a Project. The Model↔Project relationship is
  unchanged: **Models stay a separate library, built ahead of time and applied to
  spans afterward** — exactly as W1–W4 already built it.
- Any change to the stored `FenceModel` JSON shape, the API surface, or the
  draft/active/retired lifecycle. This is a frontend authoring-surface replacement,
  not a data-model or backend change.

## The shape: one live canvas, one contextual inspector

Rejected alternatives, and why: a guided step wizard (mirrors the domain's own
Frame/Infill/Fixings structure well, but forces sequence on someone who already knows
what they're changing — see non-goals); a hybrid canvas-plus-optional-wizard (real
value, but the added engineering — one canvas serving both a guided and unguided
reading — buys a persona this round explicitly excluded).

The chosen shape: a single SVG drawing of the panel *is* the editor. Clicking a
board, rail, post or fixing on the drawing selects it; its properties render as
plain-language controls in a side inspector, Figma-Auto-Layout style. There is no
forced order and no separate "form view" — dragging a rail's vertical position,
dragging a board's width or the gap after it, are first-class edits, not a
convenience layered on top of typed fields. Typed fields remain available (as the
inspector's number readouts, editable directly) for exact values — dragging sets
them, typing overrides them; neither is primary.

## Turning the closed vocabularies into controls

The reconciling principle, settled during brainstorming: **the set of values in each
closed vocabulary stays a typed, code-defined enum** — `basis`, `placement.kind`,
`justification`, `length_rule` etc. are read by real fulfillment/resolution code that
has to know what each one means, so adding a new one is a normal code change with
tests, the same cost as adding a new `JointKind` today. What changes is that every
value gets a **plain-language control**, not just a translated label. Six examples,
each covering the *entire* existing enum (no value is dropped from the picker; "no
silent capability loss" per brainstorming):

| Today | Canvas inspector |
|---|---|
| `placement.kind` select, then a different set of numeric fields per kind | "Rails: **evenly spaced ▾**" (dropdown covers all four kinds: evenly spaced / from the bottom / from the top / at exact heights) — for `distributed`, drag the rail on the drawing; for `fraction`, type an exact height; the field is always a live readout of the drag, never the only way in |
| `justification`/`excess`/`edge_margin_mm` | "Boards fill the frame: **packed left / centered / spread evenly ▾**", with "leftover space: **trim the last board / add a gap ▾**" for `excess` |
| `gap_after_mm` accepting negative values | A plain "Overlaps next board" checkbox plus a positive mm amount; sign is an implementation detail the control hides, not a fact the user has to remember |
| `basis` select | "Screws at: **every board × every rail crossing ▾**" (all six `BASES` values, each with its own small diagram showing where the dots land); the drawing shows the actual fastener positions as clickable dots |
| `role` / `length_rule` / SKU priority list / `approval` | "Boards, in preference order" — a drag-to-reorder row of product swatches (reusing existing catalog `attrs.colour`/material data, per `skuSelect`), with "let the system substitute automatically" as a checkbox standing in for `approval: auto | suggest_only` |
| Variant condition JSON AST | A sentence builder — "Applies when **panel height ▾ is at least ▾ [1800] mm**" — covering simple field-comparison conditions (the only kind any shipped model or catalog uses today); a collapsed **▸ Advanced** row keeps the raw JSON box for conditions the sentence can't express |

The `basis`/`placement.kind`/etc. dropdowns are plain-language **phrasings of the
same enum values already required to have en/he words** (`GRADES`, `BASES`,
`JUSTIFICATIONS`, `PLACEMENT_KINDS`, ... in `model-editor.js`, enforced by
`test_locale_bundles.py`'s `test_every_value_the_model_editor_offers_has_a_word_in_both_bundles`).
This redesign adds a second, sentence-length key per value (e.g.
`model.basis.sentence.per_member_crossing`) beside the existing short label,
extending a mechanism the app already has rather than inventing a new one — this is
also how "hardcoded UI choices become data" is satisfied for wording: the phrasing
lives in the locale bundles, correctable without a code release, while the
*vocabulary itself* (which basis kinds exist at all) stays typed.

## Starting a new panel: template gallery over `duplicateOf()`

`model-editor.js` already has `duplicateOf()`/`openForDuplicate()`: cloning any
existing model into a new independent draft is a shipped feature, currently reached
by picking a row from the model list. "New Panel" becomes a gallery of a handful of
curated starter models — privacy tongue-and-groove, picket, semi-privacy dogear,
horizontal slat, ranch rail — as visual cards, each just calling the existing
`duplicateOf()` under a friendlier entry point. This gets "templates never lock you
in" for free: a duplicate is already an ordinary, fully independent draft the moment
it's created, no special "templated" state to track or escape.

**Open for spec review**: the gallery defaults to showing the curated starters, with
a "start blank" card alongside them for the rare from-scratch build — this was my
synthesis of the brainstorming options, not a choice the user explicitly clicked
through, so it's called out here rather than assumed settled.

**Resolved (2026-08-17), and the five are not these five.** The "start blank"
card ships alongside the starters as proposed. What changed is *what the starters
are*: the five families named above are product families, and two of them —
tongue-and-groove and semi-privacy dogear — are board PROFILES. The panel model
does not express a board profile, and the catalog supplies no product with one.
A starter naming a SKU that does not exist previews as an unsupplied line and is
then refused at the publish gate, which is the worst thing a starter can do: it
invites an author into a document they cannot finish, for a reason that is not on
the screen they were given.

So the cards are five STRUCTURES the mechanism can say, over products that
exist — vertical slat, picket, board-on-board, horizontal boards, ranch rail —
and each is put through `validate_model` and a real priced preview in the suite,
which is what keeps that promise mechanical rather than aspirational. Adding a
tongue-and-groove starter later is a catalog change first and a card second, in
that order. Everything else the section says is unchanged: each card just calls
the existing clone path, so a starter is an ordinary independent draft the moment
it is opened, with no "templated" state to track or escape.

## Architecture

**Amended during implementation (2026-08-17): one backend change, and it is the
fasteners.** This section said "no backend or schema change" and the table above
said the drawing "shows the actual fastener positions as clickable dots". Those
could not both hold: `report/elevation.py` deliberately emits no fixing geometry
("screws are counted, not drawn, and a dot per screw would bury the panel"), so
the dots had to come from somewhere. Computing them in the browser was the option
that kept this paragraph true, and it is the wrong one — a dot count worked out
in JS from rectangles the server placed is a second derivation of a quantity, and
it would eventually show twelve dots beside a BOM line buying eight screws, on
the one surface built so an author can see what a basis does.

So `PanelElevation` gained `fixings`: fastener PLACES, each carrying its own
count, with the slot's whole `qty` apportioned across the places its basis names.
`sum(place.qty) == slot.qty` by construction, for every basis and every
`qty_per_basis` — the drawing cannot disagree with the numbers it is derived
from. `ResolvedSlot` gained `basis` to carry the rule (a geometry parameter
beside `orientation`, which is what the others there are); a run stored before it
carries `""` and draws nothing rather than a guess. Both are DERIVED read models,
so this is not a change to anything stored: `FenceModel`, the API surface and the
draft/active/retired lifecycle are untouched, exactly as the non-goals require.

Everything else below stands. The canvas constructs the same `FrameSlot` / `Infill` /
`Fixings` / `Requirement` JSON the current form builds, and saves it through the same
`PUT`/`preview` routes. Drag geometry (a rail's y-position, a board's width and
gap-after, in-panel pixel↔mm conversion) is pure point-list math with no DOM or
state coupling, mirroring `base-top.js`'s existing pattern for the side-view editor
(CLAUDE.md: "Base-top geometry is pure... Keep new profile math there so it stays
testable in node") — a new `panel-canvas-geom.js` module holds that math, and a
thinner `model-editor.js` wires it to pointer events and the inspector, the same
division `profile.js` already has with `base-top.js`. The existing raw-JSON
`toggleAdvanced` escape hatch is unchanged in mechanism, now the fallback specifically
for variant conditions the sentence builder can't express (and, if one turns up
during implementation, any other rare combination the plain-language layer doesn't
yet cover — the fallback is the parity guarantee, not a thing to design away).

Frontend contracts this must keep, per CLAUDE.md: `t()`/`data-i18n` with he/en key
parity for every new label and sentence fragment; lengths through `tu()`/`{u}`, never
a literal unit; **the panel canvas is never mirrored in RTL**, joining the plan
canvas and profile SVG in that standing rule; user/catalog text through `esc()`;
`attrs.colour` swatches reaching an SVG `fill` stay validated at catalog load
(`^#[0-9a-fA-F]{6}$`), not re-validated or weakened here.

## Testing

- Node-level geometry tests for the new pure drag math, alongside
  `test_base_top_module.py`'s existing pattern.
- `test_locale_bundles.py` gains coverage for the new sentence-phrasing keys, the
  same shape it already uses for `GRADES`/`BASES`/etc. — every closed-vocabulary value
  needs both a label and a sentence-phrasing key in both bundles.
- Browser smoke (`tools/ui_smoke.py`): create a panel from a template, drag a rail,
  toggle an overlap, reorder a product-priority list, publish — asserting the saved
  document matches what the equivalent raw-form edit would have produced, so the
  canvas is proven to be a *view* over the existing model, not a second source of
  truth for what a panel is.
- No change to the Python-side model validation or golden scenarios: the JSON shape
  produced is unchanged, so `tests/scenarios` is unaffected by this work.

## What this doc does not decide

Left for the implementation plan: the exact SVG/pointer-event mechanics per control
kind (drag handle hit-testing, snap increments), the diagram assets for each `basis`
value, and whether the inspector is a fixed side panel or a popover anchored to the
selected element. These are implementation choices within the shape this doc fixes,
not open design questions.
