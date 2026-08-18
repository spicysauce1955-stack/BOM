# Part Library — Slice 1A (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a part a named, versioned, shared library entity that a panel slot
references by id, with an item eligible for it when the two agree field by field —
with every golden scenario producing a byte-identical result.

**Architecture:** A new `fenceai/parts/` package owns the entity, the compilation of
its authored spec into the existing `Expr` AST, and its validation. A model's slot
carries `part_id`; one function resolves a whole `FenceModel`'s part references into
the `Eligibility.predicate` field that already exists, so the existing matcher, the
freezing of members, `resolve_supply`, `fulfill()` and the decision graph are all
untouched. Compilation is strictly upstream of `match_spec`, so no resolution order
moves.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite (stdlib `sqlite3`), pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-08-18-part-library-design.md`

## Global Constraints

Copied from the spec and CLAUDE.md; every task's requirements implicitly include these.

- **Integer millimetres and cents at rest; float only transient** (ADR-0002). The two
  named tolerances live in `fenceai/core/units.py`; do not add a third.
- **One rule language, one evaluator** (ADR-0005). A part's spec compiles to the owned
  `Expr` AST in `fenceai/knowledge/ast.py` and is evaluated by `evaluate_expr`. Do not
  write a second matcher, and do not add an AST node.
- **No resolution reordering.** Compilation happens before `match_spec`. The
  `height → rail positions → post → clear width → infill` DAG must not move. If a task
  seems to require reordering `strategy/generator.py`, stop and report it.
- **Read models are derived, never stored.** `Part.dimensions` is a property over
  `Part.spec`, never a stored field.
- **Data read by CODE is typed and named; data read by a predicate stays open.**
  `width_mm` and `thickness_mm` are the two keys code knows by name.
- **A `MissingField` is a NO.** `_covers` already reads an item that cannot answer as
  not having covered the requirement. Do not change this.
- **Versions are immutable; only `status` mutates.** Drafts are the one exception and
  may be rewritten in place.
- **Every user-visible warning carries `code + params`**; the English `message` is
  fallback only. A new code needs entries in BOTH `he.json` and `en.json` or
  `tests/web/test_locale_bundles.py` fails. (1A adds codes; 1B adds the surfaces.)
- **The acceptance gate is byte-identical.** `uv run pytest tests/scenarios -q` must
  produce identical BOMs, decision graphs and run digests before and after this plan.
  Anything that moves is a bug in this work, not a new behaviour.

**Out of scope for 1A** (slice 1B): `/api/parts` routes, the eligibility-preview
endpoint, the Parts tab, `parts.js` / `part-editor.js`, and any change to
`panel-inspector.js` or the canvas.

---

### Task 1: The Part entity

**Files:**
- Create: `src/fenceai/parts/__init__.py` (empty)
- Create: `src/fenceai/parts/model.py`
- Test: `tests/parts/__init__.py` (empty), `tests/parts/test_model.py`

**Interfaces:**
- Consumes: `fenceai.core.units.Mm`
- Produces: `SpecField`, `Agree`, `Part`, `PartType`, `PartLibrary`, `is_dimension(f)`,
  `Part.dimensions -> dict[str, Mm]`, `Part.ref -> str`, `Part.display_name(lang)`

- [ ] **Step 1: Write the failing test**

```python
# tests/parts/test_model.py
"""A part declares what it is; a dimension is what falls out when three fields line up."""

import pytest
from pydantic import ValidationError

from fenceai.parts.model import Part, PartType, SpecField, is_dimension


def rail() -> Part:
    return Part(
        id="rail-38-vinyl", version=1, type="rail",
        name_i18n={"en": "38mm vinyl rail", "he": "שלב ויניל 38 מ\"מ"},
        spec=[
            SpecField(key="width_mm", value=38, agree="==", unit="mm"),
            SpecField(key="thickness_mm", value=20, agree="==", unit="mm"),
            SpecField(key="face_width_mm", value=90, agree=">=", unit="mm"),
            SpecField(key="length_mm", agree="supplies", unit="mm"),
            SpecField(key="material", value="vinyl", agree="=="),
        ],
    )


def test_a_dimension_is_mm_plus_equality_plus_a_scalar():
    fields = {f.key: f for f in rail().spec}
    assert is_dimension(fields["width_mm"])
    # a floor on the item is not a dimension of the part — the part has no face width
    assert not is_dimension(fields["face_width_mm"])
    # no value at all; the bay resolves the length
    assert not is_dimension(fields["length_mm"])
    # not a measurement
    assert not is_dimension(fields["material"])


def test_dimensions_is_derived_and_carries_only_the_equalities():
    assert rail().dimensions == {"width_mm": 38, "thickness_mm": 20}


def test_the_two_keys_code_knows_by_name_have_typed_doors():
    assert rail().width_mm == 38
    assert rail().thickness_mm == 20


def test_an_undeclared_dimension_is_none_not_zero():
    """Zero is a measurement; None is 'nobody recorded it'. The elevation draws
    declared=False for the second and a real band for the first."""
    bare = Part(id="p", version=1, type="rail", spec=[])
    assert bare.width_mm is None
    assert bare.thickness_mm is None


def test_supplies_may_not_carry_a_value():
    """A part cannot declare its length: the same rail serves a 2400 bay and an
    1800 one, so the number is the slot's, not the part's."""
    with pytest.raises(ValidationError, match="supplies"):
        SpecField(key="length_mm", value=1800, agree="supplies", unit="mm")


def test_supplies_requires_a_millimetre_field():
    with pytest.raises(ValidationError, match="unit"):
        SpecField(key="material", agree="supplies")


def test_every_agreement_except_supplies_requires_a_value():
    with pytest.raises(ValidationError, match="value"):
        SpecField(key="width_mm", agree="==", unit="mm")


def test_between_takes_two_ints():
    ok = SpecField(key="width_mm", value=[36, 40], agree="between", unit="mm")
    assert ok.value == [36, 40]
    with pytest.raises(ValidationError, match="between"):
        SpecField(key="width_mm", value=[36], agree="between", unit="mm")


def test_ref_and_display_name():
    assert rail().ref == "rail-38-vinyl@v1"
    assert rail().display_name("he").startswith("שלב")
    assert rail().display_name("fr") == rail().name_i18n["en"]


def test_part_type_carries_a_localised_label():
    t = PartType(key="rail", label_i18n={"en": "Rails", "he": "שלבים"})
    assert t.label("he") == "שלבים"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/parts/test_model.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.parts'`

- [ ] **Step 3: Write the implementation**

```python
# src/fenceai/parts/model.py
"""Parts: a named, versioned, SHARED declaration of what a piece is.

Immutable versions like knowledge objects and fence models (ADR-0006): a run stamps
the part versions it resolved, so editing a part cannot change what an old run meant.

A model names a part by id and NOT by version, which is the whole reason the entity
is shared rather than copied — fixing a rail spec once has to reach every model that
names it. The price is stated in the design doc §2.1 and paid by the impact preview:
an ACTIVE model version no longer means one fixed thing forever.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from fenceai.core.units import Mm

# How an ITEM's declared value must relate to the part's. Authored per part rather
# than derived from the field name (that would put the matching vocabulary in Python,
# which `match.py` refuses) and rather than declared by the type (that would make the
# type a schema and force a release for a company with an unusual dimension). The
# cost, accepted knowingly: two rails may disagree about what `width` means.
Agree = Literal["==", "!=", ">=", "<=", "supplies", "covers", "among", "between"]

# The agreements whose value is a SET the part declares, not a scalar.
_LIST_VALUED = frozenset({"among", "between"})

# The two keys code knows by name. Everything else is matched and never drawn — the
# rule `Capabilities` already states: data read by CODE is typed and named, data read
# by a predicate stays open.
DRAWN_KEYS = ("width_mm", "thickness_mm")


class SpecField(BaseModel):
    """One declared fact, and how an item must agree with it.

    Reads left to right as a sentence about the ITEM: `item.<key> <agree> <value>`.
    One direction always, because the alternative is an editor where half the rows are
    read forwards and half backwards and the author has to remember which side they
    are standing on.
    """

    key: str
    value: int | str | bool | list[int] | list[str] | None = None
    agree: Agree = "=="
    unit: Literal["mm"] | None = None

    @model_validator(mode="after")
    def _value_matches_agreement(self) -> "SpecField":
        if self.agree == "supplies":
            # A part cannot declare its length. The same rail part serves a 2400 bay
            # and an 1800 one: length is the slot's `length_rule` answering per bay,
            # not a fact about the part. The number is also unavailable when matching
            # runs, so a literal here would be evaluated against the wrong one.
            if self.value is not None:
                raise ValueError(
                    f"{self.key}: `supplies` carries no value — a part cannot declare "
                    "its length, the bay resolves it"
                )
            if self.unit != "mm":
                raise ValueError(f"{self.key}: `supplies` needs unit='mm'")
            return self
        if self.value is None:
            raise ValueError(f"{self.key}: {self.agree} needs a value")
        if self.agree == "between":
            if (not isinstance(self.value, list) or len(self.value) != 2
                    or not all(isinstance(v, int) for v in self.value)):
                raise ValueError(f"{self.key}: `between` takes exactly two ints")
        return self


def is_dimension(f: SpecField) -> bool:
    """A dimension is not a type — it is what falls out when three fields line up.

    `unit` says the value is a measurement rather than a token. `agree` says whether
    the part's number and the item's number are the SAME number: under `==` they are,
    so "the part's width" is well defined; under `>=` or `between` it is not, because
    those are floors and ranges on the item and the part has no such dimension of its
    own. `key` says which measurement, and is the only part code knows by name.
    """
    return f.unit == "mm" and f.agree == "==" and isinstance(f.value, int)


class PartType(BaseModel):
    """The filing vocabulary, shared by parts and products.

    An entity rather than a bare string because "rails" needs a Hebrew label and a
    free string has nowhere to put one; data rather than a Python enum because a
    company that stocks a new kind of thing adds a row, not a release.
    """

    key: str
    label_i18n: dict[str, str] = {}

    def label(self, lang: str) -> str:
        return self.label_i18n.get(lang) or self.label_i18n.get("en") or self.key


class Part(BaseModel):
    id: str
    version: int
    status: Literal["draft", "active", "retired"] = "active"
    type: str
    name_i18n: dict[str, str] = {}
    spec: list[SpecField] = []

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"

    def display_name(self, lang: str) -> str:
        return self.name_i18n.get(lang) or self.name_i18n.get("en") or self.id

    @property
    def dimensions(self) -> dict[str, Mm]:
        """Derived, never stored (CLAUDE.md: read models are derived).

        A stored dimension beside the spec field producing it would be two
        authorities over one number and eventually two answers — the exact defect
        having the width on the slot AND a sku on the slot used to be.
        """
        return {f.key: f.value for f in self.spec if is_dimension(f)}

    @property
    def width_mm(self) -> Mm | None:
        return self.dimensions.get("width_mm")

    @property
    def thickness_mm(self) -> Mm | None:
        return self.dimensions.get("thickness_mm")


class PartLibrary(BaseModel):
    parts: list[Part] = []

    def latest_active(self, part_id: str) -> Part | None:
        found = [p for p in self.parts if p.id == part_id and p.status == "active"]
        return max(found, key=lambda p: p.version) if found else None

    def by_ref(self, part_id: str, version: int) -> Part | None:
        for p in self.parts:
            if p.id == part_id and p.version == version:
                return p
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/parts/test_model.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/parts tests/parts
git commit -m "feat(parts): a part declares what it is, and a dimension is derived

A dimension is not a type. It is what falls out when unit is mm, the
agreement is equality, and the value is a scalar — the only arrangement
where the number drawn and the number matched cannot disagree."
```

---

### Task 2: Compiling a spec into the owned AST

**Files:**
- Create: `src/fenceai/parts/compile.py`
- Test: `tests/parts/test_compile.py`

**Interfaces:**
- Consumes: `Part`, `SpecField` (Task 1); `fenceai.knowledge.ast` — `And`, `Cmp`,
  `FieldRef`, `Lit`, `In`, `Between`, `FnCall`, `Expr`
- Produces: `compile_spec(part: Part) -> Expr`, `compile_field(f: SpecField) -> Expr`

- [ ] **Step 1: Write the failing test**

```python
# tests/parts/test_compile.py
"""Every agreement pins its emitted Expr. A new agreement without a row here is a
missing test, visibly."""

import pytest

from fenceai.knowledge.ast import And, Between, Cmp, FieldRef, FnCall, In, Lit
from fenceai.parts.compile import compile_field, compile_spec
from fenceai.parts.model import Part, SpecField


def f(**kw) -> SpecField:
    return SpecField(**kw)


CASES = [
    (f(key="width_mm", value=38, agree="==", unit="mm"),
     Cmp(cmp="==", left=FieldRef(path="item.width_mm"), right=Lit(value=38))),
    (f(key="material", value="vinyl", agree="!="),
     Cmp(cmp="!=", left=FieldRef(path="item.material"), right=Lit(value="vinyl"))),
    (f(key="face_width_mm", value=90, agree=">=", unit="mm"),
     Cmp(cmp=">=", left=FieldRef(path="item.face_width_mm"), right=Lit(value=90))),
    (f(key="face_width_mm", value=90, agree="<=", unit="mm"),
     Cmp(cmp="<=", left=FieldRef(path="item.face_width_mm"), right=Lit(value=90))),
    (f(key="length_mm", agree="supplies", unit="mm"),
     Cmp(cmp=">=", left=FieldRef(path="item.stock_length_mm"), right=Lit(value=0))),
    (f(key="interface", value="vinyl-routed-5x5", agree="covers"),
     FnCall(name="covers", args=[FieldRef(path="item.interface"),
                                 Lit(value="vinyl-routed-5x5")])),
    (f(key="sku", value=["RAIL-3000", "RAIL-2400"], agree="among"),
     In(item=FieldRef(path="item.sku"), options=["RAIL-3000", "RAIL-2400"])),
    (f(key="width_mm", value=[36, 40], agree="between", unit="mm"),
     Between(item=FieldRef(path="item.width_mm"), low=36, high=40)),
]


@pytest.mark.parametrize("field,expected", CASES, ids=[c[0].agree for c in CASES])
def test_each_agreement_compiles_to_its_term(field, expected):
    assert compile_field(field) == expected


def test_every_agreement_value_has_a_case():
    """The table above must cover the whole vocabulary, or a new operator ships
    compiled by nothing and silently matching everything."""
    from typing import get_args
    from fenceai.parts.model import Agree
    assert {c[0].agree for c in CASES} == set(get_args(Agree))


def test_supplies_is_the_missing_field_check_not_a_disjunction():
    """`stock_length_mm` is defined for BOTH consumption kinds, so one term does it:
    an item declaring neither a purchase length nor a capability length has no such
    key, `lookup` raises MissingField, and `_covers` reads that as not covered."""
    term = compile_field(f(key="length_mm", agree="supplies", unit="mm"))
    assert isinstance(term, Cmp) and term.left.path == "item.stock_length_mm"


def test_a_whole_spec_is_a_conjunction_in_authored_order():
    part = Part(id="p", version=1, type="rail", spec=[
        f(key="type", value="rail", agree="=="),
        f(key="width_mm", value=38, agree="==", unit="mm"),
    ])
    expr = compile_spec(part)
    assert isinstance(expr, And)
    assert [t.left.path for t in expr.items] == ["item.type", "item.width_mm"]


def test_sole_excluding_term_can_still_name_the_one_term_that_excluded_everybody():
    """The conjunction is not incidental. `sole_excluding_term` only diagnoses an And
    of two or more terms, and losing that shape would turn 'your posts are punched
    300mm from where this bay wants its rails' back into a bare 'no match'."""
    from fenceai.catalog.model import Catalog, DivisibleLinear, Product
    from fenceai.fencemodel.match import sole_excluding_term

    catalog = Catalog.of(Product(
        sku="RAIL-3000", name="Rail",
        consumption=DivisibleLinear(purchase_length_mm=3000),
        attrs={"type": "rail", "width_mm": 45}))
    part = Part(id="p", version=1, type="rail", spec=[
        f(key="type", value="rail", agree="=="),
        f(key="width_mm", value=38, agree="==", unit="mm"),
    ])
    found = sole_excluding_term(compile_spec(part), catalog, {})
    assert found is not None
    term, near_misses = found
    assert term.left.path == "item.width_mm"
    assert near_misses == ["RAIL-3000"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/parts/test_compile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.parts.compile'`

- [ ] **Step 3: Write the implementation**

```python
# src/fenceai/parts/compile.py
"""A part's authored spec, as the owned Expr AST.

Authoring sugar, not a second rule engine (ADR-0005). Everything here emits nodes
`knowledge/ast.py` already defines and `evaluate_expr` already evaluates, and the
result is a CONJUNCTION of simple terms — which is not incidental: it is the shape
`sole_excluding_term` needs to name the one term that excluded everybody.
"""

from __future__ import annotations

from fenceai.knowledge.ast import And, Between, Cmp, Expr, FieldRef, FnCall, In, Lit
from fenceai.parts.model import Part, SpecField


def compile_spec(part: Part) -> Expr:
    return And(items=[compile_field(f) for f in part.spec])


def compile_field(f: SpecField) -> Expr:
    path = f"item.{f.key}"
    if f.agree == "supplies":
        # ONE term, not a disjunction over consumption kinds: `stock_length_mm` is
        # defined for both (see match._item_ctx). An item declaring neither a
        # purchase length nor a capability length has no such key, `lookup` raises
        # MissingField, and `_covers` reads that as "has not covered the
        # requirement". The comparison IS the null check, through the mechanism the
        # matcher already relies on rather than a second one.
        return Cmp(cmp=">=", left=FieldRef(path="item.stock_length_mm"), right=Lit(value=0))
    if f.agree == "covers":
        # The ITEM's declared set must include everything the part declares. The
        # other side is computed, which is exactly why `In` cannot express it —
        # `In.options` is a literal list — and why this is the function seam's first
        # real user.
        return FnCall(name="covers", args=[FieldRef(path=path), Lit(value=f.value)])
    if f.agree == "among":
        # The mirror: the ITEM's value is one of the ones the PART lists. `In`
        # already holds a computed item against a literal options list, so this
        # needs no machinery at all.
        return In(item=FieldRef(path=path), options=list(f.value))
    if f.agree == "between":
        low, high = f.value
        return Between(item=FieldRef(path=path), low=low, high=high)
    return Cmp(cmp=f.agree, left=FieldRef(path=path), right=Lit(value=f.value))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/parts/test_compile.py -q`
Expected: PASS, 12 tests

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/parts/compile.py tests/parts/test_compile.py
git commit -m "feat(parts): a spec compiles to the owned AST, as a conjunction

The conjunction is not incidental — it is the shape sole_excluding_term
needs to say which single term excluded everybody."
```

---

### Task 3: `covers`, and `stock_length_mm` as one definition

**Files:**
- Modify: `src/fenceai/fencemodel/match.py` (`_RESERVED`, `_item_ctx`, new `covers`)
- Modify: `src/fenceai/fencemodel/model.py:354` (`_can_supply_length`)
- Test: `tests/fencemodel/test_match.py` (append)

**Interfaces:**
- Consumes: `fenceai.knowledge.ast.register_function`; `catalog.model.DivisibleLinear`
- Produces: registered function `covers(item_value, part_value, *, ctx) -> bool`;
  `match.stock_length_mm(product) -> Mm | None`; `item.stock_length_mm` in the
  predicate context

- [ ] **Step 1: Write the failing test**

```python
# tests/fencemodel/test_match.py  (append to the file)

from fenceai.catalog.model import (
    Capabilities, Catalog, DivisibleLinear, IndivisibleDiscrete, PackagedDiscrete,
    Product,
)
from fenceai.knowledge.ast import FUNCTIONS, FieldRef, FnCall, Lit, MissingField, evaluate_expr
from fenceai.fencemodel.match import _item_ctx, stock_length_mm
from fenceai.fencemodel.model import _can_supply_length


def _bar(sku="BAR", length=3000):
    return Product(sku=sku, name=sku,
                   consumption=DivisibleLinear(purchase_length_mm=length))


def _fixed(sku="POST", length=2400):
    return Product(sku=sku, name=sku, consumption=IndivisibleDiscrete(),
                   capabilities=Capabilities(length_mm=length))


def _box(sku="SCREW"):
    return Product(sku=sku, name=sku,
                   consumption=PackagedDiscrete(qty_per_package=100))


def test_stock_length_reads_bar_stock_from_its_consumption():
    assert stock_length_mm(_bar(length=3000)) == 3000


def test_stock_length_reads_a_fixed_piece_from_its_capability():
    assert stock_length_mm(_fixed(length=2400)) == 2400


def test_an_item_with_no_length_anywhere_has_none():
    assert stock_length_mm(_box()) is None


def test_stock_length_and_can_supply_length_cannot_drift():
    """Two definitions of 'how long a piece can you get' would disagree the moment
    either moved. `_can_supply_length` is now expressed in terms of this one."""
    catalog = Catalog.of(_bar(), _fixed(), _box())
    for sku in catalog.products:
        assert _can_supply_length(catalog, sku) == (
            stock_length_mm(catalog.products[sku]) is not None)


def test_stock_length_reaches_a_predicate():
    assert _item_ctx(_bar(length=3000))["stock_length_mm"] == 3000


def test_an_item_without_one_omits_the_key_rather_than_passing_none():
    """A None would compare as a value and quietly satisfy `>= 0`. Absence raises
    MissingField, which `_covers` reads as 'has not covered the requirement'."""
    assert "stock_length_mm" not in _item_ctx(_box())


def test_supplies_admits_bar_stock_and_fixed_pieces_and_refuses_a_box():
    from fenceai.parts.compile import compile_field
    from fenceai.parts.model import SpecField
    term = compile_field(SpecField(key="length_mm", agree="supplies", unit="mm"))
    assert evaluate_expr(term, {"item": _item_ctx(_bar())}) is True
    assert evaluate_expr(term, {"item": _item_ctx(_fixed())}) is True
    with pytest.raises(MissingField):
        evaluate_expr(term, {"item": _item_ctx(_box())})


def test_covers_is_registered():
    assert "covers" in FUNCTIONS


def test_covers_accepts_a_scalar_inside_the_items_list():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"interface": ["vinyl-routed-5x5", "vinyl-routed-4x4"]})
    term = FnCall(name="covers", args=[FieldRef(path="item.interface"),
                                       Lit(value="vinyl-routed-5x5")])
    assert evaluate_expr(term, {"item": _item_ctx(item)}) is True


def test_covers_refuses_a_token_the_item_does_not_declare():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"interface": ["vinyl-routed-4x4"]})
    term = FnCall(name="covers", args=[FieldRef(path="item.interface"),
                                       Lit(value="vinyl-routed-5x5")])
    assert evaluate_expr(term, {"item": _item_ctx(item)}) is False


def test_covers_needs_every_one_of_the_parts_values():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"routed_at": [150, 900, 1650]})
    ok = FnCall(name="covers", args=[FieldRef(path="item.routed_at"),
                                     Lit(value=[150, 1650])])
    no = FnCall(name="covers", args=[FieldRef(path="item.routed_at"),
                                     Lit(value=[150, 1700])])
    assert evaluate_expr(ok, {"item": _item_ctx(item)}) is True
    assert evaluate_expr(no, {"item": _item_ctx(item)}) is False


def test_covers_treats_a_scalar_item_value_as_a_one_element_set():
    item = Product(sku="P", name="P", consumption=IndivisibleDiscrete(),
                   attrs={"material": "vinyl"})
    term = FnCall(name="covers", args=[FieldRef(path="item.material"),
                                       Lit(value="vinyl")])
    assert evaluate_expr(term, {"item": _item_ctx(item)}) is True


def test_field_paths_sees_through_a_function_call():
    """`validate_model` refuses a post predicate that reads outside its allowed set,
    and it asks `field_paths`. A read hidden inside an args list would slip past."""
    from fenceai.knowledge.ast import field_paths
    term = FnCall(name="covers", args=[FieldRef(path="item.interface"), Lit(value="x")])
    assert field_paths(term) == {"item.interface"}


def test_an_unregistered_function_raises_rather_than_passing():
    with pytest.raises(MissingField):
        evaluate_expr(FnCall(name="nope", args=[]), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fencemodel/test_match.py -q`
Expected: FAIL — `ImportError: cannot import name 'stock_length_mm'`

- [ ] **Step 3: Write the implementation**

In `src/fenceai/fencemodel/match.py`, add the import and the two additions:

```python
from fenceai.catalog.model import Catalog, DivisibleLinear
from fenceai.core.units import Mm
from fenceai.knowledge.ast import (
    And, MissingField, evaluate_expr, lookup, register_function,
)

# ... existing _RESERVED comment stays; extend the tuple:
_RESERVED = ("sku", "consumption", "stock_length_mm")


def stock_length_mm(product) -> Mm | None:
    """How long a piece can you get from ONE purchase unit — the single definition.

    Bar stock carries it on its consumption (`purchase_length_mm`); a fixed piece
    carries it as a capability. Before this, neither was reachable by a predicate —
    `_item_ctx` merged attrs, capabilities, sku and consumption KIND, so a bar's
    length was invisible — while `_can_supply_length` reached into the consumption
    object for it. Two definitions of one fact would disagree the moment either
    moved, so `_can_supply_length` is now expressed in terms of this one.

    None means "declares no length anywhere", and `_item_ctx` OMITS the key rather
    than passing None: a None would compare as a value and quietly satisfy `>= 0`.
    """
    if isinstance(product.consumption, DivisibleLinear):
        return product.consumption.purchase_length_mm
    return product.capabilities.length_mm


@register_function("covers")
def _covers_fn(item_value, part_value, *, ctx=None) -> bool:
    """The ITEM's declared set includes everything the PART declares.

    A scalar on either side is a one-element set, which is what lets one operator
    serve "my token is among yours" and "your holes include mine" without the author
    telling them apart. Its mirror — the item's value is one of the ones the part
    lists — is `among`, and that one compiles to `In` because there the computed side
    is the item. Two operators, because neither subsumes the other: `covers` asks
    about a set the ITEM declares, `among` about a set the PART declares.
    """
    have = set(item_value) if isinstance(item_value, list) else {item_value}
    need = set(part_value) if isinstance(part_value, list) else {part_value}
    return need <= have


def _item_ctx(product) -> dict:
    # ... existing docstring stays ...
    declared = {k: v for k, v in product.capabilities.model_dump().items()
                if v is not None}
    ctx = {**product.attrs, **declared, "sku": product.sku,
           "consumption": product.consumption.kind}
    length = stock_length_mm(product)
    if length is not None:
        ctx["stock_length_mm"] = length
    return ctx
```

In `src/fenceai/fencemodel/model.py`, replace `_can_supply_length`'s body:

```python
def _can_supply_length(catalog: Catalog, sku: str) -> bool:
    from fenceai.fencemodel.match import stock_length_mm
    product = catalog.products.get(sku)
    return product is not None and stock_length_mm(product) is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fencemodel/ tests/parts/ -q`
Expected: PASS — the new tests plus every existing `test_match.py` test unchanged

- [ ] **Step 5: Run the full suite — this task touches a shared context**

Run: `uv run pytest -q`
Expected: PASS, no regressions. `_item_ctx` gained a key, so any predicate reading
`item.*` sees one more name; nothing existing reads `stock_length_mm`.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/fencemodel/match.py src/fenceai/fencemodel/model.py tests/fencemodel/test_match.py
git commit -m "feat(match): one definition of stock length, and covers as the first registered fn

_can_supply_length reached into a consumption object for a number no
predicate could see. Now there is one answer to 'how long a piece can you
get', and _can_supply_length is expressed in terms of it."
```

---

### Task 4: `validate_part`

**Files:**
- Create: `src/fenceai/parts/validate.py`
- Test: `tests/parts/test_validate.py`

**Interfaces:**
- Consumes: `Part`, `SpecField` (Task 1); `compile_spec` (Task 2); `Catalog`;
  `match._covers` (Task 3)
- Produces: `validate_part(part: Part, catalog: Catalog) -> list[str]`,
  `matching_skus(part: Part, catalog: Catalog, facts: dict | None = None) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/parts/test_validate.py
"""A published part is refused for the same reasons a slot with no eligible product
is refused: at authoring time, when the author can still say what belongs there."""

from fenceai.catalog.model import Capabilities, Catalog, DivisibleLinear, IndivisibleDiscrete, Product
from fenceai.parts.model import Part, SpecField
from fenceai.parts.validate import matching_skus, validate_part


def catalog() -> Catalog:
    return Catalog.of(
        Product(sku="RAIL-3000", name="Rail 3000",
                consumption=DivisibleLinear(purchase_length_mm=3000),
                attrs={"width_mm": 38, "material": "vinyl", "type": "rail"}),
        Product(sku="RAIL-2400", name="Rail 2400",
                consumption=DivisibleLinear(purchase_length_mm=2400),
                attrs={"width_mm": 38, "material": "steel", "type": "rail"}),
        Product(sku="POST-V", name="Post vinyl", consumption=IndivisibleDiscrete(),
                capabilities=Capabilities(length_mm=2400, face_width_mm=127),
                attrs={"material": "vinyl", "type": "post"}),
    )


def part(*spec, status="active") -> Part:
    return Part(id="p", version=1, type="rail", status=status, spec=list(spec))


def test_a_part_whose_spec_matches_a_product_is_accepted():
    p = part(SpecField(key="width_mm", value=38, agree="==", unit="mm"),
             SpecField(key="material", value="vinyl", agree="=="))
    assert validate_part(p, catalog()) == []


def test_a_published_part_matching_nothing_is_refused():
    p = part(SpecField(key="width_mm", value=99, agree="==", unit="mm"))
    errors = validate_part(p, catalog())
    assert any("no product" in e for e in errors)


def test_a_draft_may_match_nothing():
    """The draft bargain: an author writes the spec before the item exists."""
    p = part(SpecField(key="width_mm", value=99, agree="==", unit="mm"), status="draft")
    assert validate_part(p, catalog()) == []


def test_a_duplicate_key_is_refused():
    """Two authorities over one field: it would draw one number and buy another."""
    p = part(SpecField(key="width_mm", value=38, agree="==", unit="mm"),
             SpecField(key="width_mm", value=40, agree=">=", unit="mm"))
    assert any("width_mm" in e and "twice" in e for e in validate_part(p, catalog()))


def test_a_published_part_with_an_empty_spec_is_refused():
    """An empty conjunction is `all([])` — true for every product in the catalog.
    A part that matches everything is not a specification."""
    assert any("empty" in e for e in validate_part(part(), catalog()))


def test_matching_skus_is_sorted_and_narrows_as_terms_are_added():
    c = catalog()
    wide = part(SpecField(key="type", value="rail", agree="=="))
    assert matching_skus(wide, c) == ["RAIL-2400", "RAIL-3000"]
    narrow = part(SpecField(key="type", value="rail", agree="=="),
                  SpecField(key="material", value="vinyl", agree="=="))
    assert matching_skus(narrow, c) == ["RAIL-3000"]


def test_a_missing_field_is_a_no_not_a_pass():
    """POST-V declares no width_mm. It must not be swept into a slot that asked."""
    p = part(SpecField(key="width_mm", value=38, agree="==", unit="mm"))
    assert "POST-V" not in matching_skus(p, catalog())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/parts/test_validate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.parts.validate'`

- [ ] **Step 3: Write the implementation**

```python
# src/fenceai/parts/validate.py
"""Refusals a part earns at authoring time.

The same guardrail `validate_model` already applies to a slot with no eligible
product, at the same moment and for the same reason: a part that publishes cleanly
and then reports `no_eligible_item` on every bay of every job built to it has told
the author nothing, at the one moment they could still have fixed it.
"""

from __future__ import annotations

from collections import Counter

from fenceai.catalog.model import Catalog
from fenceai.fencemodel.match import _covers
from fenceai.parts.compile import compile_spec
from fenceai.parts.model import Part


def matching_skus(part: Part, catalog: Catalog, facts: dict | None = None) -> list[str]:
    """Which products this part's spec admits, sorted by SKU.

    Sorted because `resolve_supply` groups by the members' (sku, priority, approval)
    signature and grouping decides which product is chosen — cut planning is not
    additive — so a varying order would change the answer and not merely the JSON.
    """
    predicate = compile_spec(part)
    return [sku for sku in sorted(catalog.products)
            if _covers(predicate, catalog.products[sku], facts or {})]


def validate_part(part: Part, catalog: Catalog) -> list[str]:
    errors: list[str] = []

    duplicates = [k for k, n in Counter(f.key for f in part.spec).items() if n > 1]
    for key in sorted(duplicates):
        errors.append(
            f"{part.ref}: {key!r} is declared twice — two authorities over one field, "
            "so the part would draw one number and buy another"
        )

    if part.status == "draft":
        # A draft may hold anything. That is what lets an author write a spec before
        # the item exists, and it is the same bargain a draft model already has.
        return errors

    if not part.spec:
        errors.append(
            f"{part.ref}: the spec is empty, which is a conjunction of nothing and "
            "therefore true of every product — a part that matches everything is not "
            "a specification"
        )
        return errors

    if not matching_skus(part, catalog):
        errors.append(
            f"{part.ref}: no product in the catalog covers this spec, so every slot "
            "naming it would report no_eligible_item on every bay of every job"
        )
    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/parts/ -q`
Expected: PASS, 8 new tests

- [ ] **Step 5: Add the locale entries for the codes this slice emits**

Spec §10 lists seven codes. 1A emits four; the other three are surfaces 1B builds.
Add to BOTH `src/fenceai/web/static/i18n/en.json` and `he.json`, or
`tests/web/test_locale_bundles.py` fails on the next run:

```
warning.part_spec_matches_nothing
warning.part_has_no_active_version
warning.part_still_referenced
warning.part_dimension_conflict
```

The English string is fallback only; write a real Hebrew string, not a copy of the
English one. Keep the `{part_id}` / `{model_ids}` / `{key}` params identical in both
bundles — the test pins the key sets equal, and a param present in one language and
absent in the other renders a brace to a user.

- [ ] **Step 6: Run the locale test**

Run: `uv run pytest tests/web/test_locale_bundles.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/parts/validate.py tests/parts/test_validate.py src/fenceai/web/static/i18n/
git commit -m "feat(parts): refuse a published part nothing can fill, at authoring time"
```

---

### Task 5: Persistence

**Files:**
- Modify: `src/fenceai/store/db.py` (`_SCHEMA`, new methods after the fence-model block)
- Test: `tests/store/test_parts_store.py`

**Interfaces:**
- Consumes: `Part`, `PartLibrary` (Task 1)
- Produces: `Store.save_part(part, actor="system")`,
  `Store.load_part(part_id, version) -> Part | None`,
  `Store.part_library() -> PartLibrary`,
  `Store.set_part_status(part_id, version, status, actor="system")`,
  `Store.next_part_version(part_id) -> int`

**Dependency note:** the retirement-while-referenced refusal is written here but
TESTED in Task 6, because the reference walk is `part_requirements` and that is Task
6's. The `from fenceai.parts.resolve import part_requirements` below is a local import
inside the method for exactly that reason — it is not reached until a retirement is
attempted.

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_parts_store.py
"""Parts are the third citizen of a pattern knowledge and fence models already
follow: content immutable, status the only mutation, publishing retires its
predecessor."""

import pytest

from fenceai.parts.model import Part, SpecField
from fenceai.store.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "t.db"))


def rail(version=1, status="active", width=38) -> Part:
    return Part(id="rail-38", version=version, type="rail", status=status,
                spec=[SpecField(key="width_mm", value=width, agree="==", unit="mm")])


def test_a_part_round_trips(store):
    store.save_part(rail())
    assert store.load_part("rail-38", 1).width_mm == 38


def test_a_draft_may_be_rewritten_in_place(store):
    store.save_part(rail(status="draft"))
    store.save_part(rail(status="draft", width=45))
    assert store.load_part("rail-38", 1).width_mm == 45


def test_a_published_version_is_immutable(store):
    store.save_part(rail())
    with pytest.raises(ValueError, match="immutable"):
        store.save_part(rail(width=45))


def test_publishing_retires_its_predecessor(store):
    store.save_part(rail(version=1))
    store.save_part(rail(version=2, status="draft"))
    store.set_part_status("rail-38", 2, "active")
    assert store.load_part("rail-38", 1).status == "retired"
    assert store.load_part("rail-38", 2).status == "active"


def test_an_illegal_status_transition_is_refused(store):
    store.save_part(rail(version=1))
    store.set_part_status("rail-38", 1, "retired")
    with pytest.raises(ValueError, match="illegal status transition"):
        store.set_part_status("rail-38", 1, "draft")


def test_the_library_answers_latest_active(store):
    store.save_part(rail(version=1))
    store.save_part(rail(version=2, status="draft"))
    lib = store.part_library()
    assert lib.latest_active("rail-38").version == 1
    store.set_part_status("rail-38", 2, "active")
    assert store.part_library().latest_active("rail-38").version == 2


def test_next_version_counts_from_what_exists(store):
    assert store.next_part_version("rail-38") == 1
    store.save_part(rail(version=1))
    assert store.next_part_version("rail-38") == 2


def test_saving_writes_an_audit_row(store):
    store.save_part(rail())
    assert any(r["ref"] == "rail-38@v1" for r in store.audit_log())

```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/store/test_parts_store.py -q`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'save_part'`

- [ ] **Step 3: Write the implementation**

In `_SCHEMA`, beside the `fence_models` table:

```sql
CREATE TABLE IF NOT EXISTS parts (
    part_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
    doc TEXT NOT NULL, PRIMARY KEY (part_id, version));
```

Import `Part`, `PartLibrary` at the top of `db.py`, then add after the fence-model
block. Read `save_fence_model` / `set_fence_model_status` / `next_*_version`
immediately above and mirror them exactly — including the `_serialized` decoration the
class applies, the `_audit` call, and the single `commit()` at the end of each public
method.

```python
    # -- parts (drafts mutable, published versions frozen) ---------------------

    _PART_STATUSES = ("draft", "active", "retired")

    def save_part(self, part: Part, actor: str = "system") -> None:
        """A draft may be rewritten in place; anything published is frozen.

        The refusal belongs here and not in a route, because it is the invariant
        rather than a validation of one caller — the same reason `save_fence_model`
        carries it. A run stamps `(part_id, version)` and re-reading it must give
        back the spec that run resolved.
        """
        row = self._conn.execute(
            "SELECT status FROM parts WHERE part_id=? AND version=?",
            (part.id, part.version),
        ).fetchone()
        if row is not None and row[0] != "draft":
            raise ValueError(
                f"{part.ref} is {row[0]}; its content is immutable "
                "(publish a new version, or change only its status)"
            )
        self._conn.execute(
            "INSERT INTO parts (part_id, version, status, doc) VALUES (?,?,?,?) "
            "ON CONFLICT(part_id, version) DO UPDATE SET "
            "status=excluded.status, doc=excluded.doc",
            (part.id, part.version, part.status, part.model_dump_json()),
        )
        self._audit(actor, "save_part", part.ref)
        self._conn.commit()

    def load_part(self, part_id: str, version: int) -> Part | None:
        row = self._conn.execute(
            "SELECT doc FROM parts WHERE part_id=? AND version=?", (part_id, version),
        ).fetchone()
        return Part.model_validate_json(row[0]) if row else None

    def part_library(self) -> PartLibrary:
        rows = self._conn.execute(
            "SELECT doc FROM parts ORDER BY part_id, version"
        ).fetchall()
        return PartLibrary(parts=[Part.model_validate_json(r[0]) for r in rows])

    def next_part_version(self, part_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(version) FROM parts WHERE part_id=?", (part_id,),
        ).fetchone()
        return (row[0] or 0) + 1

    def set_part_status(
        self, part_id: str, version: int, status: str, actor: str = "system"
    ) -> None:
        """Activating retires the predecessor, so `latest_active` is never ambiguous."""
        part = self.load_part(part_id, version)
        if part is None:
            raise ValueError(f"{part_id}@v{version} not found")
        if status not in self._STATUS_TRANSITIONS.get(part.status, set()):
            raise ValueError(
                f"illegal status transition {part.status} -> {status} for {part.ref}"
            )
        if status == "retired":
            # A published model naming this part would resolve to nothing at its next
            # generation. Refused here rather than in a route, because it is the
            # invariant — the same placement `save_fence_model`'s immutability refusal
            # argues for. Note it checks ACTIVE models only: a draft naming a part it
            # is about to stop naming must not block the retirement.
            naming = self._models_naming_part(part_id)
            if naming:
                raise ValueError(
                    f"{part.ref} is still named by {', '.join(naming)} — retiring it "
                    "would leave those slots with nothing eligible"
                )
        if status == "active":
            for row in self._conn.execute(
                "SELECT version FROM parts WHERE part_id=? AND status='active'",
                (part_id,),
            ).fetchall():
                if row[0] != version:
                    self._set_part_status_nocommit(part_id, row[0], "retired", actor)
        self._set_part_status_nocommit(part_id, version, status, actor)
        self._conn.commit()

    def _models_naming_part(self, part_id: str) -> list[str]:
        from fenceai.parts.resolve import part_requirements
        return sorted(
            m.ref for m in self.fence_model_library().models
            if m.status == "active"
            and any(r.part_id == part_id for _key, r in part_requirements(m))
        )

    def _set_part_status_nocommit(
        self, part_id: str, version: int, status: str, actor: str
    ) -> None:
        part = self.load_part(part_id, version)
        part.status = status  # type: ignore[assignment]
        self._conn.execute(
            "UPDATE parts SET status=?, doc=? WHERE part_id=? AND version=?",
            (status, part.model_dump_json(), part_id, version),
        )
        self._audit(actor, f"part_status:{status}", part.ref)
```

If `_STATUS_TRANSITIONS` is not already a class attribute shared with knowledge
versions, reuse whatever `update_knowledge_status` reads — do NOT define a second
transition table.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/store/ -q`
Expected: PASS, 8 new tests plus every existing store test

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/store/db.py tests/store/test_parts_store.py
git commit -m "feat(store): parts as a third versioned library, same rules as the other two"
```

---

### Task 6: The slot names a part, and a model resolves its parts

**Files:**
- Modify: `src/fenceai/fencemodel/model.py` (`PartRequirement`)
- Create: `src/fenceai/parts/resolve.py`
- Test: `tests/parts/test_resolve.py`

**Interfaces:**
- Consumes: `PartLibrary` (Task 1), `compile_spec` (Task 2), `FenceModel`, `PanelSpec`,
  `PartRequirement`, `Eligibility`
- Produces: `PartRequirement.part_id: str`;
  `part_requirements(model) -> list[tuple[str, PartRequirement]]`;
  `resolve_model_parts(model, library) -> tuple[FenceModel, list[PartUse]]`;
  `PartUse{part_id, version, content_hash}` in `fenceai/strategy/model.py` (defined
  HERE, in step 3; Task 7 adds `GenerationRun.part_snapshot` and the wiring)

**Note on `Member.width_mm` / `FrameSlot.thickness_mm`:** spec §5 has these leave the
slot for the part, but `resolve.py`, `preview.py` and `report/elevation.py` all read
them. They therefore take **the same lifetime `eligibility` has**: the field stays on
the schema, stops being something an author writes, and is filled by
`resolve_model_parts` from the part's `dimensions`. Every downstream reader is
untouched, and there is still exactly one authority for the number — the part.

**Note on `Eligibility`:** it is NOT removed. It stops being something an author writes
on a slot and stays what it always was downstream — the shape `match_eligibility`
returns and a `ResolvedSlot` freezes. `resolve_model_parts` fills
`eligibility.predicate`; the existing matcher turns it into members and clears it.

- [ ] **Step 1: Write the failing test**

```python
# tests/parts/test_resolve.py
"""A model names a part by id, unpinned; resolution turns that into the predicate
field the matcher already reads."""

import pytest

from fenceai.fencemodel.model import (
    Distributed, FenceModel, FrameSlot, PanelSpec, PartRequirement,
)
from fenceai.parts.model import Part, PartLibrary, SpecField
from fenceai.parts.resolve import part_requirements, resolve_model_parts


def library(*parts) -> PartLibrary:
    return PartLibrary(parts=list(parts))


def rail(version=1, status="active", width=38) -> Part:
    return Part(id="rail-38", version=version, status=status, type="rail",
                spec=[SpecField(key="width_mm", value=width, agree="==", unit="mm")])


def model() -> FenceModel:
    return FenceModel(id="M", version=1, default_spec=PanelSpec(frame=[
        FrameSlot(key="rail", orientation="horizontal",
                  placement=Distributed(count=2),
                  requirement=PartRequirement(part_id="rail-38",
                                              length_rule="centre_to_centre")),
    ]))


def test_resolution_fills_the_predicate_the_matcher_already_reads():
    resolved, _ = resolve_model_parts(model(), library(rail()))
    predicate = resolved.default_spec.frame[0].requirement.eligibility.predicate
    assert predicate is not None
    assert predicate.items[0].left.path == "item.width_mm"


def test_it_resolves_latest_active_not_latest():
    lib = library(rail(version=1, width=38), rail(version=2, status="draft", width=45))
    resolved, uses = resolve_model_parts(model(), lib)
    assert uses[0].version == 1
    assert resolved.default_spec.frame[0].requirement.eligibility.predicate.items[0].right.value == 38


def test_it_reports_what_it_resolved_so_the_run_can_stamp_it():
    _, uses = resolve_model_parts(model(), library(rail()))
    assert [(u.part_id, u.version) for u in uses] == [("rail-38", 1)]


def test_a_draft_carries_a_content_hash_because_its_content_can_still_move():
    """Versions are immutable only once active. A run that drew on a draft needs the
    content, not just the number — the precaution ModelUse already takes."""
    lib = library(rail(version=1, status="draft"))
    _, uses = resolve_model_parts(model(), lib)
    assert uses[0].content_hash != ""


def test_the_part_supplies_the_width_the_panel_draws():
    """One authority for the number. Keeping width authored on the slot is what let a
    model draw 38 while buying 45."""
    from fenceai.fencemodel.model import InfillSpec, Member
    m = model()
    m.default_spec.infill = InfillSpec(orientation="vertical", pattern=[
        Member(key="slat", requirement=PartRequirement(part_id="rail-38"))])
    resolved, _ = resolve_model_parts(m, library(rail(width=38)))
    assert resolved.default_spec.infill.pattern[0].width_mm == 38


def test_a_part_declaring_no_dimension_leaves_it_undeclared():
    """0 is what the elevation already renders as declared=False — a flag, not a
    nominal band that reads as measured."""
    bare = Part(id="rail-38", version=1, type="rail",
                spec=[SpecField(key="material", value="vinyl", agree="==")])
    resolved, _ = resolve_model_parts(model(), library(bare))
    assert resolved.default_spec.frame[0].thickness_mm == 0


def test_the_stored_model_is_not_mutated():
    """generate() is pure (ADR-0004). Resolution returns a new document."""
    original = model()
    resolve_model_parts(original, library(rail()))
    assert original.default_spec.frame[0].requirement.eligibility.predicate is None


def test_a_part_with_no_active_version_is_refused_by_name():
    lib = library(rail(status="draft"))
    with pytest.raises(ValueError, match="rail-38"):
        resolve_model_parts(model(), lib)


def test_retiring_a_part_a_published_model_names_is_refused(tmp_path):
    """Refused at authoring time, where it is actionable — the moment
    `validate_model` already refuses a slot no product can fill. Retiring silently
    would leave every model naming it resolving to nothing at its next generation."""
    from fenceai.store.db import Store
    store = Store(str(tmp_path / "t.db"))
    store.save_part(rail())
    store.save_fence_model(model())
    with pytest.raises(ValueError, match="rail-38.*still named"):
        store.set_part_status("rail-38", 1, "retired")


def test_retiring_is_allowed_once_nothing_names_it(tmp_path):
    from fenceai.store.db import Store
    store = Store(str(tmp_path / "t.db"))
    store.save_part(rail())
    store.set_part_status("rail-38", 1, "retired")
    assert store.load_part("rail-38", 1).status == "retired"


def test_a_draft_model_does_not_block_a_retirement(tmp_path):
    """A draft naming a part it is about to stop naming must not hold the library
    hostage. Only ACTIVE models count."""
    from fenceai.store.db import Store
    store = Store(str(tmp_path / "t.db"))
    store.save_part(rail())
    draft = model()
    draft.status = "draft"
    store.save_fence_model(draft)
    store.set_part_status("rail-38", 1, "retired")
    assert store.load_part("rail-38", 1).status == "retired"


def test_part_requirements_reaches_frame_infill_fixings_and_post():
    from fenceai.fencemodel.model import (
        FixingRule, InfillSpec, Member, PostSlot,
    )
    m = FenceModel(
        id="M", version=1,
        default_spec=PanelSpec(
            frame=[FrameSlot(key="rail", orientation="horizontal",
                             placement=Distributed(count=2),
                             requirement=PartRequirement(part_id="a"))],
            infill=InfillSpec(orientation="vertical", pattern=[
                Member(key="slat", width_mm=100,
                       requirement=PartRequirement(part_id="b"))]),
            fixings=[FixingRule(key="screw", basis="per_member_crossing",
                                qty_per_basis=1,
                                requirement=PartRequirement(part_id="c"))],
        ),
        post=PostSlot(requirement=PartRequirement(part_id="d"),
                      cap=PartRequirement(part_id="e")),
    )
    assert {r.part_id for _, r in part_requirements(m)} == {"a", "b", "c", "d", "e"}


def test_variants_are_resolved_too():
    """A variant's spec is a spec. Missing it would leave a slot with no predicate,
    and the bay would report no_eligible_item only for the heights that hit it."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import Variant
    m = model()
    m.variants = [Variant(
        condition=Cmp(cmp=">=", left=FieldRef(path="panel.height_mm"), right=Lit(value=1800)),
        spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal", placement=Distributed(count=3),
            requirement=PartRequirement(part_id="rail-38"))]))]
    resolved, uses = resolve_model_parts(m, library(rail()))
    assert resolved.variants[0].spec.frame[0].requirement.eligibility.predicate is not None
    assert len(uses) == 1  # deduplicated: one part, named twice
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/parts/test_resolve.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.parts.resolve'`

- [ ] **Step 3: Change `PartRequirement`, then write the resolver**

In `src/fenceai/fencemodel/model.py`, replace `PartRequirement`:

```python
class PartRequirement(BaseModel):
    """WHERE a part goes in this panel. What it IS lives on the part.

    The line is what the piece is versus where it goes: a joint is a relationship
    between two members in a panel, not a property of a rail — the same rail seats
    into a channel in one model and butts in another. But a rail's width is the
    rail's, and keeping it here is what let a model draw 38 while buying 45.

    `part_id` is unpinned. A slot storing `rail-38@v3` would mean fixing a rail spec
    requires republishing every model naming it, which is the entire reason the part
    is a shared entity rather than a copied template. Generation resolves
    `latest_active` and the RUN stamps what it resolved.

    `eligibility` is not authored here and carries no default a person writes: it is
    filled by `parts.resolve.resolve_model_parts` and cleared by the matcher, which
    is the same lifetime it has always had downstream.
    """

    part_id: str
    qty: int = 1
    length_rule: LengthRule | None = None
    overlap_mm: Mm = 0
    option_axis: str | None = None
    sku_by_option: dict[str, str] = {}
    eligibility: Eligibility = Eligibility()
```

```python
# src/fenceai/parts/resolve.py
"""Turning a model's part references into the predicate the matcher already reads.

Strictly UPSTREAM of `match_spec`, which is the point: the existing
`height -> rail positions -> post -> clear width -> infill` DAG does not move, and
neither does `generator.py`'s ordering. Compilation happens, then everything
downstream is what it was.
"""

from __future__ import annotations

import hashlib

from fenceai.fencemodel.model import FenceModel, PanelSpec, PartRequirement
from fenceai.parts.compile import compile_spec
from fenceai.parts.model import Part, PartLibrary
from fenceai.strategy.model import PartUse


def _spec_requirements(spec: PanelSpec) -> list[tuple[str, PartRequirement]]:
    out = [(s.key, s.requirement) for s in spec.frame]
    if spec.infill:
        out += [(m.key, m.requirement) for m in spec.infill.pattern]
    out += [(f.key, f.requirement) for f in spec.fixings]
    return out


def part_requirements(model: FenceModel) -> list[tuple[str, PartRequirement]]:
    """Every requirement in a model — default spec, every variant, post and cap.

    A variant missed here would leave a slot with no predicate and the bay would
    report `no_eligible_item` only at the heights that hit that variant, which is
    the worst shape a bug of this kind can take.
    """
    out = _spec_requirements(model.default_spec)
    for index, variant in enumerate(model.variants):
        out += [(f"variant{index}.{key}", req)
                for key, req in _spec_requirements(variant.spec)]
    if model.post is not None:
        out.append(("post", model.post.requirement))
        if model.post.cap is not None:
            out.append(("post.cap", model.post.cap))
    return out


def content_hash(part: Part) -> str:
    """Why a version number is not enough: a DRAFT is mutable. Versions are immutable
    only once active, so a run that drew on a draft needs the content. Not a new
    precaution — `ModelUse.content_hash` already takes it one level up."""
    return hashlib.sha256(part.model_dump_json().encode()).hexdigest()[:16]


def resolve_model_parts(
    model: FenceModel, library: PartLibrary
) -> tuple[FenceModel, list[PartUse]]:
    """Fill every requirement's predicate from its part; report what was resolved.

    Returns a NEW document. `generate()` is pure (ADR-0004), and mutating the stored
    model here would make a second generation from the same library mean something
    different from the first.
    """
    resolved = model.model_copy(deep=True)
    uses: dict[str, PartUse] = {}
    for key, requirement in part_requirements(resolved):
        part = library.latest_active(requirement.part_id)
        if part is None:
            raise ValueError(
                f"{model.ref} slot {key!r} names part {requirement.part_id!r}, which "
                "has no active version — nothing would be eligible for it"
            )
        requirement.eligibility = requirement.eligibility.model_copy(
            update={"predicate": compile_spec(part), "members": []})
        uses[part.id] = PartUse(part_id=part.id, version=part.version,
                                content_hash=content_hash(part))
    _apply_dimensions(resolved, library)
    return resolved, sorted(uses.values(), key=lambda u: (u.part_id, u.version))


def _apply_dimensions(model: FenceModel, library: PartLibrary) -> None:
    """Write the part's dimensions onto the holders that draw them.

    `Member.width_mm`, `Member.thickness_mm` and `FrameSlot.thickness_mm` keep their
    place on the schema because `resolve.py`, `preview.py` and `report/elevation.py`
    read them — but they stop being AUTHORED and take the same lifetime `eligibility`
    has: filled here, from the one authority. Keeping them authored is what let a
    model draw 38 while buying 45.

    A part declaring no dimension leaves the field at 0, which is what the elevation
    already renders as `declared=False` — a flag, not a nominal band that reads as
    measured.
    """
    for holder in _dimension_holders(model):
        part = library.latest_active(holder.requirement.part_id)
        if part is None:
            continue
        if hasattr(holder, "width_mm"):
            holder.width_mm = part.width_mm or 0
        holder.thickness_mm = part.thickness_mm or 0


def _dimension_holders(model: FenceModel) -> list:
    """Frame slots and infill members — the two that carry a drawn dimension.

    Fixings and posts do not: a screw has no elevation band, and a post's face width
    is a CAPABILITY read off the chosen product (`PanelContext.post_face_width_*`),
    not a dimension the panel draws.
    """
    out = []
    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        out += list(spec.frame)
        if spec.infill:
            out += list(spec.infill.pattern)
    return out
```

- [ ] **Step 4: Run the new tests**

Run: `uv run pytest tests/parts/test_resolve.py -q`
Expected: PASS, 8 tests

- [ ] **Step 5: Run the full suite and expect widespread, EXPECTED failures**

Run: `uv run pytest -q`
Expected: FAIL — every construction of `PartRequirement(role=…, eligibility=…)` in
`fencemodel/demo.py` and the tests now raises. Do NOT fix them here; Task 8 migrates
them. Record the failing count in the commit message so Task 8 can show it reaching
zero.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/fencemodel/model.py src/fenceai/parts/resolve.py tests/parts/test_resolve.py
git commit -m "feat(parts): a slot names a part, and a model resolves its references

The slot keeps where a piece goes; the part owns what it is. Resolution is
strictly upstream of match_spec, so no resolution order moves.

Demo models and their tests are red until the migration in the next task."
```

---

### Task 7: Run identity — `PartUse` and `part_snapshot`

**Files:**
- Modify: `src/fenceai/strategy/model.py` (`GenerationRun.part_snapshot`; `PartUse` came in Task 6)
- Modify: `src/fenceai/strategy/generator.py` (`segment_model`; stamp the snapshot)
- Modify: `src/fenceai/fencemodel/preview.py` (resolve from the run's snapshot)
- Modify: `src/fenceai/api/app.py` (pass the part library / snapshot into preview)
- Test: `tests/strategy/test_part_snapshot.py`

**Interfaces:**
- Consumes: `resolve_model_parts` (Task 6), `Store.part_library` (Task 5)
- Produces: `PartUse{part_id, version, content_hash}`;
  `GenerationRun.part_snapshot: list[PartUse]`;
  `resolve_model_parts_at(model, library, snapshot) -> FenceModel` in
  `parts/resolve.py` — resolves pinned versions when a snapshot is present

- [ ] **Step 1: Write the failing test**

```python
# tests/strategy/test_part_snapshot.py
"""A run records the part versions it resolved, and the bay preview reads them back
rather than resolving today's."""

from fenceai.parts.model import Part, PartLibrary, SpecField
from fenceai.parts.resolve import resolve_model_parts, resolve_model_parts_at
from fenceai.strategy.model import PartUse


def rail(version, width) -> Part:
    return Part(id="rail-38", version=version, status="active", type="rail",
                spec=[SpecField(key="width_mm", value=width, agree="==", unit="mm")])


def model():
    from fenceai.fencemodel.model import (
        Distributed, FenceModel, FrameSlot, PanelSpec, PartRequirement,
    )
    return FenceModel(id="M", version=1, default_spec=PanelSpec(frame=[
        FrameSlot(key="rail", orientation="horizontal", placement=Distributed(count=2),
                  requirement=PartRequirement(part_id="rail-38"))]))


def test_an_old_run_reads_its_own_part_version_not_todays():
    """THE trap. `bay_preview_plan` reloads the model by its STAMPED version,
    explicitly never latest_active, because the drawer once marked one product
    chosen while the run had bought another. An unpinned part_id inside that stamped
    document reopens the identical bug by a new door."""
    v1_only = PartLibrary(parts=[rail(1, 38)])
    _, uses = resolve_model_parts(model(), v1_only)

    moved = PartLibrary(parts=[rail(1, 38), rail(2, 45)])
    moved.parts[0].status = "retired"

    fresh, _ = resolve_model_parts(model(), moved)
    assert fresh.default_spec.frame[0].requirement.eligibility.predicate.items[0].right.value == 45

    as_run = resolve_model_parts_at(model(), moved, uses)
    assert as_run.default_spec.frame[0].requirement.eligibility.predicate.items[0].right.value == 38


def test_an_empty_snapshot_falls_back_to_latest_active():
    """A run generated before parts existed. `[]` is the default and needs no
    validator — the same readable-old-runs convention as catalog_skus."""
    lib = PartLibrary(parts=[rail(1, 38)])
    resolved = resolve_model_parts_at(model(), lib, [])
    assert resolved.default_spec.frame[0].requirement.eligibility.predicate is not None


def test_the_snapshot_is_part_of_run_identity():
    """Two runs building the identical fence from different part versions were not
    generated from the same thing."""
    a = PartUse(part_id="rail-38", version=1, content_hash="aaa")
    b = PartUse(part_id="rail-38", version=2, content_hash="bbb")
    assert a.sort_key() != b.sort_key()


def test_a_run_stored_before_parts_existed_still_loads():
    from fenceai.strategy.model import GenerationRun
    run = GenerationRun.model_validate_json('{"id": "r1", "project_id": "p"}')
    assert run.part_snapshot == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/strategy/test_part_snapshot.py -q`
Expected: FAIL — `ImportError: cannot import name 'PartUse'`

- [ ] **Step 3: Write the implementation**

`PartUse` already exists from Task 6:

```python
class PartUse(BaseModel):
    """A part version this run resolved.

    `content_hash` for the same reason `ModelUse` carries one: a DRAFT is mutable.
    Versions are immutable only once active, so a run that drew on a draft needs the
    content, not just the number.
    """

    part_id: str
    version: int
    content_hash: str = ""

    def sort_key(self) -> tuple:
        return (self.part_id, self.version, self.content_hash)
```

On `GenerationRun`, beside `model_snapshot`:

```python
    # the parts this run resolved — part of what "generated from" means, so it
    # belongs in the run id on `model_snapshot`'s argument. [] is a run generated
    # before parts existed, and needs no validator because it is the default.
    part_snapshot: list[PartUse] = []
```

Include `part_snapshot` wherever the run digest / run id is computed from
`model_snapshot` — grep for `sort_key()` and `model_snapshot` in `strategy/` and add
it at every site, sorted, so two runs cannot collide on it.

In `src/fenceai/parts/resolve.py`, add the pinned variant:

```python
def resolve_model_parts_at(
    model: FenceModel, library: PartLibrary, snapshot: list[PartUse]
) -> FenceModel:
    """Resolve against the versions a RUN recorded, not against what is current.

    An empty snapshot falls back to `latest_active`: that is a run generated before
    parts existed, and it is the only honest answer for one.
    """
    if not snapshot:
        resolved, _ = resolve_model_parts(model, library)
        return resolved
    pinned = PartLibrary(parts=[
        p for use in snapshot
        if (p := library.by_ref(use.part_id, use.version)) is not None
    ])
    for part in pinned.parts:
        part.status = "active"   # a retired version is still what this run resolved
    resolved, _ = resolve_model_parts(model, pinned)
    return resolved
```

In `src/fenceai/strategy/generator.py`, inside `segment_model` (around line 1249),
call `resolve_model_parts(model, part_library)` on the model document the moment it is
chosen for a segment, use the returned document everywhere downstream, and collect the
`PartUse`s into the run. Thread `part_library` in from `generate()`'s caller alongside
the catalog — do not read the store from inside `generate()`; it is pure.

In `src/fenceai/fencemodel/preview.py` and the `/api/runs/.../panel-preview` path in
`api/app.py`, call `resolve_model_parts_at(model, part_library, result.run.part_snapshot)`
instead of `resolve_model_parts`.

- [ ] **Step 4: Run the new tests**

Run: `uv run pytest tests/strategy/test_part_snapshot.py -q`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add src/fenceai/strategy tests/strategy/test_part_snapshot.py src/fenceai/parts/resolve.py src/fenceai/fencemodel/preview.py src/fenceai/api/app.py
git commit -m "feat(strategy): a run stamps the parts it resolved, and the preview reads them back

The bay preview reloads a model by its stamped version because the drawer
once marked one product chosen while the run had bought another. An
unpinned part_id inside that document reopens the same bug by a new door."
```

---

### Task 8: Migration — the demo models, the catalog backfill, and stored documents

**Files:**
- Create: `src/fenceai/parts/demo.py`
- Create: `tools/migrate_parts.py`
- Modify: `src/fenceai/fencemodel/demo.py` (every `PartRequirement`)
- Modify: `src/fenceai/catalog/demo.py` (`type` and `width_mm` on the products named)
- Modify: `src/fenceai/store/db.py` (seed demo parts beside `demo_model_versions()`)
- Test: `tests/parts/test_migration.py`

**Interfaces:**
- Consumes: everything above
- Produces: `demo_parts() -> list[Part]`, `demo_part_types() -> list[PartType]`;
  `tools/migrate_parts.py` CLI over a `.db`

- [ ] **Step 1: Write the failing test**

```python
# tests/parts/test_migration.py
"""Migration moves where a spec is written, not what it says."""

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import demo_model_versions
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.parts.resolve import part_requirements, resolve_model_parts
from fenceai.parts.validate import matching_skus, validate_part


def library() -> PartLibrary:
    return PartLibrary(parts=demo_parts())


def test_every_demo_part_is_valid_against_the_demo_catalog():
    catalog = demo_catalog()
    for part in demo_parts():
        assert validate_part(part, catalog) == [], part.ref


def test_every_slot_of_every_demo_model_names_a_part_that_resolves():
    lib = library()
    for model in demo_model_versions():
        resolve_model_parts(model, lib)   # raises if any part_id has no active version


def test_a_migrated_part_emits_no_type_row():
    """Product.type is empty on every existing product, so a `type ==` agreement
    would match nothing and every migrated slot would resolve to no eligible item —
    the gate would not merely move, it would collapse. The SKU list is already the
    whole constraint."""
    for part in demo_parts():
        assert not any(f.key == "type" for f in part.spec), part.ref


def test_a_migrated_part_carries_its_type_on_the_entity():
    assert {p.type for p in demo_parts()} >= {"rail", "screw", "infill"}


def test_the_sku_list_migrated_as_among_not_covers():
    """`covers` asks about a set the ITEM declares. A two-SKU list compiled that way
    would collapse to equality against one of them."""
    for part in demo_parts():
        sku_fields = [f for f in part.spec if f.key == "sku"]
        for f in sku_fields:
            assert f.agree == "among", part.ref


def test_the_width_a_model_drew_is_now_a_fact_on_the_product():
    """The model was already claiming that slat is 100 wide. Migration writes the
    number onto the product, where it belongs, so the part and the item agree
    because they quote the same fact."""
    catalog = demo_catalog()
    assert catalog.product("SLAT-100").attrs["width_mm"] == 100
    assert catalog.product("SLAT-V-150").attrs["width_mm"] == 150


def test_no_product_is_drawn_at_two_widths():
    """Two models drawing one SKU at two widths is a real contradiction in existing
    data, and migration reports it rather than picking."""
    from tools.migrate_parts import width_conflicts
    assert width_conflicts(demo_model_versions()) == {}


def test_a_migrated_part_still_admits_exactly_the_sku_it_used_to_name():
    catalog = demo_catalog()
    for part in demo_parts():
        sku_fields = [f for f in part.spec if f.key == "sku"]
        if sku_fields:
            assert set(matching_skus(part, catalog)) >= set(sku_fields[0].value), part.ref


def test_the_demo_seeds_one_part_with_several_eligible_items():
    """The previous arc found every demo slot naming ONE product made the drawer's
    alternatives untested — `buttons == len(options) - 1` was `0 == 0`, and deleting
    the offer button passed eighteen tests. One part must admit several."""
    catalog = demo_catalog()
    assert any(len(matching_skus(p, catalog)) > 1 for p in demo_parts())


def test_no_demo_slot_carried_a_suggest_only_member():
    """Promoting one to `auto` would let the system substitute a product a human said
    needs sign-off. Migration refuses rather than converting."""
    from tools.migrate_parts import approval_losses
    assert approval_losses(demo_model_versions()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/parts/test_migration.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.parts.demo'`

- [ ] **Step 3: Write the migration**

**3a.** Write `tools/migrate_parts.py` with three pure functions plus a CLI:

```python
"""Turning inline requirements into library parts.

Mechanical, with two refusals that are not: a SKU drawn at two widths, and a
`suggest_only` member. Both are real facts about existing data that this migration
is the first thing to look at, and neither has a safe automatic answer.
"""

from __future__ import annotations

from collections import defaultdict


def width_conflicts(models) -> dict[str, dict[int, list[str]]]:
    """{sku: {width: [model refs]}} for any SKU drawn at more than one width.

    Not a migration failure — a contradiction in the models, surfaced for the first
    time. Migration reports and stops rather than picking one.
    """
    seen: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for model in models:
        for _key, req, width in _requirements_with_width(model):
            if width is None:
                continue
            for sku in _skus(req):
                seen[sku][width].append(model.ref)
    return {sku: dict(w) for sku, w in seen.items() if len(w) > 1}


def approval_losses(models) -> list[tuple[str, str, str]]:
    """(model ref, slot key, sku) for every `suggest_only` member.

    Derived members are emitted `auto`. Promoting one would let the system substitute
    a product a human said needs sign-off, so migration refuses rather than
    converting.
    """
    out = []
    for model in models:
        for key, req, _width in _requirements_with_width(model):
            for member in req.eligibility.members:
                if member.approval == "suggest_only":
                    out.append((model.ref, key, member.sku))
    return out
```

Add `_requirements_with_width(model)` yielding `(key, requirement, width_mm | None)`
for every frame slot (`FrameSlot.thickness_mm` → `thickness_mm`), infill member
(`Member.width_mm` → `width_mm`), fixing and post/cap, and `_skus(req)` reading
`[m.sku for m in req.eligibility.members]`. Add a `main()` that opens a `.db`, reads
`fence_model_library()`, refuses on either check, writes the parts and the rewritten
models, and prints what it did.

**3b.** Write `src/fenceai/parts/demo.py` with `demo_parts()` and
`demo_part_types()`. One part per distinct `(role, sku list, width, thickness)` across
`demo_model_versions()`. Each part:

- `id` = `f"{type}-{sku.lower()}"`, e.g. `rail-rail-3000`
- `type` = the old `role`
- `name_i18n` seeded from the product's `name` / `name_i18n`
- `spec` = `[SpecField(key="sku", value=[…], agree="among")]` plus
  `SpecField(key="width_mm", value=…, agree="==", unit="mm")` where the slot carried
  a width, and the same for `thickness_mm`

Concretely, the file opens like this — the first entry is the mechanical migration of
a slot that named one SKU, the second is the deliberately multi-item part:

```python
# src/fenceai/parts/demo.py
"""The demo models' inline requirements, as library parts.

`RAIL-3000` backed a rail slot in three models as three separate acts of authoring.
Here it is one part, and editing it edits all three — which is the entity's whole
reason for being shared rather than copied.
"""

from fenceai.parts.model import Part, PartType, SpecField


def demo_part_types() -> list[PartType]:
    return [
        PartType(key="rail", label_i18n={"en": "Rails", "he": "שלבים"}),
        PartType(key="screw", label_i18n={"en": "Fixings", "he": "אמצעי חיבור"}),
        PartType(key="infill", label_i18n={"en": "Boards", "he": "קרשים"}),
        PartType(key="post", label_i18n={"en": "Posts", "he": "עמודים"}),
        PartType(key="cap", label_i18n={"en": "Caps", "he": "כובעים"}),
    ]


def demo_parts() -> list[Part]:
    return [
        # migrated: the slot named one SKU, so the SKU list IS the spec
        Part(id="rail-rail-3000", version=1, type="rail",
             name_i18n={"en": "Rail 3000", "he": "שלב 3000"},
             spec=[SpecField(key="sku", value=["RAIL-3000"], agree="among")]),
        Part(id="infill-slat-100", version=1, type="infill",
             name_i18n={"en": "Slat 100", "he": "קרש 100"},
             spec=[SpecField(key="sku", value=["SLAT-100"], agree="among"),
                   SpecField(key="width_mm", value=100, agree="==", unit="mm")]),
        # NOT a migration: authored by spec, and it admits more than one product on
        # purpose. Every demo slot naming exactly one product is what made the
        # drawer's alternatives untested last arc — `buttons == len(options) - 1`
        # was `0 == 0`, and deleting the offer button passed eighteen tests.
        Part(id="rail-38-vinyl", version=1, type="rail",
             name_i18n={"en": "38mm vinyl rail", "he": "שלב ויניל 38 מ\"מ"},
             spec=[SpecField(key="width_mm", value=38, agree="==", unit="mm"),
                   SpecField(key="material", value="vinyl", agree="=="),
                   SpecField(key="length_mm", agree="supplies", unit="mm")]),
    ]
```

Use `rail-38-vinyl` for `slat_model`'s rail slot, and give the catalog a second vinyl
38mm rail in step 3c so it genuinely has something to choose between.

**3c.** In `src/fenceai/catalog/demo.py`, add `type` to every product and `width_mm`
to `SLAT-100` (100) and `SLAT-V-150` (150), taken from what the models drew. Add a
second rail product so the multi-item part above has something to choose between.

**3d.** In `src/fenceai/fencemodel/demo.py`, replace every
`PartRequirement(role=…, eligibility=Eligibility(members=[EligibleItem(sku=…)]))`
with `PartRequirement(part_id=…)`, and delete `Member.width_mm` /
`FrameSlot.thickness_mm` where the part now carries them.

**3e.** In `src/fenceai/store/db.py`, seed `demo_parts()` beside the existing
`demo_model_versions()` seeding, using `save_part`.

- [ ] **Step 4: Run the migration tests**

Run: `uv run pytest tests/parts/test_migration.py -q`
Expected: PASS, 10 tests

- [ ] **Step 5: Run the full suite to zero**

Run: `uv run pytest -q`
Expected: PASS. Every failure Task 6 introduced is now green. If any test still
constructs `PartRequirement(role=…)`, update it to name a part — do not reintroduce
the field.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/parts/demo.py tools/migrate_parts.py src/fenceai/fencemodel/demo.py src/fenceai/catalog/demo.py src/fenceai/store/db.py tests/parts/test_migration.py
git commit -m "feat(parts): migrate the demo models into the library

RAIL-3000 backed a rail slot in three models as three separate acts of
authoring; it is now one part. The width each model drew is now a fact on
the product, because that is what the model was already claiming.

A SKU drawn at two widths and a suggest_only member are both refused rather
than resolved — neither has a safe automatic answer."
```

---

### Task 9: The gate

**Files:**
- Test: `tests/scenarios/` (run, do not modify)
- Modify: `plan/current-status.md`
- Modify: `docs/architecture/02-entities.md`, `docs/architecture/01-domains.md`

**Interfaces:**
- Consumes: everything above
- Produces: a recorded gate result and updated architecture docs

- [ ] **Step 1: Run the golden scenarios**

Run: `uv run pytest tests/scenarios -q`
Expected: PASS, 155 scenarios. **Any difference in a BOM, a decision graph or a run
digest is a bug in this work, not a new behaviour.** If one moves, do not update the
expectation — find what moved and why.

- [ ] **Step 2: Run the full suite and the browser smoke**

Run: `uv run pytest -q`
Expected: PASS

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: all checks pass. 1A changes no UI, so a smoke failure means a backend change
leaked into a rendered surface.

- [ ] **Step 3: Update the architecture docs**

CLAUDE.md: *"Change code and these docs together, or not at all."* Add `Part` and
`PartType` to `docs/architecture/02-entities.md` beside `FenceModel`, with the
unpinned-reference bargain from spec §2.1 stated in one sentence. Add the parts
package to `docs/architecture/01-domains.md`.

- [ ] **Step 4: Update `plan/current-status.md`**

Add a section in the established voice: what landed, what it cost, the counts
(`N pytest · 155 golden scenarios · N/N smoke · gate byte-identical`), and the two
things the migration refused rather than resolved.

- [ ] **Step 5: Dispatch the project reviewers**

CLAUDE.md requires both after a slice touching domain abstractions:

```
architecture-critic — check against docs/product/architecture-foundation-v0.1.md §15
test-reviewer      — check the new tests for weak assertions and missing invariants
```

- [ ] **Step 6: Commit**

```bash
git add plan/current-status.md docs/architecture/
git commit -m "docs(architecture): the part library, and the gate that held"
```

---

## Notes for the executor

**If the gate moves**, the likeliest causes in order: (1) a migrated part admits a
different SKU set than the slot's old member list — check `matching_skus` against the
old members; (2) `_item_ctx` gained `stock_length_mm` and some existing predicate now
resolves a field it used to miss; (3) member ORDER changed — `resolve_supply` groups by
the `(sku, priority, approval)` signature and grouping decides which product is chosen,
because cut planning is not additive.

**Do not** add an AST node, write a second matcher, reorder `generator.py`, or store a
dimension. If a task appears to require any of those, stop and report it.
