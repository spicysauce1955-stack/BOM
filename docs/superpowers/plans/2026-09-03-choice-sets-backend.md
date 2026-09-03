# Choice Sets — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Where two or more fences are equally admissible, offer the choice with its
measured difference instead of picking one in silence — and let a hand-placed bay be built
as placed, marked when it departs from an approval.

**Architecture:** A **choice set** is a question with two or more admissible **design
points**. Points are generated and measured **after** the baseline generation, because
what a candidate costs depends on the panel the baseline resolved. A **selection** is an
input to `generate()`, never a patch on its output. A *parameter* point becomes synthesized
`KnowledgeVersion`s so the evaluator still resolves it; a *layout* point is a width list
for one gap and binds nothing.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md` —
read §0 first: this is rev 2, and rev 1 was rejected by two reviews for reasons that are
easy to re-introduce.

**Companion plan:** `2026-09-03-choice-sets-frontend.md`. The seam is two JSON surfaces
(`run.choice_sets`, the overrides endpoint) plus one duplicated arithmetic
(`yield_threshold`), pinned from the frontend side.

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002).
  `NUMERIC_TOLERANCE_MM = 1` in `fenceai/core/units.py`.
- **`generate()` is pure and deterministic.** No clock, no I/O, inputs never mutated. It
  takes **no `Project`** — new inputs are threaded as parameters, the way `site` and
  `parts` were, and `tests/architecture/test_fitness.py` forbids a domain module loading
  its own data.
- **One resolution path per parameter.** Anything that asserts a parameter value goes
  through `resolve_param`, or the decision graph reports a rule nobody wrote.
- **Nothing is measured outside a real generation.** No second cut packer. `plan_cuts`
  **raises** on a piece longer than its stock, so it is never called speculatively.
- **Overrides anchor to `(run_id, anchor, kind)`**, never to generated element identity
  (ADR-0004). One anchor resolver only: `topology.station.anchor_station`.
- **A new platform code needs `warning.<code>` in BOTH locale bundles**, an entry in
  `tests/web/test_locale_bundles.py`'s `WARNING_CODES`, and its emitting file in that
  test's `scanned` list. A code is emitted as a **literal** `code="..."` at the raise
  site or the scan cannot see it.
- **The contract is frozen at v1.3 and nothing here edits it.** Two registry additions
  only (spec §13).
- **Tests build their inputs explicitly** — `generate(straight_topology(5000),
  demo_knowledge(), demo_catalog(), ...)`, the style of
  `tests/strategy/test_boundary_posts.py`. No shared mutable env fixture.
- Suite: `uv run pytest -q` (2320 passing today). Gate:
  `uv run pytest tests/scenarios -q`. **Tasks 1–6 must not move a golden number.**

---

## File structure

| File | Responsibility |
|---|---|
| `src/fenceai/strategy/choices.py` | **new.** `DesignPoint`, `ChoiceSet`, `dominates`, `offered`. Pure leaf — imports only `core.units`. |
| `src/fenceai/strategy/layout.py` | gains `yield_threshold` + `alternative_widths`; the existing four functions untouched. |
| `src/fenceai/topology/station.py` | `Anchor.reanchor` honoured in `anchor_station`. |
| `src/fenceai/strategy/overrides.py` | anchors on `PinPost`/`SuppressPost`, new `LockBay`, `override_station`. |
| `src/fenceai/decisions/graph.py` | `NodeKind` gains `"choice"`. |
| `src/fenceai/strategy/generator.py` | `choices` + `offer_alternatives` params, gap-scoped questions, phase 2, `lock_bay`, digest. |
| `src/fenceai/decisions/explain.py` | two templates × two languages. |
| `src/fenceai/project/model.py`, `api/app.py` | `Selection`, `Project.choices`, CRUD. |
| `src/fenceai/knowledge/parameters.py` | `paired` → parameter points; retire the refusal. |
| `docs/scenarios/golden-scenarios.md`, `tests/scenarios/test_invariants.py` | the hard-max invariant's first authorized exception. |

---

### Task 1: The design point, and dominance over open axes

**Files:**
- Create: `src/fenceai/strategy/choices.py`
- Test: `tests/strategy/test_choices.py`

**Interfaces:**
- Consumes: `fenceai.core.units.Mm`.
- Produces: `DesignPoint(id: str, label: str, widths: list[Mm] = [], bindings: dict[str, Mm] = {}, axes: dict[str, int] = {}, lexemes: dict[str, str] = {}, is_default: bool = False, delta: dict[str, int] = {})`;
  `ChoiceSet(id: str, scope: str, question: str, points: list[DesignPoint] = [], depends_on: str | None = None)`;
  `dominates(a: DesignPoint, b: DesignPoint) -> bool`; `offered(points: list[DesignPoint]) -> list[DesignPoint]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_choices.py
"""Which answers a person is offered, and the two rules that decide.

Rev 1 filtered on four fixed measures including "has an odd bay" — and an
adversarial review found that dropping that one axis makes the tiling layout
dominate the layout this engine ships today. A taste axis was the only thing
hiding that. So: the default is never eliminated, and only commensurable
physical axes eliminate anything.
"""

from __future__ import annotations

from fenceai.strategy.choices import DesignPoint, dominates, offered


def _p(pid: str, *, default: bool = False, **axes: int) -> DesignPoint:
    return DesignPoint(id=pid, label=pid, axes=axes, is_default=default)


def test_a_point_worse_on_every_shared_axis_is_dominated():
    assert dominates(_p("equal", posts=4, boards=30, cuts=30),
                     _p("metre", posts=6, boards=50, cuts=50))


def test_a_point_that_wins_on_one_axis_survives():
    """Same posts, same boards, a third of the cuts. Neither dominates, so a
    person decides — which is the whole mechanism."""
    tiling = _p("tiling", posts=4, boards=30, cuts=10)
    equal = _p("equal", posts=4, boards=30, cuts=30)
    assert not dominates(tiling, equal)
    assert not dominates(equal, tiling)


def test_identical_axes_do_not_dominate_each_other():
    """`dominates` needs a STRICT improvement, or two points measuring the same
    would each eliminate the other and nothing would be offered. Two DISTINCT
    objects, so the `is not` guard is actually exercised."""
    assert not dominates(_p("a", posts=4, boards=30, cuts=30),
                         _p("b", posts=4, boards=30, cuts=30))


def test_only_shared_axes_are_compared():
    """A footing point carries concrete; a layout point does not. Comparing a
    point against one measured on different axes must not silently treat a
    missing axis as zero — that would make every footing point dominate every
    layout point."""
    footing = _p("deep", posts=6, concrete_l=334)
    layout = _p("tiling", posts=6, boards=30)
    assert not dominates(footing, layout)
    assert not dominates(layout, footing)


def test_a_point_with_no_axes_in_common_is_never_dropped():
    kept = offered([_p("a", posts=4), DesignPoint(id="taste", label="taste")])
    assert [p.id for p in kept] == ["a", "taste"]


def test_the_default_survives_even_when_dominated():
    """The rule that retires four separate failures: the built layout is always
    a row, so no `choice_unavailable` can ever fire for a point the engine is
    building on the same screen."""
    kept = offered([_p("equal", default=True, posts=4, boards=30, cuts=30),
                    _p("tiling", posts=4, boards=30, cuts=10)])
    assert [p.id for p in kept] == ["equal", "tiling"]


def test_a_non_default_dominated_point_is_dropped_and_order_is_kept():
    kept = offered([_p("equal", default=True, posts=4, boards=30, cuts=30),
                    _p("tiling", posts=4, boards=30, cuts=10),
                    _p("sixths", posts=7, boards=30, cuts=60)])
    assert [p.id for p in kept] == ["equal", "tiling"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_choices.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.strategy.choices'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/fenceai/strategy/choices.py
"""A choice set: a question the data leaves open, and the points that answer it.

**A fifth kind, deliberately not folded into the other four.** A hard constraint
says *must*; a preference says *nicer if*; an objective says *minimise this*; an
override says *the engine got this wrong here*. A choice set says **two right
answers** — nothing was wrong and neither point is nicer, so the only honest
resolver is a person, or the stated default.

Pure leaf: `core.units` only. Measuring a point needs a whole generation and
happens in the generator; this module holds the types and the two rules that
decide what a person is shown, so both fit on one screen.

**Axes are OPEN.** A layout point differs in posts, boards and cuts; a footing
point differs in concrete and holes. Rev 1 used four fixed measures and would
have printed "same posts, same boards, same cuts" for two footing schedules 25%
apart in concrete.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm


class DesignPoint(BaseModel):
    """One admissible answer.

    `widths` is a bay list where the point IS a layout; `bindings` are parameter
    values where it asserts some (a `paired` row's depth and span). The two are
    handled differently and the distinction is load-bearing: a binding becomes a
    synthesized `KnowledgeVersion` so `resolve_param` still decides, while a
    width list binds no parameter and needs no synthesizing.

    `lexemes` carries the source's own words per binding — `24"` beside 610 —
    because obligation 5 requires the display to keep them.

    `is_default` marks what the engine builds. A default is never eliminated.
    """

    id: str
    label: str
    widths: list[Mm] = []
    bindings: dict[str, Mm] = {}
    lexemes: dict[str, str] = {}
    # Physical axes measured BY a probe. Never money: a stored price goes stale
    # the moment the catalog moves, and ADR-0011 puts what a fence costs in a
    # SupplyRun against one yard.
    axes: dict[str, int] = {}
    # What choosing this would change, relative to the baseline, on shared axes.
    delta: dict[str, int] = {}
    is_default: bool = False


class ChoiceSet(BaseModel):
    """A question, its points, and what it depends on.

    `scope` is a GAP between fixed stations, not a section: any corner, gate,
    step or single pinned post makes a run several gaps, and a section-scoped
    answer would be applied to a gap it was never measured for.
    """

    id: str
    scope: str
    question: str
    points: list[DesignPoint] = []
    depends_on: str | None = None


def dominates(a: DesignPoint, b: DesignPoint) -> bool:
    """Is `a` at least as good as `b` on every axis BOTH carry, and better on one?

    Only shared axes are compared. Treating a missing axis as zero would make a
    footing point (measured in concrete) dominate a layout point (measured in
    boards) on an axis the second never claimed.

    Every axis minimises. That is why "has an odd bay" is not an axis: it is
    taste, and taste does not eliminate — it is printed on the row instead.
    """
    shared = set(a.axes) & set(b.axes)
    if not shared:
        return False
    return (all(a.axes[k] <= b.axes[k] for k in shared)
            and any(a.axes[k] < b.axes[k] for k in shared))


def offered(points: list[DesignPoint]) -> list[DesignPoint]:
    """The points worth showing, in the order they were generated.

    The default is exempt. Without that, the layout the engine builds can be
    absent from its own panel — and a stored selection naming it would report
    `choice_unavailable` for a layout being built on the same screen.
    """
    return [
        p for p in points
        if p.is_default
        or not any(o is not p and dominates(o, p) for o in points)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_choices.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/choices.py tests/strategy/test_choices.py
git commit -m "feat(choices): design points, open axes, and a default that is never eliminated"
```

---

### Task 2: The yield threshold and the alternative width lists

**Files:**
- Modify: `src/fenceai/strategy/layout.py` (append only)
- Test: `tests/strategy/test_layout_alternatives.py`

**Interfaces:**
- Consumes: `equal_layout`, `exact_layout` (both already in `layout.py`).
- Produces: `yield_threshold(stock_mm: Mm, kerf_mm: Mm, pieces: int) -> Mm`;
  `alternative_widths(length_mm, max_span_mm, *, default: list[Mm], exact_mm=None, min_span_mm=None, piece_stock_mm=None, kerf_mm=3, piece_shorter_by_mm=0) -> list[tuple[str, list[Mm]]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_layout_alternatives.py
"""The alternatives to whatever the engine just built.

Two things rev 1 got wrong here. The yield threshold is a threshold on the
INFILL PIECE, and a piece is cut to the clear opening — `clear_opening_mm`
subtracts a whole post face — so a bay-width threshold is measured on a length
the cut planner never sees. And the default was regenerated rather than passed
in, so a `min_span` rule that only WARNS in `layout_segment` while REJECTING in
candidate generation could leave the built layout absent from its own panel.
"""

from __future__ import annotations

from fenceai.strategy.layout import alternative_widths, yield_threshold


def test_the_yield_threshold_is_the_cliff_plan_cuts_actually_has():
    """Each piece costs `length + kerf` against a capacity of `stock + kerf`, so
    two fit at 998 and not at 1000. `tests/strategy/test_measure_from_probe.py`
    checks these numbers against `plan_cuts` itself rather than against this
    formula."""
    assert yield_threshold(2000, 3, 2) == 998
    assert yield_threshold(2000, 0, 2) == 1000
    assert yield_threshold(2000, 3, 1) == 2000


def test_a_degenerate_piece_count_returns_zero_rather_than_dividing():
    """JS gives Infinity for the same call, so both sides guard it and the node
    test compares them."""
    assert yield_threshold(2000, 3, 0) == 0
    assert yield_threshold(0, 3, 2) == 0


def test_the_default_is_never_returned_as_an_alternative():
    """It is already a point, and offering it twice asks the same question
    twice."""
    got = alternative_widths(5000, 1800, default=[1667, 1667, 1666])
    assert [name for name, _ in got] == []


def test_a_manufactured_width_is_offered_beside_the_default():
    got = dict(alternative_widths(5000, 2000, default=[1667, 1667, 1666],
                                   exact_mm=2000))
    assert got["tiling"] == [2000, 2000, 1000]


def test_the_yield_alternative_converts_through_the_post_face():
    """The threshold is on the PIECE. With a 70 mm post face a bay may be 70 mm
    wider than the piece it holds, so the bay-width target is the piece
    threshold plus the face — and rev 1's 998 was 70 mm off."""
    got = dict(alternative_widths(
        5000, 2000, default=[1667, 1667, 1666],
        piece_stock_mm=2000, kerf_mm=3, piece_shorter_by_mm=70))
    # piece threshold 998 -> bay target 1068 -> ceil(5000/1068) = 5 bays
    assert got["best_yield"] == [1000, 1000, 1000, 1000, 1000]


def test_no_stock_means_no_yield_alternative_rather_than_a_guessed_one():
    assert "best_yield" not in dict(
        alternative_widths(5000, 2000, default=[1667, 1667, 1666]))


def test_an_alternative_below_the_minimum_span_is_not_offered():
    got = dict(alternative_widths(
        5000, 2000, default=[1667, 1667, 1666], min_span_mm=1200,
        piece_stock_mm=2000, kerf_mm=3, piece_shorter_by_mm=0))
    assert "best_yield" not in got


def test_an_alternative_over_the_maximum_span_is_not_offered():
    """`exact_span` wider than the resolved maximum is a conflict the generator
    already reports; it is not an option to put on a panel."""
    assert alternative_widths(5000, 1800, default=[1667, 1667, 1666],
                               exact_mm=2000) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_layout_alternatives.py -q`
Expected: FAIL — `ImportError: cannot import name 'alternative_widths'`

- [ ] **Step 3: Write minimal implementation**

Append to `layout.py`:

```python
def yield_threshold(stock_mm: Mm, kerf_mm: Mm, pieces: int) -> Mm:
    """The longest PIECE that still yields `pieces` per stock length.

    `plan_cuts` charges each piece `length + kerf` against a capacity of
    `stock + kerf` — it credits back the kerf nobody cuts after the last piece —
    so `pieces` fit when `pieces * (p + kerf) <= stock + kerf`. Integer
    division, because a rounded-up threshold names a length that does not fit.

    This is a threshold on the PIECE, not on the bay. An infill piece is cut to
    the clear opening (`fencemodel/resolve.py`), which is narrower than the bay
    by one post face — so a caller converting this into a bay width adds the
    face back. Getting that wrong is how rev 1 advertised a saving 70 mm away
    from where it actually is.
    """
    if pieces < 1 or stock_mm <= 0:
        return 0
    return (stock_mm + kerf_mm) // pieces - kerf_mm


def alternative_widths(
    length_mm: Mm,
    max_span_mm: Mm,
    *,
    default: list[Mm],
    exact_mm: Mm | None = None,
    min_span_mm: Mm | None = None,
    piece_stock_mm: Mm | None = None,
    kerf_mm: Mm = 3,
    piece_shorter_by_mm: Mm = 0,
) -> list[tuple[str, list[Mm]]]:
    """Width lists worth offering BESIDE the one already built.

    `default` is passed in rather than recomputed: `layout_segment` decides what
    is built (honouring `prefer_equal`, a nominal preference, and a `min_span`
    rule it only WARNS about), and a second opinion here is how the built layout
    came to be missing from its own panel.

    `piece_stock_mm` / `piece_shorter_by_mm` come from the BASELINE's resolved
    infill — its product's stock length and how much narrower a piece is than
    its bay. Before the baseline exists there is no answer, and this returns no
    yield alternative rather than a guessed one.
    """
    out: list[tuple[str, list[Mm]]] = []
    seen = {tuple(default)}

    def offer(name: str, widths: list[Mm]) -> None:
        if not widths or tuple(widths) in seen:
            return
        if max(widths) > max_span_mm:
            return
        if min_span_mm and min(widths) < min_span_mm:
            return
        seen.add(tuple(widths))
        out.append((name, widths))

    if exact_mm:
        offer("tiling", exact_layout(length_mm, exact_mm)[0])
    if piece_stock_mm:
        # Two pieces per board is the only step worth offering: three is a bay
        # under 700 mm on 2 m stock, which `min_span_mm` exists to refuse.
        piece = yield_threshold(piece_stock_mm, kerf_mm, 2)
        target = piece + piece_shorter_by_mm
        if 0 < target < max_span_mm:
            offer("best_yield", equal_layout(length_mm, target))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_layout_alternatives.py tests/strategy -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/layout.py tests/strategy/test_layout_alternatives.py
git commit -m "feat(layout): alternatives beside the built default, with the yield threshold on the piece"
```

---

### Task 3: One anchor resolver, two behaviours

**Files:**
- Modify: `src/fenceai/topology/model.py` (`Anchor.reanchor`)
- Modify: `src/fenceai/topology/station.py` (`anchor_station` honours it)
- Test: `tests/topology/test_anchor_reanchor.py`

**Interfaces:**
- Produces: `Anchor.reanchor: Literal["proportional", "rigid"] = "proportional"`;
  `anchor_station` unchanged in signature.

- [ ] **Step 1: Write the failing test**

```python
# tests/topology/test_anchor_reanchor.py
"""Two behaviours, one resolver.

An elevation sample belongs to its segment PROPORTIONALLY — stretch the segment
and the sample stays a third of the way along (ADR-0003). A pinned POST does
not: a post placed 800 mm from a corner stays 800 mm from that corner, because
that is what the person measured.

Rev 1 added a SECOND resolver for overrides, which put the same pin 800 mm apart
in the plan canvas and the generator. The policy belongs on the anchor.
"""

from __future__ import annotations

from fenceai.topology.model import Anchor
from fenceai.topology.station import anchor_station, make_anchor
from tests.conftest import straight_topology


def _stretched(length_mm: int):
    topo = straight_topology(length_mm)
    return topo, topo.run("run1")


def test_a_proportional_anchor_moves_with_its_segment():
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 1000)
    topo2, run2 = _stretched(8000)
    assert anchor_station(topo2, run2, a) == 2000


def test_a_rigid_anchor_keeps_its_offset():
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 1000).model_copy(update={"reanchor": "rigid"})
    topo2, run2 = _stretched(8000)
    assert anchor_station(topo2, run2, a) == 1000


def test_proportional_is_the_default_so_nothing_stored_changes_meaning():
    assert Anchor(segment_index=0, offset_mm=10,
                   seg_len_at_authoring_mm=100).reanchor == "proportional"


def test_a_rigid_anchor_past_the_end_of_a_shrunken_segment_clamps():
    """It does NOT return None. Orphaning is the generator's decision, made from
    the resolved station, and a resolver that sometimes returns None forces
    every caller to branch on a case only one of them cares about."""
    topo, run = _stretched(4000)
    a = make_anchor(topo, run, 3000).model_copy(update={"reanchor": "rigid"})
    topo2, run2 = _stretched(1000)
    assert anchor_station(topo2, run2, a) == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/topology/test_anchor_reanchor.py -q`
Expected: FAIL — `ValidationError` / `AttributeError` on `reanchor`

- [ ] **Step 3: Write minimal implementation**

On `Anchor` in `topology/model.py`:

```python
    # How this anchor follows a change in its segment's length. PROPORTIONAL is
    # ADR-0003's rule and stays the default, so nothing stored changes meaning:
    # an elevation sample a third of the way along a wall stays a third of the
    # way along when the wall is stretched.
    #
    # RIGID is for an anchor whose OFFSET is the fact — a post a person placed
    # 800 mm from a corner. Stretch an earlier leg and it is still 800 mm from
    # that corner, which is what they measured.
    #
    # The policy lives here rather than in a second resolver because rev 1's
    # second resolver put the same pin 800 mm apart in the canvas and the
    # generator (spec §10).
    reanchor: Literal["proportional", "rigid"] = "proportional"
```

...and in `anchor_station`, branch on it, clamping a rigid offset to the segment's
current length rather than returning `None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/topology tests/scenarios -q`
Expected: PASS — the default keeps every existing anchor's behaviour identical.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/topology/model.py src/fenceai/topology/station.py \
        tests/topology/test_anchor_reanchor.py
git commit -m "feat(topology): an anchor declares how it re-anchors; one resolver, two behaviours"
```

---

### Task 4: Anchored overrides, and `lock_bay`

**Files:**
- Modify: `src/fenceai/strategy/overrides.py`
- Test: `tests/strategy/test_override_anchors.py`

**Interfaces:**
- Produces: `PinPost.anchor: Anchor | None`, `SuppressPost.anchor: Anchor | None`,
  `LockBay(kind, at: Anchor, width_mm: Mm)`, and
  `override_station(topo, run, directive) -> Mm | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_override_anchors.py
"""Where a directive applies, resolved the way every other anchor is.

`override_station` is a two-line wrapper over `anchor_station` ON PURPOSE. Rev 1
reimplemented the resolution and its three tests all avoided the one case where
the two implementations differ — a segment that changed length with the anchor
still inside it.
"""

from __future__ import annotations

from fenceai.strategy.overrides import LockBay, PinPost, override_station
from fenceai.topology.station import anchor_station, make_anchor
from tests.conftest import straight_topology


def _rigid(topo, run, station):
    return make_anchor(topo, run, station).model_copy(update={"reanchor": "rigid"})


def test_a_pin_resolves_exactly_as_anchor_station_does():
    """The equivalence rev 1's tests could not see. If these two ever disagree,
    the plan canvas and the generator draw the same post in two places."""
    topo = straight_topology(4000)
    run = topo.run("run1")
    pin = PinPost(anchor=_rigid(topo, run, 1200))
    bigger = straight_topology(9000)
    assert override_station(bigger, bigger.run("run1"), pin) \
        == anchor_station(bigger, bigger.run("run1"), pin.anchor)


def test_a_pinned_post_keeps_its_distance_when_the_run_grows():
    topo = straight_topology(4000)
    pin = PinPost(anchor=_rigid(topo, topo.run("run1"), 1200))
    bigger = straight_topology(9000)
    assert override_station(bigger, bigger.run("run1"), pin) == 1200


def test_a_stored_pin_with_no_anchor_still_resolves():
    """Every stored override carries `station_mm` and nothing else, and every
    golden scenario is single-segment, where both readings agree exactly."""
    topo = straight_topology(4000)
    assert override_station(topo, topo.run("run1"), PinPost(station_mm=1200)) == 1200


def test_a_directive_carrying_neither_is_orphaned_not_pinned_at_zero():
    """`station_mm` gains a default so the anchor can be the only field, and
    `0 < station < length` would silently discard a bare PinPost with no report."""
    topo = straight_topology(4000)
    assert override_station(topo, topo.run("run1"), PinPost()) is None


def test_a_locked_bay_is_one_anchor_and_a_width():
    """NOT two anchors. Two anchors can half-orphan, can swallow a corner when
    a leg grows, and silently redefine which bay was locked — all three found by
    review."""
    topo = straight_topology(5000)
    lock = LockBay(at=_rigid(topo, topo.run("run1"), 2000), width_mm=1000)
    assert override_station(topo, topo.run("run1"), lock) == 2000
    assert lock.width_mm == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_override_anchors.py -q`
Expected: FAIL — `ImportError: cannot import name 'LockBay'`

- [ ] **Step 3: Write minimal implementation**

```python
class LockBay(BaseModel):
    """Build the bay starting at this anchor, exactly this wide.

    One anchor and a width, not two anchors. Two anchors can resolve to a
    half-orphaned interval, can grow to contain a corner (which is structurally
    unsuppressable), and can silently relabel which bay a person signed off on.

    This is the one directive this work adds, and the reason hand placement
    means what it says: without it `layout_segment` honours `max_span_mm` inside
    a hand-placed gap and puts a post back that nobody asked for.
    """

    kind: Literal["lock_bay"] = "lock_bay"
    at: Anchor
    width_mm: Mm


def override_station(topo: Topology, run: Run, directive) -> Mm | None:
    """Where this directive applies, or None when it applies nowhere.

    A two-line wrapper over `anchor_station` — deliberately not a second
    implementation. `None` means orphaned, which the generator already reports
    as `orphaned_override`; it is returned only when the directive carries
    neither an anchor nor a usable station, never as a re-anchoring decision.
    """
    anchor = getattr(directive, "anchor", None) or getattr(directive, "at", None)
    if anchor is not None:
        return anchor_station(topo, run, anchor)
    station = getattr(directive, "station_mm", 0)
    return station or None
```

...plus `anchor` on `PinPost` and `SuppressPost`, `station_mm: Mm = 0`, and `LockBay` in
the `Directive` union.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_override_anchors.py tests/scenarios -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/overrides.py tests/strategy/test_override_anchors.py
git commit -m "feat(overrides): anchored pins, lock_bay as anchor plus width, one resolver reused"
```

---

### Task 5: A selection on the project, and its API

**Files:**
- Modify: `src/fenceai/project/model.py`, `src/fenceai/api/app.py`,
  `docs/architecture/04-backend.md`
- Test: `tests/api/test_choices_routes.py`

**Interfaces:**
- Produces: `Selection(choice_set, scope, widths: list[Mm] = [], bindings: dict[str, Mm] = {}, asked: bool = True, author: str = "user", created_at: str = "")` with `key() -> tuple[str, str]`;
  `Project.choices: list[Selection]`; `PUT /api/projects/{id}/choices`;
  `DELETE /api/projects/{id}/choices/{choice_set}?scope=...`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_choices_routes.py
"""Recording an answer, and pinning a question shut.

A selection names WHAT was chosen — the widths, or the bindings — not which
generator proposed it. `fewest_posts` is defined relative to `max_span`, so
answering a footing question silently changed what that name meant.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fenceai.api.app import app


def _project(client) -> str:
    return client.post("/api/projects", json={"name": "choices"}).json()["id"]


def test_a_selection_records_the_widths_it_chose_and_its_author():
    with TestClient(app) as client:
        pid = _project(client)
        got = client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "bay_layout", "scope": "gap:run1:0",
            "widths": [2000, 2000, 1000], "author": "bob",
        })
        assert got.status_code == 200, got.text
        stored = client.get(f"/api/projects/{pid}").json()["choices"]
        assert stored == [{"choice_set": "bay_layout", "scope": "gap:run1:0",
                            "widths": [2000, 2000, 1000], "bindings": {},
                            "asked": True, "author": "bob", "created_at": ""}]


def test_choosing_again_replaces_rather_than_accumulates():
    with TestClient(app) as client:
        pid = _project(client)
        for widths in ([2000, 2000, 1000], [1667, 1667, 1666]):
            client.put(f"/api/projects/{pid}/choices", json={
                "choice_set": "bay_layout", "scope": "gap:run1:0", "widths": widths})
        stored = client.get(f"/api/projects/{pid}").json()["choices"]
        assert [c["widths"] for c in stored] == [[1667, 1667, 1666]]


def test_two_gaps_on_one_run_are_two_separate_answers():
    """The upsert key is (set, scope) and scope is the GAP. A section-scoped key
    made one answer apply to a gap it was never measured for."""
    with TestClient(app) as client:
        pid = _project(client)
        for scope in ("gap:run1:0", "gap:run1:3000"):
            client.put(f"/api/projects/{pid}/choices", json={
                "choice_set": "bay_layout", "scope": scope, "widths": [1500, 1500]})
        assert len(client.get(f"/api/projects/{pid}").json()["choices"]) == 2


def test_a_pinned_question_is_a_selection_that_is_not_asked_again():
    with TestClient(app) as client:
        pid = _project(client)
        client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "footing_schedule", "scope": "model:M-VINYL",
            "bindings": {"footing_depth_mm": 610, "max_span_mm": 1676},
            "asked": False})
        assert client.get(f"/api/projects/{pid}").json()["choices"][0]["asked"] is False


def test_a_scope_with_a_slash_survives_the_round_trip():
    """`model:mfr/certainteed/rail` is a real scope. A path segment cannot carry
    it, which is why the scope is a query parameter on DELETE."""
    with TestClient(app) as client:
        pid = _project(client)
        scope = "model:mfr/certainteed/rail"
        client.put(f"/api/projects/{pid}/choices", json={
            "choice_set": "footing_schedule", "scope": scope, "bindings": {}})
        gone = client.delete(f"/api/projects/{pid}/choices/footing_schedule",
                              params={"scope": scope})
        assert gone.status_code == 200
        assert client.get(f"/api/projects/{pid}").json()["choices"] == []


def test_an_unknown_project_is_a_404_in_the_house_style():
    with TestClient(app) as client:
        got = client.put("/api/projects/nope/choices", json={
            "choice_set": "bay_layout", "scope": "gap:run1:0", "widths": []})
        assert got.status_code == 404
        assert "not found" in str(got.json()["detail"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_choices_routes.py -q`
Expected: FAIL — 404/405 from `PUT /api/projects/{id}/choices`

- [ ] **Step 3: Write minimal implementation**

`Selection` on `project/model.py` with the docstring from spec §3 (a choice is not an
override and not a correction), `Project.choices`, and two routes in `api/app.py` using
the existing `_project(project_id)` helper — the house pattern, which raises
`HTTPException(404, f"project {project_id} not found")` — then `state.store.save_project`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_choices_routes.py tests/architecture -q`
Expected: `test_choices_routes` PASS; `test_fitness` FAILS with *"the doc says 57 routes
and the app serves 59"*. Set the count in `docs/architecture/04-backend.md` and add a
**Choices** row — not to the Overrides row, since a choice is not an override.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/project/model.py src/fenceai/api/app.py \
        docs/architecture/04-backend.md tests/api/test_choices_routes.py
git commit -m "feat(choices): a selection naming the widths it chose, scoped to a gap"
```

---

### Task 6: Generation offers the alternatives

**Files:**
- Modify: `src/fenceai/strategy/generator.py`, `src/fenceai/decisions/graph.py`
- Test: `tests/strategy/test_choice_generation.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `generate(..., choices: list[Selection] | None = None, offer_alternatives: bool = True)`;
  `GenerationResult.choice_sets: list[ChoiceSet]`; `RunMeta.probe_count: int`;
  `NodeKind` gains `"choice"`; warning code `choice_unavailable`.

**This is the task that carries the risk.** Four shape changes land here; read spec §5–§7
and §12 before starting, and run the gate at the end of every step.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_choice_generation.py
"""Questions offered, answers honoured, and the gate unmoved.

Inputs are built explicitly — the style of `tests/strategy/test_boundary_posts.py`
— because rev 1 rested 17 test functions on an eight-method env fixture that
appeared in no task.

The literals come from the demo knowledge: `max_span_mm = 1800`
(`knowledge/demo.py`), so `equal_layout(5000, 1800)` is `[1667, 1667, 1666]`.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.project.model import Selection
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def _run(**kw):
    return generate(straight_topology(5000), demo_knowledge(), demo_catalog(), **kw)


def test_with_no_selection_the_default_is_todays_answer():
    """The property that keeps the gate still, asserted against a literal
    derived from the demo knowledge rather than against a second call."""
    out = _run()
    assert [s.width_mm for s in out.strategy.spans] == [1667, 1667, 1666]


def test_the_default_is_always_offered_as_a_point():
    out = _run()
    sets = {cs.id: cs for cs in out.choice_sets}
    if "bay_layout" in sets:
        assert sets["bay_layout"].points[0].is_default
        assert sets["bay_layout"].points[0].widths == [1667, 1667, 1666]


def test_the_scope_of_a_question_is_the_gap_not_the_run():
    """One pinned post makes a 5 m run two gaps. A run-scoped key emitted the
    same question twice and applied one answer to both."""
    from fenceai.strategy.overrides import Override, PinPost
    from fenceai.topology.station import make_anchor
    topo = straight_topology(5000)
    pin = make_anchor(topo, topo.run("run1"), 2000).model_copy(
        update={"reanchor": "rigid"})
    out = generate(topo, demo_knowledge(), demo_catalog(),
                   overrides=[Override(id="o1", run_id="run1",
                                        directive=PinPost(anchor=pin))])
    scopes = [cs.scope for cs in out.choice_sets if cs.id == "bay_layout"]
    assert len(scopes) == len(set(scopes)), scopes
    assert all(s.startswith("gap:run1:") for s in scopes)


def test_a_probe_does_not_offer_its_own_alternatives():
    """The bound that makes the cost linear. Without it `G(n) = 1 + n·G(n-1)`:
    two questions cost 5 generations and six sections cost 1957."""
    assert _run(offer_alternatives=False).choice_sets == []


def test_n_questions_cost_one_plus_n_generations():
    out = _run()
    offered = sum(len([p for p in cs.points if not p.is_default])
                  for cs in out.choice_sets)
    assert out.run.probe_count == offered


def test_generation_never_mutates_its_inputs():
    """A probe deep-copies. If it did not, the baseline's own choices would grow
    by one selection per probe."""
    topo = straight_topology(5000)
    choices = [Selection(choice_set="bay_layout", scope="gap:run1:0",
                          widths=[2000, 2000, 1000])]
    before = [c.model_dump() for c in choices]
    generate(topo, demo_knowledge(), demo_catalog(), choices=choices)
    assert [c.model_dump() for c in choices] == before


def test_a_selection_whose_widths_are_no_longer_offered_reports_and_falls_back():
    """Never a silent fallback — and the widths, not a generator name, are what
    goes stale."""
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[9999], author="bob")])
    assert [s.width_mm for s in out.strategy.spans] == [1667, 1667, 1666]
    gap = next(g for g in out.strategy.gaps
               if g.because.code == "choice_unavailable")
    assert gap.because.params["author"] == "bob"
    assert gap.closes_by == "planning"


def test_a_pinned_selection_whose_point_vanished_reopens_the_question():
    """Rev 1 emitted the gap and suppressed the panel row, telling a person to
    choose again through a control that pinning had removed."""
    out = _run(choices=[Selection(choice_set="bay_layout", scope="gap:run1:0",
                                   widths=[9999], asked=False)])
    assert any(cs.id == "bay_layout" for cs in out.choice_sets)


def test_two_runs_agree_on_the_questions_as_well_as_the_fence():
    """`test_determinism` covers strategy and graph; the new surface needs the
    same guarantee, and a probe is exactly the kind of thing that leaks dict
    iteration order into output."""
    a, b = _run(), _run()
    assert b.strategy.model_dump() == a.strategy.model_dump()
    assert [cs.model_dump() for cs in b.choice_sets] \
        == [cs.model_dump() for cs in a.choice_sets]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_choice_generation.py -q`
Expected: FAIL — `TypeError: generate() got an unexpected keyword argument 'choices'`

- [ ] **Step 3: Write minimal implementation**

In order, committing after each sub-step and running the gate each time:

1. `NodeKind` gains `"choice"` in `decisions/graph.py`.
2. `generate()` gains `choices` and `offer_alternatives`, threaded exactly as `site` and
   `parts` are; `api/app.py` passes the project's choices.
3. The span loop keys questions on `gap:{run.id}:{seg_start}` and applies a selection whose
   `widths` are offered for that gap; a selection whose widths are absent emits
   `code="choice_unavailable"` (a literal, so the locale scan sees it) and the default
   stands.
4. Phase 2, only when `offer_alternatives`: per gap, derive alternatives from
   `alternative_widths(...)` using the baseline's resolved infill stock, kerf and
   piece-vs-bay difference; probe each with
   `generate(..., choices=[...], offer_alternatives=False)`; diff the physical axes; run
   `offered(...)`; attach the sets and set `run.probe_count`.
5. The digest: append the choices tuple to the hashed **positional list** — not as a
   `RunMeta` field — and **only when non-empty**, so no existing run id moves and
   `RUN_DIGEST_VERSION` does not change.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/strategy/test_choice_generation.py -q && uv run pytest tests/scenarios -q && uv run pytest -q`
Expected: all PASS, **and the scenario count unmoved.** A moved golden number means a
default changed by accident — fix the default, never the scenario.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/generator.py src/fenceai/decisions/graph.py \
        src/fenceai/api/app.py tests/strategy/test_choice_generation.py
git commit -m "feat(choices): gap-scoped questions, probe-sourced measures, linear probe cost"
```

---

### Task 7: The explanation, in both languages

**Files:**
- Modify: `src/fenceai/decisions/explain.py`, `src/fenceai/web/static/i18n/{en,he}.json`,
  `tests/web/test_locale_bundles.py`
- Test: `tests/decisions/test_choice_explanation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/decisions/test_choice_explanation.py
"""Two sentences, because a default and a decision are different facts.

Also: the losing point rides a `defeated` edge only for a PARAMETER point, whose
synthesized version has a real ref. `GraphBuilder.add(defeated=[...])` calls
`_knowledge_node(ref)` on every string, so a layout point's id there would
invent a knowledge fact — against that method's own comment.
"""

from __future__ import annotations

import re

import pytest

from fenceai.decisions.explain import TEMPLATES


@pytest.mark.parametrize("key", ["resolve_choice_set", "resolve_choice_set_default"])
def test_both_bundles_carry_both_sentences(key):
    assert key in TEMPLATES["en"] and key in TEMPLATES["he"]


@pytest.mark.parametrize("key", ["resolve_choice_set", "resolve_choice_set_default"])
def test_the_two_languages_interpolate_the_same_params(key):
    """Key parity is guarded by `test_locale_bundles`; PARAM parity is not, and a
    template interpolating a param its sibling does not supply renders a literal
    `{point}` to a reader."""
    en = set(re.findall(r"\{(\w+)\}", TEMPLATES["en"][key]))
    he = set(re.findall(r"\{(\w+)\}", TEMPLATES["he"][key]))
    assert en == he


def test_a_default_never_renders_as_a_decision():
    """"Nobody has chosen" and "you chose" must not be one sentence."""
    assert "{when}" in TEMPLATES["en"]["resolve_choice_set"]
    assert "{when}" not in TEMPLATES["en"]["resolve_choice_set_default"]
```

- [ ] **Step 2: Run it and watch it fail** — `KeyError: 'resolve_choice_set'`.
- [ ] **Step 3: Implement** — both templates in both languages, param-identical;
  `warning.choice_unavailable` and `warning.span_placed_over_maximum` in both bundles;
  both codes in `WARNING_CODES`; `knowledge/parameters.py` and `strategy/generator.py`
  already in `scanned`.
- [ ] **Step 4: Run** `uv run pytest tests/decisions tests/web/test_locale_bundles.py -q`
- [ ] **Step 5: Commit.**

---

### Task 8: `lock_bay`, and the invariant's first authorized exception

**Files:**
- Modify: `src/fenceai/strategy/generator.py`, `docs/scenarios/golden-scenarios.md`,
  `tests/scenarios/test_invariants.py`
- Test: `tests/strategy/test_lock_bay.py`

**The load-bearing line:** `generator.py` **raises** `GenerationFailure` when
`width > sm.max_span`. This task edits the system's hard-constraint enforcement point;
rev 1's plan did not know that.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_lock_bay.py
"""A hand-placed bay is built as placed, and marked when it departs.

The actor lives on `Override.author`, not on the directive — so the generator
reaches the enclosing override, and the test asserts the whole param dict rather
than one key, because `run_id` is what the surfaces need to draw the bay.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import LockBay, Override, PinPost
from fenceai.topology.station import make_anchor
from tests.conftest import straight_topology


def _rigid(topo, station):
    return make_anchor(topo, topo.run("run1"), station).model_copy(
        update={"reanchor": "rigid"})


def test_an_unlocked_gap_is_still_subdivided():
    """Correct: an unlocked gap is what was left to the engine. demo max_span is
    1800, so a 3000 mm gap becomes two bays."""
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(),
                   overrides=[Override(id="o1", run_id="run1",
                                        directive=PinPost(anchor=_rigid(topo, 3000)))])
    assert [s.width_mm for s in out.strategy.spans][:2] == [1500, 1500]


def test_a_locked_bay_is_built_as_placed():
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o1", run_id="run1",
                 directive=PinPost(anchor=_rigid(topo, 3000))),
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    assert [s.width_mm for s in out.strategy.spans][0] == 3000


def test_a_locked_bay_over_the_maximum_warns_with_every_figure_a_surface_needs():
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o1", run_id="run1",
                 directive=PinPost(anchor=_rigid(topo, 3000))),
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    warn = next(w for w in out.strategy.warnings
                if w.code == "span_placed_over_maximum")
    assert warn.params == {"run_id": "run1", "placed_mm": 3000,
                            "max_mm": 1800, "over_mm": 1200, "author": "bob"}


def test_the_graph_attributes_the_placement_to_a_person():
    topo = straight_topology(5000)
    out = generate(topo, demo_knowledge(), demo_catalog(), overrides=[
        Override(id="o1", run_id="run1",
                 directive=PinPost(anchor=_rigid(topo, 3000))),
        Override(id="o2", run_id="run1", author="bob",
                 directive=LockBay(at=_rigid(topo, 0), width_mm=3000)),
    ])
    node = next(n for n in out.graph.nodes if n.action == "lock_bay")
    assert node.payload["author"] == "bob"
    assert node.kind == "override_applied"
```

- [ ] **Step 2: Run it and watch it fail** — `GenerationFailure: span … exceeds hard max`.
- [ ] **Step 3: Implement** — a locked interval is emitted as one span; the hard-max raise
  becomes conditional on the span not being locked; `code="span_placed_over_maximum"` as a
  literal; a locked bay under a `prefer_min_span_width` rule uses the existing
  `sliver_span`.
- [ ] **Step 4: Restate the invariant, then run the gate.** In
  `docs/scenarios/golden-scenarios.md`, the hard-max invariant becomes a conjunction —
  *within the maximum, **or** placed by a person and reported* — and
  `tests/scenarios/test_invariants.py` enforces the new form, so the next accidental
  over-max span does not look authorized.
- [ ] **Step 5: Commit.**

---

### Task 9: A `paired` row becomes parameter points

**Files:**
- Modify: `src/fenceai/knowledge/parameters.py`, `tests/web/test_locale_bundles.py`,
  `src/fenceai/web/static/i18n/{en,he}.json`
- Test: `tests/knowledge/test_paired_points.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/test_paired_points.py
"""The five refused tables, consumed.

Both assertions rev 1 made here passed on a positional reader and on
`points[0]`, because the fixture's declared order matched its value order and
its shortest span was also its first pair. These fixtures break both ties.
"""

from __future__ import annotations

from fenceai.knowledge.parameters import default_point, paired_points


def test_the_column_names_come_from_the_declared_value_type(paired_desc_first):
    """`paired(max_span_mm:mm, footing_depth_mm:mm)` with the SAME value list as
    the ordinary declaration. A positional reader swaps depth and span here and
    passes every test that compares a set of keys."""
    p = paired_points(paired_desc_first, paired_desc_first.rows[0])[0]
    assert p.bindings == {"max_span_mm": 610, "footing_depth_mm": 1676}


def test_the_default_is_the_shortest_span_not_the_first_pair(paired_span_desc):
    """Pairs published shortest-LAST, so `points[0]` is the wrong answer."""
    points = paired_points(paired_span_desc, paired_span_desc.rows[0])
    assert [p.bindings["max_span_mm"] for p in points] == [2464, 1676]
    assert default_point(points).bindings["max_span_mm"] == 1676
    assert default_point(points).is_default


def test_each_point_carries_the_sources_own_words(paired_real):
    """Obligation 5: the display keeps the lexeme. `24"` rides with 610."""
    p = paired_points(paired_real, paired_real.rows[0])[0]
    assert p.lexemes["footing_depth_mm"] == '24"'
    assert p.bindings["footing_depth_mm"] == 610


def test_the_refusal_is_gone(paired_real):
    from fenceai.knowledge.parameters import expand
    _, gaps, _ = expand(paired_real, as_of="2026-09-03")
    assert "parameter_paired_unsupported" not in {g.because.code for g in gaps}
```

- [ ] **Step 2: Run it and watch it fail** — `ImportError: cannot import name 'paired_points'`.
- [ ] **Step 3: Implement** — parse the declared `value_type` for its column names, one
  point per pair with `to_mm()` and `value_raw[0]` per binding, `default_point` picking the
  shortest span; replace the `_paired_unsupported_gap` call.
- [ ] **Step 4: Retire the code from ALL FOUR places it is listed** — `WARNING_CODES`,
  `KNOWLEDGE_SURFACE_UNTRANSLATED` (as `warning.parameter_paired_unsupported`), and both
  bundles — or `test_backend_code_list_is_current` fails on `listed_but_gone`. Then
  `uv run pytest -q`.
- [ ] **Step 5: Commit, then write `conversation.md` T45** in `fence-rag`: this closes the
  item, and the useful half to send back is which point each of the five tables defaults to
  and what the alternative saves. Declare the two new codes as registry additions (spec
  §13).

---

### Task 10: The golden scenario the shallow footing wins

**Files:**
- Modify: `docs/scenarios/golden-scenarios.md`, `tests/scenarios/`

At the 40 ft run the deeper footing wins on posts *and* concrete, so nothing exercises the
panel in the other direction. Use the `golden-scenarios` skill — the document and the tests
move together — to add a scenario at a run length where the **shallow** schedule wins, and
assert both the chosen point and the BOM difference.

---

## Self-review

**Spec coverage.** §3 concept → Task 1. §4.1 → Task 9; §4.2/§4.3 → Tasks 2, 6. §5.1 →
Tasks 6, 9. §5.2 → Task 1. §5.3 → Tasks 1, 6. §6 → Task 6. §7 → Task 6. §8 → Tasks 4, 5.
§9 → the frontend plan. §10 → Task 3. §11 → Task 8. §12 → Tasks 5, 6, 7. §13 → Task 9's
step 5. §15 → each task's test step.

**Placeholders:** none. Tasks 7–10 carry their tests in full and their implementations as
ordered sub-steps, because each is a small edit across files already specified.

**Type consistency:** `DesignPoint`, `ChoiceSet`, `dominates`, `offered`,
`yield_threshold`, `alternative_widths`, `Anchor.reanchor`, `override_station`, `LockBay`,
`Selection`, `paired_points`, `default_point` — each defined once and used with the same
signature after. `yield_threshold` deliberately exists twice, once per language; the
frontend plan owns the test that pins them together.

**The three failure modes this repo has recorded, checked against this plan:** no
assertion here is independent of the code under test (the golden guard is a literal derived
from `demo.py`'s `max_span_mm = 1800`); no test rebuilds the object under test (Task 8
asserts the whole param dict); and no test shares mutable state (every test builds its own
topology, and `tests/api/conftest.py`'s autouse isolation covers Task 5).
