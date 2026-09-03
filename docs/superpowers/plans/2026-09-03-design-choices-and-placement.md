# Choice Sets and Hand Placement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Where two or more fences are equally admissible, offer the choice with its
measured difference instead of picking one in silence — and let a person place any
post by hand, in the plan view or the side view, without the engine quietly putting
it back.

**Architecture:** A **choice set** is a question with two or more admissible **design
points**. Candidates are generated (three generators), measured through the existing
cut planner, and filtered by Pareto dominance so the option count comes from the data.
A **selection** is stored on the project as an input to `generate()` — never a patch on
its output — so it joins the run digest and survives a redraw. Hand placement reuses
the override machinery that already exists (`pin_post` is already a hard layout
boundary); the new parts are a segment-local anchor, a `lock_bay` directive, and one
pure JS module shared by two canvas adapters.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLite; vanilla ES modules + inline
SVG on the frontend (no build step, no framework); pytest; node for pure-JS module
tests.

**Spec:** `docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md`
(read it first — this plan argues from it, and the sheet references `S-01`…`S-12` point
at its drawing set).

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002). The two
  named tolerances live in `fenceai/core/units.py`; `NUMERIC_TOLERANCE_MM = 1`.
- **`generate()` is pure and deterministic.** No clock, no I/O, inputs never mutated.
- **Overrides are anchored to `(run_id, station/interval, kind)`, never to generated
  element identity** (ADR-0004).
- **Read models never recompute a quantity** — and the browser is a read model: the
  frontend may compute a *snap position*, never a board count.
- **Hard constraint ≠ preference ≠ objective ≠ override ≠ choice set** — five kinds,
  five handlings. Do not fold the new one into an existing one.
- **Every new platform code needs `warning.<code>` in BOTH
  `web/static/i18n/en.json` and `he.json`**, plus an entry in
  `tests/web/test_locale_bundles.py`'s `WARNING_CODES`, and the emitting file must be
  in that test's `scanned` list. Key sets must stay identical between bundles.
- **JS modules communicate ONLY via `state.js`.** No module touches another's DOM
  subtree. No framework, no build step, no CDN.
- **Mutation order, always:** `pushSnapshot(label)` → mutate `state.project` →
  `saveTopology()`. After a non-topology mutation use `reloadProject()`, never
  `openProject()`, or the undo stack is wiped.
- **Anchors are segment-local:** author with `geom.anchorFor`, resolve with
  `geom.stationOfAnchor`; never read `anchor.offset_mm` as a station.
- **The plan canvas and the side-view profile are NEVER mirrored in RTL.**
- **The boundary contract is frozen at v1.3. Nothing in this plan edits it.**
- Run the suite with `uv run pytest -q`; the release gate is
  `uv run pytest tests/scenarios -q`. **Slice 1 must not move a golden number.**

---

# SLICE 1 — the machinery and the two geometry questions

## File structure, slice 1

| File | Responsibility |
|---|---|
| `src/fenceai/strategy/choices.py` | **new.** `DesignPoint`, `Measures`, `ChoiceSet`, `dominates`, `undominated`. Pure: no catalog, no topology, no graph. |
| `src/fenceai/strategy/layout.py` | gains `yield_threshold` and `layout_candidates`; existing functions untouched. |
| `src/fenceai/strategy/measure.py` | **new.** Measures one candidate through `plan_cuts()`. Separate from `choices.py` because it is the only part that needs the catalog's cut semantics. |
| `src/fenceai/project/model.py` | `Project.choices: list[Selection]`. |
| `src/fenceai/api/app.py` | choices CRUD; the alternatives on a run. |
| `src/fenceai/strategy/generator.py` | reads selections, probes alternatives, records physical deltas, `digest-v5`. |
| `src/fenceai/decisions/explain.py` | the `choice` templates, en + he. |
| `src/fenceai/web/static/js/choices.js` | **new.** The panel. Reads state, writes selections, renders nothing anyone else owns. |

---

### Task 1: Dominance — the filter that decides how many options appear

**Files:**
- Create: `src/fenceai/strategy/choices.py`
- Test: `tests/strategy/test_choices.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Measures(posts: int, boards: int, cuts: int, odd_bay: bool)`,
  `DesignPoint(id: str, label: str, bindings: dict[str, int], widths: list[int],
  measures: Measures | None)`, `ChoiceSet(id: str, scope: str, question: str,
  points: list[DesignPoint], depends_on: str | None)`,
  `dominates(a: Measures, b: Measures) -> bool`,
  `undominated(points: list[DesignPoint]) -> list[DesignPoint]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_choices.py
"""Which options a person is offered, and why it is not a number we chose.

Every candidate is measured on four axes the engine already computes, and a
candidate worse on ALL of them than another is never shown. The numbers below are
measured — `tests/strategy/test_measure.py` is where they come from — so this file
tests the filter, not the arithmetic.
"""

from __future__ import annotations

from fenceai.strategy.choices import DesignPoint, Measures, dominates, undominated


def _p(name: str, posts: int, boards: int, cuts: int, odd: bool) -> DesignPoint:
    return DesignPoint(id=name, label=name, bindings={}, widths=[],
                       measures=Measures(posts=posts, boards=boards, cuts=cuts,
                                          odd_bay=odd))


def test_a_candidate_worse_on_everything_is_dominated():
    """5 x 1000 against 3 x 1667 with a saw: two more posts, twenty more boards,
    twenty more cuts, and no compensating equality."""
    assert dominates(_p("equal", 4, 30, 30, False).measures,
                     _p("five", 6, 50, 50, False).measures)


def test_a_candidate_that_wins_on_one_axis_survives():
    """The pair the whole design turns on. `2+2+1` buys the same boards with a
    third of the cuts; `3 x 1667` has no odd bay. Neither dominates, so both are
    offered — which is why four measures are needed and not two."""
    tiling = _p("tiling", 4, 30, 10, True).measures
    equal = _p("equal", 4, 30, 30, False).measures
    assert not dominates(tiling, equal)
    assert not dominates(equal, tiling)


def test_identical_measures_do_not_dominate_each_other():
    """`dominates` needs a STRICT improvement somewhere. Without that, two
    candidates measuring the same would each eliminate the other and the filter
    would return nothing."""
    a = _p("a", 4, 30, 30, False).measures
    assert not dominates(a, a)


def test_the_filter_keeps_the_survivors_in_candidate_order():
    """Order is the generators' order, so the panel lists what the engine reaches
    for first, first — and two runs of the same project never disagree."""
    kept = undominated([_p("equal", 4, 30, 30, False),
                        _p("tiling", 4, 30, 10, True),
                        _p("yield", 7, 30, 60, False),
                        _p("quarter", 5, 40, 40, False)])
    assert [p.id for p in kept] == ["equal", "tiling"]


def test_a_point_with_no_measures_is_never_filtered_out():
    """A placement variant is measured nowhere, because reordering widths changes
    no quantity. An unmeasured point is a taste question and must survive."""
    kept = undominated([_p("end", 4, 30, 10, True),
                        DesignPoint(id="centred", label="centred", bindings={},
                                     widths=[], measures=None)])
    assert [p.id for p in kept] == ["end", "centred"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_choices.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.strategy.choices'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fenceai/strategy/choices.py
"""A choice set: a question the data leaves open, and the points that answer it.

**A fifth kind, and deliberately not folded into the other four.** A hard
constraint says *must*; a preference says *nicer if*; an objective says *minimise
this*; an override says *the engine got this wrong here*. A choice set says **two
right answers** — nothing was wrong and neither point is nicer, so the only honest
resolver is a person, or a stated default.

Pure: no catalog, no topology, no decision graph. Measuring a point needs the
catalog's cut semantics and lives in `measure.py`; generating layout candidates
needs the layout and lives in `layout.py`. This module holds the types and the
filter, so the rule that decides what a person is shown can be read in one screen.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm


class Measures(BaseModel):
    """What a candidate costs, on the four axes the engine already computes.

    All four MINIMISE, `odd_bay` included — which is a claim worth stating: a bay
    that differs from its neighbours is not automatically worse, but it is the
    thing a person notices, so it belongs on the axis where "fewer is better" and
    a person is left to disagree. That is why `2000 · 2000 · 1000` is offered
    rather than chosen.

    `boards` is the number of stock lengths BOUGHT, not `waste_mm`. A 333 mm
    offcut clears `min_reusable_remnant_mm` and becomes inventory, so waste reads
    zero for every candidate and the differences vanish.
    """

    posts: int
    boards: int
    cuts: int
    odd_bay: bool


class DesignPoint(BaseModel):
    """One admissible answer.

    `bindings` are parameter values this point asserts (`footing_depth_mm`,
    `max_span_mm`) — the shape a `paired` row publishes. `widths` is the bay list
    where the point IS a layout. A point may carry either, and a placement variant
    carries widths with no bindings.

    `measures` is `None` where measuring would be meaningless rather than
    unfinished: reordering widths changes no quantity, so a placement variant has
    nothing to measure and must not be filtered on the absence.
    """

    id: str
    label: str
    bindings: dict[str, Mm] = {}
    widths: list[Mm] = []
    measures: Measures | None = None


class ChoiceSet(BaseModel):
    """A question, its points, and what it depends on.

    `depends_on` names another set whose answer must be settled first: the
    placement question exists only while the chosen widths leave a stub, and a
    dependent set whose parent moved is dropped rather than orphaned.
    """

    id: str
    scope: str
    question: str
    points: list[DesignPoint] = []
    depends_on: str | None = None


_AXES = ("posts", "boards", "cuts")


def dominates(a: Measures, b: Measures) -> bool:
    """Is `a` at least as good on every axis and strictly better on one?

    The strictness matters: without it, two candidates measuring the same would
    each dominate the other and the filter would return an empty list.
    """
    at = tuple(getattr(a, k) for k in _AXES) + (int(a.odd_bay),)
    bt = tuple(getattr(b, k) for k in _AXES) + (int(b.odd_bay),)
    return all(x <= y for x, y in zip(at, bt)) and any(x < y for x, y in zip(at, bt))


def undominated(points: list[DesignPoint]) -> list[DesignPoint]:
    """The points worth offering, in the order the generators produced them.

    Order is preserved rather than sorted by any axis: sorting would make the
    panel's first row a judgement this module has no basis for, and the
    generators' order is already meaningful (fewest posts, then the manufactured
    tiling, then yield).
    """
    return [
        p for p in points
        if p.measures is None
        or not any(other.measures is not None and p is not other
                   and dominates(other.measures, p.measures)
                   for other in points)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_choices.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/choices.py tests/strategy/test_choices.py
git commit -m "feat(choices): a choice set, a design point, and the dominance filter"
```

---

### Task 2: The three candidate generators

**Files:**
- Modify: `src/fenceai/strategy/layout.py` (append; do not touch `equal_layout`,
  `nominal_layout`, `exact_layout` or `layout_segment`)
- Test: `tests/strategy/test_layout_candidates.py`

**Interfaces:**
- Consumes: `equal_layout(length_mm, max_span_mm) -> list[Mm]`,
  `exact_layout(length_mm, exact_mm) -> tuple[list[Mm], Mm | None]` (both already in
  `layout.py`).
- Produces: `yield_threshold(stock_mm: Mm, kerf_mm: Mm, pieces: int) -> Mm`,
  `layout_candidates(length_mm, max_span_mm, *, exact_mm=None, min_span_mm=None,
  stock_mm=None, kerf_mm=3) -> list[tuple[str, list[Mm]]]` returning
  `(generator_name, widths)` in generator order, deduplicated.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_layout_candidates.py
"""The three layout candidates, and the arithmetic behind the third.

`yield_threshold` is the widest bay whose infill still cuts `pieces` to a board.
It exists because the cliff is invisible: on 2 m stock with a 3 mm kerf a 1000 mm
bay takes one piece per board and a 998 mm bay takes two, and no person eyeballing
a drawing finds that.
"""

from __future__ import annotations

from fenceai.strategy.layout import layout_candidates, yield_threshold


def test_the_yield_threshold_is_the_cliff_the_cut_planner_actually_has():
    """Each piece costs `length + kerf` against a capacity of `stock + kerf`, so
    two pieces fit at 998 and not at 1000. Verified against `plan_cuts` itself in
    `tests/strategy/test_measure.py`."""
    assert yield_threshold(2000, 3, 2) == 998
    assert yield_threshold(2000, 0, 2) == 1000
    assert yield_threshold(2000, 3, 1) == 2000


def test_the_fewest_posts_candidate_is_always_offered():
    got = dict(layout_candidates(5000, 2000))
    assert got["fewest_posts"] == [1667, 1667, 1666]


def test_a_manufactured_width_adds_the_tiling_candidate():
    got = dict(layout_candidates(5000, 2000, exact_mm=2000))
    assert got["tiling"] == [2000, 2000, 1000]


def test_the_yield_candidate_appears_only_when_stock_is_known():
    """No stock, no third candidate — and no invented one. The engine does not
    guess a stock length in order to have something to offer."""
    assert "best_yield" not in dict(layout_candidates(5000, 2000))
    got = dict(layout_candidates(5000, 2000, stock_mm=2000, kerf_mm=3))
    assert got["best_yield"] == [834, 834, 833, 833, 833, 833]


def test_the_yield_candidate_is_dropped_when_it_would_change_nothing():
    """A threshold at or above the maximum span produces the layout the first
    generator already produced, and a duplicate row in the panel is a question
    asked twice."""
    got = layout_candidates(5000, 900, stock_mm=2000, kerf_mm=3)
    assert [name for name, _ in got] == ["fewest_posts"]


def test_a_candidate_below_the_minimum_span_is_not_offered():
    """A sliver is not an option. `prefer_min_span_width` is a knowledge rule, so
    the caller passes it in rather than this module inventing a floor."""
    got = dict(layout_candidates(5000, 2000, stock_mm=2000, kerf_mm=3,
                                  min_span_mm=1200))
    assert "best_yield" not in got


def test_identical_candidates_are_deduplicated_keeping_the_first_generator():
    """A 6 m run tiled by 2 m panels divides exactly, so tiling and fewest-posts
    agree — one candidate, and the panel asks nothing."""
    got = layout_candidates(6000, 2000, exact_mm=2000)
    assert [name for name, _ in got] == ["fewest_posts"]
    assert dict(got)["fewest_posts"] == [2000, 2000, 2000]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_layout_candidates.py -q`
Expected: FAIL — `ImportError: cannot import name 'layout_candidates'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/fenceai/strategy/layout.py`:

```python
def yield_threshold(stock_mm: Mm, kerf_mm: Mm, pieces: int) -> Mm:
    """The widest bay whose infill still yields `pieces` per stock length.

    `plan_cuts` charges each piece `length + kerf` against a capacity of
    `stock + kerf` — it credits back the kerf nobody cuts after the last piece —
    so `pieces` fit when `pieces * (w + kerf) <= stock + kerf`. Integer division,
    because a bay width is integer millimetres and a threshold rounded up would
    name a width that does not fit.

    This is the ONLY place the yield arithmetic lives on the Python side, and
    `tests/strategy/test_measure.py` checks it against `plan_cuts` rather than
    against itself.
    """
    if pieces < 1 or stock_mm <= 0:
        return 0
    return (stock_mm + kerf_mm) // pieces - kerf_mm


def layout_candidates(
    length_mm: Mm,
    max_span_mm: Mm,
    *,
    exact_mm: Mm | None = None,
    min_span_mm: Mm | None = None,
    stock_mm: Mm | None = None,
    kerf_mm: Mm = 3,
) -> list[tuple[str, list[Mm]]]:
    """Every layout worth measuring for this segment, in generator order.

    Three generators and no scan over bay counts. A range scan would need a
    bound nobody can justify — "try n up to 10" is a number we made up — while
    each of these answers a question somebody actually asks: what is the fewest
    posts, what does the manufacturer ship, and what cuts cleanly out of stock.

    Deduplicated by width list, keeping the first generator that produced it: a
    segment that divides exactly makes tiling and fewest-posts agree, and offering
    the same layout twice is asking the same question twice.
    """
    out: list[tuple[str, list[Mm]]] = []
    seen: set[tuple[Mm, ...]] = set()

    def offer(name: str, widths: list[Mm]) -> None:
        if not widths:
            return
        if min_span_mm and min(widths) < min_span_mm:
            return
        if max(widths) > max_span_mm:
            return
        key = tuple(widths)
        if key in seen:
            return
        seen.add(key)
        out.append((name, widths))

    offer("fewest_posts", equal_layout(length_mm, max_span_mm))
    if exact_mm and exact_mm <= max_span_mm:
        offer("tiling", exact_layout(length_mm, exact_mm)[0])
    if stock_mm:
        # Two pieces per board is the only step worth offering: three is a bay
        # under 665 mm on 2 m stock, which is a sliver on any real fence, and
        # the generator that offers slivers is the one an operator turns off.
        threshold = yield_threshold(stock_mm, kerf_mm, 2)
        if 0 < threshold < max_span_mm:
            offer("best_yield", equal_layout(length_mm, threshold))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_layout_candidates.py -q`
Expected: PASS (7 tests)

Then confirm nothing else moved: `uv run pytest tests/strategy -q`

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/layout.py tests/strategy/test_layout_candidates.py
git commit -m "feat(layout): three candidate generators, and the yield threshold behind the third"
```

---

### Task 3: Measuring a candidate through the real cut planner

**Files:**
- Create: `src/fenceai/strategy/measure.py`
- Test: `tests/strategy/test_measure.py`

**Interfaces:**
- Consumes: `plan_cuts(sku: str, semantics: DivisibleLinear, pieces: list[CutPiece],
  remnants=None) -> CutPlan` from `fenceai.fulfillment.cutplan`;
  `DivisibleLinear(purchase_length_mm: Mm, kerf_mm: Mm = 3,
  min_reusable_remnant_mm: Mm = 300)` from `fenceai.catalog.model`;
  `Measures` from Task 1.
- Produces: `measure_widths(widths: list[Mm], *, stock_mm: Mm, kerf_mm: Mm,
  rows_per_bay: int) -> Measures`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_measure.py
"""What a candidate costs, measured by the cut planner rather than estimated.

The numbers here are the plan's own table (spec §5) and they are asserted against
`plan_cuts` — so if the packing changes, this file says so rather than the panel
quietly showing a stale saving.
"""

from __future__ import annotations

from fenceai.strategy.measure import measure_widths


def test_the_kerf_decides_whether_a_metre_bay_is_cheap():
    """The finding the whole design turns on. Two 1000 mm pieces cost 2006 against
    a 2003 capacity, so a 1 m bay eats a whole 2 m board; at 998 mm two pieces fit
    and the board count halves."""
    at_1000 = measure_widths([1000] * 5, stock_mm=2000, kerf_mm=3, rows_per_bay=10)
    at_998 = measure_widths([998] * 5, stock_mm=2000, kerf_mm=3, rows_per_bay=10)
    assert at_1000.boards == 50
    assert at_998.boards == 25


def test_the_measured_table_the_panel_argues_from():
    """5 m run, ten slat rows, 2 m stock, 3 mm kerf."""
    equal = measure_widths([1667, 1667, 1666], stock_mm=2000, kerf_mm=3,
                            rows_per_bay=10)
    tiling = measure_widths([2000, 2000, 1000], stock_mm=2000, kerf_mm=3,
                             rows_per_bay=10)
    assert (equal.posts, equal.boards, equal.cuts) == (4, 30, 30)
    assert (tiling.posts, tiling.boards, tiling.cuts) == (4, 30, 10)


def test_a_one_millimetre_spread_is_not_an_odd_bay():
    """`equal_layout` hands the remainder out one millimetre at a time, so
    `1667 · 1667 · 1666` must read as equal. Using the engine's own
    `NUMERIC_TOLERANCE_MM` rather than an inequality is what makes that true."""
    assert measure_widths([1667, 1667, 1666], stock_mm=2000, kerf_mm=3,
                           rows_per_bay=10).odd_bay is False
    assert measure_widths([2000, 2000, 1000], stock_mm=2000, kerf_mm=3,
                           rows_per_bay=10).odd_bay is True


def test_a_bay_cut_from_a_whole_board_needs_no_cut():
    """Cuts are saw passes, not pieces: a 2000 mm piece out of 2000 mm stock is
    the board, and counting it as a cut would make the tiling candidate look worse
    than it is on the one axis it wins."""
    got = measure_widths([2000, 2000], stock_mm=2000, kerf_mm=3, rows_per_bay=1)
    assert got.boards == 2
    assert got.cuts == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_measure.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.strategy.measure'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fenceai/strategy/measure.py
"""What a layout candidate costs — through `plan_cuts`, never estimated.

Separate from `choices.py` on purpose: the filter is pure arithmetic over four
integers and should be readable in one screen, while this needs the catalog's cut
semantics. It is also the seam where a second measure would be added, and keeping
it out of the types means adding one does not touch them.

**There is no second implementation of the packing.** A quicker
`ceil(pieces / per_board)` would be right until a remnant, a mixed-width bay or a
kerf credit made it wrong, and then the panel would advertise a saving the cut
list does not deliver.
"""

from __future__ import annotations

from fenceai.catalog.model import DivisibleLinear
from fenceai.core.units import NUMERIC_TOLERANCE_MM, Mm
from fenceai.fulfillment.cutplan import CutPiece, plan_cuts
from fenceai.strategy.choices import Measures


def measure_widths(
    widths: list[Mm], *, stock_mm: Mm, kerf_mm: Mm, rows_per_bay: int,
) -> Measures:
    """Measure one candidate layout.

    `rows_per_bay` is how many infill pieces a bay needs — the slat rows of a
    horizontal-slat panel. It is the caller's number because it comes from the
    resolved panel, not from the layout.

    `cuts` counts SAW PASSES, not pieces: a board consumed exactly by its pieces
    took one pass fewer than it holds, because the last piece is the rest of the
    board. Counting pieces instead would charge the tiling candidate for two
    uncut bays and hide the one axis it wins on.
    """
    pieces = [
        CutPiece(length_mm=w, requirement_id=f"bay{i}")
        for i, w in enumerate(widths)
        for _ in range(max(1, rows_per_bay))
    ]
    plan = plan_cuts(
        "candidate",
        DivisibleLinear(purchase_length_mm=stock_mm, kerf_mm=kerf_mm),
        pieces,
    )
    cuts = sum(
        len(bar.pieces) if bar.leftover_mm > 0 else max(0, len(bar.pieces) - 1)
        for bar in plan.bars
    )
    spread = max(widths) - min(widths) if widths else 0
    return Measures(
        posts=len(widths) + 1,
        boards=plan.new_bar_count,
        cuts=cuts,
        odd_bay=spread > NUMERIC_TOLERANCE_MM,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_measure.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/measure.py tests/strategy/test_measure.py
git commit -m "feat(choices): measure a candidate through the cut planner, never an estimate"
```

---

### Task 4: A selection on the project, and its API

**Files:**
- Modify: `src/fenceai/project/model.py` (add `Selection`, add `Project.choices`)
- Modify: `src/fenceai/api/app.py` (two routes)
- Modify: `docs/architecture/04-backend.md` (route count and the row)
- Test: `tests/api/test_choices_routes.py`

**Interfaces:**
- Produces: `Selection(choice_set: str, scope: str, point_id: str, asked: bool = True,
  author: str = "user", created_at: str = "")`; `Project.choices: list[Selection]`;
  `PUT /api/projects/{id}/choices` (body: one `Selection`, upsert by
  `(choice_set, scope)`), `DELETE /api/projects/{id}/choices/{choice_set}/{scope}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_choices_routes.py
"""Recording a choice, and pinning a question shut.

A selection is an INPUT to generation, so it lives on the project beside the
overrides rather than on a run — which is what makes it survive a redraw and what
puts it in the run digest.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fenceai.api.app import app


def _project(client) -> str:
    return client.post("/api/projects", json={"name": "choices"}).json()["id"]


def test_a_selection_is_recorded_with_its_author():
    with TestClient(app) as client:
        pid = _project(client)
        got = client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "bay_layout", "scope": "section:A",
            "point_id": "tiling", "author": "bob",
        })
        assert got.status_code == 200, got.text
        choices = client.get(f"/api/projects/{pid}").json()["choices"]
        assert len(choices) == 1
        assert choices[0]["point_id"] == "tiling"
        assert choices[0]["author"] == "bob"


def test_choosing_again_replaces_rather_than_accumulates():
    """One answer per question per scope. Appending would leave two answers and
    a rule about which wins, which is a rule nobody would remember."""
    with TestClient(app) as client:
        pid = _project(client)
        for point in ("tiling", "fewest_posts"):
            client.put(f"/api/projects/{pid}/choices", json={
                "choice_set": "bay_layout", "scope": "section:A",
                "point_id": point,
            })
        choices = client.get(f"/api/projects/{pid}").json()["choices"]
        assert [c["point_id"] for c in choices] == ["fewest_posts"]


def test_a_pinned_question_is_a_selection_that_is_not_asked_again():
    """Pinning is not choosing: same record, one flag. It is what keeps the probe
    count down, so it has to be storable without inventing a second type."""
    with TestClient(app) as client:
        pid = _project(client)
        client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "footing_schedule", "scope": "model:M-VINYL",
            "point_id": "610_1676", "asked": False,
        })
        assert client.get(f"/api/projects/{pid}").json()["choices"][0]["asked"] is False


def test_a_selection_can_be_withdrawn():
    with TestClient(app) as client:
        pid = _project(client)
        client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "bay_layout", "scope": "section:A", "point_id": "tiling",
        })
        gone = client.delete(f"/api/projects/{pid}/choices/bay_layout/section:A")
        assert gone.status_code == 200
        assert client.get(f"/api/projects/{pid}").json()["choices"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_choices_routes.py -q`
Expected: FAIL — 404 from `PUT /api/projects/{id}/choices`

- [ ] **Step 3: Write minimal implementation**

In `src/fenceai/project/model.py`, above `class Project`:

```python
class Selection(BaseModel):
    """A person's answer to a choice set — an INPUT to generation.

    Anchored to a SCOPE rather than to a station, which is the whole difference
    from an override: an override says "the engine got this post wrong" and dies
    when the fence is redrawn, while a choice says "of the two right answers, this
    one" and should outlive any amount of redrawing.

    `asked=False` is a PIN: stop offering this question. Same record and one flag,
    because pinning and choosing differ in what happens next rather than in what
    was decided — and a second type would need a rule for what happens when both
    exist.
    """

    choice_set: str
    scope: str
    point_id: str
    asked: bool = True
    author: str = "user"
    created_at: str = ""

    def key(self) -> tuple[str, str]:
        return (self.choice_set, self.scope)
```

...and on `Project`, beside `overrides`:

```python
    # Answers to choice sets (specs/2026-09-03-design-choices-and-placement).
    # Beside `overrides` because they are the same category of thing — a person's
    # input to generation — and deliberately NOT inside `policy`: they are read by
    # the generator, stamped into the run digest, and rendered in the decision
    # graph, so a typo has to fail at the boundary rather than at generation.
    choices: list[Selection] = []
```

In `src/fenceai/api/app.py`:

```python
@app.put("/api/projects/{project_id}/choices")
def put_choice(project_id: str, body: Selection):
    """Record one answer, replacing any previous answer to the same question.

    Upsert by `(choice_set, scope)`: one question in one scope has one answer, and
    a list that accumulated them would need a precedence rule nobody would
    remember. `PUT` rather than `POST` for the same reason — this is the state of
    one answer, not an event in a log.
    """
    project = state.store.load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    project.choices = [c for c in project.choices if c.key() != body.key()]
    project.choices.append(body)
    state.store.save_project(project, actor=body.author)
    return body


@app.delete("/api/projects/{project_id}/choices/{choice_set}/{scope}")
def delete_choice(project_id: str, choice_set: str, scope: str):
    """Withdraw an answer, which returns the question to the panel."""
    project = state.store.load_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    project.choices = [c for c in project.choices
                        if c.key() != (choice_set, scope)]
    state.store.save_project(project, actor="user")
    return {"ok": True}
```

Import `Selection` beside the other project types at the top of `app.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_choices_routes.py -q`
Expected: PASS (4 tests)

Then update the route count: `uv run pytest tests/architecture/test_fitness.py -q`
will fail with *"the doc says 57 routes and the app serves 59"*. Set the number in
`docs/architecture/04-backend.md` and add the routes to the table's Overrides row.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/project/model.py src/fenceai/api/app.py \
        docs/architecture/04-backend.md tests/api/test_choices_routes.py
git commit -m "feat(choices): a selection on the project, upserted by question and scope"
```

---

### Task 5: Generation reads the selections, and the digest moves

**Files:**
- Modify: `src/fenceai/strategy/generator.py` (the `layout_segment` call site around
  `:2313`, `RUN_DIGEST_VERSION` at `:153`, the digest payload around `:290`)
- Test: `tests/strategy/test_choice_generation.py`

**Interfaces:**
- Consumes: `Selection` (Task 4), `layout_candidates` (Task 2), `measure_widths`
  (Task 3), `undominated` (Task 1).
- Produces: `GenerationResult.choice_sets: list[ChoiceSet]` (the open questions this
  run carries), and `Strategy` layouts that honour a recorded selection.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_choice_generation.py
"""A recorded choice changes the fence, deterministically, and says so.

Three properties, and the third is the one that makes the other two safe: the
same project with the same choices generates the same run id forever.
"""

from __future__ import annotations

from fenceai.project.model import Selection
from tests.conftest import straight_topology   # 5 m single-run helper


def test_with_no_selection_the_default_is_todays_answer(demo_env):
    """The property that keeps the golden gate still. Slice 1 adds questions and
    changes no answers."""
    out = demo_env.generate()
    widths = [s.width_mm for s in out.strategy.spans]
    assert widths == demo_env.generate_before_choices_widths


def test_a_recorded_selection_changes_the_layout(demo_env):
    demo_env.project.choices = [Selection(
        choice_set="bay_layout", scope="section:run1", point_id="tiling")]
    widths = [s.width_mm for s in demo_env.generate().strategy.spans]
    assert widths == [2000, 2000, 1000]


def test_the_same_choice_gives_the_same_run_id_and_a_different_one_a_new_id(demo_env):
    """`objective_preset` was removed from the digest because a design is what it
    is regardless of how it is bought. A choice is the opposite: it changes the
    design, so it belongs in the digest and a new answer must mint a new id."""
    first = demo_env.generate().run.id
    again = demo_env.generate().run.id
    assert first == again

    demo_env.project.choices = [Selection(
        choice_set="bay_layout", scope="section:run1", point_id="tiling")]
    assert demo_env.generate().run.id != first


def test_an_unanswered_question_is_carried_on_the_run(demo_env):
    """Two candidates survive for this segment, so the run reports one open
    question with both points and the measured difference."""
    out = demo_env.generate()
    sets = {cs.id: cs for cs in out.choice_sets}
    assert "bay_layout" in sets
    points = sets["bay_layout"].points
    assert len(points) == 2
    assert all(p.measures is not None for p in points)


def test_a_selection_naming_a_point_that_no_longer_exists_is_reported(demo_env):
    """The stale case, and it must never be a silent fallback: the default applies
    AND the plan says which point vanished."""
    demo_env.project.choices = [Selection(
        choice_set="bay_layout", scope="section:run1", point_id="best_yield")]
    out = demo_env.generate()
    codes = [g.because.code for g in out.strategy.gaps]
    assert "choice_unavailable" in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_choice_generation.py -q`
Expected: FAIL — `AttributeError: 'GenerationResult' object has no attribute
'choice_sets'`

- [ ] **Step 3: Write minimal implementation**

At the `layout_segment` call site, replace the single-layout call with candidate
generation, then honour a selection:

```python
        # The candidates for this segment, measured and filtered. `layout_segment`
        # still decides the DEFAULT — that is what keeps every golden number
        # still — and the candidates exist to be offered beside it.
        layout = layout_segment(
            seg_len, sm.max_span,
            prefer_equal=prefer_equal, min_span_mm=min_span, nominal_mm=width_pref,
            exact_mm=sm.exact_span,
        )
        cands = layout_candidates(
            seg_len, sm.max_span, exact_mm=sm.exact_span, min_span_mm=min_span,
            stock_mm=sm.infill_stock_mm, kerf_mm=sm.infill_kerf_mm,
        )
        points = [
            DesignPoint(
                id=name, label=" · ".join(str(w) for w in widths), widths=widths,
                measures=measure_widths(
                    widths, stock_mm=sm.infill_stock_mm,
                    kerf_mm=sm.infill_kerf_mm, rows_per_bay=sm.infill_rows),
            )
            for name, widths in cands
        ] if sm.infill_stock_mm else []
        offered = undominated(points)
        scope = f"section:{run.id}"
        chosen = next((c for c in selections
                       if c.choice_set == "bay_layout" and c.scope == scope), None)
        if chosen is not None:
            picked = next((p for p in offered if p.id == chosen.point_id), None)
            if picked is None:
                # Never a silent fallback: the default stands and the plan says
                # which point disappeared, and who had chosen it.
                strategy.gaps.append(_choice_unavailable_gap(
                    "bay_layout", scope, chosen, run))
            else:
                layout = LayoutResult(widths=picked.widths,
                                       rejected_alternative=layout.widths)
        if len(offered) > 1 and (chosen is None or chosen.asked):
            choice_sets.append(ChoiceSet(
                id="bay_layout", scope=scope,
                question="layout.question.bay_widths", points=offered))
```

Add the gap builder beside the other builders in `generator.py`:

```python
def _choice_unavailable_gap(set_id: str, scope: str, chosen, run) -> Gap:
    """A recorded answer whose point is gone — a re-cut snapshot, an edited model.

    `closes_by: planning` because nothing a curator publishes fixes it: either the
    person chooses again or this engine stops offering the point. Reported rather
    than resolved silently, which is the same call `_paired_unsupported_gap`
    makes.
    """
    return Gap(
        id=f"gap:choice_unavailable:{set_id}:{scope}",
        kind="missing_value",
        subject=GapSubject(kind="entity", ref_kind="section", id=run.id),
        because=Because(code="choice_unavailable",
                         params={"choice_set": set_id, "point": chosen.point_id,
                                 "author": chosen.author}),
        would_close=(f"choose again for {set_id} on {scope}, or restore the "
                     f"{chosen.point_id} option this project was built to"),
        closes_by="planning", severity="warns_line",
    )
```

Bump the digest and put the choices in it:

```python
RUN_DIGEST_VERSION = "digest-v5"
# v5: `choices` joined the digest's inputs. A selection changes the DESIGN — bay
# widths, a footing depth, where the stub sits — and the digest's own rule is that
# anything changing what the run MEANS belongs in it. This is the mirror image of
# v3, which REMOVED `objective_preset` because a design is what it is regardless
# of how it will be bought.
```

...and in the digest payload, beside `overrides_applied`:

```python
        choices=sorted((c.choice_set, c.scope, c.point_id) for c in selections),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_choice_generation.py -q`
Expected: PASS (5 tests)

**Then the gate, which is the point of this task:**
Run: `uv run pytest tests/scenarios -q`
Expected: PASS, unmoved. A moved number means a default changed by accident —
fix the default, never the scenario.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/generator.py tests/strategy/test_choice_generation.py
git commit -m "feat(choices): generation offers the candidates and honours a selection (digest-v5)"
```

---

### Task 6: Probing the alternatives for a physical delta

**Files:**
- Modify: `src/fenceai/strategy/generator.py` (a `probe_alternatives` helper called
  once per run, after the baseline strategy exists)
- Test: `tests/strategy/test_choice_probes.py`

**Interfaces:**
- Produces: `DesignPoint.delta: dict[str, int]` on every offered, unchosen point —
  physical only (`posts`, `boards`, `cuts`), relative to the baseline.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_choice_probes.py
"""What the alternative would cost, measured by generating it.

One probe per offered point, against the baseline — never a cross product. And
never a cheaper parallel calculation: a second way of counting posts is how a read
model comes to disagree with the bill of materials.
"""

from __future__ import annotations


def test_an_offered_point_carries_a_physical_delta(demo_env):
    out = demo_env.generate()
    alt = next(p for cs in out.choice_sets for p in cs.points if p.delta)
    assert set(alt.delta) <= {"posts", "boards", "cuts"}
    assert "cost_cents" not in alt.delta, "money is derived where prices live"


def test_two_questions_cost_three_generations_not_four(demo_env):
    """The baseline plus one probe per point, so the count is a SUM over
    questions and not a product of them."""
    demo_env.count_generations()
    demo_env.generate()
    assert demo_env.generation_count == 3


def test_a_placement_variant_is_never_probed(demo_env):
    """Reordering widths changes no bay width, so the demand and the cut plan are
    identical. Probing it would spend a generation to learn nothing."""
    demo_env.generate()
    placement = next(cs for cs in demo_env.result.choice_sets
                     if cs.id == "stub_placement")
    assert all(p.delta == {} for p in placement.points)


def test_a_pinned_question_is_not_probed(demo_env):
    """Pinning is what keeps the probe count down — the reason there is no cap."""
    demo_env.pin("bay_layout", "section:run1", "fewest_posts")
    demo_env.count_generations()
    demo_env.generate()
    assert demo_env.generation_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_choice_probes.py -q`
Expected: FAIL — `AttributeError: 'DesignPoint' object has no attribute 'delta'`

- [ ] **Step 3: Write minimal implementation**

Add `delta: dict[str, int] = {}` to `DesignPoint` in `choices.py`, with:

```python
    # What choosing this point would change, PHYSICALLY: posts, boards, cuts.
    # Never money. A stored price goes stale the moment the catalog moves, and the
    # BOM layer is where prices live — so the run records what a builder counts
    # and the money is derived downstream.
    delta: dict[str, int] = {}
```

...then in `generator.py`, after the baseline strategy is built:

```python
def _probe(base_generate, project, point: DesignPoint, set_id: str, scope: str):
    """Generate this project again with one point selected, and diff the physical
    counts against the baseline.

    ONE choice at a time. A cross product over questions would be the honest way
    to price a combination, and it is also exponential — while the panel only ever
    claims "relative to the plan you are looking at", which is exactly a
    one-at-a-time delta.
    """
    probed = project.model_copy(deep=True)
    probed.choices = [c for c in probed.choices
                       if (c.choice_set, c.scope) != (set_id, scope)]
    probed.choices.append(Selection(choice_set=set_id, scope=scope,
                                     point_id=point.id, author="probe"))
    return base_generate(probed)
```

Call it for every offered point whose `measures` differ from the chosen one's, skip
points with `measures is None` (placement variants) and skip whole sets whose
selection has `asked=False`. Record `delta` as
`{k: probed[k] - baseline[k] for k in ("posts", "boards", "cuts") if probed[k] != baseline[k]}`,
and `log`/count the probes performed on the run so a runaway is visible.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_choice_probes.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/choices.py src/fenceai/strategy/generator.py \
        tests/strategy/test_choice_probes.py
git commit -m "feat(choices): one probe per offered point, physical deltas only"
```

---

### Task 7: The explanation, in both languages

**Files:**
- Modify: `src/fenceai/strategy/generator.py` (a `choice` node at the layout site)
- Modify: `src/fenceai/decisions/explain.py` (`TEMPLATES` en + he)
- Modify: `src/fenceai/web/static/i18n/en.json`, `he.json`
- Modify: `tests/web/test_locale_bundles.py` (`WARNING_CODES`, `KNOWLEDGE_SURFACE_UNTRANSLATED` if the sentence names a snapshot)
- Test: `tests/decisions/test_choice_explanation.py`

**Interfaces:**
- Produces: graph node `("choice", "resolve_choice_set")` with payload
  `{choice_set, scope, point, chosen_by, alternatives}`; templates
  `resolve_choice_set` and `resolve_choice_set_default`; warning code
  `choice_unavailable`.

- [ ] **Step 1: Write the failing test**

```python
# tests/decisions/test_choice_explanation.py
"""Two sentences, because a default and a decision are different facts.

"Three equal bays because nobody has chosen" and "because you chose them on 3 Sep"
must not render the same, or the graph asserts a decision nobody made.
"""

from __future__ import annotations

from fenceai.decisions.explain import TEMPLATES


def test_both_bundles_carry_both_sentences():
    for lang in ("en", "he"):
        assert "resolve_choice_set" in TEMPLATES[lang]
        assert "resolve_choice_set_default" in TEMPLATES[lang]


def test_the_two_sentences_take_the_same_params():
    """`test_locale_bundles` guards key parity; this guards PARAM parity, which
    nothing else can see. A template interpolating a param its sibling does not
    supply renders a literal `{point}` to a reader."""
    import re
    for key in ("resolve_choice_set", "resolve_choice_set_default"):
        en = set(re.findall(r"\{(\w+)\}", TEMPLATES["en"][key]))
        he = set(re.findall(r"\{(\w+)\}", TEMPLATES["he"][key]))
        assert en == he, (key, en ^ he)


def test_the_node_names_the_alternative_it_did_not_build(demo_env):
    """A choice node with no loser is an assertion. The losing point goes on the
    `defeated` edge, which is the convention the graph already uses."""
    out = demo_env.generate()
    node = next(n for n in out.graph.nodes if n.action == "resolve_choice_set_default")
    assert node.payload["alternatives"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/decisions/test_choice_explanation.py -q`
Expected: FAIL — `KeyError: 'resolve_choice_set'`

- [ ] **Step 3: Write minimal implementation**

In `explain.py` `TEMPLATES["en"]`:

```python
        # A choice set: two answers were admissible and this is the one built.
        # Two templates, because "nobody chose" and "you chose" are different
        # facts and one sentence covering both would assert a decision that may
        # not have happened.
        "resolve_choice_set": (
            "{question}: {point}. You chose this on {when}; {alternatives} "
            "{was_available}."
        ),
        "resolve_choice_set_default": (
            "{question}: {point}. Nobody has chosen, so the usual answer stands; "
            "{alternatives} {was_available}."
        ),
```

...and the Hebrew equivalents in `TEMPLATES["he"]`, key-identical and taking the
same params. Add `warning.choice_unavailable` to both bundles and
`"choice_unavailable"` to `WARNING_CODES` in `tests/web/test_locale_bundles.py`.

Emit the node at the layout site, `defeated` carrying the losing point's id.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/decisions/test_choice_explanation.py tests/web/test_locale_bundles.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/decisions/explain.py src/fenceai/strategy/generator.py \
        src/fenceai/web/static/i18n/en.json src/fenceai/web/static/i18n/he.json \
        tests/web/test_locale_bundles.py tests/decisions/test_choice_explanation.py
git commit -m "feat(decisions): a choice node, and two sentences so a default never reads as a decision"
```

---

### Task 8: The panel

**Files:**
- Create: `src/fenceai/web/static/js/choices.js`
- Modify: `src/fenceai/web/static/js/tabs.js` (mount it), `i18n/{en,he}.json`
- Test: `tests/web/test_choices_panel.py` (node, in the style of
  `tests/web/test_base_top_module.py`)

**Interfaces:**
- Consumes: `state.result.choice_sets`, `state.project.choices`, `apiSend`,
  `t`, `tu`/`toDisplayValue`, `esc`.
- Produces: `renderChoices(host, sets, selections)` returning the host element;
  `chooseLabel(point)` — the one function with logic, so it can be tested in node.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_choices_panel.py
"""The panel's one piece of logic: how a delta becomes a chip.

The renderer is DOM and belongs in the browser smoke suite. `chooseLabel` is
arithmetic — a sign, a unit, a plural — and it is the part that is wrong at 3 a.m.
"""
SCRIPT = """
import { chooseLabel } from "%(static)s/js/choices.js";
const out = [
  chooseLabel({delta: {posts: -3, boards: -5}}),
  chooseLabel({delta: {}}),
  chooseLabel({delta: {cuts: 20}}),
];
console.log(JSON.stringify(out));
"""
```

...asserting `["−3 posts · −5 boards", "no material change", "+20 cuts"]` — a
minus sign that is a real minus (U+2212), not a hyphen, and the empty case reading
as a statement rather than a blank.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_choices_panel.py -q`
Expected: FAIL — cannot resolve `js/choices.js`

- [ ] **Step 3: Write minimal implementation**

`choices.js`, following the module contract: it reads `state`, writes through
`apiSend` + `reloadProject()`, renders only into the host it is given, and every
string goes through `t()`. Dimensions render with `tu()` so a centimetre preference
reads in centimetres. `esc()` every interpolated label — a point label carries
widths, but an author name is user text.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/web/test_choices_panel.py tests/web/test_locale_bundles.py -q`
Expected: PASS

- [ ] **Step 5: Commit + browser smoke**

```bash
uv run --with websocket-client python tools/ui_smoke.py
git add src/fenceai/web/static/js/choices.js src/fenceai/web/static/js/tabs.js \
        src/fenceai/web/static/i18n/en.json src/fenceai/web/static/i18n/he.json \
        tests/web/test_choices_panel.py
git commit -m "feat(web): the alternatives panel, with the delta as countable chips"
```

---

# SLICE 2 — direct placement

### Task 9: A pin measures from its own segment

**Files:**
- Modify: `src/fenceai/strategy/overrides.py` (`PinPost.anchor`, `SuppressPost.anchor`)
- Modify: `src/fenceai/strategy/generator.py` (`:1955` — resolve the anchor)
- Test: `tests/strategy/test_override_anchors.py`

**Interfaces:**
- Consumes: `Anchor(segment_index: int, offset_mm: Mm, seg_len_at_authoring_mm: Mm)`
  from `fenceai.topology.model`; `anchor_station(topo, run, anchor) -> Mm` and
  `make_anchor(topo, run, station_mm) -> Anchor` from `fenceai.topology.station`.
- Produces: `PinPost.anchor: Anchor | None`, `SuppressPost.anchor: Anchor | None`,
  and `override_station(topo, run, directive) -> Mm | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_override_anchors.py
"""A pinned post keeps its distance from the corner it was measured from.

`PinPost.station_mm` was an ABSOLUTE station while every point event in the
topology uses a segment-local anchor. With one pinned post nobody notices; with a
hand-built layout it is the first thing that happens, so it is fixed before the
drag ships.
"""

from __future__ import annotations

from fenceai.strategy.overrides import PinPost, override_station
from fenceai.topology.station import make_anchor


def test_a_pin_authored_past_a_corner_stays_past_the_corner(l_shaped_topo):
    """3 m leg then a 2 m leg; a post pinned 800 mm past the corner. Lengthen the
    first leg by 1500 mm and the post must still be 800 mm past the corner — where
    an absolute station 3800 lands 700 mm BEFORE it, on the other leg."""
    topo, run = l_shaped_topo
    pin = PinPost(anchor=make_anchor(topo, run, 3800))
    assert pin.anchor.segment_index == 1
    assert pin.anchor.offset_mm == 800

    topo = lengthen_first_leg(topo, run, by_mm=1500)
    assert override_station(topo, run, pin) == 4500 + 800


def test_a_stored_pin_with_no_anchor_still_resolves(l_shaped_topo):
    """Existing projects carry `station_mm` and nothing else. They must keep
    working — every run in the demo and the golden scenarios is single-segment,
    where the two readings agree exactly."""
    topo, run = l_shaped_topo
    assert override_station(topo, run, PinPost(station_mm=1200)) == 1200


def test_a_pin_whose_segment_shrank_past_it_resolves_to_none(l_shaped_topo):
    """Which is what makes it ORPHAN rather than silently move: the generator
    already reports `orphaned_override` for a directive it could not apply."""
    topo, run = l_shaped_topo
    pin = PinPost(anchor=make_anchor(topo, run, 3800))
    topo = shorten_second_leg(topo, run, to_mm=400)
    assert override_station(topo, run, pin) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_override_anchors.py -q`
Expected: FAIL — `ImportError: cannot import name 'override_station'`

- [ ] **Step 3: Write minimal implementation**

```python
class PinPost(BaseModel):
    kind: Literal["pin_post"] = "pin_post"
    # LEGACY, and kept readable rather than migrated: every stored override
    # carries it, and on a single-segment run — which is every golden scenario —
    # it means exactly what the anchor means. Read it only through
    # `override_station`.
    station_mm: Mm = 0
    # §ADR-0003's anchor, the shape every point event already uses. A post placed
    # 800 mm past a corner stays 800 mm past the corner when an earlier segment's
    # length changes, which an absolute station does not.
    anchor: Anchor | None = None
```

```python
def override_station(topo, run, directive) -> Mm | None:
    """Where this directive applies, or None if it no longer applies at all.

    `None` is the orphan signal the generator already knows how to report: a
    segment that shrank past its own anchor has no station to offer, and guessing
    one would move somebody's post rather than telling them it was lost.
    """
    anchor = getattr(directive, "anchor", None)
    if anchor is None:
        return getattr(directive, "station_mm", None)
    points = run_points(topo, run)
    lens = segment_lengths(points)
    if anchor.segment_index >= len(lens):
        return None
    if anchor.offset_mm > lens[anchor.segment_index]:
        return None
    return sum(lens[:anchor.segment_index]) + anchor.offset_mm
```

...and at `generator.py:1955`, replace `d.station_mm` with
`override_station(topo, run, d)`, treating `None` as "not applied" so the existing
orphan report fires.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_override_anchors.py -q && uv run pytest tests/scenarios -q`
Expected: PASS both — the scenarios are single-segment, so nothing moves.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/overrides.py src/fenceai/strategy/generator.py \
        tests/strategy/test_override_anchors.py
git commit -m "fix(overrides): a pin measures from its own segment, not from the run start"
```

---

### Task 10: `lock_bay`, and a placement that breaks a rule

**Files:**
- Modify: `src/fenceai/strategy/overrides.py` (`LockBay` + the `Directive` union)
- Modify: `src/fenceai/strategy/generator.py` (locked intervals bypass subdivision)
- Modify: `i18n/{en,he}.json`, `tests/web/test_locale_bundles.py`
- Test: `tests/strategy/test_lock_bay.py`

**Interfaces:**
- Produces: `LockBay(kind: Literal["lock_bay"], start: Anchor, end: Anchor)`;
  warning code `span_placed_over_maximum` with params
  `{run_id, placed_mm, max_mm, over_mm, author}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_lock_bay.py
"""A hand-placed bay is built as placed — and says so when it breaks a rule.

Today the engine wins this argument in silence: pin posts 3 m apart under a 2 m
maximum and the layout puts a post back in the middle. The person asked for one
bay and got two, with nothing said. That is the failure this task removes.
"""

from __future__ import annotations


def test_an_unlocked_gap_is_still_subdivided(placed_env):
    """Which is correct: an unlocked gap is what was left to the engine."""
    placed_env.pin_posts(0, 3000)
    widths = [s.width_mm for s in placed_env.generate().strategy.spans]
    assert widths[:2] == [1500, 1500]


def test_a_locked_bay_is_built_as_placed(placed_env):
    placed_env.pin_posts(0, 3000)
    placed_env.lock_bay(0, 3000)
    widths = [s.width_mm for s in placed_env.generate().strategy.spans]
    assert widths[0] == 3000


def test_a_locked_bay_over_the_maximum_warns_with_both_figures(placed_env):
    """The approved figure, the placed figure and the difference — a warning that
    named only one of them cannot be checked by the person reading the plan."""
    placed_env.pin_posts(0, 2438)
    placed_env.lock_bay(0, 2438, author="bob")
    out = placed_env.generate(max_span_mm=1676)
    warn = next(w for w in out.strategy.warnings
                if w.code == "span_placed_over_maximum")
    assert warn.params["placed_mm"] == 2438
    assert warn.params["max_mm"] == 1676
    assert warn.params["over_mm"] == 762
    assert warn.params["author"] == "bob"


def test_a_locked_sliver_is_built_and_reported_through_the_existing_code(placed_env):
    """The other direction. A 400 mm bay against a wall is a thing people want,
    and `sliver_span` already exists to say so — a second code would split one
    fact across two sentences."""
    placed_env.pin_posts(0, 400)
    placed_env.lock_bay(0, 400)
    out = placed_env.generate(min_span_mm=1200)
    assert any(w.code == "sliver_span" for w in out.strategy.warnings)


def test_the_graph_attributes_the_placement_to_a_person(placed_env):
    """So nothing reads as the engine's own choice."""
    placed_env.pin_posts(0, 2438)
    placed_env.lock_bay(0, 2438, author="bob")
    out = placed_env.generate(max_span_mm=1676)
    node = next(n for n in out.graph.nodes if n.action == "lock_bay")
    assert node.payload["author"] == "bob"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_lock_bay.py -q`
Expected: FAIL — `ImportError: cannot import name 'LockBay'`

- [ ] **Step 3: Write minimal implementation**

```python
class LockBay(BaseModel):
    """Build the bay between these two anchors exactly as placed.

    The one directive this design adds, and the reason hand placement means what
    it says: without it, `layout_segment` honours `max_span_mm` inside a
    hand-placed gap and puts a post back that nobody asked for.

    An interval rather than a station, and two anchors rather than two stations,
    for `PinPost.anchor`'s reason — a locked bay that slid when a corner moved
    would lock the wrong bay.
    """

    kind: Literal["lock_bay"] = "lock_bay"
    start: Anchor
    end: Anchor
```

Add it to the `Directive` union. In the generator, a locked interval is emitted as
one span with no call to `layout_segment`, and the width is compared against the
resolved `max_span_mm` / `min_span` to raise `span_placed_over_maximum` (new,
literal `code="span_placed_over_maximum"` at the raise site so the locale scan
can read it) or the existing `sliver_span`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_lock_bay.py tests/web/test_locale_bundles.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/overrides.py src/fenceai/strategy/generator.py \
        src/fenceai/web/static/i18n/en.json src/fenceai/web/static/i18n/he.json \
        tests/web/test_locale_bundles.py tests/strategy/test_lock_bay.py
git commit -m "feat(overrides): lock_bay — a placed bay is built as placed, and marked when it exceeds an approval"
```

---

### Task 11: `post-drag.js` — the arithmetic, out of both views

**Files:**
- Create: `src/fenceai/web/static/js/post-drag.js`
- Test: `tests/web/test_post_drag_module.py`

**Interfaces:**
- Consumes: nothing. **No imports from a view, no DOM, no `state.js`** — the rule
  `base-top.js` exists to enforce.
- Produces: `layoutWithPin(fixed, length, station, {maxSpanMm, minSpanMm})`,
  `snapCandidates({station, prev, next, maxSpanMm, displayUnit, stock, rowsPerBay})`,
  `violations(widths, {maxSpanMm, minSpanMm})`,
  `yieldThreshold(stockMm, kerfMm, pieces)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_post_drag_module.py
"""Post-drag arithmetic (static/js/post-drag.js), run in node.

Two canvases drag a post: the plan view, where the pointer must be projected onto
the run's polyline, and the side view, where the x axis already IS the station.
The arithmetic they share lives here so they cannot drift — the same reason
`base-top.js` holds the profile's base transforms.
"""
SCRIPT = """
import { layoutWithPin, snapCandidates, violations, yieldThreshold }
  from "%(static)s/js/post-drag.js";

const out = {};
out.threshold3 = yieldThreshold(2000, 3, 2);
out.threshold0 = yieldThreshold(2000, 0, 2);
out.layout = layoutWithPin([0, 5000], 5000, 2500, {maxSpanMm: 2000}).widths;
out.snaps = snapCandidates({
  station: 3960, prev: 2000, next: 5000, maxSpanMm: 2000,
  displayUnit: "mm", stock: {lengthMm: 2000, kerfMm: 3}, rowsPerBay: 10,
}).map((s) => [s.kind, s.station]);
out.violation = violations([1281, 1281, 2438], {maxSpanMm: 1676});
console.log(JSON.stringify(out));
"""
```

Asserted:
- `threshold3 == 998`, `threshold0 == 1000` — the same numbers
  `strategy/layout.py::yield_threshold` returns, checked here so the two
  implementations cannot diverge silently;
- `layout == [2500, 2500]` — a pin at 2500 splits a 5 m run into two bays and the
  engine adds nothing, because neither exceeds the maximum;
- `snaps` contains `["yield", 4002]` — the station that makes the last bay 998 mm —
  and `["equal", 3500]`, the station that matches the neighbouring bay;
- `violation == [{index: 2, code: "span_placed_over_maximum", over_mm: 762}]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_post_drag_module.py -q`
Expected: FAIL — cannot resolve `js/post-drag.js`

- [ ] **Step 3: Write minimal implementation**

```javascript
// Pure drag arithmetic for a post: what the layout becomes, where it may snap,
// and what rule it breaks. No DOM, no state, no view imports — the plan canvas
// and the side-view profile both call this, and the only way they cannot drift is
// if neither of them owns it. Tested in node (tests/web/test_post_drag_module.py),
// the same arrangement base-top.js has.
//
// It computes POSITIONS. It never computes a quantity: the board count on the
// panel always comes from the backend generation after the drop, because a second
// implementation of the packing would eventually advertise a saving the cut list
// does not deliver.

/** The widest bay whose infill still yields `pieces` per stock length.
 *  Mirrors strategy/layout.py::yield_threshold — same formula, same integer
 *  division, and tests/web/test_post_drag_module.py pins both to the same
 *  numbers. */
export function yieldThreshold(stockMm, kerfMm, pieces) {
  if (pieces < 1 || stockMm <= 0) return 0;
  return Math.floor((stockMm + kerfMm) / pieces) - kerfMm;
}
```

...plus `layoutWithPin` (insert the station into the fixed list, then fill each gap
with the equal layout — the same `ceil` and remainder-spreading as
`layout.equal_layout`, which the node test pins), `snapCandidates` (round via the
display unit's step, equal-to-neighbour, and the yield station), and `violations`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/web/test_post_drag_module.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/post-drag.js tests/web/test_post_drag_module.py
git commit -m "feat(web): pure post-drag arithmetic, shared by both canvases"
```

---

### Task 12: Adapter A — dragging in the plan canvas

**Files:**
- Modify: `src/fenceai/web/static/js/editor.js` (the drag session at `:191-240`,
  `onDragMove` at `:315`)
- Test: browser smoke (`tools/ui_smoke.py`) — a drag is a pointer gesture and the
  arithmetic is already covered by Task 11.

**Interfaces:**
- Consumes: `geom.stationAtPoint(run, xMm, yMm)`, `geom.anchorFor(runId, station)`,
  `post-drag.js` (Task 11), `pushSnapshot`, `apiSend`, `reloadProject`.
- Produces: `drag.kind === "post"` sessions that POST a `pin_post` with an anchor.

- [ ] **Step 1: Add the smoke case first**

In `tools/ui_smoke.py`, a case that generates a plan, drags the second post 500 mm
along the run, and screenshots: the ghost, both live dimensions, and the snap rail.
Run it and watch it fail to find a draggable post.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: the new case FAILS; the other 262 pass.

- [ ] **Step 3: Write minimal implementation**

Extend the existing session rather than adding a second one:

```javascript
    } else if (target.dataset.post) {
      // A generated post has no stable identity, so a drag does not "move" one:
      // it PINS a post where the pointer lands, and the layout stops producing
      // the one it was standing on because the gap it filled is now two gaps.
      drag = { kind: "post", runId: target.dataset.run,
               from: +target.dataset.station, start: [ev.clientX, ev.clientY] };
    }
```

...and in `onDragMove`, past the existing 4 px threshold, `pushSnapshot("move-post")`
once, then project and preview:

```javascript
  if (drag.kind === "post") {
    const run = runById(drag.runId);
    const station = stationAtPoint(run, mx, my);      // pointer -> polyline
    const snapped = nearestSnap(station, snapCandidates({ ... }));
    // Preview ONLY. `state.project` is not touched until pointerup: a
    // pointermove that mutated it would push history per frame and save per
    // frame.
    previewPost(run, snapped);
    return;
  }
```

On `pointerup`: POST `{kind: "pin_post", anchor: anchorFor(runId, station)}`, then
`reloadProject()`. A gesture that never passed the threshold is a click — select the
post and open the inspector.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: all cases pass; review the new screenshots before regenerating baselines.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/editor.js tools/ui_smoke.py \
        tools/smoke_baseline/*
git commit -m "feat(web): drag a post in the plan canvas, projected onto the run"
```

---

### Task 13: Adapter B — dragging in the side view

**Files:**
- Modify: `src/fenceai/web/static/js/profile.js`
- Test: browser smoke, plus the pure module (Task 11) already covering the maths.

**Interfaces:**
- Consumes: the same `post-drag.js` exports as Task 12. **No import from
  `editor.js`** — the two adapters never reference each other.

- [ ] **Step 1: Add the smoke case first**

A case that drags the same post in the profile and asserts the plan canvas shows it
moved after the drop — the cross-view property, which is only true because both
adapters write one override through `state.js` and both re-render from state.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: the new case FAILS.

- [ ] **Step 3: Write minimal implementation**

The profile's x axis already *is* the station, so the projection is one division by
the module's own scale — no `stationAtPoint`. Reuse the existing top-dot drag idiom
and its proximity snap (`STEP_SNAP_PX`), and delegate every number to
`post-drag.js`; do not inline the arithmetic, which is the rule `base-top.js` exists
to enforce.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/js/profile.js tools/ui_smoke.py tools/smoke_baseline/*
git commit -m "feat(web): drag a post in the side view, sharing one arithmetic with the plan"
```

---

### Task 14: The post inspector — three directives that have never had a control

**Files:**
- Modify: `src/fenceai/web/static/js/inspector.js`, `i18n/{en,he}.json`
- Test: browser smoke

**Interfaces:**
- Produces: controls for `force_post_sku`, `force_mounting`, `force_vertical`, and
  the suppress gesture's button equivalent.

- [ ] **Step 1: Add the smoke case first** — select a post, force its sku, assert
  the BOM line changes.
- [ ] **Step 2: Run it and watch it fail** (there is no post inspector).
- [ ] **Step 3: Implement** — the selected post's panel, one control per directive,
  every label through `t()` and every locale key in both bundles.
- [ ] **Step 4: Run the smoke suite** and the full python suite.
- [ ] **Step 5: Commit.**

---

# SLICE 3 — the `paired` row

### Task 15: A published `paired` row becomes design points

**Files:**
- Modify: `src/fenceai/knowledge/parameters.py` (replace
  `_paired_unsupported_gap`'s call site with point extraction)
- Modify: `tests/web/test_locale_bundles.py` (retire
  `parameter_paired_unsupported` from `WARNING_CODES`)
- Test: `tests/knowledge/test_paired_points.py`, and the pinned real snapshot in
  `tests/knowledge/test_real_snapshot.py`

**Interfaces:**
- Consumes: `ParameterTable.value_type == "paired(footing_depth_mm:mm, max_span_mm:mm)"`,
  `ChoiceSet`/`DesignPoint` (Task 1).
- Produces: `paired_points(table, row) -> list[DesignPoint]` with `bindings` keyed by
  the parameter names the `value_type` declares.

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_paired_points.py
"""The five refused tables, consumed.

`paired` was refused with a gap naming the work — "a cost objective in the Planning
repo that chooses between the design points" — and this is that work. The shape was
always ratified and correct; what was missing was ours.
"""

from __future__ import annotations


def test_a_paired_row_becomes_one_point_per_pair(paired_table):
    points = paired_points(paired_table, paired_table.rows[0])
    assert [p.bindings for p in points] == [
        {"footing_depth_mm": 610, "max_span_mm": 1676},
        {"footing_depth_mm": 762, "max_span_mm": 2464},
    ]


def test_the_binding_keys_come_from_the_declared_value_type(paired_table):
    """`paired(footing_depth_mm:mm, max_span_mm:mm)` names its own columns. Reading
    them positionally would silently swap depth and span the first time a publisher
    declared them the other way round."""
    assert set(paired_points(paired_table, paired_table.rows[0])[0].bindings) == {
        "footing_depth_mm", "max_span_mm"}


def test_the_default_is_the_shortest_span(paired_table):
    """Most posts, stiffest fence. The engine does not spend the customer's money
    on its own initiative — the cheaper point is one click away."""
    points = paired_points(paired_table, paired_table.rows[0])
    assert default_point(points).bindings["max_span_mm"] == 1676


def test_the_refusal_gap_is_gone(real_paired_snapshot):
    snapshot, defects = load(real_paired_snapshot)
    out = ingest(snapshot, as_of="2026-09-03", gap_defects=defects)
    assert "parameter_paired_unsupported" not in {g.because.code for g in out.gaps}
    assert len([cs for cs in out.choice_sets if cs.id == "footing_schedule"]) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/knowledge/test_paired_points.py -q`
Expected: FAIL — `NameError: name 'paired_points' is not defined`

- [ ] **Step 3: Write minimal implementation**

Parse the declared `value_type` for its column names, build one `DesignPoint` per
pair with `to_mm()` on each `Quantity`, and replace the `_paired_unsupported_gap`
call with the points. Keep the gap builder itself in the file, unreferenced, until
the next task deletes it — a code with a locale entry and no producer is caught by
`test_backend_code_list_is_current`, so retire both in one commit.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/knowledge -q tests/web/test_locale_bundles.py && uv run pytest tests/scenarios -q`
Expected: PASS

- [ ] **Step 5: Commit + the turn back**

```bash
git add src/fenceai/knowledge/parameters.py tests/knowledge/ \
        tests/web/test_locale_bundles.py
git commit -m "feat(knowledge): a paired row becomes design points; the refusal is retired"
```

Then write `conversation.md` T45 in `fence-rag` — this closes the only thing they
are waiting on us for, and the measured result (which point each of the five tables
defaults to, and what the alternative saves) is the useful half to send back.

---

## Self-review

**Spec coverage.** §3 concept → Task 1. §4.1 paired → Task 15; §4.2 widths → Task 2;
§4.3 placement → Task 2 + Task 8 (the placement set is generated from the chosen
widths and needs no probe, per §7). §5 dominance + measures → Tasks 1, 3. §6 defaults
and staleness → Task 5. §7 probes → Task 6. §8 the four acts → Tasks 4 (choose, pin),
9–13 (place), 10 (lock). §8.1 the unreachable directives → Task 14. §9 both views →
Tasks 11–13. §10 anchors → Task 9. §11 placement vs rule → Task 10. §12 mechanism,
digest, graph → Tasks 5, 7. §13 slices → the three parts. §14 files → each task's
Files block. §15 how we know → each task's test step, plus the gate runs in Tasks 5,
9 and 15.

**One gap found and closed:** §15 asks for *"a golden scenario at a run length where
the shallow footing option wins, so the panel is exercised in both directions."* No
task carried it. It belongs with Task 15, where footing points first exist — add it
there via the `golden-scenarios` skill rather than by hand-editing
`tests/scenarios/`, since the docs and the tests have to move together.

**Placeholders:** none. Tasks 12–14 carry gesture code rather than full renderers on
purpose — the deliverable there is a screenshot diff, and the arithmetic they call is
fully specified in Task 11.

**Type consistency:** `Measures`, `DesignPoint`, `ChoiceSet`, `Selection`,
`measure_widths`, `layout_candidates`, `yield_threshold`, `override_station`,
`LockBay`, `layoutWithPin`, `snapCandidates`, `violations`, `chooseLabel` — each
defined once and referenced by the same name and signature everywhere after.
`yield_threshold` deliberately exists twice, once per language, and Task 11's node
test pins both to the same numbers.
