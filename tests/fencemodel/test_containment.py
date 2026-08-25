"""Parts inside parts, and the credit that keeps the panel from buying them twice.

The driving case is the one the contract names: a kit that ships its own hinges.
Two facts have to hold at once and they pull in opposite directions.

* **Obligation 9** — "a published panel places every one of its members ...
  including parts contained inside other parts". So the hinges in the box are
  members of the panel: addressable, countable, and placeable by an assembly step
  or reported `unplaced`.
* **`Sigma(parts) = BOM`** — the panel must not ALSO buy those hinges, and every
  requirement line must still be pegged by a BOM line or an allocation.

The resolution is that the two lists stop being the same list, on purpose: the
BOM says what is BOUGHT, the panel says what is PLACED, and a contained member is
supplied by the line that bought its container. What holds the pair together is
one path key — `kit/hinge` — carried by both.

Every number below is arithmetic a person can check: the kit ships two hinges,
the panel wants four, so it buys two.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FixingRule, FrameSlot,
    PanelSpec, PartRequirement, AssemblyStep, Variant, validate_model,
)
from fenceai.fencemodel.resolve import PanelContext, resolve_panel
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.fulfill import fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.parts.model import ContainedPart, Part, PartLibrary, SpecField
from fenceai.parts.resolve import resolve_model_parts
from fenceai.report.assembly import assembly_plan
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

MODEL_ID = "M-KIT"


# --- the library ---------------------------------------------------------------

def _parts(hinges_per_kit: int = 2, nested: bool = False) -> PartLibrary:
    """A kit that ships hinges and a latch, and the pieces it ships.

    `nested` puts a washer inside the hinge, which is the only way to prove the
    path key composes rather than being a one-level special case.
    """
    hinge_contains = (
        [ContainedPart(key="washer", part_id="fix-washer", qty=2)] if nested else []
    )
    return PartLibrary(parts=[
        Part(id="rail-3000", version=1, type="rail",
             spec=[SpecField(key="sku", value=["RAIL-3000"], agree="among")]),
        Part(id="fix-hinge", version=1, type="fixing",
             spec=[SpecField(key="sku", value=["HINGE-SET"], agree="among")],
             contains=hinge_contains),
        Part(id="fix-latch", version=1, type="fixing",
             spec=[SpecField(key="sku", value=["LATCH"], agree="among")]),
        Part(id="fix-washer", version=1, type="fixing",
             spec=[SpecField(key="sku", value=["SCREW-S10"], agree="among")]),
        Part(id="kit-gate", version=1, type="gate_kit",
             spec=[SpecField(key="sku", value=["GATE-KIT-1000"], agree="among")],
             contains=[
                 ContainedPart(key="hinge", part_id="fix-hinge", qty=hinges_per_kit),
                 ContainedPart(key="latch", part_id="fix-latch", qty=1),
             ]),
    ])


def _spec(hinges_wanted: int, credits: dict[str, str] | None = None,
          with_hinge_slot: bool = True) -> PanelSpec:
    fixings = [FixingRule(
        key="kit", basis="per_panel", qty_per_basis=1,
        requirement=PartRequirement(
            part_id="kit-gate",
            credits={"hinge": "hinges"} if credits is None else credits),
    )]
    if with_hinge_slot:
        fixings.append(FixingRule(
            key="hinges", basis="per_panel", qty_per_basis=hinges_wanted,
            requirement=PartRequirement(part_id="fix-hinge"),
        ))
    return PanelSpec(
        frame=[FrameSlot(key="rail", orientation="horizontal",
                         placement=Distributed(count=2),
                         requirement=PartRequirement(part_id="rail-3000",
                                                     length_rule="centre_to_centre"))],
        fixings=fixings,
    )


def _model(spec: PanelSpec | None = None, **kw) -> FenceModel:
    return FenceModel(id=MODEL_ID, version=1,
                      default_spec=spec if spec is not None else _spec(4), **kw)


def _panel(model: FenceModel, library: PartLibrary):
    resolved, _ = resolve_model_parts(model, library)
    return resolve_panel(
        resolved.default_spec,
        PanelContext(centre_width_mm=1500, clear_width_mm=1500, height_mm=1800),
        model_ref=model.ref)


def _slot(panel, key):
    return next((s for s in panel.slots if s.slot_key == key), None)


def _priced(model: FenceModel, library: PartLibrary):
    """The whole spine for a three-metre run of this model."""
    catalog = demo_catalog()
    result = generate(straight_topology(3000), demo_knowledge(), catalog,
                      models=FenceModelLibrary(models=[model]), parts=library,
                      default_model=FenceModelChoice(model_id=MODEL_ID))
    reqs = derive_requirements(result.strategy, catalog)
    resolution = resolve_supply(reqs, catalog)
    return result, resolution, fulfill(resolution.requirements, catalog)


# --- 1 · containment reaches the panel's slot list ------------------------------

def test_a_contained_part_is_a_member_of_the_panel_under_a_path_key():
    """The identity is `<container>/<piece>`, and it is the ORDINARY slot key —
    the same string `demand`, the structure sheet, the elevation and the canvas
    already address a part by. A contained piece therefore needs no second kind
    of id, and inherits the uniqueness the slot key already had."""
    panel = _panel(_model(), _parts())
    keys = [s.slot_key for s in panel.slots]
    assert "kit/hinge" in keys and "kit/latch" in keys
    assert _slot(panel, "kit/hinge").contained_in == "kit"
    assert _slot(panel, "kit/hinge").role == "fixing"    # from the part it names
    assert _slot(panel, "kit/hinge").slot_kind == "contained"


def test_a_path_key_composes_so_nesting_costs_the_readers_nothing():
    panel = _panel(_model(), _parts(nested=True))
    washer = _slot(panel, "kit/hinge/washer")
    assert washer is not None and washer.contained_in == "kit/hinge"
    # 1 kit x 2 hinges x 2 washers. The multiplication is the whole point: a
    # panel that counted 2 would leave a fitter two washers short.
    assert washer.qty == 4


def test_contained_quantity_multiplies_by_its_container():
    """Two kits, two hinges each, is four hinges — not two."""
    spec = _spec(4)
    spec.fixings[0].qty_per_basis = 2
    panel = _panel(_model(spec), _parts())
    assert _slot(panel, "kit").qty == 2
    assert _slot(panel, "kit/hinge").qty == 4


def test_a_container_this_bay_placed_none_of_contains_nothing():
    """A slot the panel resolved to zero brings no members with it. Emitting its
    contents anyway would put pieces in the panel that arrived in a box nobody
    bought."""
    spec = _spec(4)
    spec.fixings[0].qty_per_basis = 0
    panel = _panel(_model(spec), _parts())
    assert [s for s in panel.slots if s.contained_in] == []


# --- 2 · containment does not become demand -------------------------------------

def test_a_contained_part_is_placed_but_never_bought():
    """The kit is on the BOM; its hinges are not. That is the divergence the
    feature exists to express — and the hinges are still members, which is what
    obligation 9 asks."""
    _, resolution, bom = _priced(_model(), _parts())
    assert not any(r.slot_key.startswith("kit/") for r in resolution.requirements)
    assert "GATE-KIT-1000" in {l.sku for l in bom.lines}


def test_a_contained_member_is_placeable_by_an_assembly_step_and_otherwise_unplaced():
    """Obligation 9, both halves, in one panel: a step that names `kit/hinge`
    places it; the latch nobody names is REPORTED rather than dropped."""
    model = _model(assembly=[
        AssemblyStep(key="fit", slots=["rail", "kit", "kit/hinge", "hinges"]),
    ])
    panel = _panel(model, _parts())
    plan = assembly_plan(model, panel)
    # the step's own order, which is the order a person does it in
    assert [p.slot_key for p in plan.steps[0].parts] == \
        ["rail", "kit", "kit/hinge", "hinges"]
    assert next(p for p in plan.steps[0].parts if p.slot_key == "kit/hinge").qty == 2
    assert [p.slot_key for p in plan.unplaced] == ["kit/latch"]


def test_a_step_naming_a_contained_part_that_does_not_exist_is_refused_at_authoring():
    model = _model(assembly=[AssemblyStep(key="fit", slots=["kit/handle"])])
    errors = validate_model(model, demo_catalog(), _parts())
    assert any("kit/handle" in e for e in errors)


# --- 3 · the credit -------------------------------------------------------------

def test_a_credit_is_a_supply_route_recorded_on_both_slots_it_relates():
    """The panel wants four hinges, two arrive in the kit, so it buys two.

    Neither number is silent: the demanding slot says how many came that way and
    from where, the contained slot says which slot it supplies. A reduced count
    with no source is the thing these two fields exist instead of.
    """
    panel = _panel(_model(_spec(4)), _parts())
    hinges, contained = _slot(panel, "hinges"), _slot(panel, "kit/hinge")
    assert hinges.qty == 2                       # what is left to buy
    assert hinges.credited_qty == 2              # ... and where the rest went
    assert hinges.credited_by == ["kit/hinge"]
    assert contained.credits_slot_key == "hinges" and contained.credited_qty == 2
    # the original requirement is recoverable, and the contained pieces are NOT
    # counted on the demanding slot as well — that would place four hinges twice
    assert hinges.qty + hinges.credited_qty == 4
    assert panel.credit_notes == []


def test_the_credit_reaches_the_bom_as_a_smaller_positive_line_never_a_negative_one():
    """A BOM line of -2 hinges is a document a purchaser cannot act on. What a
    credit produces is one honest positive line for a smaller number."""
    _, _, credited = _priced(_model(_spec(4)), _parts())
    _, _, uncredited = _priced(_model(_spec(4, credits={})), _parts())

    def hinges(bom):
        return next(l for l in bom.lines if l.sku == "HINGE-SET")

    assert all(l.purchase_qty > 0 for l in credited.lines)
    # one bay of a 3000 mm run at max span is two bays; 4 wanted, 2 credited each
    assert hinges(uncredited).purchase_qty == 2 * hinges(credited).purchase_qty
    assert credited.total_cents < uncredited.total_cents


def test_a_fully_credited_slot_asks_for_nothing_and_the_identity_still_closes():
    """Every hinge the panel wants arrives in the box, so it buys none — and the
    slot that asked produces no requirement line at all.

    A zero line would be a requirement no BOM line could peg to, which is the
    `covered == req_ids` identity the scenario suite asserts as `Sigma(parts) =
    BOM`. The trace does not vanish with the line: it is on the panel's own slot
    and in the `credit_contained` decision node.
    """
    result, resolution, bom = _priced(_model(_spec(2)), _parts())
    assert not any(r.slot_key == "hinges" for r in resolution.requirements)
    assert "HINGE-SET" not in {l.sku for l in bom.lines}

    req_ids = {r.id for r in resolution.requirements}
    covered = ({p for l in bom.lines for p in l.pegs}
               | {p for a in bom.allocations for p in a.pegs})
    assert covered == req_ids

    span = result.strategy.spans[0]
    hinges = _slot(span.panel, "hinges")
    assert hinges.qty == 0 and hinges.credited_qty == 2


def test_the_credit_is_explained_by_a_decision_node_in_both_languages():
    """A smaller purchase leaves no line of its own to trace, so the reduction
    gets a node — with the whole subtraction in it, because a reader given only
    the difference cannot check it."""
    from fenceai.decisions.explain import explain_node

    result, _, _ = _priced(_model(_spec(4)), _parts())
    node = next(n for n in result.graph.nodes if n.action == "credit_contained")
    assert node.payload["of"] == 4 and node.payload["qty"] == 2
    assert node.payload["remaining"] == 2 and node.payload["contained"] == "kit/hinge"
    assert node.scope_refs and node.scope_refs[0] in set(result.strategy.element_ids())
    for lang in ("en", "he"):
        line = explain_node(result.graph, node, lang=lang)
        assert line and "{" not in line


# --- 4 · over-crediting ---------------------------------------------------------

def test_a_kit_shipping_more_than_the_panel_wants_saves_only_what_it_wanted():
    """Over-crediting is worse than under-crediting: a saving is invisible on the
    finished document, because the line is simply not there. So the credit is
    capped at what the slot asked for, and the surplus is reported rather than
    quietly banked."""
    panel = _panel(_model(_spec(1)), _parts(hinges_per_kit=4))
    assert _slot(panel, "hinges").qty == 0
    assert _slot(panel, "hinges").credited_qty == 1        # not 4
    assert _slot(panel, "kit/hinge").credited_qty == 1     # ... and it says so
    assert [(n.kind, n.qty) for n in panel.credit_notes] == [("surplus", 3)]


def test_a_credit_aimed_at_a_slot_this_bay_does_not_build_credits_nothing():
    """The variant this bay resolved to has no hinge slot. `validate_model`
    cannot answer that — it is per bay — so the resolver reports it and takes no
    saving."""
    panel = _panel(_model(_spec(4, with_hinge_slot=False)), _parts())
    assert [(n.kind, n.slot_key) for n in panel.credit_notes] == \
        [("unmatched", "hinges")]
    assert _slot(panel, "kit/hinge").credited_qty == 0


def test_both_ways_a_credit_can_miss_reach_the_user_as_a_warning():
    """One sentence per model and slot, aggregated the way every other panel
    warning is — not one per bay of a sixty-bay fence."""
    spec = _spec(1)
    spec.fixings.append(FixingRule(
        key="spare", basis="per_panel", qty_per_basis=1,
        requirement=PartRequirement(part_id="kit-gate",
                                    credits={"latch": "latches"}),
    ))
    # `latches` exists in a VARIANT that no bay of this run reaches, so the model
    # validates clean and the credit still lands on nothing per bay
    variant = _spec(1)
    variant.fixings.append(FixingRule(
        key="latches", basis="per_panel", qty_per_basis=1,
        requirement=PartRequirement(part_id="fix-latch"),
    ))
    model = _model(spec, variants=[Variant(
        condition=Cmp(cmp="==", left=FieldRef(path="panel.vertical"),
                      right=Lit(value="raked")),
        spec=variant)])
    result, _, _ = _priced(model, _parts(hinges_per_kit=4))
    codes = {w.code for w in result.strategy.warnings}
    assert "contained_credit_surplus" in codes
    assert "contained_credit_unmatched" in codes
    surplus = next(w for w in result.strategy.warnings
                   if w.code == "contained_credit_surplus")
    assert surplus.params["qty"] == 3 and surplus.decision_ref
    assert surplus.element_refs      # named bays, not "somewhere in this fence"


# --- 5 · what the author is refused ---------------------------------------------

@pytest.mark.parametrize("credits, expected", [
    ({"handle": "hinges"}, "not a piece contained in this slot"),
    ({"hinge": "nowhere"}, "no spec of this model declares"),
    ({"hinge": "kit"}, "credits its own container"),
    ({"hinge": "rail"}, "A credit removes a purchase"),
])
def test_a_credit_that_could_not_work_is_refused_where_it_can_still_be_fixed(
        credits, expected):
    """Each of these would silently remove a purchase, or fail to, on every bay
    of every job. `validate_model` is the last moment an author can act."""
    errors = validate_model(_model(_spec(4, credits=credits)),
                           demo_catalog(), _parts())
    assert any(expected in e for e in errors), errors


def test_a_valid_credit_validates_clean():
    assert validate_model(_model(_spec(4)), demo_catalog(), _parts()) == []


def test_an_authored_slot_key_may_not_spell_a_path():
    """A key holding the separator could spell a path some container also
    produces, and then one string addresses two different pieces — the identity
    failure the whole scheme exists to avoid, arriving by the front door."""
    spec = _spec(4)
    spec.fixings[1].key = "kit/hinge"
    errors = validate_model(_model(spec), demo_catalog(), _parts())
    assert any("reserved" in e for e in errors)


def test_a_contained_path_that_collides_with_a_slot_key_is_a_duplicate():
    """Held to the same uniqueness a slot key always had, because it IS one."""
    spec = _spec(4)
    spec.fixings[0].key = "kit"
    spec.fixings[1].key = "kit"
    errors = validate_model(_model(spec), demo_catalog(), _parts())
    assert any("duplicate slot key" in e for e in errors)


def test_a_slot_naming_a_part_may_not_also_author_what_is_in_the_box():
    """The same refusal `role` and `eligibility` already earn: resolution
    OVERWRITES `contained` from the part, so a document carrying both would have
    its authored half deleted without a word."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="contained"):
        PartRequirement(part_id="kit-gate",
                        contained=[ContainedPart(key="hinge", role="fixing")])


def test_a_contained_piece_naming_a_part_may_not_author_what_that_part_says():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="one authority"):
        ContainedPart(key="hinge", part_id="fix-hinge", role="fixing")
    with pytest.raises(ValidationError, match="one authority"):
        ContainedPart(key="hinge", part_id="fix-hinge",
                      contains=[ContainedPart(key="washer", role="fixing")])


def test_a_contained_key_may_not_spell_a_path_either():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="path separator"):
        ContainedPart(key="hinge/pin", role="fixing")


def test_a_part_that_contains_itself_is_refused_by_name():
    """A library that cannot be built, not a fence — so it fails with the part in
    the message rather than as a RecursionError with nothing in it."""
    library = PartLibrary(parts=[
        Part(id="rail-3000", version=1, type="rail",
             spec=[SpecField(key="sku", value=["RAIL-3000"], agree="among")]),
        Part(id="kit-gate", version=1, type="gate_kit",
             spec=[SpecField(key="sku", value=["GATE-KIT-1000"], agree="among")],
             contains=[ContainedPart(key="inner", part_id="kit-gate")]),
    ])
    with pytest.raises(ValueError, match="contains itself"):
        resolve_model_parts(_model(_spec(4, credits={})), library)


def test_a_pin_on_a_contained_slot_is_refused_rather_than_ignored():
    """Nothing chooses a contained piece — it arrives inside whatever supplies
    its container — so there is no eligibility for a pin to narrow. Accepted and
    ignored would price a panel nobody asked for."""
    from fenceai.core.errors import RequestRefused

    resolved, _ = resolve_model_parts(_model(), _parts())
    ctx = PanelContext(centre_width_mm=1500, clear_width_mm=1500, height_mm=1800,
                       slot_skus={"kit/hinge": "HINGE-SET"})
    with pytest.raises(RequestRefused) as caught:
        resolve_panel(resolved.default_spec, ctx)
    assert caught.value.code == "sku_not_eligible"


# --- 6 · the run stays what a run has to be -------------------------------------

def test_a_contained_part_is_stamped_into_the_run_snapshot():
    """A run re-read through `library_at` would otherwise pin the kit and lose
    the hinge, and resolution would then put today's hinge into a fence that was
    priced against last year's."""
    result, _, _ = _priced(_model(), _parts())
    stamped = {u.part_id for u in result.run.part_snapshot}
    assert {"kit-gate", "fix-hinge", "fix-latch"} <= stamped


def test_credits_are_deterministic():
    a, _, bom_a = _priced(_model(), _parts())
    b, _, bom_b = _priced(_model(), _parts())
    assert a.strategy.model_dump() == b.strategy.model_dump()
    assert a.graph.model_dump() == b.graph.model_dump()
    assert bom_a.model_dump() == bom_b.model_dump()


def test_a_model_that_contains_nothing_resolves_exactly_as_it_did():
    """The whole feature is inert on a panel with no containment — which is every
    panel shipped before it, and the reason the compatibility gate did not move."""
    panel = _panel(_model(_spec(4, credits={}, with_hinge_slot=False)),
                   PartLibrary(parts=[
                       Part(id="rail-3000", version=1, type="rail",
                            spec=[SpecField(key="sku", value=["RAIL-3000"],
                                            agree="among")]),
                       Part(id="kit-gate", version=1, type="gate_kit",
                            spec=[SpecField(key="sku", value=["GATE-KIT-1000"],
                                            agree="among")]),
                   ]))
    assert [s.slot_key for s in panel.slots] == ["rail", "kit"]
    assert all(s.contained_in == "" and s.credited_qty == 0 for s in panel.slots)
    assert panel.credit_notes == []
