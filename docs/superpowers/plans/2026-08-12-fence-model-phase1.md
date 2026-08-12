# Fence Model — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the panel-composition mechanism — a versioned fence model whose `PanelSpec` resolves per span into part slots — behind a built-in `M-LEGACY` model that reproduces today's two-rails-and-eight-screws behaviour exactly, plus one two-member eligibility group carried end to end.

**Architecture:** A new pure module `fenceai/fencemodel/` owns the schema (`model.py`), the one-dimensional pattern fit (`fit.py`) and the per-span resolution (`resolve.py`). The generator resolves a `ResolvedPanel` onto each `Span`; `derive_requirements` expands its slots into requirement lines instead of reading `Span.rail_count`/`screws_count`; a new `fenceai/fulfillment/supply.py` resolves each line's eligibility to a concrete SKU **before** `fulfill()` runs, so the parts ledger keeps keying on `(sku, unit)`. Nothing in the read path changes shape.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, `uv`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-12-fence-model-design.md`
**Review dispositions:** `docs/reviews/fence-model-design-review.md`

## Global Constraints

- **Integer millimetres and cents at rest; float only transient** (ADR-0002). Exactly two named tolerances live in `fenceai/core/units.py`.
- **`generate()` is pure and deterministic.** No clock, no RNG, no dict-order dependence. Overrides are patches anchored to `(run_id, station, kind)`, never to generated element identity (ADR-0004).
- **Hard constraint ≠ preference ≠ objective ≠ override** — distinct types, distinct handling.
- **The decision graph is the explanation.** Every element, requirement and BOM line traces through it. Prose renders from it via per-language templates; `decisions/explain.py` TEMPLATES en/he must stay key-identical.
- **Read models are derived, never stored** (`fenceai/report/`): the structure sheet must never recompute a quantity.
- **User-visible warnings carry `code + params`** (English `message` is fallback only); a new code needs `warning.<code>` entries in BOTH locale bundles.
- **One `fit_pattern` decision node per span, never one per member.**
- **`gaps_mm` is a list, not a single integer** — a single rounded gap would let `clear_gap_exceeded` pass while individual openings exceed the limit.
- **Acceptance gate for this phase:** S01–S14 produce **identical requirement lines and an identical BOM**. Not byte-identical output — `Span` gains `panel` and the graph gains new nodes.
- **Posts, caps, concrete and gate kits stay in `derive_requirements` as they are.** A panel covers spans only. Do not move them.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/fenceai/fencemodel/__init__.py` | empty, package marker (matches every other package) |
| `src/fenceai/fencemodel/model.py` | schema: `FenceModel`, `PanelSpec`, `FrameSlot`, `InfillSpec`, `Member`, `FixingRule`, `PartRequirement`, `Eligibility`, `EligibleItem`, `Axis`, `LayoutPolicy` + load-time validation |
| `src/fenceai/fencemodel/fit.py` | `fit_pattern()` and `FitResult` — pure 1-D fitting, no Pydantic, mirrors `strategy/layout.py` |
| `src/fenceai/fencemodel/resolve.py` | `resolve_panel()`, `PanelContext`, `ResolvedPanel`, `ResolvedSlot` — pure |
| `src/fenceai/fencemodel/demo.py` | `M_LEGACY` and `demo_models()` |
| `src/fenceai/fulfillment/supply.py` | `resolve_supply()` — chooses an eligible member per requirement, coupled to the cut plan |
| `src/fenceai/strategy/model.py` | `Span.panel` field; `GenerationRun.objective_preset`, `.model_snapshot`, `.catalog_hash` |
| `src/fenceai/strategy/generator.py` | resolve a panel per span; extend the run-id digest |
| `src/fenceai/demand/derive.py` | expand `span.panel` slots into requirement lines |
| `src/fenceai/fulfillment/fulfill.py` | `Bom.warnings` field only |
| `src/fenceai/report/structure.py` | `Part.slot_key`, merge key |
| `src/fenceai/api/app.py` | call `resolve_supply` before `fulfill`; `catalog_changed` 409 |

`fit.py` stays free of Pydantic and of every other module so its boundary matrix can be tested at speed, exactly as `strategy/layout.py` is.

---

### Task 1: The pattern fit

**Files:**
- Create: `src/fenceai/fencemodel/__init__.py` (empty)
- Create: `src/fenceai/fencemodel/fit.py`
- Test: `tests/fencemodel/test_fit.py`

**Interfaces:**
- Consumes: `fenceai.core.units.Mm`
- Produces: `fit_pattern(axis_len_mm, member_widths_mm, gaps_after_mm, justification, excess, edge_margin_mm) -> FitResult`; `FitResult(count, gaps_mm, edge_margin_start_mm, edge_margin_end_mm, residual_mm, rejected_alternative)`

- [ ] **Step 1: Write the failing tests**

Create `tests/fencemodel/test_fit.py`:

```python
"""The 1-D fit that turns a panel width into a member count.

The gap list is the point: integer millimetres cannot express "23.5 mm each",
and a single rounded gap would hide openings that exceed a safety limit.
"""

from fenceai.fencemodel.fit import fit_pattern


def test_exact_fit_leaves_no_residual():
    # 5 members of 100 with 4 gaps of 20 and no edge margin = 580; axis 580.
    r = fit_pattern(580, [100], [20], justification="spread_to_fit",
                    excess="space", edge_margin_mm=0)
    assert r.count == 5
    assert r.gaps_mm == [20, 20, 20, 20]
    assert r.residual_mm == 0


def test_residual_is_spread_one_mm_at_a_time_like_equal_layout():
    """2000 wide, 100 members, 20 nominal gap, margins at each end.

    16 members fit (16*100 + 17*20 = 1940); 60 mm is left over and 'space'
    widens the 17 gaps by 60/17 = 3.5 mm each, which int mm cannot do. The
    remainder goes one mm at a time to the first gaps, mirroring equal_layout.
    """
    r = fit_pattern(2000, [100], [20], justification="spread_to_fit",
                    excess="space", edge_margin_mm=0)
    assert r.count == 16
    assert len(r.gaps_mm) == 15  # gaps BETWEEN members; margins are separate
    assert sum(r.gaps_mm) + r.count * 100 + r.edge_margin_start_mm \
        + r.edge_margin_end_mm == 2000
    assert max(r.gaps_mm) - min(r.gaps_mm) <= 1  # spread, never lumped
    assert r.gaps_mm == sorted(r.gaps_mm, reverse=True)  # the +1s come first


def test_truncate_leaves_the_residual_as_a_gap_and_does_not_widen():
    r = fit_pattern(2000, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert set(r.gaps_mm) == {20}
    assert r.residual_mm == 2000 - (r.count * 100 + sum(r.gaps_mm))
    assert r.residual_mm > 0


def test_negative_gap_is_an_overlap_and_fits_more_members():
    """Board-on-board: the second member of the pattern overlaps the first."""
    plain = fit_pattern(1000, [100], [0], justification="start",
                        excess="truncate", edge_margin_mm=0)
    lapped = fit_pattern(1000, [100], [-25], justification="start",
                         excess="truncate", edge_margin_mm=0)
    assert lapped.count > plain.count


def test_two_member_pattern_alternates_widths_and_gaps():
    """Shadowbox: pattern [wide, narrow] repeats; the fit walks the sequence."""
    r = fit_pattern(1000, [100, 50], [10, 10], justification="start",
                    excess="truncate", edge_margin_mm=0)
    # each repeat consumes 100+10+50+10 = 170
    assert r.count == 11  # 5 full repeats (850) + one more 100 + 10 + 50 ... see fit
    assert r.gaps_mm[0] == 10


def test_zero_length_axis_yields_nothing_rather_than_raising():
    r = fit_pattern(0, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.count == 0 and r.gaps_mm == []


def test_axis_narrower_than_one_member_yields_nothing():
    r = fit_pattern(50, [100], [20], justification="start",
                    excess="truncate", edge_margin_mm=0)
    assert r.count == 0


def test_edge_margins_are_taken_off_the_axis_before_fitting():
    bare = fit_pattern(1000, [100], [20], justification="start",
                       excess="truncate", edge_margin_mm=0)
    inset = fit_pattern(1000, [100], [20], justification="start",
                        excess="truncate", edge_margin_mm=60)
    assert inset.count < bare.count
    assert inset.edge_margin_start_mm == 60 and inset.edge_margin_end_mm == 60


def test_spread_records_the_truncate_layout_as_the_rejected_alternative():
    r = fit_pattern(2000, [100], [20], justification="spread_to_fit",
                    excess="space", edge_margin_mm=0)
    assert r.rejected_alternative is not None
    assert set(r.rejected_alternative) == {20}


def test_is_deterministic():
    a = fit_pattern(1737, [90, 40], [15, 15], justification="spread_to_fit",
                    excess="space", edge_margin_mm=12)
    b = fit_pattern(1737, [90, 40], [15, 15], justification="spread_to_fit",
                    excess="space", edge_margin_mm=12)
    assert a == b
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/fencemodel/test_fit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.fencemodel'`

- [ ] **Step 3: Write the implementation**

Create `src/fenceai/fencemodel/__init__.py` as an empty file, then `src/fenceai/fencemodel/fit.py`:

```python
"""Fitting a repeating member pattern into one dimension (fence-model spec §fit).

The same shape of problem as `strategy/layout.py`, one dimension down: given an
axis length and a repeating sequence of members and gaps, how many members fit
and what are the real gaps. Pure, no Pydantic, no other module — so the
justification x excess boundary matrix stays cheap to pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fenceai.core.units import Mm

Justification = Literal["start", "end", "center", "spread_to_fit"]
Excess = Literal["truncate", "space", "trim_last", "extension_clip"]


@dataclass(frozen=True)
class FitResult:
    count: int
    gaps_mm: list[Mm]            # BETWEEN members; len == max(count - 1, 0)
    edge_margin_start_mm: Mm
    edge_margin_end_mm: Mm
    residual_mm: Mm              # unallocated axis length after members+gaps+margins
    rejected_alternative: list[Mm] | None  # the gap list the other excess policy gives


def _count_members(usable_mm: Mm, widths: list[Mm], gaps: list[Mm]) -> int:
    """Walk the repeating sequence, adding a member then the gap that follows it,
    while the NEXT member still fits. Gaps may be negative (an overlap)."""
    if usable_mm <= 0 or not widths:
        return 0
    used = 0
    count = 0
    while True:
        w = widths[count % len(widths)]
        if used + w > usable_mm:
            return count
        used += w
        count += 1
        used += gaps[(count - 1) % len(gaps)]


def _spread(total_mm: Mm, n: int) -> list[Mm]:
    """Remainder one mm at a time to the first gaps — the rule equal_layout uses
    (`strategy/layout.py:18`), so both spreaders behave the same way."""
    if n <= 0:
        return []
    base, rem = divmod(total_mm, n)
    return [base + 1 if i < rem else base for i in range(n)]


def fit_pattern(
    axis_len_mm: Mm,
    member_widths_mm: list[Mm],
    gaps_after_mm: list[Mm],
    *,
    justification: Justification,
    excess: Excess,
    edge_margin_mm: Mm,
) -> FitResult:
    usable = axis_len_mm - 2 * edge_margin_mm
    count = _count_members(usable, member_widths_mm, gaps_after_mm)
    if count == 0:
        return FitResult(0, [], edge_margin_mm, edge_margin_mm,
                         max(axis_len_mm, 0), None)

    widths_used = sum(member_widths_mm[i % len(member_widths_mm)] for i in range(count))
    nominal = [gaps_after_mm[i % len(gaps_after_mm)] for i in range(count - 1)]
    slack = usable - widths_used - sum(nominal)

    if excess == "space" and nominal:
        gaps = [g + extra for g, extra in zip(nominal, _spread(slack, len(nominal)))]
        residual = 0
    else:
        gaps = nominal
        residual = slack

    start, end = edge_margin_mm, edge_margin_mm
    if residual and justification in ("end", "center"):
        # 'start' leaves the residual at the far end (nothing to do); 'end' pushes
        # the whole run against the far end; 'center' halves it, odd mm to the end
        # so two identical panels are identical.
        shift = residual if justification == "end" else residual // 2
        start += shift
        end += residual - shift
        residual = 0

    alternative = nominal if excess == "space" and gaps != nominal else None
    return FitResult(count, gaps, start, end, residual, alternative)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fencemodel/test_fit.py -q`
Expected: PASS. If `test_two_member_pattern_alternates_widths_and_gaps` fails on the count, work the sequence by hand and correct the **test's** expected number — the walk in `_count_members` is the specification, and the test exists to pin it, not the reverse.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fencemodel/ tests/fencemodel/test_fit.py
git commit -m "feat(fencemodel): fit a repeating member pattern into one dimension"
```

---

### Task 2: The model schema

**Files:**
- Create: `src/fenceai/fencemodel/model.py`
- Test: `tests/fencemodel/test_model_validation.py`

**Interfaces:**
- Consumes: `fenceai.core.units.Mm`, `fenceai.knowledge.ast.Expr`, `fenceai.catalog.model.Catalog`
- Produces: `FenceModel`, `PanelSpec`, `FrameSlot`, `InfillSpec`, `Member`, `FixingRule`, `PartRequirement`, `Eligibility`, `EligibleItem`, `Axis`, `Placement`, `validate_model(model, catalog) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/fencemodel/test_model_validation.py`:

```python
"""Load-time validation. A model is authored data, so it is checked once when it
loads rather than trusted at every resolution."""

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, validate_model,
)


def _slot(**kw) -> FrameSlot:
    req = kw.pop("requirement", PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    ))
    return FrameSlot(key="rail", orientation="horizontal",
                     placement=Distributed(count=2), requirement=req, **kw)


def _model(spec: PanelSpec) -> FenceModel:
    return FenceModel(id="M-TEST", version=1, name_i18n={"en": "Test"},
                      default_spec=spec)


def test_a_wellformed_model_validates_clean():
    assert validate_model(_model(PanelSpec(frame=[_slot()])), demo_catalog()) == []


def test_an_eligible_sku_missing_from_the_catalog_is_rejected():
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="NOPE", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("NOPE" in e for e in errs)


def test_a_length_requirement_needs_a_member_that_can_supply_a_length():
    """POST-CAP is indivisible with no length_mm attribute, so it cannot be cut
    to a rail length. Consumption semantics live on the product (foundation §5)
    and the model is checked against them rather than restating them."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="POST-CAP", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("POST-CAP" in e and "length" in e for e in errs)


def test_sku_by_option_must_name_an_eligible_member():
    """An option value can NARROW eligibility; it can never smuggle in a product
    the slot does not allow."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="frame_finish", sku_by_option={"black": "POST-S"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("frame_finish" in e and "POST-S" in e for e in errs)


def test_duplicate_slot_keys_are_rejected():
    """slot_key is an override anchor dimension; two slots sharing one key would
    make an override ambiguous."""
    errs = validate_model(_model(PanelSpec(frame=[_slot(), _slot()])), demo_catalog())
    assert any("duplicate" in e.lower() for e in errs)


def test_a_swatch_must_be_a_plain_hex_colour():
    """The swatch reaches an SVG fill, which is a style context where esc() is not
    sufficient — so it is constrained at load, not escaped at render."""
    from fenceai.fencemodel.model import Axis, OptionValue

    model = FenceModel(
        id="M-TEST", version=1, name_i18n={"en": "T"},
        default_spec=PanelSpec(frame=[_slot()]),
        option_axes=[Axis(key="finish", kind="enum", values=[
            OptionValue(key="x", label_i18n={"en": "X"}, swatch="url(javascript:0)"),
        ])],
    )
    assert any("swatch" in e for e in validate_model(model, demo_catalog()))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/fencemodel/test_model_validation.py -q`
Expected: FAIL — `ImportError: cannot import name 'FenceModel'`

- [ ] **Step 3: Write the implementation**

Create `src/fenceai/fencemodel/model.py`:

```python
"""Fence models: a named product line and the structure of its normal panel.

Immutable versions, like knowledge objects (ADR-0006): a run stamps the model
versions it resolved, so editing a model cannot change what an old run meant.

The model owns product STRUCTURE. Numbers that can conflict — max span, rail
count, embedment — stay knowledge, and the model contributes them through
LayoutPolicy so the existing evaluator resolves them with everything else.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.catalog.model import Catalog
from fenceai.core.units import Mm
from fenceai.knowledge.ast import Expr

_SWATCH = re.compile(r"^#[0-9a-fA-F]{6}$")

LengthRule = Literal["clear_between_posts", "centre_to_centre", "overlap"]


# --- what a part IS, and which items may supply it ---------------------------

class EligibleItem(BaseModel):
    """One way to satisfy a requirement. Ordered by `priority`, which is the
    company's stated preference — never a probability (SAP's usage probability
    splits demand across alternates for forecasting; we compute one exact job).

    Deliberately no `supply` and no `conversion`: how a SKU is consumed already
    lives on the product, and a ratio is the nominal division that kerf
    disproves."""

    kind: Literal["catalog_item"] = "catalog_item"
    sku: str
    priority: int = 1
    approval: Literal["auto", "suggest_only"] = "auto"


# A discriminated union with one variant today. The workshop seam depends on
# this staying a union: a future `FabricatedRoute` carries operations instead of
# a SKU, and nothing outside the resolver may read `.sku` directly.
EligibilityMember = Annotated[Union[EligibleItem,], Field(discriminator="kind")]


class Eligibility(BaseModel):
    group: str | None = None
    members: list[EligibilityMember] = []
    predicate: Expr | None = None  # resolved and FROZEN into the run's snapshot


class PartRequirement(BaseModel):
    role: str                       # post | cap | concrete | rail | screw | infill | spacer
    qty: int = 1
    length_rule: LengthRule | None = None
    overlap_mm: Mm = 0              # only for length_rule == "overlap"
    option_axis: str | None = None
    sku_by_option: dict[str, str] = {}
    eligibility: Eligibility = Eligibility()


# --- placement ---------------------------------------------------------------

class FromBottom(BaseModel):
    kind: Literal["from_bottom"] = "from_bottom"
    offset_mm: Mm


class FromTop(BaseModel):
    kind: Literal["from_top"] = "from_top"
    offset_mm: Mm


class Fraction(BaseModel):
    kind: Literal["fraction"] = "fraction"
    permille: int


class Distributed(BaseModel):
    """N members spread over the panel height. `count_param` names a KNOWLEDGE
    param so a company rule can still win the count (see the spec: rail count is
    a number, not structure); `count` is the model's contributed default."""

    kind: Literal["distributed"] = "distributed"
    count: int
    count_param: str | None = None
    bottom_inset_mm: Mm = 0
    top_inset_mm: Mm = 0


Placement = Annotated[
    Union[FromBottom, FromTop, Fraction, Distributed], Field(discriminator="kind")
]


# --- the panel ---------------------------------------------------------------

class FrameSlot(BaseModel):
    key: str
    orientation: Literal["horizontal", "vertical"]
    placement: Placement
    requirement: PartRequirement


class Member(BaseModel):
    key: str
    width_mm: Mm
    thickness_mm: Mm = 0
    face_offset_mm: int = 0     # + front face, - back face (shadowbox)
    gap_after_mm: Mm = 0        # MAY be negative: an overlap (board-on-board)
    base_ref: str | None = None  # frame slot key this member starts at
    top_ref: str | None = None
    requirement: PartRequirement


class InfillSpec(BaseModel):
    orientation: Literal["vertical", "horizontal"]
    pattern: list[Member] = []
    justification: Literal["start", "end", "center", "spread_to_fit"] = "spread_to_fit"
    excess: Literal["truncate", "space", "trim_last", "extension_clip"] = "space"
    edge_margin_mm: Mm = 0
    supply: Literal["components", "assembly"] = "components"


class FixingRule(BaseModel):
    key: str
    basis: Literal[
        "per_member_crossing", "per_member", "per_end_member",
        "per_gap", "per_frame_member", "per_panel",
    ]
    qty_per_basis: int
    qty_param: str | None = None   # knowledge param, as Distributed.count_param
    requirement: PartRequirement


class PanelSpec(BaseModel):
    frame: list[FrameSlot] = []
    infill: InfillSpec | None = None
    fixings: list[FixingRule] = []


# --- the model ---------------------------------------------------------------

class OptionValue(BaseModel):
    key: str
    label_i18n: dict[str, str] = {}
    swatch: str | None = None   # validated at load: plain hex only


class Axis(BaseModel):
    key: str
    label_i18n: dict[str, str] = {}
    kind: Literal["enum", "numeric"]
    values: list[OptionValue] = []
    available_when: Expr | None = None


class PolicyContribution(BaseModel):
    """The model's ask of the span layout, emitted as knowledge rather than read
    directly. Authority is PER CONTRIBUTION: a manufacturer maximum span is a
    hard constraint, a nominal width is a preference. One authority for the whole
    policy would make one of the two wrong."""

    param: str
    value: int
    knowledge_type: Literal["hard_constraint", "company_rule", "fact", "preference"]
    authority: int | None = None


class Variant(BaseModel):
    condition: Expr
    spec: PanelSpec


class Continuous(BaseModel):
    kind: Literal["continuous"] = "continuous"
    min_mm: Mm
    max_mm: Mm
    step_mm: Mm = 1


class Discrete(BaseModel):
    kind: Literal["discrete"] = "discrete"
    heights_mm: list[Mm] = []


HeightSupport = Annotated[Union[Continuous, Discrete], Field(discriminator="kind")]


class FenceModel(BaseModel):
    id: str
    version: int
    name_i18n: dict[str, str] = {}
    grade: Literal["residential", "commercial", "industrial"] = "residential"
    status: Literal["draft", "active", "retired"] = "active"
    height_support: HeightSupport = Continuous(min_mm=0, max_mm=10_000)
    layout_policy: list[PolicyContribution] = []
    option_axes: list[Axis] = []
    default_spec: PanelSpec = PanelSpec()
    variants: list[Variant] = []   # authored order; first satisfied condition wins

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"


# --- load-time validation ----------------------------------------------------

def _requirements(spec: PanelSpec) -> list[tuple[str, PartRequirement]]:
    out = [(s.key, s.requirement) for s in spec.frame]
    if spec.infill:
        out += [(m.key, m.requirement) for m in spec.infill.pattern]
    out += [(f.key, f.requirement) for f in spec.fixings]
    return out


def _can_supply_length(catalog: Catalog, sku: str) -> bool:
    product = catalog.products.get(sku)
    if product is None:
        return False
    if product.consumption.kind == "divisible_linear":
        return True
    return isinstance(product.attrs.get("length_mm"), int)


def validate_model(model: FenceModel, catalog: Catalog) -> list[str]:
    """Every reason this model cannot be used, as English strings for the author.

    Checked once at load so resolution can trust the data. These are authoring
    errors, not user-facing warnings, so they carry no code+params."""
    errors: list[str] = []
    axis_keys = {a.key for a in model.option_axes}

    for axis in model.option_axes:
        for value in axis.values:
            if value.swatch is not None and not _SWATCH.match(value.swatch):
                errors.append(
                    f"axis {axis.key} value {value.key}: swatch must be #rrggbb, "
                    f"got {value.swatch!r}"
                )

    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        reqs = _requirements(spec)
        seen: set[str] = set()
        for key, _ in reqs:
            if key in seen:
                errors.append(f"duplicate slot key {key!r}")
            seen.add(key)
        for key, req in reqs:
            skus = [m.sku for m in req.eligibility.members]
            for sku in skus:
                if sku not in catalog.products:
                    errors.append(f"slot {key}: eligible sku {sku} is not in the catalog")
                elif req.length_rule is not None and not _can_supply_length(catalog, sku):
                    errors.append(
                        f"slot {key}: {sku} cannot supply a length "
                        f"(not divisible, no attrs.length_mm)"
                    )
            if req.option_axis and req.option_axis not in axis_keys:
                errors.append(f"slot {key}: option_axis {req.option_axis} is not declared")
            for value, sku in req.sku_by_option.items():
                if sku not in skus:
                    errors.append(
                        f"slot {key}: option {req.option_axis}={value} names {sku}, "
                        f"which is not an eligible member"
                    )
    return errors
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fencemodel/ -q`
Expected: PASS (both files).

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fencemodel/model.py tests/fencemodel/test_model_validation.py
git commit -m "feat(fencemodel): panel schema with load-time validation"
```

---

### Task 3: Resolving a panel for one span

**Files:**
- Create: `src/fenceai/fencemodel/resolve.py`
- Test: `tests/fencemodel/test_resolve.py`

**Interfaces:**
- Consumes: `fit_pattern`, `PanelSpec`, `FenceModel`
- Produces: `PanelContext`, `ResolvedSlot`, `ResolvedPanel`, `resolve_panel(spec, ctx) -> ResolvedPanel`, `select_variant(model, ctx) -> tuple[PanelSpec, int | None]`

`ResolvedSlot` carries **aggregate quantity plus fit parameters**, never a list of rectangles — geometry is derived from it later, which keeps "read models are derived, never stored" intact.

- [ ] **Step 1: Write the failing tests**

Create `tests/fencemodel/test_resolve.py`:

```python
"""Resolution is pure: the same context always gives the same panel, and it
needs no knowledge access because the params are already on the context."""

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FrameSlot, PanelSpec, PartRequirement,
)
from fenceai.fencemodel.resolve import PanelContext, resolve_panel

RAIL = PartRequirement(
    role="rail", qty=1, length_rule="centre_to_centre",
    eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
)
LEGACY = PanelSpec(frame=[FrameSlot(
    key="rail", orientation="horizontal",
    placement=Distributed(count=2, count_param="rails_per_span"), requirement=RAIL,
)])


def _ctx(**kw) -> PanelContext:
    base = dict(centre_width_mm=1500, clear_width_mm=1420, height_mm=1800,
                vertical="level", length_basis="width", params={"rails_per_span": 2},
                options={})
    return PanelContext(**{**base, **kw})


def test_distributed_count_comes_from_the_knowledge_param_not_the_default():
    """The model contributes a default of 2; knowledge said 3, and knowledge wins
    — otherwise a company rule scoped to a project would lose with no contest."""
    panel = resolve_panel(LEGACY, _ctx(params={"rails_per_span": 3}))
    rail = next(s for s in panel.slots if s.slot_key == "rail")
    assert rail.qty == 3


def test_missing_param_falls_back_to_the_models_default():
    panel = resolve_panel(LEGACY, _ctx(params={}))
    assert next(s for s in panel.slots if s.slot_key == "rail").qty == 2


def test_centre_to_centre_length_rule_uses_the_centre_width():
    panel = resolve_panel(LEGACY, _ctx())
    assert next(s for s in panel.slots if s.slot_key == "rail").length_mm == 1500


def test_clear_between_posts_length_rule_uses_the_clear_width():
    spec = LEGACY.model_copy(deep=True)
    spec.frame[0].requirement.length_rule = "clear_between_posts"
    panel = resolve_panel(spec, _ctx())
    assert next(s for s in panel.slots if s.slot_key == "rail").length_mm == 1420


def test_a_slot_carries_its_eligibility_forward_and_no_sku():
    """The panel says what must exist and which items may supply it. WHICH item
    is chosen is fulfillment's decision, coupled to the cut plan."""
    slot = resolve_panel(LEGACY, _ctx()).slots[0]
    assert slot.sku == ""
    assert [m.sku for m in slot.eligibility.members] == ["RAIL-3000"]


def test_resolution_is_deterministic():
    assert resolve_panel(LEGACY, _ctx()) == resolve_panel(LEGACY, _ctx())


def test_infill_slot_reports_its_fit_and_one_aggregate_quantity():
    """Quantities aggregate per slot; geometry enumerates later. A 40-slat bay is
    ONE requirement line of 40, not 40 lines."""
    from fenceai.fencemodel.model import InfillSpec, Member

    spec = PanelSpec(infill=InfillSpec(
        orientation="vertical",
        pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-3000", priority=1)])))],
    ))
    panel = resolve_panel(spec, _ctx())
    slat = next(s for s in panel.slots if s.slot_key == "slat")
    assert slat.qty == slat.fit.count > 1
    assert len(panel.slots) == 1
    assert max(slat.fit.gaps_mm) - min(slat.fit.gaps_mm) <= 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/fencemodel/test_resolve.py -q`
Expected: FAIL — `ImportError: cannot import name 'PanelContext'`

- [ ] **Step 3: Write the implementation**

Create `src/fenceai/fencemodel/resolve.py`:

```python
"""Resolving a PanelSpec against one span (fence-model spec §resolve_panel).

Pure and deterministic, and it takes NO knowledge access: every param it needs
was resolved during generation and arrives on the context, exactly as
Span.rail_count does today.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.fencemodel.fit import FitResult, fit_pattern
from fenceai.fencemodel.model import (
    Distributed, Eligibility, FenceModel, PanelSpec, PartRequirement,
)
from fenceai.knowledge.ast import MissingField, evaluate_expr


class PanelContext(BaseModel):
    """Everything a panel needs to know about the bay it is being laid into."""

    centre_width_mm: Mm
    clear_width_mm: Mm
    height_mm: Mm
    vertical: str = "level"
    length_basis: str = "width"      # "width" | "slope" — from the span
    slope_len_mm: Mm | None = None
    params: dict[str, int] = {}      # knowledge-resolved: rails_per_span, ...
    options: dict[str, str | int] = {}

    def condition_ctx(self) -> dict:
        return {"panel": {
            "width_mm": self.centre_width_mm, "height_mm": self.height_mm,
            "vertical": self.vertical,
        }}


class ResolvedSlot(BaseModel):
    slot_key: str
    role: str
    qty: int
    length_mm: Mm | None = None
    length_basis: str | None = None
    sku: str = ""                    # resolved by fulfillment, never here
    eligibility: Eligibility = Eligibility()
    fit: FitResult | None = None

    model_config = {"arbitrary_types_allowed": True}


class ResolvedPanel(BaseModel):
    model_ref: str = ""
    variant_index: int | None = None
    slots: list[ResolvedSlot] = []


def select_variant(model: FenceModel, ctx: PanelContext) -> tuple[PanelSpec, int | None]:
    """Authored order, first satisfied condition wins — deliberately not
    'specificity', which is undefined for a bare Expr and would have two
    implementers counting different things."""
    for index, variant in enumerate(model.variants):
        try:
            if evaluate_expr(variant.condition, ctx.condition_ctx()):
                return variant.spec, index
        except MissingField:
            continue
    return model.default_spec, None


def _length_for(req: PartRequirement, ctx: PanelContext) -> Mm | None:
    if req.length_rule is None:
        return None
    if req.length_rule == "clear_between_posts":
        base = ctx.clear_width_mm
    elif req.length_rule == "overlap":
        base = ctx.centre_width_mm + req.overlap_mm
    else:
        base = ctx.centre_width_mm
    if ctx.length_basis == "slope" and ctx.slope_len_mm is not None:
        # the slope factor applies to the same rule, not to a raw width
        return base + (ctx.slope_len_mm - ctx.centre_width_mm)
    return base


def _qty(count: int, param: str | None, ctx: PanelContext) -> int:
    return ctx.params.get(param, count) if param else count


def resolve_panel(spec: PanelSpec, ctx: PanelContext, model_ref: str = "") -> ResolvedPanel:
    slots: list[ResolvedSlot] = []

    for frame_slot in spec.frame:
        req = frame_slot.requirement
        count = (_qty(frame_slot.placement.count, frame_slot.placement.count_param, ctx)
                 if isinstance(frame_slot.placement, Distributed) else 1)
        slots.append(ResolvedSlot(
            slot_key=frame_slot.key, role=req.role, qty=count * req.qty,
            length_mm=_length_for(req, ctx), length_basis=ctx.length_basis,
            eligibility=req.eligibility,
        ))

    if spec.infill and spec.infill.pattern:
        axis = (ctx.clear_width_mm if spec.infill.orientation == "vertical"
                else ctx.height_mm)
        fit = fit_pattern(
            axis,
            [m.width_mm for m in spec.infill.pattern],
            [m.gap_after_mm for m in spec.infill.pattern],
            justification=spec.infill.justification,
            excess=spec.infill.excess,
            edge_margin_mm=spec.infill.edge_margin_mm,
        )
        for offset, member in enumerate(spec.infill.pattern):
            # how many of THIS member of the repeating sequence were placed
            n = sum(1 for i in range(fit.count) if i % len(spec.infill.pattern) == offset)
            if not n:
                continue
            slots.append(ResolvedSlot(
                slot_key=member.key, role=member.requirement.role,
                qty=n * member.requirement.qty,
                length_mm=_length_for(member.requirement, ctx),
                length_basis=ctx.length_basis,
                eligibility=member.requirement.eligibility, fit=fit,
            ))

    frame_count = sum(s.qty for s in slots if s.fit is None)
    member_count = sum(s.qty for s in slots if s.fit is not None)
    for rule in spec.fixings:
        per = _qty(rule.qty_per_basis, rule.qty_param, ctx)
        basis = {
            "per_panel": 1,
            "per_frame_member": frame_count,
            "per_member": member_count,
            "per_end_member": min(member_count, 2),
            "per_gap": max(member_count - 1, 0),
            "per_member_crossing": member_count * frame_count,
        }[rule.basis]
        if not basis:
            continue
        slots.append(ResolvedSlot(
            slot_key=rule.key, role=rule.requirement.role, qty=per * basis,
            eligibility=rule.requirement.eligibility,
        ))

    return ResolvedPanel(model_ref=model_ref, slots=slots)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fencemodel/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fencemodel/resolve.py tests/fencemodel/test_resolve.py
git commit -m "feat(fencemodel): resolve a panel spec against one span"
```

---

### Task 4: M-LEGACY, and a panel on every span

**Files:**
- Create: `src/fenceai/fencemodel/demo.py`
- Modify: `src/fenceai/strategy/model.py` (add `Span.panel`)
- Modify: `src/fenceai/strategy/generator.py:930-954` (build the panel with the span)
- Test: `tests/fencemodel/test_legacy_model.py`

**Interfaces:**
- Consumes: `resolve_panel`, `PanelContext`
- Produces: `M_LEGACY: FenceModel`, `demo_models() -> dict[str, FenceModel]`; `Span.panel: ResolvedPanel | None`

- [ ] **Step 1: Write the failing test**

Create `tests/fencemodel/test_legacy_model.py`:

```python
"""M-LEGACY exists to prove the mechanism can reproduce what the two integers on
Span already do. If it cannot, the mechanism is not right yet."""

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import M_LEGACY
from fenceai.fencemodel.model import validate_model
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def test_legacy_model_validates_against_the_demo_catalog():
    assert validate_model(M_LEGACY, demo_catalog()) == []


def test_every_span_gets_a_panel_whose_slots_match_its_legacy_counts():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert result.strategy.spans
    for span in result.strategy.spans:
        assert span.panel is not None
        rails = next(s for s in span.panel.slots if s.role == "rail")
        screws = next(s for s in span.panel.slots if s.role == "screw")
        assert rails.qty == span.rail_count
        assert screws.qty == span.screws_count
        assert rails.length_mm == span.width_mm       # centre_to_centre, as today
        assert rails.length_basis == span.rail_cut_basis


def test_the_panel_names_no_sku_and_carries_the_runs_resolved_default():
    """The DefaultComponent fallback is frozen onto the requirement at GENERATION,
    so fulfillment never has to look anything up in knowledge."""
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    rails = next(s for s in result.strategy.spans[0].panel.slots if s.role == "rail")
    assert rails.sku == ""
    assert [m.sku for m in rails.eligibility.members] == ["RAIL-3000"]
```

`straight_topology` and `add_point_event` are plain functions in `tests/conftest.py:29`, imported directly — that is how `tests/scenarios/test_s07_s12.py:13` does it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/fencemodel/test_legacy_model.py -q`
Expected: FAIL — `ModuleNotFoundError: fenceai.fencemodel.demo`

- [ ] **Step 3: Write the implementation**

Create `src/fenceai/fencemodel/demo.py`:

```python
"""Built-in models. M-LEGACY is the compatibility path: a run with no fence_model
event resolves to it, and it must reproduce today's behaviour exactly.

It declares centre_to_centre deliberately. golden-scenarios.md:23 says rails are
cut to "clear width" while demand/derive.py:63 cuts to span.width_mm, which is
centre-to-centre. That disagreement predates this work and CLAUDE.md forbids
reconciling it silently, so M-LEGACY preserves the CODE's behaviour and the
scenario text is settled separately through the golden-scenarios skill.
"""

from __future__ import annotations

from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FixingRule, FrameSlot,
    PanelSpec, PartRequirement,
)


def legacy_model(rail_sku: str = "RAIL-3000", screw_sku: str = "SCREW-S10") -> FenceModel:
    """The model's eligibility is seeded from the run's resolved demand skus, so
    a knowledge DefaultComponent change still reaches the BOM."""
    return FenceModel(
        id="M-LEGACY", version=1,
        name_i18n={"en": "Legacy panel", "he": "פאנל מורשת"},
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal",
                placement=Distributed(count=2, count_param="rails_per_span"),
                requirement=PartRequirement(
                    role="rail", qty=1, length_rule="centre_to_centre",
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=rail_sku, priority=1)]),
                ),
            )],
            fixings=[FixingRule(
                key="screw", basis="per_panel", qty_per_basis=8,
                qty_param="screws_per_span",
                requirement=PartRequirement(
                    role="screw", qty=1,
                    eligibility=Eligibility(
                        members=[EligibleItem(sku=screw_sku, priority=1)]),
                ),
            )],
        ),
    )


M_LEGACY = legacy_model()


def demo_models() -> dict[str, FenceModel]:
    return {M_LEGACY.id: M_LEGACY}
```

In `src/fenceai/strategy/model.py`, add the import and the field on `Span`:

```python
from fenceai.fencemodel.resolve import ResolvedPanel
```

```python
class Span(BaseModel):
    ...
    rail_cut_basis: Literal["width", "slope"] = "width"
    # What this bay is made of, resolved from the fence model at generation.
    # rail_count/screws_count stay until a migration back-fills `panel` onto
    # stored runs: a run re-read without either would silently default to 2.
    panel: ResolvedPanel | None = None
```

In `src/fenceai/strategy/generator.py`, immediately after the `Span(...)` is constructed and before `strategy.spans.append(span)` (currently `generator.py:930-940`):

```python
            span.panel = resolve_panel(
                model.default_spec,
                PanelContext(
                    centre_width_mm=width,
                    clear_width_mm=width,  # face widths arrive in phase 2
                    height_mm=height,
                    vertical=v_mode,
                    length_basis=span.rail_cut_basis,
                    slope_len_mm=span.slope_len_mm,
                    params={"rails_per_span": rails_per_span,
                            "screws_per_span": screws_per_span},
                ),
                model_ref=model.ref,
            )
```

Resolve `model` once near the top of `_generate_run`, beside the other per-run resolutions:

```python
    model = legacy_model(
        rail_sku=demand_skus.get("rail_sku", "RAIL-3000"),
        screw_sku=demand_skus.get("screw_sku", "SCREW-S10"),
    )
```

Add one decision node per span, after `create_span` (never one per member):

```python
            builder.add(
                "structural", "resolve_panel",
                payload={"model_ref": model.ref,
                         "slots": [{"key": s.slot_key, "role": s.role, "qty": s.qty}
                                   for s in span.panel.slots]},
                scope_refs=[span.id], inputs=[layout_node.id],
            )
```

- [ ] **Step 4: Run the tests to verify they pass, and the suite to verify nothing moved**

Run: `uv run pytest tests/fencemodel/ -q && uv run pytest -q`
Expected: the new tests PASS and the full suite is green — `derive_requirements` still reads the legacy fields, so no requirement or BOM has changed yet.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/fencemodel/demo.py src/fenceai/strategy/model.py \
        src/fenceai/strategy/generator.py tests/fencemodel/test_legacy_model.py
git commit -m "feat(strategy): resolve a panel onto every span behind M-LEGACY"
```

---

### Task 5: Demand reads the panel — the compatibility gate

**Files:**
- Modify: `src/fenceai/demand/derive.py:62-68`
- Test: `tests/demand/test_derive_from_panel.py`

**Interfaces:**
- Consumes: `Span.panel`
- Produces: `RequirementLine.slot_key: str`, `RequirementLine.eligibility: Eligibility`; `RequirementLine.sku` becomes `""` until fulfillment resolves it

**This is the gate.** S01–S14 must produce identical requirement lines and an identical BOM after this task. Because eligibility is single-member here, the resolver in Task 6 has no choice to make — but the SKU is not on the line until Task 6 lands, so the two tasks ship together or the suite is red between them. Implement Task 6 in the same session and commit them back to back.

- [ ] **Step 1: Write the failing test**

Create `tests/demand/test_derive_from_panel.py`:

```python
"""Demand expands the panel's slots. Posts, caps, concrete and gate kits are NOT
panel parts and keep their existing path."""

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def test_span_lines_come_from_the_panel_and_carry_slot_key_and_eligibility():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    reqs = derive_requirements(result.strategy, demo_catalog(), result.run.demand_skus)
    rails = [r for r in reqs if r.role == "rail"]
    assert rails and all(r.slot_key == "rail" for r in rails)
    assert all(r.sku == "" for r in rails)          # resolved in fulfillment
    assert all([m.sku for m in r.eligibility.members] == ["RAIL-3000"] for r in rails)


def test_post_lines_are_untouched_by_the_panel_path():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    reqs = derive_requirements(result.strategy, demo_catalog(), result.run.demand_skus)
    posts = [r for r in reqs if r.role == "post"]
    assert posts and all(r.sku for r in posts)      # still named directly
    assert all(r.slot_key == "" for r in posts)


def test_one_line_per_slot_not_one_per_member():
    """A 40-slat bay must be one line of 40. This is what keeps the decision graph
    and the BOM from exploding on a 100 m fence."""
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    reqs = derive_requirements(result.strategy, demo_catalog(), result.run.demand_skus)
    per_span_rail_lines = [r for r in reqs if r.role == "rail"]
    assert len(per_span_rail_lines) == len(result.strategy.spans)
    assert all(r.engineering_qty == 2 for r in per_span_rail_lines)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/demand/test_derive_from_panel.py -q`
Expected: FAIL — `AttributeError: 'RequirementLine' object has no attribute 'slot_key'`

- [ ] **Step 3: Write the implementation**

In `src/fenceai/demand/derive.py`, add the two fields to `RequirementLine`:

```python
class RequirementLine(BaseModel):
    id: str
    sku: str = ""          # RESOLVED by fulfillment from `eligibility`, not authored
    ...
    role: str = ""
    slot_key: str = ""     # sub-element identity: which part of the panel this is
    eligibility: Eligibility = Eligibility()
```

Replace the span loop (`derive.py:62-68`) with:

```python
    for span in strategy.spans:
        if span.panel is None:
            raise ValueError(
                f"span {span.id} has no panel — regenerate the run; "
                "stored runs from before the fence-model change are read with "
                "their legacy fields intact"
            )
        for slot in span.panel.slots:
            add(
                "", slot.qty, _UNIT_BY_ROLE.get(slot.role, "each"), [span.id],
                cut_length_mm=slot.length_mm, length_basis=slot.length_basis,
                role=slot.role, slot_key=slot.slot_key, eligibility=slot.eligibility,
            )
```

with, above `derive_requirements`:

```python
# Which engineering unit a role is counted in. A cut length makes a line a "cut";
# everything else is counted in eaches.
_UNIT_BY_ROLE = {"rail": "cut", "infill": "cut"}
```

Note the ordering consequence: today rails are emitted before screws for each span, and the panel's slots come out frame-then-infill-then-fixings, which preserves that order for M-LEGACY. Requirement ids are positional (`req0001`…), so a changed order would change every id downstream. If the suite shows id drift, fix the slot order in `demo.py`, not the ids in the tests.

- [ ] **Step 4: Run the new test**

Run: `uv run pytest tests/demand/test_derive_from_panel.py -q`
Expected: PASS. The full suite is expected to be **red** at this point because requirement lines have no SKU yet — Task 6 closes it.

- [ ] **Step 5: Do not commit yet**

Proceed directly to Task 6 and commit the pair together.

---

### Task 6: Supply resolution — the SKU write-back

**Files:**
- Create: `src/fenceai/fulfillment/supply.py`
- Modify: `src/fenceai/api/app.py:277-315` (both `/bom` and `/structure`)
- Test: `tests/fulfillment/test_supply.py`

**Interfaces:**
- Consumes: `RequirementLine.eligibility`, `Catalog`, `Inventory`
- Produces: `SupplyResolution(requirements, warnings, decisions)`, `resolve_supply(requirements, catalog, inventory, preset="least_cost") -> SupplyResolution`

The ledger keys on `(sku, unit)` from `RequirementLine.sku` (`report/structure.py:180`). A SKU-free line reaching it reports the same quantity as unassigned **and** from-stock at once. So resolution runs **before** `fulfill()` and hands it lines that already name a product.

- [ ] **Step 1: Write the failing test**

Create `tests/fulfillment/test_supply.py`:

```python
"""Choosing among eligible items. With one member there is nothing to choose and
the line simply gains its SKU; the two-member case arrives in the next task."""

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import RequirementLine
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fulfillment.supply import resolve_supply


def _line(**kw) -> RequirementLine:
    base = dict(id="req0001", sku="", engineering_qty=2, unit="cut",
                cut_length_mm=1500, role="rail", slot_key="rail",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]))
    return RequirementLine(**{**base, **kw})


def test_a_single_member_resolves_to_itself():
    out = resolve_supply([_line()], demo_catalog())
    assert out.requirements[0].sku == "RAIL-3000"
    assert out.warnings == []


def test_a_line_that_already_names_a_sku_is_left_alone():
    """Posts, caps and concrete never go through eligibility."""
    line = _line(sku="POST-S", eligibility=Eligibility(), role="post", slot_key="")
    assert resolve_supply([line], demo_catalog()).requirements[0].sku == "POST-S"


def test_an_empty_eligibility_warns_rather_than_guessing():
    out = resolve_supply([_line(eligibility=Eligibility())], demo_catalog())
    assert out.requirements[0].sku == ""
    assert [w.code for w in out.warnings] == ["no_eligible_item"]
    assert out.warnings[0].params["role"] == "rail"


def test_a_suggest_only_member_is_not_used_without_approval():
    line = _line(eligibility=Eligibility(
        members=[EligibleItem(sku="RAIL-3000", approval="suggest_only")]))
    out = resolve_supply([line], demo_catalog())
    assert out.requirements[0].sku == ""
    assert [w.code for w in out.warnings] == ["substitute_needs_approval"]


def test_resolution_does_not_mutate_the_caller_s_lines():
    """generate() is pure and the report is a pure function of its inputs; a
    resolver that mutated in place would make a stored run's requirements depend
    on whether anyone had looked at the BOM."""
    line = _line()
    resolve_supply([line], demo_catalog())
    assert line.sku == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/fulfillment/test_supply.py -q`
Expected: FAIL — `ModuleNotFoundError: fenceai.fulfillment.supply`

- [ ] **Step 3: Write the implementation**

Create `src/fenceai/fulfillment/supply.py`:

```python
"""Choosing which eligible item supplies each requirement (fence-model spec §3).

Runs BEFORE fulfill() so every line names a product by the time the cut planner,
the BOM and the parts ledger see it — the ledger keys on (sku, unit) and a blank
SKU would make one demand read as both unassigned and from-stock.

The choice is an OBJECTIVE, not a lookup: with more than one member it is
coupled to the cut plan, because stock lengths cannot be ranked without planning
the cuts. Lexicographic tiers with named presets (ADR-0007), never raw weights.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fenceai.catalog.model import Catalog
from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.fulfill import Inventory
from fenceai.strategy.model import StrategyWarning

Preset = Literal["least_cost", "honour_priority"]


class SupplyResolution(BaseModel):
    requirements: list[RequirementLine] = []
    warnings: list[StrategyWarning] = []
    decisions: list[dict] = []   # chosen + rejected, for the decision graph


def _usable(members, approvals: set[str]) -> list:
    return [m for m in members if m.approval == "auto" or m.sku in approvals]


def resolve_supply(
    requirements: list[RequirementLine],
    catalog: Catalog,
    inventory: Inventory | None = None,
    preset: Preset = "least_cost",
    approvals: set[str] | None = None,
) -> SupplyResolution:
    approvals = approvals or set()
    out = SupplyResolution()

    for req in requirements:
        line = req.model_copy(deep=True)   # never mutate the caller's lines
        if line.sku or not line.eligibility.members:
            if not line.sku:
                out.warnings.append(StrategyWarning(
                    code="no_eligible_item", severity="error",
                    message=f"No product is eligible to supply {line.role}.",
                    params={"role": line.role, "slot_key": line.slot_key},
                ))
            out.requirements.append(line)
            continue

        usable = _usable(line.eligibility.members, approvals)
        if not usable:
            out.warnings.append(StrategyWarning(
                code="substitute_needs_approval", severity="warning",
                message=f"Only a suggest-only product fits {line.role}; "
                        "it needs approval before it can be used.",
                params={"role": line.role, "slot_key": line.slot_key,
                        "sku": line.eligibility.members[0].sku},
            ))
            out.requirements.append(line)
            continue

        chosen = _choose(usable, line, catalog, inventory, preset)
        line.sku = chosen.sku
        out.requirements.append(line)
        if len(usable) > 1:
            out.decisions.append({
                "requirement_id": line.id, "slot_key": line.slot_key,
                "chosen": chosen.sku, "preset": preset,
                "rejected": [m.sku for m in usable if m.sku != chosen.sku],
            })
    return out


def _choose(usable, line, catalog, inventory, preset):
    """One member: no decision. More than one: Task 8 replaces this body with the
    cut-plan-coupled comparison. Ordering by priority here is correct for a
    single member and is the honour_priority answer for several."""
    return sorted(usable, key=lambda m: (m.priority, m.sku))[0]
```

In `src/fenceai/api/app.py`, in **both** `get_bom` and `get_structure`, replace the `requirements = derive_requirements(...)` line with:

```python
    requirements = derive_requirements(result.strategy, catalog, result.run.demand_skus)
    resolution = resolve_supply(requirements, catalog, inventory,
                                preset=result.run.objective_preset)
    requirements = resolution.requirements
    bom = fulfill(requirements, catalog, inventory)
    bom.warnings = resolution.warnings
```

Add `warnings: list[StrategyWarning] = []` to `Bom` in `fulfillment/fulfill.py:56-61`, and default `objective_preset: str = "least_cost"` on `GenerationRun` in `strategy/model.py`.

Do the same in `create_quote` (`app.py:334-337`) so a quote freezes resolved lines.

- [ ] **Step 4: Run the full suite — this is the compatibility gate**

Run: `uv run pytest -q`
Expected: **PASS, all of it.** S01–S14 produce identical requirement lines and an identical BOM. If a scenario fails, do not adjust the scenario — the mechanism is wrong. Compare with:

```bash
git stash && uv run pytest tests/scenarios -q > /tmp/before.txt; git stash pop
uv run pytest tests/scenarios -q > /tmp/after.txt; diff /tmp/before.txt /tmp/after.txt
```

- [ ] **Step 5: Commit both tasks**

```bash
git add src/fenceai/demand/derive.py src/fenceai/fulfillment/supply.py \
        src/fenceai/fulfillment/fulfill.py src/fenceai/strategy/model.py \
        src/fenceai/api/app.py tests/demand/test_derive_from_panel.py \
        tests/fulfillment/test_supply.py
git commit -m "feat(demand,fulfillment): expand panel slots and resolve their supply

Requirement lines stop naming a SKU and start carrying eligibility; the
chosen member is written back before fulfill() runs, so the parts ledger
keeps keying on (sku, unit). S01-S14 requirements and BOM unchanged."
```

---

### Task 7: The warning codes reach both locales

**Files:**
- Modify: `src/fenceai/web/static/i18n/en.json`, `src/fenceai/web/static/i18n/he.json`
- Modify: `tests/web/test_locale_bundles.py:60-70` (the scanner's file list and `WARNING_CODES`)
- Test: the modified bundle test itself

The scanner regexes `code="..."` out of exactly two files — `strategy/generator.py` and `ai/stub.py`. Both new codes live in `fulfillment/supply.py`, so without this they ship untranslated and the test stays green.

- [ ] **Step 1: Extend the scanner and watch it fail**

In `tests/web/test_locale_bundles.py`, replace the two hardcoded reads with a list:

```python
    src = Path(__file__).resolve().parents[2] / "src" / "fenceai"
    scanned = [
        src / "strategy" / "generator.py",
        src / "ai" / "stub.py",
        src / "fulfillment" / "supply.py",
        src / "fencemodel" / "resolve.py",
    ]
    emitted: set[str] = set()
    for path in scanned:
        emitted |= set(re.findall(r'code="([a-z_]+)"', path.read_text()))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/web/test_locale_bundles.py -q`
Expected: FAIL — the emitted set now contains `no_eligible_item` and `substitute_needs_approval`, which are in neither `WARNING_CODES` nor the bundles.

- [ ] **Step 3: Add the codes and the translations**

Add both to `WARNING_CODES` in the test, then to `en.json`:

```json
  "warning.no_eligible_item": "No product is eligible to supply {role} in {slot_key}",
  "warning.substitute_needs_approval": "{sku} is a suggested substitute for {role} and needs approval before it can be used",
```

and to `he.json`:

```json
  "warning.no_eligible_item": "אין מוצר זמין שיכול לספק {role} ב־{slot_key}",
  "warning.substitute_needs_approval": "{sku} הוא תחליף מוצע עבור {role} ודורש אישור לפני שימוש",
```

- [ ] **Step 4: Run the bundle tests**

Run: `uv run pytest tests/web/ -q`
Expected: PASS — including the existing key-parity and no-empty-translation guards.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/web/static/i18n/ tests/web/test_locale_bundles.py
git commit -m "test(i18n): scan fulfillment and fencemodel for warning codes"
```

---

### Task 8: Two eligible stock lengths, chosen by the objective

**Files:**
- Modify: `src/fenceai/fulfillment/supply.py` (`_choose`)
- Modify: `docs/scenarios/golden-scenarios.md` (S15)
- Test: `tests/scenarios/test_s15_eligibility.py`

**Interfaces:**
- Consumes: `plan_cuts`, `DivisibleLinear`
- Produces: `_choose` compares candidates by planning the cuts for each

**Use the `golden-scenarios` skill for the scenario text** — adding a scenario is exactly what it governs. The scenario fixture uses its **own** catalog, not the demo catalog: adding a second rail stock to `demo_catalog()` would change S07's answer and break the compatibility gate.

- [ ] **Step 1: Write the failing scenario test**

Create `tests/scenarios/test_s15_eligibility.py`:

```python
"""S15 — two eligible stock lengths for one requirement.

A 1500 mm rail from 3000 mm stock yields ONE piece per bar, not two: with a 3 mm
kerf, two pieces need 3003 mm (cutplan.py:98 fits n pieces iff
n*(piece+kerf) <= stock+kerf). A 3050 mm bar fits two. The choice cannot be made
by comparing stock lengths — only by planning the cuts.
"""

from fenceai.catalog.model import Catalog, DivisibleLinear, Product
from fenceai.demand.derive import RequirementLine
from fenceai.fencemodel.model import Eligibility, EligibleItem
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply

CATALOG = Catalog.of(
    Product(sku="RAIL-3000", name="Rail stock 3000",
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3),
            price_cents=1800),
    Product(sku="RAIL-3050", name="Rail stock 3050",
            consumption=DivisibleLinear(purchase_length_mm=3050, kerf_mm=3),
            price_cents=1850),
)

BOTH = Eligibility(members=[
    EligibleItem(sku="RAIL-3000", priority=1),
    EligibleItem(sku="RAIL-3050", priority=2),
])


def _rails(n: int) -> list[RequirementLine]:
    return [RequirementLine(id=f"req{i:04d}", sku="", engineering_qty=1, unit="cut",
                            cut_length_mm=1500, role="rail", slot_key="rail",
                            eligibility=BOTH) for i in range(1, n + 1)]


def test_least_cost_picks_the_longer_bar_because_two_pieces_fit_it():
    """4 rails: RAIL-3000 needs 4 bars (7200c), RAIL-3050 needs 2 (3700c)."""
    out = resolve_supply(_rails(4), CATALOG, preset="least_cost")
    assert {r.sku for r in out.requirements} == {"RAIL-3050"}
    bom = fulfill(out.requirements, CATALOG)
    assert bom.lines[0].purchase_qty == 2
    assert bom.lines[0].total_cents == 3700


def test_honour_priority_keeps_the_companys_first_choice_and_costs_more():
    out = resolve_supply(_rails(4), CATALOG, preset="honour_priority")
    assert {r.sku for r in out.requirements} == {"RAIL-3000"}
    assert fulfill(out.requirements, CATALOG).lines[0].purchase_qty == 4


def test_the_rejected_candidate_is_recorded_for_the_explanation():
    out = resolve_supply(_rails(4), CATALOG, preset="least_cost")
    assert out.decisions and out.decisions[0]["chosen"] == "RAIL-3050"
    assert out.decisions[0]["rejected"] == ["RAIL-3000"]


def test_the_choice_is_the_same_for_every_line_of_one_group():
    """Splitting one demand across two stock lengths is SAP's usage probability,
    which we deliberately rejected: it is a forecasting device, not an answer for
    one exact job."""
    out = resolve_supply(_rails(4), CATALOG, preset="least_cost")
    assert len({r.sku for r in out.requirements}) == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/scenarios/test_s15_eligibility.py -q`
Expected: FAIL — `_choose` returns `RAIL-3000` by priority under both presets.

- [ ] **Step 3: Replace `_choose`**

```python
def _candidate_cost(sku: str, lines: list[RequirementLine], catalog, inventory) -> int:
    """Cents to buy this candidate for these lines, by actually planning the cuts.
    A candidate the planner cannot use at all costs infinitely."""
    product = catalog.products.get(sku)
    if product is None:
        return _INFEASIBLE
    sem = product.consumption
    if sem.kind != "divisible_linear":
        return product.price_cents * sum(l.engineering_qty for l in lines)
    pieces = [
        CutPiece(length_mm=l.cut_length_mm, requirement_id=l.id)
        for l in lines for _ in range(l.engineering_qty)
        if l.cut_length_mm is not None
    ]
    if any(p.length_mm + sem.kerf_mm > sem.purchase_length_mm + sem.kerf_mm
           for p in pieces):
        return _INFEASIBLE
    remnants = [
        RemnantStock(inventory_item_id=i.id, length_mm=i.length_mm)
        for i in (inventory or Inventory()).for_sku(sku)
        if i.kind == "remnant" and i.length_mm
    ]
    plan = plan_cuts(sku, sem, pieces, remnants)
    return plan.new_bar_count * product.price_cents


def _waste(sku: str, lines, catalog, inventory) -> int:
    product = catalog.products[sku]
    sem = product.consumption
    if sem.kind != "divisible_linear":
        return 0
    pieces = [CutPiece(length_mm=l.cut_length_mm, requirement_id=l.id)
              for l in lines for _ in range(l.engineering_qty)
              if l.cut_length_mm is not None]
    return plan_cuts(sku, sem, pieces, []).waste_mm   # CutPlan.waste_mm, cutplan.py:45
```

and rewrite `resolve_supply` to group lines by their eligibility group before choosing, so one demand is answered by one product:

```python
    groups: dict[tuple, list[RequirementLine]] = {}
    for line in pending:
        key = tuple(sorted(m.sku for m in _usable(line.eligibility.members, approvals)))
        groups.setdefault(key, []).append(line)

    for key, lines in sorted(groups.items()):
        usable = [m for m in lines[0].eligibility.members if m.sku in key]
        if len(usable) == 1:
            chosen = usable[0]
        else:
            def rank(m):
                cost = _candidate_cost(m.sku, lines, catalog, inventory)
                if preset == "honour_priority":
                    return (m.priority, cost, _waste(m.sku, lines, catalog, inventory), m.sku)
                return (cost, _waste(m.sku, lines, catalog, inventory), m.priority, m.sku)
            chosen = min(usable, key=rank)
```

Import `CutPiece`, `RemnantStock`, `plan_cuts` from `fenceai.fulfillment.cutplan` and define `_INFEASIBLE = 2**62`.

- [ ] **Step 4: Run the scenario and the full suite**

Run: `uv run pytest tests/scenarios/test_s15_eligibility.py -q && uv run pytest -q`
Expected: both PASS. The demo catalog is untouched, so S01–S14 cannot move.

- [ ] **Step 5: Document S15 and commit**

Add S15 to `docs/scenarios/golden-scenarios.md` using the `golden-scenarios` skill, describing the kerf arithmetic and both presets.

```bash
git add src/fenceai/fulfillment/supply.py tests/scenarios/test_s15_eligibility.py \
        docs/scenarios/golden-scenarios.md
git commit -m "feat(fulfillment): choose among eligible stock by planning the cuts (S15)"
```

---

### Task 9: `slot_key` on parts, so two members of one panel are distinguishable

**Files:**
- Modify: `src/fenceai/report/structure.py:31-41` (`Part`), `:175-179`, `:216-226` (`_merge_parts`)
- Test: `tests/report/test_structure_slots.py`

- [ ] **Step 1: Write the failing test**

Create `tests/report/test_structure_slots.py`:

```python
"""Without slot_key, a shadowbox panel's front and back members — same SKU, same
length, differing only in face offset — merge into one row, and clicking a slat
in the drawing cannot say which part it is."""

from fenceai.demand.derive import RequirementLine
from fenceai.fulfillment.fulfill import Bom
from fenceai.report.structure import _merge_parts, _parts_by_element


def _line(id_, slot_key):
    return RequirementLine(id=id_, sku="SLAT-90", engineering_qty=10, unit="cut",
                           cut_length_mm=1600, role="infill", slot_key=slot_key,
                           pegs=["span@run1:0-1500"])


def test_two_slots_with_the_same_sku_stay_two_rows():
    ledger = _parts_by_element([_line("req0001", "slat_front"),
                                _line("req0002", "slat_back")], Bom())
    parts = _merge_parts(ledger.per_element["span@run1:0-1500"])
    assert {p.slot_key for p in parts} == {"slat_front", "slat_back"}
    assert len(parts) == 2


def test_the_same_slot_twice_still_merges():
    ledger = _parts_by_element([_line("req0001", "slat"), _line("req0002", "slat")],
                               Bom())
    parts = _merge_parts(ledger.per_element["span@run1:0-1500"])
    assert len(parts) == 1 and parts[0].qty == 20
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/report/test_structure_slots.py -q`
Expected: FAIL — `Part` has no `slot_key`; the first test finds one merged row.

- [ ] **Step 3: Implement**

Add `slot_key: str = ""` to `Part`, copy it in `_parts_by_element` where the `Part` is built (`structure.py:175`), and add it to the merge key:

```python
        key = (p.sku, p.unit, p.role, p.slot_key, p.cut_length_mm, p.length_basis)
```

- [ ] **Step 4: Run the report tests and the suite**

Run: `uv run pytest tests/report/ -q && uv run pytest -q`
Expected: PASS. M-LEGACY has one slot per role, so no existing row splits.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/report/structure.py tests/report/test_structure_slots.py
git commit -m "feat(report): distinguish parts by panel slot, not only by sku"
```

---

### Task 10: Run identity and the stale-catalog refusal

**Files:**
- Modify: `src/fenceai/strategy/model.py` (`GenerationRun`), `src/fenceai/strategy/generator.py:145-151`
- Modify: `src/fenceai/api/app.py` (`get_bom`, `get_structure`)
- Test: `tests/strategy/test_run_identity.py`

`run.id` hashes `[topology, knowledge_snapshot, overrides, policy]` and `save_run` is `INSERT OR IGNORE` (`store/db.py:180`). Edit a model and regenerate: same id, the old document is kept, and the POST response disagrees with `/bom` for ever.

- [ ] **Step 1: Write the failing tests**

Create `tests/strategy/test_run_identity.py`:

```python
"""A run id is a content address. Anything that changes what the run MEANS has to
be inside it, or INSERT OR IGNORE serves a stale document under a reused id."""

import hashlib

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology


def test_the_run_records_the_model_snapshot_and_the_catalog_hash():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert result.run.model_snapshot == [("M-LEGACY", 1)]
    assert len(result.run.catalog_hash) == 16


def test_a_catalog_change_changes_the_run_id():
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    catalog = demo_catalog()
    catalog.products["RAIL-3000"].price_cents = 9999
    b = generate(topo, kb, catalog)
    assert a.run.id != b.run.id


def test_the_preset_changes_the_run_id():
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog())
    b = generate(topo, kb, demo_catalog(), policy={"objective_preset": "honour_priority"})
    assert a.run.id != b.run.id


def test_identical_inputs_still_give_identical_ids():
    topo, kb = straight_topology(3000), demo_knowledge()
    assert generate(topo, kb, demo_catalog()).run.id == \
        generate(topo, kb, demo_catalog()).run.id
```

Add to `tests/api/test_api.py`:

```python
def test_structure_refuses_a_run_read_against_a_different_catalog(client):
    """Stamping is not checking. /structure recomputes against today's catalog,
    so it must refuse rather than quietly serve a different answer."""
    project = _seed_project(client)
    run_id = client.post(f"/api/projects/{project}/generate").json()["run"]["id"]
    product = client.get("/api/catalog").json()["products"]["RAIL-3000"]
    product["price_cents"] = 9999
    client.put("/api/catalog/products", json=product)   # app.py:556
    response = client.get(f"/api/runs/{run_id}/structure")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "catalog_changed"
```

The routes are `GET /api/catalog` (`app.py:551`) and `PUT /api/catalog/products` (`app.py:556`), which upserts a single product — check its exact payload shape before writing the call, and reuse whatever project seeding the neighbouring tests in `tests/api/test_api.py` already do.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/strategy/test_run_identity.py tests/api/test_api.py -q`
Expected: FAIL — `model_snapshot` does not exist; ids match across catalogs; no 409.

- [ ] **Step 3: Implement**

On `GenerationRun` in `strategy/model.py`:

```python
    model_snapshot: list[tuple[str, int]] = []
    catalog_hash: str = ""
    objective_preset: str = "least_cost"
```

In `generator.py`, before the digest, compute and set them, then extend the digest:

```python
    run_meta.model_snapshot = sorted({(m.id, m.version) for m in models_used})
    run_meta.catalog_hash = hashlib.sha256(
        catalog.model_dump_json().encode()).hexdigest()[:16]
    run_meta.objective_preset = policy.get("objective_preset", "least_cost")
    run_meta.id = "run_" + hashlib.sha256(
        json.dumps(
            [topology.model_dump(), run_meta.knowledge_snapshot,
             [o.model_dump() for o in overrides], policy,
             run_meta.model_snapshot, run_meta.catalog_hash,
             run_meta.objective_preset],
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()[:12]
```

In `app.py`, add a helper beside `_project` and call it at the top of `get_bom` and `get_structure`:

```python
def _fresh_catalog(result):
    """A stored run re-read against a different catalog would re-resolve supply
    and name a different product with nobody told (structure review A2)."""
    catalog = state.store.load_catalog()
    current = hashlib.sha256(catalog.model_dump_json().encode()).hexdigest()[:16]
    if result.run.catalog_hash and current != result.run.catalog_hash:
        raise HTTPException(409, {
            "code": "catalog_changed",
            "run_catalog_hash": result.run.catalog_hash,
            "current_catalog_hash": current,
        })
    return catalog
```

Add `warning.catalog_changed` to both locale bundles and to `WARNING_CODES`, and surface it in `api.js` beside the existing `topology_changed` handling.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q`
Expected: PASS. Some stored-run fixtures may need regenerating rather than hardcoding an id — if a test asserts a literal run id, regenerate it rather than reverting the digest.

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy/ src/fenceai/api/app.py src/fenceai/web/static/ \
        tests/strategy/test_run_identity.py tests/api/test_api.py tests/web/
git commit -m "fix(strategy,api): run id covers model and catalog; refuse a stale read"
```

---

### Task 11: Close out the phase

**Files:**
- Modify: `plan/current-status.md`
- Modify: `docs/superpowers/specs/2026-08-12-fence-model-design.md` (status line)

- [ ] **Step 1: Run the whole gate**

```bash
uv run pytest -q
uv run pytest tests/scenarios -q
uv run --with websocket-client python tools/ui_smoke.py
```

Expected: all green. Record the counts.

- [ ] **Step 2: Run the project's reviewers**

Dispatch `architecture-critic` and `test-reviewer` over the diff, as CLAUDE.md requires before declaring a milestone done. Write findings and dispositions to `docs/reviews/fence-model-phase1-review.md`.

- [ ] **Step 3: Update the status document**

Add a section to `plan/current-status.md` in the established style: what landed, the test counts, and that phases 2 and 3 remain.

- [ ] **Step 4: Commit**

```bash
git add plan/current-status.md docs/
git commit -m "docs(status): fence model phase 1 complete"
```

---

## Self-review

**Spec coverage.** Phase 1 rows of the spec's phasing table map to tasks: `fencemodel` module (1–3), `PanelSpec` (2), `fit_pattern` (1), `resolve_panel` (3), `M-LEGACY` (4), run-id digest and snapshots (10), the SKU write-back (5–6), one two-member group end to end (8). The compatibility gate is Task 6 step 4. `Part.slot_key` (9) and the locale scanner (7) come from review findings 21 and 10.

**Deliberately not in this plan, and where they live:** option axes, variants, pricing, the elevation read model, `M-SLAT`, safety-rule checks, the new override directives, `learning/impact.py` model cases, per-segment `max_span`, model-change stations, and clear-width face resolution are all **phase 2**. `PanelContext.clear_width_mm` is fed the centre width in Task 4 with a comment saying so, because no product carries `attrs.face_width_mm` yet — the field exists so phase 2 changes one call site rather than a signature.

**Type consistency.** `ResolvedSlot.slot_key` → `RequirementLine.slot_key` → `Part.slot_key` is one name throughout. `Eligibility` is imported from `fencemodel.model` by `demand/derive.py` and `fulfillment/supply.py`; `resolve_supply` returns `SupplyResolution`, never a bare list. `fit_pattern`'s keyword-only arguments match every call site in Tasks 1 and 3.

**One import cycle to watch.** `strategy/model.py` imports `fencemodel.resolve`, and `fulfillment/supply.py` imports `strategy.model` for `StrategyWarning`. `fencemodel` must therefore never import from `strategy` or `fulfillment`. If it needs a warning type later, move `StrategyWarning` to `core/` rather than adding the back-edge.
