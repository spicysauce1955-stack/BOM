# Panel Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Models tab's sentence-row form with a live SVG panel drawing that *is* the editor — click a board, rail or fastener to select it, drag it to change it, read and type exact values in a contextual inspector whose controls speak boards and screws rather than `basis` and `justification`.

**Architecture:** The drawing stays the server's. `report/elevation.py` is already the derived read model that places every rectangle, and this plan extends it with fastener POSITIONS (never a second geometry engine in JS). The frontend gains four small modules with one responsibility each — a pure vocabulary/document module, pure drag inverse-math, a pure condition-sentence ⇄ AST translator, and an interaction layer over the existing `elevation.js` renderer — leaving `model-editor.js` as session lifecycle plus mounting.

**Tech Stack:** Python 3.12 / Pydantic v2 / FastAPI (backend read model); vanilla ES modules + SVG, no build step (frontend); pytest, node-driven module tests (`tests/web/`), CDP browser smoke (`tools/ui_smoke.py`).

**Spec:** `docs/superpowers/specs/2026-08-17-panel-canvas-design.md`

## Global Constraints

These are the spec's and CLAUDE.md's project-wide rules. Every task's requirements implicitly include this section.

- **Integer millimetres at rest.** Display units (mm | cm) convert only at the field boundary, via `toDisplayValue`/`toMm`; length strings render through `tu()` with `{…_mm}` + `{u}`, never a literal unit.
- **The panel canvas is NEVER mirrored in RTL.** It joins the plan canvas, the profile SVG and the macro elevation in that standing rule (`direction: ltr` in CSS).
- **Every user-visible string goes through `t("key")` (JS) or `data-i18n` (HTML)**; `i18n/he.json` and `en.json` must keep identical key sets (`test_bundle_key_parity`).
- **No new geometry engine in JS.** Every rectangle drawn comes from `PanelElevation`. The frontend owns only the INVERSE — pixel/mm → the authored number a drag writes.
- **No silent capability loss.** Every value of every closed vocabulary stays offered; the raw-JSON `toggleAdvanced` escape hatch stays, and its exit is never gated on the JSON being valid.
- **`gap_after_mm` MAY BE NEGATIVE.** A negative gap is an overlap, and board-on-board and shadowbox are exactly that. No `min` reaches that field, at any layer.
- **A swatch reaching an SVG/CSS colour is validated `^#[0-9a-fA-F]{6}$`** (`SWATCH_RE`) before it is assigned; user and catalog text interpolated into `innerHTML` goes through `esc()`.
- **No stored-shape change.** `FenceModel` JSON, the API surface and the draft/active/retired lifecycle are untouched. `ResolvedSlot`/`PanelElevation` are DERIVED read models and may gain fields.
- Frontend modules communicate only via `state.js` and their callers' callbacks; no module writes another's DOM subtree.

## Decisions this plan fixes (asked and answered before writing it)

1. **Fastener dots come from the server.** `report/elevation.py` gains fixing POSITIONS whose quantities sum to the resolver's own `qty`, so the drawing cannot disagree with the BOM. This is the one backend change; the spec's "no backend change" claim is superseded here, deliberately, and the spec doc is amended in Task 11.
2. **The starter gallery ships five STRUCTURES over SKUs that exist** (vertical slat, picket, board-on-board, horizontal slat, ranch rail). The spec's tongue-and-groove and dogear are board PROFILES, which this model cannot express and this catalog cannot supply; a starter naming an absent SKU previews unsupplied and is refused at the publish gate. Plus a "start blank" card.
3. **Id / name / grade, the variant picker and the option axes stay as a compact settings strip** above the canvas. They are not things you can click on a drawing. The canvas + inspector replace the frame / infill / fixings row lists entirely.

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `src/fenceai/web/static/js/panel-model.js` | The closed vocabularies (`BASES`, `PLACEMENT_KINDS`, …) and the pure document shapes (`blankModel`, `default*`, `draftCopyOf`, `duplicateOf`, `specOf`, `freeId`, `idCollision`). No DOM, no state — three modules share it, so it cannot live in any one of them. |
| `src/fenceai/web/static/js/panel-canvas-geom.js` | Pure drag inverse-math: where the handles are, and what authored number a drag writes. No DOM, no state. |
| `src/fenceai/web/static/js/condition-sentence.js` | Pure `Expr` AST ⇄ `{field, cmp, value}` sentence translation for variant conditions. |
| `src/fenceai/web/static/js/panel-canvas.js` | The interactive drawing: mounts `renderElevation`'s SVG, overlays handles, owns pointer events, calls back. Touches only the host element its caller hands it. |
| `src/fenceai/web/static/js/panel-inspector.js` | Builds the detached inspector DOM for one selection: plain-language controls over the live document. |
| `src/fenceai/web/static/js/panel-templates.js` | The five starter structures, as pure functions returning drafts. |
| `tests/web/test_panel_model_module.py` | (renamed from `test_model_editor_module.py`) the document shapes, judged by the real schema. |
| `tests/web/test_panel_canvas_geom_module.py` | The drag math, in node. |
| `tests/web/test_condition_sentence_module.py` | Sentence ⇄ AST round-trips, judged by the real `Expr` schema. |
| `tests/web/test_panel_templates_module.py` | Every starter is a model `validate_model` accepts. |

**Modified**

| File | Change |
|---|---|
| `src/fenceai/fencemodel/resolve.py` | `ResolvedSlot.basis` — the fixing rule's basis, carried as a geometry parameter like `orientation` already is. |
| `src/fenceai/report/elevation.py` | `ElevationFixing` + `PanelElevation.fixings`, derived. |
| `src/fenceai/web/static/js/elevation.js` | Export `elevationLayout()` (the transform `renderElevation` already computes) and add the `fixings` draw option. |
| `src/fenceai/web/static/js/model-editor.js` | Loses the vocabularies, the document shapes and the four row-list renderers; gains the settings strip and the canvas/inspector mounting. |
| `src/fenceai/web/static/index.html` | `#tab-models` markup: settings strip, canvas host, inspector host, gallery host. |
| `src/fenceai/web/static/style.css` | Canvas handles, inspector, gallery cards, fastener dots. |
| `src/fenceai/web/static/i18n/{en,he}.json` | Sentence phrasings per vocabulary value, plus the new surface's labels. |
| `tests/web/test_locale_bundles.py` | Read the vocabularies from `panel-model.js`; require a sentence key beside every label key; retarget the shared-renderer owners. |
| `tests/report/test_elevation.py` | The fastener positions and the sum-equals-qty invariant. |
| `tools/ui_smoke.py` | The Models-tab block, driven through the canvas. |

---

### Task 1: `panel-model.js` — one home for the vocabularies and the document shapes

Three modules need `BASES` and `defaultSlot()`. Leaving them in `model-editor.js` and importing them from the inspector makes a cycle (`model-editor` → `inspector` → `model-editor`); copying them makes two answers to "which basis kinds exist". So they move out first, with no behaviour change, and the two node suites that read them follow.

**Files:**
- Create: `src/fenceai/web/static/js/panel-model.js`
- Modify: `src/fenceai/web/static/js/model-editor.js` (delete lines 41–192's consts and pure shapes; import them)
- Rename: `tests/web/test_model_editor_module.py` → `tests/web/test_panel_model_module.py`
- Modify: `tests/web/test_locale_bundles.py` (`test_every_value_the_model_editor_offers_has_a_word_in_both_bundles` reads `panel-model.js`)

**Interfaces:**
- Produces: `panel-model.js` exports, unchanged in name and behaviour — `ROLES, LENGTH_RULES, PLACEMENT_KINDS, JUSTIFICATIONS, EXCESS, BASES, APPROVALS, GRADES, AXIS_KINDS, COUNT_PARAMS, SWATCH_RE, blankModel(id), defaultEligibility(), defaultEligibleMember(sku, priority), defaultRequirement(role), defaultPlacement(kind), defaultSlot(key), defaultMember(key), defaultInfill(), defaultFixing(key), defaultAxis(key), defaultVariant(), draftCopyOf(model), duplicateOf(model, newId), specOf(model, index), freeId(base, rows), canChooseId(session), idCollision(session, rows)`.

- [ ] **Step 1: Move the code**

Cut `model-editor.js` lines 41–192 (the `// --- the closed vocabularies` block through `specOf`) plus `freeId`, `canChooseId` and `idCollision` into a new `panel-model.js`, keeping every comment verbatim — those comments are the reasons the values are what they are. Head the new file:

```js
// The fence model as DATA: the closed vocabularies the schema fixes, and the
// shape of every row an "+ Add" button appends.
//
// Pure — no DOM, no state, no fetch — because three surfaces now read it: the
// editor's lifecycle (model-editor.js), the inspector that renders a selected
// element's controls (panel-inspector.js), and the starter templates
// (panel-templates.js). A second copy of BASES is two answers to "which fixing
// bases exist", and they diverge the first time one of them is extended.
//
// The vocabularies are pinned against `fencemodel/model.py` in BOTH directions
// by tests/web/test_panel_model_module.py: a value offered and not in the schema
// is a save that 422s, and one in the schema and not here is a product line
// nobody can author.
```

In `model-editor.js`, replace them with one import:

```js
import {
  APPROVALS, AXIS_KINDS, BASES, COUNT_PARAMS, EXCESS, GRADES, JUSTIFICATIONS,
  LENGTH_RULES, PLACEMENT_KINDS, ROLES, SWATCH_RE, blankModel, canChooseId,
  defaultAxis, defaultEligibility, defaultEligibleMember, defaultFixing,
  defaultInfill, defaultMember, defaultPlacement, defaultRequirement,
  defaultSlot, defaultVariant, draftCopyOf, duplicateOf, freeId, idCollision,
  specOf,
} from "./panel-model.js";
```

`model-editor.js` keeps `const idTaken = () => idCollision(session, listing);` and its own `canChooseId()` call site — note the existing call `canChooseId()` at `renderHead` passes no argument; change it to `canChooseId(session)`.

- [ ] **Step 2: Point the node suite at the new module**

`git mv tests/web/test_model_editor_module.py tests/web/test_panel_model_module.py`, then in it:

- `_js_const` reads `panel-model.js`;
- the `SCRIPT` import comes from `panel-model.js`;
- delete the `globalThis.localStorage` / `globalThis.document` stubs from `SCRIPT` — the new module reaches neither, and a stub that is no longer needed is a claim about the module that stops being true silently;
- update the two source-reading assertions that scan `model-editor.js`:
  - `test_a_negative_gap_is_offered_by_the_field_itself` scans for the `num(member, "gap_after_mm", …)` call — that call moves to `panel-inspector.js` in Task 7. For THIS task point it at `model-editor.js` still (unchanged there); Task 7 re-points it.
  - `test_the_swatch_field_refuses_anything_but_plain_hex` reads `function swatchField` out of `model-editor.js` — unchanged in this task.
- update the module docstring's first line to name `static/js/panel-model.js`.

- [ ] **Step 3: Point the locale guard at the new module**

In `tests/web/test_locale_bundles.py::test_every_value_the_model_editor_offers_has_a_word_in_both_bundles`, change `src = (STATIC / "js" / "model-editor.js").read_text()` to `panel-model.js`, and rename the test to `test_every_value_the_model_vocabulary_offers_has_a_word_in_both_bundles`. Update its docstring's reference from "the editor's arrays" to "panel-model.js's arrays".

- [ ] **Step 4: Run the suites**

Run: `uv run pytest tests/web -q`
Expected: PASS, same count as before the move.

- [ ] **Step 5: Commit**

```bash
git add -A src/fenceai/web/static/js tests/web
git commit -m "refactor(models): the fence-model vocabulary becomes its own module"
```

---

### Task 2: The elevation says where the fasteners land

`per_member_crossing` is the hardest thing in the fixing vocabulary to picture, and the drawing is the one place it could be obvious. Today `report/elevation.py` emits nothing for a fixing — "screws are counted, not drawn, and a dot per screw would bury the panel". Both halves of that stay true: what is emitted is a POSITION with a QUANTITY on it, and the positions' quantities sum to exactly the `qty` the resolver counted, so the picture cannot claim a different number of screws from the BOM line beside it.

**Files:**
- Modify: `src/fenceai/fencemodel/resolve.py` (`ResolvedSlot`, the fixing loop ~585–605)
- Modify: `src/fenceai/report/elevation.py`
- Test: `tests/report/test_elevation.py`

**Interfaces:**
- Produces: `fenceai.report.elevation.ElevationFixing` with fields `slot_key: str, role: str, basis: str, index: int, x_mm: Mm, y_mm: Mm, qty: int`; `PanelElevation.fixings: list[ElevationFixing] = []`. `ResolvedSlot.basis: str = ""`.
- Consumes: `ResolvedSlot.slot_kind`, `.qty`, `ElevationMember.kind/x_mm/y_mm/w_mm/h_mm` — all existing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/report/test_elevation.py`:

```python
# --- fasteners: positions, never screws ---------------------------------------

def _fixing_model(basis: str, qty_per_basis: int = 1):
    """M_SLAT with its screw rule re-based, so one fixture exercises all six."""
    model = M_SLAT.model_copy(deep=True)
    rule = model.default_spec.fixings[0]
    model.default_spec.fixings[0] = rule.model_copy(
        update={"basis": basis, "qty_per_basis": qty_per_basis, "qty_param": None})
    return model


def _fixing_slot(panel, key="screw"):
    return next(s for s in panel.slots if s.slot_key == key)


@pytest.mark.parametrize("basis", [
    "per_panel", "per_frame_member", "per_member", "per_end_member", "per_gap",
    "per_member_crossing",
])
def test_the_drawn_fasteners_total_exactly_what_the_resolver_counted(basis):
    """The property the dots exist to keep: a drawing that showed twelve points
    beside a BOM line buying eight screws would be a picture disagreeing with the
    numbers it is derived from. `qty` rides on the POINT, so the sum is exact by
    construction for every basis and every `qty_per_basis`."""
    model = _fixing_model(basis, qty_per_basis=3)
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    drawn = [f for f in elevation.fixings if f.slot_key == "screw"]
    assert drawn, basis
    assert sum(f.qty for f in drawn) == _fixing_slot(panel).qty
    assert all(f.basis == basis for f in drawn)


def test_a_fastener_point_sits_inside_the_opening():
    elevation = elevation_of(_fixing_model("per_member_crossing"))
    for f in elevation.fixings:
        assert 0 <= f.x_mm <= BAY.clear_width_mm
        assert 0 <= f.y_mm <= BAY.height_mm


def test_per_crossing_puts_a_point_where_a_board_meets_a_rail():
    """The basis nobody can picture from its name. Two rails and N slats is
    2N crossings, and each point is on a rail's line."""
    model = _fixing_model("per_member_crossing")
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    slats = by_slot(elevation, "slat")
    rails = by_slot(elevation, "rail")
    points = [f for f in elevation.fixings if f.slot_key == "screw"]
    assert len(points) == len(slats) * len(rails)
    rail_bands = [(r.y_mm, r.y_mm + r.h_mm) for r in rails]
    assert all(any(lo <= f.y_mm <= hi for lo, hi in rail_bands) for f in points)


def test_per_gap_puts_a_point_between_two_boards_and_never_on_one():
    model = _fixing_model("per_gap")
    panel = resolve_panel(model.default_spec, BAY)
    elevation = panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm)
    slats = sorted(by_slot(elevation, "slat"), key=lambda m: m.x_mm)
    points = sorted((f for f in elevation.fixings), key=lambda f: f.x_mm)
    assert len(points) == len(slats) - 1
    for point, left, right in zip(points, slats, slats[1:]):
        assert left.x_mm + left.w_mm <= point.x_mm <= right.x_mm


def test_a_panel_with_no_fixing_rule_draws_no_fasteners():
    model = M_SLAT.model_copy(deep=True)
    model.default_spec.fixings = []
    assert elevation_of(model).fixings == []


def test_a_resolved_panel_that_predates_the_basis_draws_no_fasteners():
    """A run stored before `basis` rode on the slot carries "" — and a drawing
    that guessed a basis for it would put screws where that fence has none."""
    panel = resolve_panel(M_SLAT.default_spec, BAY)
    for slot in panel.slots:
        if slot.slot_kind == "fixing":
            slot.basis = ""
    assert panel_elevation(panel, BAY.clear_width_mm, BAY.height_mm).fixings == []


def test_fasteners_are_deterministic():
    model = _fixing_model("per_member_crossing")
    assert elevation_of(model) == elevation_of(model)
```

Add `import pytest` to the test module's imports if it is not already there.

- [ ] **Step 2: Run them to watch them fail**

Run: `uv run pytest tests/report/test_elevation.py -q -k fasten or crossing or per_gap`
Expected: FAIL — `PanelElevation` has no attribute `fixings`.

- [ ] **Step 3: Carry the basis on the resolved slot**

In `src/fenceai/fencemodel/resolve.py`, add to `ResolvedSlot`, in the "geometry PARAMETERS, never rectangles" block, after `cycle_gaps_mm`:

```python
    # fixing slots: which basis put this count where it is. A geometry PARAMETER
    # exactly like `orientation` above — the elevation derives the fastener
    # POINTS from it, and a read model that had to guess the basis from a count
    # would put screws where the fence has none. "" is a run stored before this
    # field existed, and draws nothing rather than a guess.
    basis: str = ""
```

and in the fixing loop, add `basis=rule.basis,` to the `ResolvedSlot(...)` construction.

- [ ] **Step 4: Derive the points**

In `src/fenceai/report/elevation.py`, add the model after `ElevationMember`:

```python
class ElevationFixing(BaseModel):
    """Where one fixing rule's fasteners land, in panel coordinates.

    A POINT, never a screw: `qty` is how many fasteners the resolver counted for
    this point, and the points of a slot sum to exactly the `qty` on that slot.
    That is the whole reason this is derived here rather than drawn by the client
    — a dot count worked out in JS would eventually say twelve beside a BOM line
    buying eight, on the one surface built so an author can see what a basis
    means. "A dot per screw would bury the panel" still holds; this is a dot per
    PLACE, carrying its own count.
    """

    slot_key: str
    role: str
    basis: str
    index: int
    x_mm: Mm
    y_mm: Mm
    qty: int
```

Add to `PanelElevation`:

```python
    # where the fasteners land — points, with a count on each. Empty for a panel
    # with no fixing rule, and for a run stored before the basis rode on the slot.
    fixings: list[ElevationFixing] = []
```

In `panel_elevation`, after `out.details = list(_details(panel))`:

```python
    out.fixings = list(_fixings(panel, out.members, width_mm, height_mm))
```

And the derivation:

```python
def _fixings(panel: ResolvedPanel, members: list[ElevationMember],
             width_mm: Mm, height_mm: Mm):
    """The fastener points of every fixing slot.

    Each basis names a set of PLACES on the drawing, and the slot's whole `qty`
    is apportioned across them (remainder to the first, integer arithmetic, one
    rounding) — so the drawing's total is the resolver's total for every basis
    and every `qty_per_basis`, including the ones that do not divide.

    Nothing is recomputed: the places are read off the rectangles this same
    function already placed. A slot whose basis names no place — one gap on a
    single-board panel, a crossing on a panel with no frame — draws nothing
    rather than a point somewhere plausible.
    """
    frame = [m for m in members if m.kind == "frame"]
    infill = sorted((m for m in members if m.kind == "infill"),
                    key=lambda m: (m.x_mm, m.y_mm))
    for slot in panel.slots:
        if slot.slot_kind != "fixing" or not slot.basis:
            continue
        places = _places(slot.basis, frame, infill, width_mm, height_mm)
        if not places:
            continue
        shares = _apportion_qty(slot.qty, len(places))
        for index, ((x, y), qty) in enumerate(zip(places, shares)):
            yield ElevationFixing(
                slot_key=slot.slot_key, role=slot.role, basis=slot.basis,
                index=index, x_mm=x, y_mm=y, qty=qty,
            )


def _places(basis: str, frame: list[ElevationMember], infill: list[ElevationMember],
            width_mm: Mm, height_mm: Mm) -> list[tuple[Mm, Mm]]:
    centre = lambda m: (m.x_mm + m.w_mm // 2, m.y_mm + m.h_mm // 2)  # noqa: E731
    if basis == "per_panel":
        return [(width_mm // 2, height_mm // 2)]
    if basis == "per_frame_member":
        return [centre(m) for m in frame]
    if basis == "per_member":
        return [centre(m) for m in infill]
    if basis == "per_end_member":
        return [centre(m) for m in (infill[:1] + infill[-1:])] if infill else []
    if basis == "per_gap":
        return [((a.x_mm + a.w_mm + b.x_mm) // 2, (a.y_mm + a.h_mm + b.y_mm) // 2)
                for a, b in zip(infill, infill[1:])]
    if basis == "per_member_crossing":
        return [place for m in infill for f in frame
                if (place := _overlap_centre(m, f)) is not None]
    return []


def _overlap_centre(a: ElevationMember, b: ElevationMember) -> tuple[Mm, Mm] | None:
    """Where two drawn members cross, or None when they do not touch.

    A crossing that is not on the drawing is not a place to put a screw: a slat
    seated between two rails crosses both, and a slat that stops short of the top
    rail crosses one. Reporting the second one twice would be the drawing
    inventing a fixing the resolver's own count does not contain — so the
    apportionment runs over the crossings that ARE there.
    """
    x0, x1 = max(a.x_mm, b.x_mm), min(a.x_mm + a.w_mm, b.x_mm + b.w_mm)
    y0, y1 = max(a.y_mm, b.y_mm), min(a.y_mm + a.h_mm, b.y_mm + b.h_mm)
    if x1 < x0 or y1 < y0:
        return None
    return ((x0 + x1) // 2, (y0 + y1) // 2)


def _apportion_qty(total: int, places: int) -> list[int]:
    """Split a count across places, remainder to the first — so the points sum
    to the whole exactly, for a `qty_per_basis` that does not divide evenly."""
    base, rem = divmod(total, places)
    return [base + (1 if i < rem else 0) for i in range(places)]
```

Note `zip(infill, infill[1:])` for `per_gap` walks placements in drawn order, which is the axis order the fit produced — `infill` is sorted by `(x_mm, y_mm)` above precisely so a horizontal pattern's gaps read up the panel and a vertical one's across it.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/report tests/fencemodel tests/scenarios -q`
Expected: PASS. `test_screws_are_counted_not_drawn` must still pass untouched — screws stay out of `members`.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/fencemodel/resolve.py src/fenceai/report/elevation.py tests/report/test_elevation.py
git commit -m "feat(elevation): where the fasteners land, with the count on the point"
```

---

### Task 3: `elevation.js` shares its transform, and can draw the fasteners

The canvas overlays drag handles on the drawing, in the drawing's own coordinates. That transform already exists inside `renderElevation`; a second copy in the canvas module is how a handle ends up 3 px from the board it moves. So it is extracted and exported, and `renderElevation` calls it — one implementation, as with everything else in this file.

**Files:**
- Modify: `src/fenceai/web/static/js/elevation.js`
- Test: `tests/web/test_elevation_module.py`

**Interfaces:**
- Produces:
  - `elevationLayout(elev) -> {s, x0, y0, vw, vh, w_mm, h_mm} | null` — `s` is px-per-mm in viewBox units, `x0`/`y0` the drawing origin, `vw`/`vh` the viewBox size. `null` when there is nothing to draw.
  - `layoutPx(layout, x_mm, y_mm) -> [x, y]` and `layoutMm(layout, x, y) -> [x_mm, y_mm]` — the transform and its inverse, in PANEL coordinates (y up from the panel bottom).
  - `renderElevation(elev, {onSelect, annotations, joints, fixings})` — `fixings` defaults to **false**, so the Panel and Structure tabs are byte-identical to today.
- Consumes: `PanelElevation.fixings` from Task 2.

- [ ] **Step 1: Write the failing tests**

Append to the `SCRIPT` in `tests/web/test_elevation_module.py` (and to its import list `elevationLayout, layoutMm, layoutPx`):

```js
// the transform, and its inverse: a handle drawn from it lands on the member
const layout = elevationLayout(SLAT);
out.layout_round_trip = (() => {
  const [x, y] = layoutPx(layout, 300, 900);
  const [mx, my] = layoutMm(layout, x, y);
  return [mx, my];
})();
out.layout_origin = layoutPx(layout, 0, SLAT.height_mm);   // panel top-left
out.layout_top = layout.y0;
out.layout_empty = elevationLayout({members: []});
```

and the assertions:

```python
def test_the_layout_transform_inverts_exactly(elev):
    """The canvas overlays handles in the drawing's own coordinates. A second
    copy of this transform is how a handle ends up beside the board it moves."""
    assert elev["layout_round_trip"] == [300, 900]


def test_the_panel_origin_is_the_drawing_origin(elev):
    """Panel y counts UP from the bottom; SVG y grows down. The top-left of the
    panel is therefore the drawing's own origin — and the origin is NOT a
    constant: a fitted-gap callout takes a lane above the panel and moves it
    down, which is exactly why an overlay must read the layout rather than
    assume the padding."""
    x, y = elev["layout_origin"]
    assert round(x) == 58                      # PAD_START
    assert round(y) == round(elev["layout_top"])


def test_there_is_no_layout_for_a_panel_with_nothing_in_it(elev):
    assert elev["layout_empty"] is None
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/web/test_elevation_module.py -q`
Expected: FAIL — `elevationLayout` is not exported.

- [ ] **Step 3: Extract the transform**

In `elevation.js`, above `renderElevation`:

```js
/** The drawing's box and scale, in viewBox units — the ONE transform.
 *
 * `renderElevation` computed this inline until the canvas needed to put drag
 * handles on the same rectangles. Two copies of a scale is a handle three pixels
 * from the board it moves, so it is computed here and called from both. `null`
 * when there is nothing to draw, which is the same condition the renderer
 * refuses on.
 *
 * `annotations` changes the padding (a gap callout needs room above the panel),
 * so a caller overlaying handles must pass the SAME options it renders with. */
export function elevationLayout(elev, { annotations = true } = {}) {
  const w = elev?.width_mm || 0;
  const h = elev?.height_mm || 0;
  if (!(w > 0) || !(h > 0) || !(elev?.members || []).length) return null;
  const dim = annotations ? gapDimension(elev) : null;
  const pitch = annotations ? pitchDimension(elev) : null;
  const margins = annotations ? edgeMargins(elev) : null;
  const above = [dim, pitch].filter((d) => d?.axis === "x").length;
  const beside = [dim, pitch].filter((d) => d?.axis === "y").length;
  const padTop = above ? PAD_TOP_GAP + (above - 1) * CALLOUT_STEP : PAD_TOP;
  const padEnd = beside ? PAD_END_GAP + (beside - 1) * CALLOUT_STEP : PAD_END;
  const padBottom = PAD_BOTTOM + (margins ? MARGIN_ROW : 0);
  const s = Math.min(MAX_DRAW_W / w, MAX_DRAW_H / h);
  return {
    s, x0: PAD_START, y0: padTop, w_mm: w, h_mm: h,
    dw: w * s, dh: h * s,
    vw: PAD_START + w * s + padEnd, vh: padTop + h * s + padBottom,
    dim, pitch, margins,
  };
}

/** Panel millimetres -> viewBox units. Panel y counts UP from the bottom. */
export const layoutPx = (L, x_mm, y_mm) =>
  [L.x0 + x_mm * L.s, L.y0 + (L.h_mm - y_mm) * L.s];

/** ... and back, for a pointer landing on the drawing. */
export const layoutMm = (L, x, y) =>
  [Math.round((x - L.x0) / L.s), Math.round(L.h_mm - (y - L.y0) / L.s)];
```

Rewrite `renderElevation`'s opening to consume it:

```js
export function renderElevation(elev, {
  onSelect, annotations = true, joints = true, fixings = false,
} = {}) {
  const L = elevationLayout(elev, { annotations });
  if (!L) return null;
  const rects = elevationRects(elev);
  const { s, x0, y0, dw, dh, vw, vh, dim, pitch, margins } = L;
  const w = L.w_mm;
  const h = L.h_mm;
  const px = (mm) => x0 + mm * s;
  const py = (mm) => y0 + mm * s;
  …unchanged from `const svg = el("svg", …` down…
```

(`py` keeps taking an already-flipped SVG-space millimetre, as it does today — `elevationRects` flips. `layoutPx` takes PANEL y and flips itself; the two are used by different callers and both are exercised by tests.)

- [ ] **Step 4: Draw the fasteners, when asked**

After the `elev-edges` group and before `if (annotations)`:

```js
  // The fasteners, when the caller wants them. OFF by default: the Panel and
  // Structure tabs answer "what is this panel made of", where a screw is a BOM
  // line; the canvas answers "what does per-member-crossing MEAN", where it is
  // the only way to see it. Each dot is a PLACE and carries its own count, so a
  // panel with 96 screws is 32 dots reading "×3" and not a rash.
  if (fixings) {
    const group = el("g", { class: "elev-fixings" }, svg);
    for (const f of elev.fixings || []) {
      const [fx, fy] = layoutPx(L, f.x_mm, f.y_mm);
      const dot = el("circle", {
        class: "elev-fixing", cx: r(fx), cy: r(fy), r: 5,
        "data-slot": f.slot_key, "data-index": String(f.index),
      }, group);
      el("title", {}, dot).textContent = `${f.slot_key} ×${f.qty}`;
    }
  }
```

- [ ] **Step 5: Style the dots**

In `style.css`, beside the other `.elev-*` rules:

```css
/* a fastener PLACE, with its count in the title: never one dot per screw */
.elev-fixing { fill: #f59e0b; stroke: #78350f; stroke-width: 1; }
.elev-fixing.selected { fill: #2563eb; stroke: #1e3a8a; stroke-width: 2; }
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/web/static/js/elevation.js src/fenceai/web/static/style.css tests/web/test_elevation_module.py
git commit -m "feat(elevation): one shared transform, and fasteners on request"
```

---

### Task 4: `panel-canvas-geom.js` — what a drag writes

The pure half of the canvas, and the reason a `base-top.js` exists beside `profile.js`: the arithmetic that turns "the user let go of this handle here" into "`bottom_inset_mm` is now 150" is testable in node, and only testable there if it never touches the DOM.

Two rules the tests pin, because both are easy to get plausibly wrong:

- **Width is absolute, gap and margin are DELTAS.** A member's width is its width. A *gap* is not: under `excess: "space"` the fit spreads the leftover across the gaps, so the gap you see is not the gap that was authored. Reading the drawn distance back as the authored number would make every drag of a spread pattern jump.
- **A drag never authors a document the publish gate refuses.** `validate_model` bounds a member's net advance (`width_mm + gap_after_mm > 0`); the drag clamps to it rather than letting the author discover it at the gate.

**Files:**
- Create: `src/fenceai/web/static/js/panel-canvas-geom.js`
- Test: `tests/web/test_panel_canvas_geom_module.py`

**Interfaces:**
- Produces:
  - `SNAP_MM` (= 5), `snap(mm, step = SNAP_MM)`
  - `handlesFor(elev, spec) -> Handle[]` where `Handle = {id, kind, slot_key, index, axis, x_mm, y_mm}` and `kind ∈ "placement" | "width" | "gap" | "margin"`
  - `placementFromDrag(placement, {orientation, index, count, height_mm, width_mm, x_mm, y_mm}) -> placement'` (new object, never mutated)
  - `widthFromDrag(member, {x_mm, member_x_mm}) -> int`
  - `gapFromDrag(member, {delta_mm}) -> int`
  - `marginFromDrag(infill, {delta_mm}) -> int`
  - `overlapOf(member) -> {overlaps: boolean, amount_mm: int}`
  - `gapForOverlap(overlaps, amount_mm) -> int`
- Consumes: `PanelElevation` (`members`, `width_mm`, `height_mm`) and the authored `PanelSpec` — both plain objects.

- [ ] **Step 1: Write the failing tests**

Create `tests/web/test_panel_canvas_geom_module.py`:

```python
"""What a drag on the panel canvas WRITES (static/js/panel-canvas-geom.js).

The canvas's pure half, tested the way `base-top.js` is: a browser can only show
that a rail moved, and what breaks silently is which authored number moved with
it — a `from_top` rail whose offset is measured from the bottom is a drag that
works perfectly until the bay height changes.

Two rules here are load-bearing and neither is obvious from a screenshot:

  * a WIDTH is read absolutely and a GAP as a delta. Under `excess: "space"` the
    fit spreads the leftover across the gaps, so the gap on the drawing is not
    the gap that was authored; reading the drawn distance back would make every
    drag of a spread pattern jump by the spread;
  * a drag may not author what the publish gate refuses. `validate_model` bounds
    the member's net advance, so the overlap a drag can reach is bounded here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import {
  SNAP_MM, gapForOverlap, gapFromDrag, handlesFor, marginFromDrag, overlapOf,
  placementFromDrag, snap, widthFromDrag,
} from "./js/panel-canvas-geom.js";

const out = {};
const H = 1800, W = 2400;

// --- placement: each kind reads from the end it names ----------------------
const at = (placement, extra) => placementFromDrag(placement, {
  orientation: "horizontal", index: 0, count: 1, height_mm: H, width_mm: W,
  x_mm: 0, y_mm: 0, ...extra,
});
out.from_bottom = at({kind: "from_bottom", offset_mm: 100}, {y_mm: 640});
out.from_top = at({kind: "from_top", offset_mm: 100}, {y_mm: 640});
out.fraction = at({kind: "fraction", permille: 500}, {y_mm: 900});
out.fraction_top = at({kind: "fraction", permille: 500}, {y_mm: 1800});

// distributed: only the OUTER rails are placeable, and each moves its own inset
const dist = {kind: "distributed", count: 3, count_param: null,
              bottom_inset_mm: 0, top_inset_mm: 0};
out.dist_bottom = at(dist, {index: 0, count: 3, y_mm: 200});
out.dist_top = at(dist, {index: 2, count: 3, y_mm: 1600});
out.dist_middle = at(dist, {index: 1, count: 3, y_mm: 900});
// ... and neither inset may cross the other
out.dist_clamped = at({...dist, top_inset_mm: 1700}, {index: 0, count: 3, y_mm: 1750});
out.dist_negative = at(dist, {index: 0, count: 3, y_mm: -300});

// a VERTICAL frame slot reads x, not y
out.vertical = placementFromDrag({kind: "from_bottom", offset_mm: 0}, {
  orientation: "vertical", index: 0, count: 1, height_mm: H, width_mm: W,
  x_mm: 600, y_mm: 0,
});

// the input is never mutated
out.placement_input_untouched = dist;

// --- width is absolute -----------------------------------------------------
const member = {key: "slat", width_mm: 100, gap_after_mm: 20};
out.width = widthFromDrag(member, {x_mm: 445, member_x_mm: 300});
out.width_min = widthFromDrag(member, {x_mm: 299, member_x_mm: 300});
// widening past the overlap that swallows it is refused, not authored
const overlapping = {key: "board", width_mm: 140, gap_after_mm: -120};
out.width_vs_overlap = widthFromDrag(overlapping, {x_mm: 400, member_x_mm: 300});

// --- gap and margin are DELTAS --------------------------------------------
out.gap_wider = gapFromDrag(member, {delta_mm: 30});
out.gap_to_overlap = gapFromDrag(member, {delta_mm: -75});
// the bound that IS real: width + gap must still advance
out.gap_clamped = gapFromDrag(member, {delta_mm: -400});
out.margin = marginFromDrag({edge_margin_mm: 40}, {delta_mm: 25});
out.margin_floor = marginFromDrag({edge_margin_mm: 40}, {delta_mm: -200});

// --- the sign is the control's business, not the author's -----------------
out.overlap_of = [overlapOf({gap_after_mm: 20}), overlapOf({gap_after_mm: -40}),
                  overlapOf({gap_after_mm: 0})];
out.gap_for_overlap = [gapForOverlap(false, 20), gapForOverlap(true, 40),
                       gapForOverlap(true, -40)];

// --- handles: one per authored number a drag can reach --------------------
const ELEV = {
  width_mm: W, height_mm: H,
  members: [
    {slot_key: "rail", role: "rail", kind: "frame", index: 0,
     x_mm: 0, y_mm: 0, w_mm: W, h_mm: 60},
    {slot_key: "rail", role: "rail", kind: "frame", index: 1,
     x_mm: 0, y_mm: 1740, w_mm: W, h_mm: 60},
    {slot_key: "slat", role: "infill", kind: "infill", index: 0,
     x_mm: 40, y_mm: 0, w_mm: 100, h_mm: H},
    {slot_key: "slat", role: "infill", kind: "infill", index: 1,
     x_mm: 160, y_mm: 0, w_mm: 100, h_mm: H},
  ],
};
const SPEC = {
  frame: [{key: "rail", orientation: "horizontal",
           placement: {kind: "distributed", count: 2, bottom_inset_mm: 0,
                       top_inset_mm: 0}}],
  infill: {orientation: "vertical", edge_margin_mm: 40,
           pattern: [{key: "slat", width_mm: 100, gap_after_mm: 20}]},
  fixings: [],
};
const handles = handlesFor(ELEV, SPEC);
out.handle_kinds = handles.map((h) => `${h.kind}:${h.slot_key}#${h.index}`);
out.handle_at = Object.fromEntries(handles.map((h) => [h.id, [h.x_mm, h.y_mm]]));

// a three-rail distributed slot offers handles on the ENDS only
const three = {...ELEV, members: [
  ...ELEV.members.slice(0, 2),
  {slot_key: "rail", role: "rail", kind: "frame", index: 2,
   x_mm: 0, y_mm: 870, w_mm: W, h_mm: 60},
]};
out.three_rail_handles = handlesFor(three, SPEC)
  .filter((h) => h.kind === "placement").map((h) => h.index);

out.snap = [snap(103), snap(107), snap(-103), SNAP_MM];

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def g():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_each_placement_kind_reads_from_the_end_it_names(g):
    """A `from_top` rail dragged to 640 mm above the panel bottom is 1160 mm
    down from the top — and stays there when the bay gets taller, which is the
    whole reason the kinds are different."""
    assert g["from_bottom"] == {"kind": "from_bottom", "offset_mm": 640}
    assert g["from_top"] == {"kind": "from_top", "offset_mm": 1160}
    assert g["fraction"]["permille"] == 500
    assert g["fraction_top"]["permille"] == 1000


def test_only_the_outer_rails_of_a_distributed_slot_are_placeable(g):
    """`distributed` spreads N members between two insets: the ends are the two
    numbers there are, and an interior rail has no authored position to move.
    Returning the placement unchanged is what makes the canvas honest about it —
    the inspector says so in words, and no handle is drawn."""
    assert g["dist_bottom"]["bottom_inset_mm"] == 200
    assert g["dist_bottom"]["top_inset_mm"] == 0
    assert g["dist_top"]["top_inset_mm"] == 200
    assert g["dist_middle"] == {"kind": "distributed", "count": 3,
                                "count_param": None, "bottom_inset_mm": 0,
                                "top_inset_mm": 0}


def test_the_insets_may_not_cross_each_other_or_leave_the_panel(g):
    assert g["dist_clamped"]["bottom_inset_mm"] <= 1800 - 1700
    assert g["dist_negative"]["bottom_inset_mm"] == 0


def test_a_vertical_frame_slot_is_placed_across_the_panel(g):
    assert g["vertical"] == {"kind": "from_bottom", "offset_mm": 600}


def test_the_placement_handed_in_is_never_mutated(g):
    assert g["placement_input_untouched"] == {
        "kind": "distributed", "count": 3, "count_param": None,
        "bottom_inset_mm": 0, "top_inset_mm": 0}


def test_a_width_is_read_absolutely(g):
    assert g["width"] == 145
    assert g["width_min"] == 1, "a board of no width is not a board"


def test_a_width_may_not_be_dragged_under_its_own_overlap(g):
    """`validate_model` bounds the member's net advance: a board 120 mm inside
    its neighbour may not be narrowed to 100. The gate's rule, enforced at the
    handle rather than discovered at publish."""
    assert g["width_vs_overlap"] == 121


def test_a_gap_moves_by_the_drag_not_to_it(g):
    """The fit spreads the leftover across the gaps under `excess: space`, so
    the drawn gap is not the authored one. A drag adds what the pointer moved."""
    assert g["gap_wider"] == 50
    assert g["gap_to_overlap"] == -55, "a negative gap is an overlap, and typable"
    assert g["gap_clamped"] == -99, "width + gap must still advance"


def test_a_margin_moves_by_the_drag_and_never_below_zero(g):
    assert g["margin"] == 65
    assert g["margin_floor"] == 0


def test_the_overlap_control_hides_the_sign(g):
    """"Overlaps next board" + a positive amount. The author never has to
    remember that a minus means an overlap; the control means it."""
    assert g["overlap_of"] == [
        {"overlaps": False, "amount_mm": 20},
        {"overlaps": True, "amount_mm": 40},
        {"overlaps": False, "amount_mm": 0},
    ]
    assert g["gap_for_overlap"] == [20, -40, -40]


def test_there_is_one_handle_per_authored_number_a_drag_can_reach(g):
    assert sorted(g["handle_kinds"]) == sorted([
        "placement:rail#0", "placement:rail#1",
        "width:slat#0", "gap:slat#0", "margin:slat#0",
    ])


def test_a_handle_sits_on_the_thing_it_moves(g):
    at = g["handle_at"]
    assert at["placement:rail:0"] == [1200, 30]      # centre of the bottom rail
    assert at["width:slat:0"] == [140, 900]          # the board's trailing edge
    assert at["gap:slat:0"] == [150, 900]            # the middle of the gap after it
    assert at["margin:slat:0"] == [40, 900]          # the board's leading edge


def test_three_rails_still_offer_two_handles(g):
    assert sorted(g["three_rail_handles"]) == [0, 2]


def test_snapping_is_five_millimetres(g):
    assert g["snap"] == [105, 105, -105, 5]
```

- [ ] **Step 2: Run to see it fail**

Run: `uv run pytest tests/web/test_panel_canvas_geom_module.py -q`
Expected: FAIL — cannot resolve `./js/panel-canvas-geom.js`.

- [ ] **Step 3: Write the module**

Create `src/fenceai/web/static/js/panel-canvas-geom.js`:

```js
// The panel canvas's pure half: where the handles are, and what a drag WRITES.
//
// Same division `base-top.js` has with `profile.js`, for the same reason —
// "make it that height" and "make this board wider" are point transforms, and a
// transform tangled with a pointer event is only testable by aiming a mouse at
// a browser. Nothing here touches the DOM, the document store or `state.js`.
//
// The drawing is NOT computed here. Every rectangle comes from the server's
// `PanelElevation` (`report/elevation.py`), because the fit that decides where a
// board sits has a justification x excess matrix behind it and a JS copy of it
// would eventually disagree with the cut list. What this module owns is the
// INVERSE: a pointer landing at 445 mm means `width_mm = 145`.
//
// Two rules that look like details and are not:
//
//   * a WIDTH is read absolutely, a GAP and a MARGIN as DELTAS. Under
//     `excess: "space"` the fit spreads the leftover across the gaps, so the
//     drawn gap is not the authored one — reading it back absolutely makes every
//     drag of a spread pattern jump by the spread.
//   * a drag may not author what the publish gate refuses. `validate_model`
//     bounds a member's net advance (width + gap > 0), so the overlap a handle
//     can reach is bounded to it. The author meets the rule at the handle,
//     where it is a limit, rather than at the gate, where it is a rejection.

export const SNAP_MM = 5;

export const snap = (mm, step = SNAP_MM) => Math.round(mm / step) * step;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));

// --- placement ---------------------------------------------------------------

/** The placement a drag to (x_mm, y_mm) writes — a NEW object, never a mutation.
 *
 * Each kind is measured from the end it names, which is what makes them
 * different things rather than four spellings of a height: a `from_top` rail
 * stays 150 mm below the cap when the bay gets taller, and a `fraction` one
 * stays halfway up it.
 *
 * `distributed` has no per-member position at all — it spreads `count` members
 * between two insets — so only the outermost drawn member is placeable, and it
 * moves the inset on its own side. An interior rail returns the placement
 * unchanged; the canvas draws it no handle, and the inspector says why. */
export function placementFromDrag(placement, {
  orientation = "horizontal", index = 0, count = 1,
  height_mm = 0, width_mm = 0, x_mm = 0, y_mm = 0,
} = {}) {
  const axisLen = orientation === "vertical" ? width_mm : height_mm;
  const along = snap(clamp(orientation === "vertical" ? x_mm : y_mm, 0, axisLen));
  switch (placement?.kind) {
    case "from_bottom":
      return { ...placement, offset_mm: along };
    case "from_top":
      return { ...placement, offset_mm: axisLen - along };
    case "fraction":
      return { ...placement,
               permille: axisLen ? Math.round((along * 1000) / axisLen) : 0 };
    case "distributed": {
      if (index !== 0 && index !== count - 1) return { ...placement };
      const bottom = placement.bottom_inset_mm || 0;
      const top = placement.top_inset_mm || 0;
      return index === 0
        ? { ...placement, bottom_inset_mm: clamp(along, 0, Math.max(axisLen - top, 0)) }
        : { ...placement, top_inset_mm: clamp(axisLen - along, 0,
                                              Math.max(axisLen - bottom, 0)) };
    }
    default:
      return { ...placement };
  }
}

// --- the infill pattern ------------------------------------------------------

/** The width a drag of the trailing edge writes, absolutely.
 *
 * Floored at 1 mm, and at whatever the member's own overlap needs: a board
 * 120 mm inside its neighbour cannot be 100 mm wide, because `validate_model`
 * requires the pattern to advance. */
export function widthFromDrag(member, { x_mm, member_x_mm }) {
  const floor = Math.max(1, 1 - (member?.gap_after_mm || 0));
  return Math.max(floor, snap(x_mm - member_x_mm));
}

/** The gap a drag writes: the authored gap PLUS what the pointer moved.
 *
 * May go negative — that is an overlap, and board-on-board and shadowbox are
 * exactly that. Bounded only where the gate bounds it. */
export function gapFromDrag(member, { delta_mm }) {
  const width = member?.width_mm || 0;
  return Math.max(1 - width, (member?.gap_after_mm || 0) + snap(delta_mm));
}

/** The edge margin a drag writes, by the same delta rule and never negative. */
export function marginFromDrag(infill, { delta_mm }) {
  return Math.max(0, (infill?.edge_margin_mm || 0) + snap(delta_mm));
}

/** The gap as the author reads it: "does it overlap, and by how much". */
export function overlapOf(member) {
  const gap = member?.gap_after_mm || 0;
  return { overlaps: gap < 0, amount_mm: Math.abs(gap) };
}

/** ... and back. The control owns the sign, so the author never has to. */
export const gapForOverlap = (overlaps, amount_mm) =>
  (overlaps ? -Math.abs(amount_mm) : Math.abs(amount_mm));

// --- handles -----------------------------------------------------------------

/** Every authored number a drag can reach on this drawing, as a point on it.
 *
 * One handle per NUMBER, not per rectangle: twenty slats of one pattern member
 * share one width, so the handle rides the first drawn one. `id` is
 * `kind:slot_key:index` — stable across a re-render, which is what lets a drag
 * survive the re-price that follows it. */
export function handlesFor(elev, spec) {
  const out = [];
  const members = elev?.members || [];
  const height = elev?.height_mm || 0;
  const mid = (m) => [m.x_mm + m.w_mm / 2, m.y_mm + m.h_mm / 2];

  for (const slot of spec?.frame || []) {
    const drawn = members
      .filter((m) => m.kind === "frame" && m.slot_key === slot.key)
      .sort((a, b) => (a.y_mm - b.y_mm) || (a.x_mm - b.x_mm));
    const placeable = slot.placement?.kind === "distributed"
      ? [0, drawn.length - 1].filter((i, n, all) => i >= 0 && all.indexOf(i) === n)
      : drawn.map((_, i) => i);
    for (const i of placeable) {
      const m = drawn[i];
      if (!m) continue;
      const [cx, cy] = mid(m);
      out.push({ id: `placement:${slot.key}:${i}`, kind: "placement",
                 slot_key: slot.key, index: i,
                 axis: slot.orientation === "vertical" ? "x" : "y",
                 x_mm: Math.round(cx), y_mm: Math.round(cy) });
    }
  }

  const infill = spec?.infill;
  const vertical = (infill?.orientation ?? "vertical") === "vertical";
  (infill?.pattern || []).forEach((member) => {
    const drawn = members
      .filter((m) => m.kind === "infill" && m.slot_key === member.key)
      .sort((a, b) => (a.x_mm - b.x_mm) || (a.y_mm - b.y_mm));
    const first = drawn[0];
    if (!first) return;
    const [cx, cy] = mid(first);
    const trailing = vertical
      ? [first.x_mm + first.w_mm, cy] : [cx, first.y_mm + first.h_mm];
    const leading = vertical ? [first.x_mm, cy] : [cx, first.y_mm];
    out.push({ id: `width:${member.key}:0`, kind: "width", slot_key: member.key,
               index: 0, axis: vertical ? "x" : "y",
               x_mm: Math.round(trailing[0]), y_mm: Math.round(trailing[1]) });
    // the gap handle sits in the middle of the gap AFTER this member, which is
    // where the eye looks for it — and there is one only if something follows
    const next = members
      .filter((m) => m.kind === "infill"
        && (vertical ? m.x_mm > first.x_mm : m.y_mm > first.y_mm))
      .sort((a, b) => (vertical ? a.x_mm - b.x_mm : a.y_mm - b.y_mm))[0];
    if (next) {
      const gapMid = vertical
        ? [(first.x_mm + first.w_mm + next.x_mm) / 2, cy]
        : [cx, (first.y_mm + first.h_mm + next.y_mm) / 2];
      out.push({ id: `gap:${member.key}:0`, kind: "gap", slot_key: member.key,
                 index: 0, axis: vertical ? "x" : "y",
                 x_mm: Math.round(gapMid[0]), y_mm: Math.round(gapMid[1]) });
    }
    out.push({ id: `margin:${member.key}:0`, kind: "margin", slot_key: member.key,
               index: 0, axis: vertical ? "x" : "y",
               x_mm: Math.round(leading[0]), y_mm: Math.round(leading[1]) });
  });
  return out;
  // `height` is read by callers off the elevation, not here — a handle is a
  // point on the drawing and the drawing already decided where that is.
}
```

Delete the unused `height` binding if the linter objects; it is referenced only by the closing comment.

Only the FIRST pattern member gets a margin handle in practice — `handlesFor` emits one per member; the canvas draws only the one on the member whose drawn rectangle is outermost. Keep the emission simple and let the test above pin the single-member case.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/web/test_panel_canvas_geom_module.py -q`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/panel-canvas-geom.js tests/web/test_panel_canvas_geom_module.py
git commit -m "feat(models): the drag arithmetic the canvas will need, in node"
```

---

### Task 5: `condition-sentence.js` — a variant condition as a sentence

Today a new variant's first screen is `{"op":"cmp","cmp":">=","left":{"op":"field","path":"panel.height_mm"},"right":{"op":"lit","value":1800}}` in a textarea. Every shipped model and every fixture uses exactly one shape — a field compared to a literal — so that shape becomes a sentence, and everything else keeps the JSON box it has now.

**Files:**
- Create: `src/fenceai/web/static/js/condition-sentence.js`
- Test: `tests/web/test_condition_sentence_module.py`

**Interfaces:**
- Produces:
  - `CONDITION_FIELDS: string[]` — the field paths the sentence offers.
  - `CONDITION_CMPS: string[]` — `[">=", ">", "==", "!=", "<", "<="]`.
  - `readSentence(expr) -> {path, cmp, value} | null` — null when the AST is not a field-to-literal comparison.
  - `writeSentence({path, cmp, value}) -> expr`
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests**

Create `tests/web/test_condition_sentence_module.py`:

```python
"""A variant's condition as a sentence (static/js/condition-sentence.js).

The AST the box holds today is `Expr` (knowledge/ast.py) and stays it: this
module reads the ONE shape every shipped model uses — a field compared to a
literal — into three fields, and writes it back. Anything else reads back as
`null`, and the canvas leaves the raw JSON box in charge of it.

Judged by the real `Expr` schema and the real evaluator, not by a fixture:
a sentence that produces JSON pydantic rejects is a 422 the author cannot see
coming, and one that produces a VALID expression meaning something else is
worse.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.knowledge.ast import evaluate_expr, parse_expr

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import {
  CONDITION_CMPS, CONDITION_FIELDS, readSentence, writeSentence,
} from "./js/condition-sentence.js";

const HEIGHT_AT_LEAST_1800 = {
  op: "cmp", cmp: ">=",
  left: {op: "field", path: "panel.height_mm"},
  right: {op: "lit", value: 1800},
};

console.log(JSON.stringify({
  fields: CONDITION_FIELDS,
  cmps: CONDITION_CMPS,
  read: readSentence(HEIGHT_AT_LEAST_1800),
  round_trip: writeSentence(readSentence(HEIGHT_AT_LEAST_1800)),
  // the shapes the sentence cannot say: an `and`, a field-to-field comparison,
  // and a literal on the left
  not_a_sentence: [
    readSentence({op: "and", args: [HEIGHT_AT_LEAST_1800]}),
    readSentence({op: "cmp", cmp: ">=",
                  left: {op: "field", path: "a"}, right: {op: "field", path: "b"}}),
    readSentence({op: "cmp", cmp: ">=",
                  left: {op: "lit", value: 1}, right: {op: "field", path: "a"}}),
    readSentence(null),
  ],
  written: CONDITION_CMPS.map((cmp) =>
    writeSentence({path: "panel.width_mm", cmp, value: 2400})),
  // a value the author has half-typed must not become a string in the AST
  blank_value: writeSentence({path: "panel.height_mm", cmp: ">=", value: ""}),
}));
"""


@pytest.fixture(scope="module")
def s():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_shipped_condition_reads_as_a_sentence(s):
    assert s["read"] == {"path": "panel.height_mm", "cmp": ">=", "value": 1800}


def test_the_sentence_round_trips_to_the_same_ast(s):
    assert s["round_trip"] == {
        "op": "cmp", "cmp": ">=",
        "left": {"op": "field", "path": "panel.height_mm"},
        "right": {"op": "lit", "value": 1800},
    }


def test_anything_the_sentence_cannot_say_reads_as_nothing(s):
    """The parity guarantee: a condition this cannot express keeps the raw JSON
    box, rather than being silently rewritten into one it can."""
    assert s["not_a_sentence"] == [None, None, None, None]


def test_every_written_condition_is_an_expression_the_backend_accepts(s):
    """The claim the round trip alone does not make: pydantic has to take it."""
    for raw in s["written"]:
        expr = parse_expr(raw)
        assert evaluate_expr(expr, {"panel": {"width_mm": 2400}}) in (True, False)


def test_a_blank_value_is_a_number_not_a_string(s):
    """`{"op":"lit","value":""}` validates and then compares a string to a
    millimetre — an expression that is accepted and means nothing."""
    assert s["blank_value"]["right"] == {"op": "lit", "value": 0}


def test_the_offered_fields_are_facts_a_bay_actually_carries(s):
    """A path nothing supplies is a variant that never fires, and the resolver
    treats a missing field as 'not applicable' rather than as an error — so the
    author would get silence."""
    from fenceai.fencemodel.resolve import PanelContext

    ctx = PanelContext(centre_width_mm=2500, clear_width_mm=2400, height_mm=1800)
    supplied = ctx.condition_ctx()
    for path in s["fields"]:
        head, _, tail = path.partition(".")
        assert head in supplied, path
        assert tail in supplied[head], path
```

- [ ] **Step 2: Confirm the field list against the real context**

Run: `uv run python -c "from fenceai.fencemodel.resolve import PanelContext; print(PanelContext(centre_width_mm=2500, clear_width_mm=2400, height_mm=1800).condition_ctx())"`

Use exactly the keys it prints for `CONDITION_FIELDS` (expected to include `panel.height_mm`, `panel.width_mm` and the vertical mode). If a key it prints is not a number, do not offer it in the numeric sentence.

- [ ] **Step 3: Run the tests to watch them fail**

Run: `uv run pytest tests/web/test_condition_sentence_module.py -q`
Expected: FAIL — module not found.

- [ ] **Step 4: Write the module**

```js
// A variant's condition, as a sentence.
//
// The stored shape is and stays `Expr` (knowledge/ast.py). Every shipped model
// and every fixture conditions a variant one way — a field compared to a
// literal — so THAT shape gets words ("applies when panel height is at least
// 1800 mm") and everything else keeps the raw JSON box it has today.
//
// `readSentence` returning null is the parity guarantee, not a failure: a
// condition this cannot say is left alone rather than rewritten into one it can.

export const CONDITION_FIELDS = ["panel.height_mm", "panel.width_mm"];
export const CONDITION_CMPS = [">=", ">", "==", "!=", "<", "<="];

/** The three fields of a field-to-literal comparison, or null. */
export function readSentence(expr) {
  if (!expr || expr.op !== "cmp") return null;
  if (expr.left?.op !== "field" || typeof expr.left.path !== "string") return null;
  if (expr.right?.op !== "lit") return null;
  if (!CONDITION_CMPS.includes(expr.cmp)) return null;
  return { path: expr.left.path, cmp: expr.cmp, value: expr.right.value };
}

/** ... and the expression they mean. A half-typed value is 0 rather than "":
 *  `{op:"lit", value:""}` validates and then compares a string to a millimetre,
 *  which is an expression that is accepted and means nothing. */
export function writeSentence({ path, cmp, value }) {
  const n = Number(value);
  return {
    op: "cmp", cmp: CONDITION_CMPS.includes(cmp) ? cmp : ">=",
    left: { op: "field", path },
    right: { op: "lit", value: Number.isFinite(n) ? Math.round(n) : 0 },
  };
}
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/web/test_condition_sentence_module.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static/js/condition-sentence.js tests/web/test_condition_sentence_module.py
git commit -m "feat(models): a variant condition as three fields, or as it was"
```

---

### Task 6: Every vocabulary value gets a sentence, in both languages

The spec's mechanism: a second, sentence-length key beside each existing short label, living in the locale bundles so the phrasing is correctable without a code release while the vocabulary itself stays typed. The guard test comes with the keys, or the next value added ships a raw `model.basis.sentence.per_gap` into a Hebrew UI.

**Files:**
- Modify: `src/fenceai/web/static/i18n/en.json`, `src/fenceai/web/static/i18n/he.json`
- Modify: `tests/web/test_locale_bundles.py`

- [ ] **Step 1: Write the failing guard**

In `tests/web/test_locale_bundles.py`, beside the existing vocabulary test:

```python
# The vocabularies that appear on the canvas as a SENTENCE rather than a label:
# "Screws at: every board x every rail crossing", not "basis: per_member_crossing".
# The values stay a typed, code-defined enum (fulfillment reads them); only the
# phrasing is data, which is what makes it correctable without a release.
SENTENCE_VOCABULARIES = [
    ("BASES", "model.basis."),
    ("PLACEMENT_KINDS", "model.placement."),
    ("JUSTIFICATIONS", "model.justification."),
    ("EXCESS", "model.excess."),
    ("LENGTH_RULES", "model.length_rule."),
]


def test_every_sentence_vocabulary_value_has_both_a_label_and_a_phrasing():
    """The canvas reads `model.basis.sentence.<v>`; the compact places still read
    `model.basis.<v>`. A value with only one of the two renders either a raw key
    inside a Hebrew sentence or a sentence where a chip should be."""
    import re

    en, he = _bundles()
    src = (STATIC / "js" / "panel-model.js").read_text()
    missing = []
    for const, prefix in SENTENCE_VOCABULARIES:
        body = re.search(rf"const {const} = \[(.*?)\];", src, re.S)
        assert body, const
        for value in re.findall(r'"([a-z_]+)"', body.group(1)):
            for key in (f"{prefix}{value}", f"{prefix}sentence.{value}"):
                for lang, table in (("en", en), ("he", he)):
                    if key not in table:
                        missing.append(f"{lang}:{key}")
    assert not missing, missing
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/web/test_locale_bundles.py -q -k sentence_vocabulary`
Expected: FAIL, listing every `*.sentence.*` key.

- [ ] **Step 3: Add the phrasings**

Add to `en.json` (and the matching Hebrew to `he.json` — Hebrew-first app, so write real Hebrew, not transliteration). Lengths carry no literal unit; none of these strings names a millimetre, so none needs `{u}`.

```jsonc
  "model.basis.sentence.per_panel":            "once per panel",
  "model.basis.sentence.per_frame_member":     "on every rail",
  "model.basis.sentence.per_member":           "on every board",
  "model.basis.sentence.per_end_member":       "on the first and last board only",
  "model.basis.sentence.per_gap":              "in every gap between boards",
  "model.basis.sentence.per_member_crossing":  "where every board meets every rail",

  "model.placement.sentence.distributed":  "spaced evenly",
  "model.placement.sentence.from_bottom":  "measured up from the bottom",
  "model.placement.sentence.from_top":     "measured down from the top",
  "model.placement.sentence.fraction":     "at a fraction of the height",

  "model.justification.sentence.start":         "packed against the first post",
  "model.justification.sentence.end":           "packed against the last post",
  "model.justification.sentence.center":        "centred, with the slack split between the posts",
  "model.justification.sentence.spread_to_fit": "spread evenly across the opening",

  "model.excess.sentence.truncate": "leave the leftover space where it falls",
  "model.excess.sentence.space":    "share the leftover out between the gaps",

  "model.length_rule.sentence.clear_between_posts": "cut to the opening between the posts",
  "model.length_rule.sentence.centre_to_centre":    "cut from post centre to post centre",
  "model.length_rule.sentence.overlap":             "cut to the opening plus an overlap at each end",
  "model.length_rule.sentence.panel_height":        "cut to the full height of the panel",
  "model.length_rule.sentence.between_frame":       "cut to fit between the rails it seats into"
```

Hebrew (`he.json`), same keys:

```jsonc
  "model.basis.sentence.per_panel":            "פעם אחת לכל פאנל",
  "model.basis.sentence.per_frame_member":     "על כל מסילה",
  "model.basis.sentence.per_member":           "על כל קרש",
  "model.basis.sentence.per_end_member":       "רק על הקרש הראשון והאחרון",
  "model.basis.sentence.per_gap":              "בכל מרווח בין הקרשים",
  "model.basis.sentence.per_member_crossing":  "בכל מפגש של קרש עם מסילה",

  "model.placement.sentence.distributed":  "בפריסה אחידה",
  "model.placement.sentence.from_bottom":  "נמדד כלפי מעלה מהתחתית",
  "model.placement.sentence.from_top":     "נמדד כלפי מטה מהחלק העליון",
  "model.placement.sentence.fraction":     "בשבר מהגובה",

  "model.justification.sentence.start":         "צמוד לעמוד הראשון",
  "model.justification.sentence.end":           "צמוד לעמוד האחרון",
  "model.justification.sentence.center":        "במרכז, כשהעודף מתחלק בין העמודים",
  "model.justification.sentence.spread_to_fit": "בפריסה אחידה על פני הפתח",

  "model.excess.sentence.truncate": "להשאיר את העודף היכן שהוא נופל",
  "model.excess.sentence.space":    "לחלק את העודף בין המרווחים",

  "model.length_rule.sentence.clear_between_posts": "נחתך לפתח שבין העמודים",
  "model.length_rule.sentence.centre_to_centre":    "נחתך ממרכז עמוד למרכז עמוד",
  "model.length_rule.sentence.overlap":             "נחתך לפתח בתוספת חפיפה בכל קצה",
  "model.length_rule.sentence.panel_height":        "נחתך לגובה המלא של הפאנל",
  "model.length_rule.sentence.between_frame":       "נחתך כך שיתאים בין המסילות שהוא יושב בהן"
```

- [ ] **Step 4: Run the bundle suite**

Run: `uv run pytest tests/web/test_locale_bundles.py -q`
Expected: PASS — including `test_bundle_key_parity`, `test_no_empty_translations`, `test_lengths_carry_the_unit_placeholder_not_a_literal` and `test_no_double_escaped_unicode_in_bundles`.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/i18n tests/web/test_locale_bundles.py
git commit -m "feat(i18n): a sentence for every value the panel vocabulary offers"
```

---

### Task 7: `panel-inspector.js` — the selected element, in plain language

The controls the spec's table describes. Built as a detached element the caller mounts, like `renderElevation` — the inspector never reaches for a global id, so the same function serves the canvas and (in this task) the existing form, which is what makes the swap in Task 9 a mount change rather than a rewrite.

Every capability of the W4 rows survives: `role`, `qty`, `length_rule` (+ `overlap_mm`), `option_axis` and `sku_by_option`, the ordered eligibility with `approval`, `key`, `orientation`, `thickness_mm`, `face_offset_mm`, `base_ref`/`top_ref`, `count_param`/`qty_param`. What changes is how they read and that the ordered list is dragged rather than numbered.

**Files:**
- Create: `src/fenceai/web/static/js/panel-inspector.js`
- Modify: `src/fenceai/web/static/js/model-editor.js` (mount it under the existing rows, driven by a `selection`)
- Modify: `src/fenceai/web/static/index.html` (`<div id="model-inspector"></div>` inside `#model-editor`)
- Modify: `src/fenceai/web/static/style.css`
- Modify: `src/fenceai/web/static/i18n/{en,he}.json`
- Modify: `tests/web/test_locale_bundles.py` (shared-renderer owners), `tests/web/test_panel_model_module.py` (the two source-scanning tests follow `num(member, …)` and `swatchField` to their new home)

**Interfaces:**
- Consumes: `panel-model.js` (vocabularies, `defaultEligibleMember`), `panel-canvas-geom.js` (`overlapOf`, `gapForOverlap`), `builder-ui.js` (`el`, `field`, `option`, `skuSelect`, `loadCatalogProducts`), `units.js`, `i18n.js`.
- Produces:
  - `renderInspector(host, {selection, spec, model, products, preview, onChange, onSelect})` — replaces `host`'s children with the controls for `selection`. `selection` is `{kind, key}` with `kind ∈ "frame" | "infill" | "fixing" | "panel"`; `onChange({rerender})` is called after every committed edit; `onSelect(selection)` when a control moves the selection (e.g. "edit the board this fixing lands on").
  - `SELECTION_NONE = { kind: "panel", key: null }`

- [ ] **Step 1: Move the field builders**

Cut `num`, `text`, `choice`, `removeButton`, `i18nLabelField`, `swatchField` and `requirementRows` out of `model-editor.js` into `panel-inspector.js`, keeping every comment. They lose their implicit dependency on module-level `session`/`touch`: `touch` becomes the injected `onChange`, and `session.model` becomes an argument. Signature changes:

- `num(obj, key, labelKey, {length, min, onCommit})` → unchanged, with `onCommit` defaulting to the module-level `notify` set by `renderInspector`.
- `requirementRows(req, products)` → `requirementRows(req, {products, model})` — `session.model.option_axes` becomes `model.option_axes`.

Head the file:

```js
// The inspector: one selected thing on the panel canvas, in the words a person
// who builds fences uses.
//
// The vocabularies underneath are unchanged and still typed — `basis`,
// `justification`, `length_rule` are read by fulfillment code that has to know
// what each value means, so adding one stays a code change with tests. What is
// data is the PHRASING: each value renders through `model.<vocab>.sentence.<v>`
// out of the locale bundles, correctable without a release
// (test_locale_bundles.py pins both halves in both languages).
//
// Detached DOM only: `renderInspector` fills the host it is handed and reaches
// for no global id, which is what lets the canvas and the old row list mount the
// same controls. Every edit goes through `onChange`, which is the caller's
// "the document moved" — nothing here saves, previews or knows what a session is.
//
// `data-f="<field>"` rides on every input, as it did on the rows: the controls
// are generated, so a test (or a person reading the DOM) has no other stable way
// to name "the length rule of the selected slot", and a positional selector is
// exactly the kind that keeps passing after a field moves.
```

- [ ] **Step 2: Write the sentence controls**

Add to `panel-inspector.js`:

```js
/** A select over a closed vocabulary, rendered as a SENTENCE.
 *
 * The same values `choice()` offers, with the phrasing key instead of the label
 * key — so "Screws at: where every board meets every rail" is one control, and
 * the enum behind it is untouched. A value the document carries and this list
 * does not is still shown, exactly as `choice` does it: an authoring surface may
 * not silently rewrite a document it merely opened. */
function sentenceChoice(obj, key, values, prefix, labelKey, opts = {}) {
  return choice(obj, key, values, (v) => t(`${prefix}sentence.${v}`), labelKey, opts);
}
```

and the per-kind renderers, in this order inside `renderInspector`:

- **`frame`** — heading `model.inspect.rail` with the slot key as a `<bdi class="sku">`; then
  - `text(slot, "key", "model.key", {size: 10, ltr: true})`
  - `sentenceChoice(slot, "orientation", ["horizontal","vertical"], "model.orientation.", "model.orientation")` (needs `model.orientation.sentence.*` keys: "across the panel" / "up the panel")
  - the placement kind through `sentenceChoice(..., PLACEMENT_KINDS, "model.placement.", "model.placement", {rerender: true})`, rebuilding `slot.placement` with `defaultPlacement()` on change, exactly as the row did
  - the kind's own numbers, each a live readout of the drag: `count`, `count_param`, `bottom_inset_mm`, `top_inset_mm` / `offset_mm` / `permille`
  - when `placement.kind === "distributed" && placement.count > 2`, a `<div class="meta">` reading `t("model.inspect.interior_not_placeable")` — "the rails in between are spaced evenly; move the top or bottom one to move the band" — which is the sentence the missing handle in Task 4 owes the author
  - `requirementRows(slot.requirement, {products, model})`
  - a remove button calling `onChange({rerender: true})` after splicing
- **`infill`** (a pattern member is selected) — two groups:
  - `model.inspect.all_boards`: orientation, `sentenceChoice(infill, "justification", JUSTIFICATIONS, "model.justification.", "model.justification")`, `sentenceChoice(infill, "excess", EXCESS, "model.excess.", "model.excess")`, `num(infill, "edge_margin_mm", "model.edge_margin_mm", {length: true})`
  - `model.inspect.this_board`: `key`, `width_mm` (min 1), **the overlap control** (below), `face_offset_mm`, `thickness_mm`, `base_ref`, `top_ref`, then `requirementRows`
- **`fixing`** — `key`, `sentenceChoice(fix, "basis", BASES, "model.basis.", "model.basis", {rerender: true})` with a small inline schematic per value (Step 4), `qty_per_basis`, `qty_param`, `requirementRows`
- **`panel`** (nothing selected) — the variant sentence builder (Task 5's module) plus the add buttons, moved here in Task 9.

The overlap control, replacing `num(member, "gap_after_mm", …)`:

```js
/** "Overlaps next board" + a positive amount.
 *
 * `gap_after_mm` may be NEGATIVE and that is the whole point — a negative gap is
 * an overlap, and board-on-board and shadowbox ARE that. The sign is what the
 * author had to remember; this control remembers it instead. No `min` reaches
 * the amount field either: the bound that is real lives on the member's net
 * advance, in `validate_model` and in `gapFromDrag`.
 */
function gapControl(member, notify) {
  const wrap = el("div", { class: "builder-row" });
  const state = overlapOf(member);
  const box = el("input", { type: "checkbox", "data-f": "overlaps" });
  box.checked = state.overlaps;
  const amount = el("input", {
    type: "number", "data-f": "gap_after_mm", step: inputStep(),
    value: String(toDisplayValue(state.amount_mm)),
  });
  const commit = () => {
    member.gap_after_mm = gapForOverlap(box.checked, toMm(amount.value) ?? 0);
    notify();
  };
  box.addEventListener("change", commit);
  amount.addEventListener("change", commit);
  wrap.append(
    el("label", { class: "builder-field" },
      box, el("span", { class: "meta", text: t("model.overlaps_next") })),
    field(box.checked ? "model.overlap_amount" : "model.gap_amount", amount));
  return wrap;
}
```

`data-f="gap_after_mm"` stays on the amount field so the smoke script and any reader still address it by name.

The ordered product list, replacing the numbered `priority` column:

```js
/** "Boards, in preference order" — the eligibility, dragged rather than numbered.
 *
 * `priority` is the company's stated preference and the ORDER it is read in is
 * part of the answer, so the list is the priority: dropping a row renumbers
 * every member from 1, which is the only way the two can never disagree. The
 * numbers still exist in the document; they have simply stopped being something
 * a person types. */
function eligibilityList(req, { products, model }, notify) { … }
```

Implementation notes for it: a `<ul class="pref-list">` of `<li draggable="true" data-eligible-row="i">`, each carrying the existing `skuSelect` (`data-f="sku"`), a swatch chip painted from `products[sku]?.attrs?.colour` **only when `SWATCH_RE.test()` passes**, a checkbox `data-f="approval"` labelled `model.approval.sentence.auto` ("let the system substitute this automatically") writing `"auto"` / `"suggest_only"`, and a remove button. On `drop`, splice the dragged index to the drop index and rewrite `member.priority = i + 1` across the list, then `notify({rerender: true})`.

- [ ] **Step 3: Add the locale keys**

New keys in both bundles (`model.inspect.rail`, `model.inspect.board`, `model.inspect.screws`, `model.inspect.panel`, `model.inspect.all_boards`, `model.inspect.this_board`, `model.inspect.interior_not_placeable`, `model.overlaps_next`, `model.overlap_amount`, `model.gap_amount`, `model.prefer_order`, `model.prefer_hint`, `model.approval.sentence.auto`, `model.approval.sentence.suggest_only`, `model.orientation.sentence.horizontal`, `model.orientation.sentence.vertical`, `model.inspect.select_hint`). Any string naming a length uses `{…_mm} {u}` via `tu()`.

- [ ] **Step 4: The basis schematics**

Six inline SVGs, one per `BASES` value, drawn as a 60×40 viewBox: two rails, three boards, and the dots where that basis lands. They live in `panel-inspector.js` as a `BASIS_DIAGRAM` map of static SVG-building calls (never as an HTML string), rendered beside the basis select. They are illustrations of the vocabulary, not of this panel — a fixed three-board sketch, so a model with 20 boards still shows a legible picture.

- [ ] **Step 5: Mount it, still beside the rows**

In `model-editor.js`, add module state `let selection = SELECTION_NONE;`, render the inspector into `#model-inspector` at the end of `renderForm()`, and make each existing row's group clickable to set `selection` — so this task is testable in the browser before the canvas exists.

- [ ] **Step 6: Retarget the source-scanning tests**

- `tests/web/test_panel_model_module.py::test_a_negative_gap_is_offered_by_the_field_itself`: read `panel-inspector.js`, and assert against `gapControl` — the claim becomes "the amount field carries no `min`, and the sign comes from `gapForOverlap`":

```python
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    body = src[src.index("function gapControl"):]
    body = body[:body.index("\n}\n")]
    assert "gapForOverlap(" in body, "the sign must come from the shared helper"
    assert 'min' not in body, (
        "a min on the gap amount deletes board-on-board and shadowbox from the editor")
```
  Keep the second half of that test (the `validate_model` bound) exactly as it is.
- `test_the_swatch_field_refuses_anything_but_plain_hex`: read `panel-inspector.js` for `function swatchField`.
- `tests/web/test_locale_bundles.py::test_one_module_owns_each_shared_renderer`: the final two assertions move from `model-editor.js` to the pair — `renderImpactReport` stays a `model-editor.js` import, `skuSelect` becomes a `panel-inspector.js` import. Update the assertion and its comment to say which module owes which.

- [ ] **Step 7: Run everything**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A src/fenceai/web/static tests/web
git commit -m "feat(models): the inspector — one selected thing, in plain language"
```

---

### Task 8: `panel-canvas.js` — the drawing becomes the editor

**Files:**
- Create: `src/fenceai/web/static/js/panel-canvas.js`
- Modify: `src/fenceai/web/static/index.html`, `style.css`
- Modify: `src/fenceai/web/static/js/model-editor.js` (mount the canvas; feed it the preview)

**Interfaces:**
- Consumes: `elevation.js` (`renderElevation`, `elevationLayout`, `layoutPx`, `layoutMm`, `highlightSlot`), `panel-canvas-geom.js` (all of it), `i18n.js`, `units.js`.
- Produces: `renderCanvas(host, {elev, spec, selection, dragging}, {onSelect, onDrag, onCommit})` and `isDragging()`.
  - `onSelect(selection)` — a member, a fastener dot, or the empty opening (`{kind:"panel", key:null}`).
  - `onDrag(handle, valueMm)` — live, for the readout only; the caller does NOT re-price on it.
  - `onCommit(handle, valueMm)` — pointerup; the caller writes the document and re-prices.

- [ ] **Step 1: Build the canvas**

```js
// The panel canvas: the drawing IS the editor.
//
// It draws nothing of its own. `renderElevation` paints the rectangles the
// server placed (`report/elevation.py`), and this module lays an interaction
// layer over them in the same coordinates — `elevationLayout` is shared for
// exactly that reason, because a second copy of the transform is a handle three
// pixels from the board it moves.
//
// The canvas is NEVER mirrored in RTL. It joins the plan canvas, the profile and
// the macro elevation in that rule: the first board of a panel is the first
// board in every language, and a mirrored drawing would reverse it against the
// plan drawn one tab over.
//
// A drag does NOT re-price per frame. Pricing is a request, the fit runs on the
// server, and a drawing rebuilt under the pointer would fight the hand holding
// it — so the handle and a dashed ghost move locally with a live numeric
// readout, and the commit on pointerup is what writes the document and asks for
// the new panel. `isDragging()` is how the caller knows not to repaint.
```

Structure:

1. `renderCanvas` clears `host`, calls `renderElevation(elev, {onSelect: …, fixings: true})`.
   - `null` (a model with nothing in it yet) → an empty opening: a plain `<svg>` with one `.elev-opening` rect at the preview bay's proportions and a centred `t("canvas.empty_hint")` — "add a rail or a set of boards to start".
2. Append `<g class="canvas-handles">` to the returned svg. For each handle from `handlesFor(elev, spec)` place a `<circle class="canvas-handle" data-handle="<id>">` at `layoutPx(L, x_mm, y_mm)`, with `data-axis`.
3. Pointer events on the svg:
   - `pointerdown` on `[data-handle]` → `setPointerCapture`, record `{handle, startMm}` from `layoutMm(L, …)` via `svg.getScreenCTM().inverse()` applied to the event point (the one DOM-bound piece of the transform, and the reason `layoutMm` is pure and separate).
   - `pointermove` → compute the new authored value with the matching `*FromDrag` from `panel-canvas-geom.js`, move the handle and a dashed `<line class="canvas-ghost">`, set the readout `<text class="canvas-readout">` to `tu("canvas.value", {len_mm: value})`, and call `onDrag`.
   - `pointerup` → `onCommit(handle, value)`, clear the drag state.
   - `click` on a `.elev-member` or `.elev-fixing` → `onSelect({kind, key})` where `kind` comes from the member's `data-slot` matched against `spec.frame` / `spec.infill.pattern` / `spec.fixings`; a click landing on nothing → `{kind: "panel", key: null}`.
4. `highlightSlot(svg, selection.key)` after mounting, plus `.selected` on the matching fastener dots.
5. A `canvas-toolbar` above the drawing carrying the add buttons, keeping the ids the smoke suite already uses: `#btn-model-add-slot`, `#btn-model-toggle-infill`, `#btn-model-add-member`, `#btn-model-add-fixing`. The caller wires them (they mutate the document); the canvas only lays them out.

- [ ] **Step 2: Style it**

```css
/* the canvas: the drawing IS the editor, so it is never mirrored — same rule as
   the plan canvas, the profile and the macro elevation */
#model-canvas { direction: ltr; }
#model-canvas .elevation-svg { max-block-size: 520px; cursor: default; }
.canvas-handle { fill: #fff; stroke: #2563eb; stroke-width: 2; r: 6;
  cursor: grab; }
.canvas-handle:active { cursor: grabbing; }
.canvas-handle[data-axis="y"] { cursor: ns-resize; }
.canvas-handle[data-axis="x"] { cursor: ew-resize; }
.canvas-ghost { stroke: #2563eb; stroke-width: 1.5; stroke-dasharray: 6 4; }
.canvas-readout { font-size: 20px; fill: #1d4ed8; }
.canvas-toolbar { display: flex; gap: 6px; flex-wrap: wrap;
  margin-block-end: 6px; }
```

- [ ] **Step 3: Wire it in `model-editor.js`**

- `renderCanvas` is called from `renderPreview()` with `preview.elevation` and `specOf(session.model, specIndex)`.
- `onSelect` sets `selection` and re-renders the inspector only.
- `onCommit(handle, value)` writes the authored field — `slot.placement = placementFromDrag(...)`, `member.width_mm = ...`, `member.gap_after_mm = ...`, `infill.edge_margin_mm = ...` — then `touch()`, which is the existing "the document moved, re-price it" path. Nothing new saves.
- `refreshPreview` early-returns while `isDragging()`, and re-runs once on commit.

- [ ] **Step 4: Add the locale keys**

`canvas.empty_hint`, `canvas.value` (`"{len_mm} {u}"`), `canvas.add_rail`, `canvas.add_boards`, `canvas.remove_boards`, `canvas.add_fixing`, `canvas.select_hint`, in both bundles.

- [ ] **Step 5: Run the suites, then look at it**

Run: `uv run pytest tests/web -q`
Then: `uv run uvicorn fenceai.api.app:app --reload`, open the Models tab, edit M-SLAT, and drag a rail. The rail must move, the readout must show millimetres (or centimetres, under the cm toggle), and the parts table must re-price on release and not during.

- [ ] **Step 6: Commit**

```bash
git add -A src/fenceai/web/static
git commit -m "feat(models): the panel drawing becomes the editor"
```

---

### Task 9: The rows come out; the settings strip goes in

**Files:**
- Modify: `src/fenceai/web/static/js/model-editor.js`, `index.html`, `style.css`, `i18n/{en,he}.json`

- [ ] **Step 1: Delete the row lists**

Remove `renderFrame`, `renderInfill`, `renderFixings` and their hosts (`#model-frame`, `#model-infill`, `#model-fixings`) from `model-editor.js` and `index.html`. `subhead` goes with them; the add buttons live on the canvas toolbar with the same ids.

- [ ] **Step 2: The settings strip**

`#model-settings` above the canvas, one wrapping `.builder-row`: the id / name / grade fields (`renderHead`, unchanged), the spec picker (`renderSpecPicker`), and a `▸ Option axes` `<details>` holding `renderAxes` — axes are a repeating editor and belong behind a disclosure rather than in the way of the drawing.

- [ ] **Step 3: The variant condition becomes a sentence**

In `renderSpecPicker`, replace the raw textarea with:

```js
  const said = readSentence(variant.condition);
  if (said) { …three controls: field select, comparison select, number input… }
  else host.appendChild(el("div", { class: "meta", text: t("model.condition_advanced") }));
  // ▸ Advanced keeps the raw box, for conditions the sentence cannot express —
  // the fallback IS the parity guarantee, not a thing to design away
```

The three controls write `variant.condition = writeSentence({path, cmp, value})` and `touch()`. The `<details>` below them holds the existing textarea verbatim, including its "keeps the user's text; nothing is saved from it until it parses" behaviour. The number input is a length in millimetres when the path ends `_mm`, so it goes through `toDisplayValue`/`toMm` like every other length.

- [ ] **Step 4: Layout**

```css
.models-row > #model-form { flex: 3 1 640px; }
#model-settings .builder-row { align-items: flex-end; }
#model-editor { display: flex; gap: 10px; align-items: flex-start;
  flex-wrap: wrap; }
#model-canvas { flex: 3 1 420px; }
#model-inspector { flex: 2 1 280px; min-inline-size: 260px; }
```

- [ ] **Step 5: Run everything and drive it**

Run: `uv run pytest -q`
Expected: PASS. Then open the app and author a panel end to end without touching a raw field.

- [ ] **Step 6: Commit**

```bash
git add -A src/fenceai/web/static
git commit -m "feat(models): the rows come out, the canvas and its inspector stay"
```

---

### Task 10: The starter gallery

Five structures the mechanism can express, over SKUs the catalog holds, each landing as an ordinary independent draft — which is what makes "templates never lock you in" free: a duplicate has no special state to escape.

**Files:**
- Create: `src/fenceai/web/static/js/panel-templates.js`, `tests/web/test_panel_templates_module.py`
- Modify: `model-editor.js` (the "+ New model" button opens the gallery), `index.html`, `style.css`, `i18n/{en,he}.json`

**Interfaces:**
- Produces: `TEMPLATES: [{key, id_base, build(id) -> FenceModel}]` with keys `slat`, `picket`, `board_on_board`, `horizontal`, `ranch`; and `blankTemplate` for the "start blank" card.
- Consumes: `panel-model.js`'s `blankModel`, `defaultSlot`, `defaultMember`, `defaultInfill`, `defaultFixing`, `defaultEligibleMember`.

- [ ] **Step 1: Write the failing test**

`tests/web/test_panel_templates_module.py` builds each template in node and judges it with the real loader — the same shape as `test_the_smallest_authored_model_is_one_the_backend_accepts`:

```python
def test_every_starter_is_a_model_the_backend_would_publish(out):
    """A card that lands a draft the publish gate then refuses is worse than no
    card: the author is invited into a document they cannot finish, for a reason
    that is not on the screen they were given."""
    for key, doc in out["templates"].items():
        model = FenceModel.model_validate(doc)
        assert validate_model(model, demo_catalog()) == [], key


def test_every_starter_prices_a_panel_with_something_in_it(out):
    """A structure nothing in the catalog supplies previews as unsupplied — a
    starter has to arrive already answerable."""
    for key, doc in out["templates"].items():
        preview = preview_panel(FenceModel.model_validate(doc),
                                PreviewRequest(height_mm=1800, width_mm=2500),
                                demo_catalog())
        assert preview.unsupplied == [], key
        assert preview.total_cents > 0, key


def test_the_five_starters_are_five_different_panels(out):
    """Cards that produce the same document are one card wearing five hats."""
    drawn = {key: json.dumps(doc["default_spec"], sort_keys=True)
             for key, doc in out["templates"].items()}
    assert len(set(drawn.values())) == len(drawn)


def test_a_starter_names_itself_in_both_languages(out):
    for key, doc in out["templates"].items():
        assert set(doc["name_i18n"]) == {"en", "he"}, key
```

- [ ] **Step 2: Write the templates**

Each is `blankModel(id)` plus a `default_spec`, built from the same `default*` factories the add buttons use — never a literal, or the templates and the buttons drift:

| key | structure | SKUs |
|---|---|---|
| `slat` | two distributed rails (`count_param: "rails_per_span"`), vertical infill, `SLAT-100` at 100 wide / 20 gap, `spread_to_fit` + `space`, screws `per_member_crossing` | `RAIL-3000`, `SLAT-100`, `SCREW-S10` |
| `picket` | as `slat` with `gap_after_mm: 70` and `justification: "center"` | same |
| `board_on_board` | two-member pattern: board at `face_offset_mm: 0`, gap 60; board at `face_offset_mm: -18`, gap 60 — the overlap the negative-gap rule exists for | same |
| `horizontal` | infill `orientation: "horizontal"`, `SLAT-100` boards across the bay, `length_rule: "clear_between_posts"`, screws `per_member` | `SLAT-100`, `SCREW-S10` |
| `ranch` | three distributed rails, no infill, screws `per_frame_member` | `RAIL-3000`, `SCREW-S10` |

Names come from the bundles at build time (`{en: t("model.template.slat.name", {}, "en"), he: …}`) — or, simpler and without an i18n API change, from a literal `name_i18n` per template in `panel-templates.js` with the card's own label read from the bundle. Choose the literal: a model's name is its own data and travels to a server that has no locale bundle.

- [ ] **Step 3: The gallery**

`#btn-model-new` opens `#model-gallery` (a `.panel` of `.template-card` buttons) instead of calling `openSession` directly. Each card shows the template's name, one line of description, and a drawing: mount the template through the existing preview route once per card on open (`POST /api/fence-models/preview`) and render its `elevation` with `renderElevation(elev, {annotations: false, joints: false})`. A sixth card, `model.template.blank`, calls `openSession(blankModel(freeId("M-NEW")), null, {isNew: true})` — exactly today's behaviour.

Picking a card calls `openSession(build(freeId(id_base)), null, {isNew: true})`, which is `duplicateOf`'s path: an ordinary independent draft the moment it exists.

- [ ] **Step 4: Locale keys**

`model.template.<key>.name` and `.desc` for the five plus `blank`, `model.gallery_title`, `model.gallery_hint`, in both bundles.

- [ ] **Step 5: Run**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A src/fenceai/web/static tests/web
git commit -m "feat(models): New Panel is a gallery of starters that already work"
```

---

### Task 11: Browser smoke, and the record

The claim this whole surface has to earn: the canvas is a VIEW over the existing model, not a second source of truth for what a panel is. The smoke proves it by driving the canvas and comparing the SAVED DOCUMENT against what the equivalent raw edit produces.

**Files:**
- Modify: `tools/ui_smoke.py`
- Modify: `plan/current-status.md`, `docs/superpowers/specs/2026-08-17-panel-canvas-design.md`

- [ ] **Step 1: Rewrite the Models block's authoring path**

In the block beginning `# --- the Models tab: authoring a fence model`, replace the row-driven edits with canvas-driven ones, keeping every existing check:

- `#btn-model-new` → the gallery; click the `slat` card; assert a draft opened with a drawing in it:

```python
        check("a starter arrives as a panel that is already drawn",
              c.js("document.querySelectorAll('#model-canvas .elev-member').length") > 4)
```

- select a rail by clicking its rectangle, then drag its handle down and assert the AUTHORED number moved and the drawing followed:

```python
        rail_before = c.js("""
{ const g = document.querySelector('#model-canvas [data-handle^="placement:"]');
  const r = g.getBoundingClientRect();
  JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2}); }""")
        …c.drag(from, to)…
        check("dragging a rail writes the placement the drawing shows",
              inset_after > 0 and drawn_y_after != drawn_y_before)
```

- toggle the overlap checkbox on the selected board and assert the stored gap went NEGATIVE:

```python
        check("an overlap is a checkbox, and a negative gap underneath",
              stored_gap < 0)
```

- drag the second product above the first in the preference list and assert `priority` renumbered from 1 in the saved document;
- publish, then compare the whole `default_spec` against the same document built by a raw `PUT` of the equivalent JSON:

```python
        check("the canvas is a view over the model, not a second answer",
              canvas_spec == raw_spec)
```

- assert the fastener dots are on the drawing and total the parts table's screw quantity:

```python
        check("the fasteners drawn total the screws counted", dot_total == parts_qty)
```

- [ ] **Step 2: Run the browser suite**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: every check passes; screenshots `21-models-canvas.png`, `21b-models-gallery.png` land in the shots directory.

- [ ] **Step 3: Run the whole gate**

Run: `uv run pytest -q && uv run pytest tests/scenarios -q`
Expected: PASS, scenario count unchanged — the JSON this produces is unchanged, so `tests/scenarios` is unaffected.

- [ ] **Step 4: Write the record**

- `plan/current-status.md`: a new section at the top in the file's own voice — what the canvas is, the three decisions taken against the spec (fasteners derived on the server; five structures rather than five product families; the settings strip), and the counts.
- `docs/superpowers/specs/2026-08-17-panel-canvas-design.md`: amend the two paragraphs the implementation contradicts — the Architecture section's "No backend or schema change" gains the fastener-position exception and says why, and the gallery section's "Open for spec review" is resolved with the answer and the reason the five named families were not buildable.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(smoke): the panel canvas, driven through the browser"
```

---

## Review checkpoints

Per CLAUDE.md, run before declaring this done:

- `architecture-critic` after Task 2 (the read model gained a field) and after Task 9 (the frontend contracts moved).
- `test-reviewer` after Task 11, over the new node suites and the smoke additions.
