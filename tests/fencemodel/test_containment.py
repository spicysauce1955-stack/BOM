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
        Part(id="screw-s10", version=1, type="screw",
             spec=[SpecField(key="sku", value=["SCREW-S10"], agree="among")]),
        Part(id="kit-gate", version=1, type="gate_kit",
             spec=[SpecField(key="sku", value=["GATE-KIT-1000"], agree="among")],
             contains=[
                 ContainedPart(key="hinge", part_id="fix-hinge", qty=hinges_per_kit),
                 ContainedPart(key="latch", part_id="fix-latch", qty=1),
             ]),
    ])


def _spec(hinges_wanted: int, credits: dict[str, str] | None = None,
          with_hinge_slot: bool = True, screws: bool = False) -> PanelSpec:
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
    if screws:
        # a second UNDRAWN slot of a different role, so the role-agreement
        # refusal can be provoked without also tripping the drawn-target one
        fixings.append(FixingRule(
            key="screws", basis="per_panel", qty_per_basis=4,
            requirement=PartRequirement(part_id="screw-s10"),
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
    # ... and no box means no CREDIT either. Asserting only the absence of the
    # members left the panel free to have taken a saving from a kit it never
    # bought, which is the phantom saving in its purest form.
    assert _slot(panel, "hinges").qty == 4
    assert _slot(panel, "hinges").credited_qty == 0
    assert panel.credit_notes == []


# --- 2 · containment does not become demand -------------------------------------

def test_a_contained_part_is_placed_but_never_bought():
    """The kit is on the BOM; its hinges are not. That is the divergence the
    feature exists to express — and the hinges are still members, which is what
    obligation 9 asks.

    Asserted against the DEMAND lines and not only against the resolved ones,
    which is not fussiness: a contained slot carries no eligibility, so a demand
    line for one does not reach `requirements` at all — it lands in `unresolved`
    under a `no_eligible_item` ERROR. Checking the resolved list alone let the
    mutation that removes the skip survive with the whole suite green and every
    priced fence carrying two spurious errors per bay.
    """
    catalog = demo_catalog()
    result, resolution, bom = _priced(_model(), _parts())
    reqs = derive_requirements(result.strategy, catalog)
    assert not any(r.slot_key.startswith("kit/") for r in reqs)
    assert resolution.unresolved == [] and resolution.warnings == []
    assert "GATE-KIT-1000" in {l.sku for l in bom.lines}
    # ... and the hinges are not bought a second time under their own SKU: the
    # only HINGE-SET on this BOM is the two the panel still wants
    assert next(l for l in bom.lines if l.sku == "HINGE-SET").engineering_qty == \
        2 * len(result.strategy.spans)


def test_a_contained_member_is_placeable_by_an_assembly_step_and_otherwise_unplaced():
    """Obligation 9, both halves, in one panel: a step that names `kit/hinge`
    places it; the latch nobody names is REPORTED rather than dropped."""
    model = _model(assembly=[
        AssemblyStep(key="fit", slots=["rail", "kit", "kit/hinge", "hinges"]),
    ])
    # the step may NAME it, which is the half a check over `spec_requirements`
    # alone would refuse — leaving every contained piece permanently unplaceable
    # while the suite stayed green
    assert validate_model(model, demo_catalog(), _parts()) == []
    panel = _panel(model, _parts())
    plan = assembly_plan(model, panel)
    # the step's own order, which is the order a person does it in
    assert [p.slot_key for p in plan.steps[0].parts] == \
        ["rail", "kit", "kit/hinge", "hinges"]
    assert next(p for p in plan.steps[0].parts if p.slot_key == "kit/hinge").qty == 2
    assert [p.slot_key for p in plan.unplaced] == ["kit/latch"]


def test_a_slot_emptied_by_a_credit_is_neither_placed_nor_unplaced():
    """Every hinge came in the box, so the `hinges` slot has nothing to fit. It
    must not appear in `unplaced`: a "fit 0 hinges" row tells a fitter to look
    for parts that are not in the pile, which is the same lie `unplaced` exists
    to prevent, told the other way round. The pieces themselves ARE in the plan,
    under the path key of the container that brought them."""
    # the step NAMES `hinges`, which is the half that matters: with the slot
    # merely absent from every step, only the `unplaced` filter is exercised and
    # dropping the one on `by_slot` goes unnoticed
    model = _model(_spec(2), assembly=[
        AssemblyStep(key="fit", slots=["rail", "kit", "kit/hinge", "hinges"]),
    ])
    plan = assembly_plan(model, _panel(model, _parts()))
    assert [p.slot_key for p in plan.steps[0].parts] == ["rail", "kit", "kit/hinge"]
    assert "hinges" not in {p.slot_key for s in plan.steps for p in s.parts}
    assert [p.slot_key for p in plan.unplaced] == ["kit/latch"]
    assert all(p.qty > 0 for p in plan.unplaced)


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
    # ABSOLUTE, not a ratio: `uncredited == 2 * credited` also holds if both
    # halve. A 3000 mm run at max span is two bays, each wanting 4 hinges, each
    # kit shipping 2.
    assert hinges(uncredited).purchase_qty == 8
    assert hinges(credited).purchase_qty == 4
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
        # the VALUES, not merely that something rendered. Numbers and a path key
        # are language-independent, so both bundles are held to the same three:
        # asserting only "no braces survived" let every one of them be read from
        # the wrong payload field and still pass.
        assert "4" in line and "2" in line and "kit/hinge" in line, (lang, line)
        assert "None" not in line


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
    # the QUANTITY too: two pieces credited nothing, and a note that lost the
    # number cannot tell a reader how much was not saved
    assert [(n.kind, n.slot_key, n.qty) for n in panel.credit_notes] == \
        [("unmatched", "hinges", 2)]
    assert _slot(panel, "kit/hinge").credited_qty == 0
    assert _slot(panel, "kit/hinge").credits_slot_key == ""


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
    # EVERY affected bay, named. `element_refs` truthy passes when the warning
    # kept only the first of sixty, which is the aggregation quietly losing the
    # thing it aggregates.
    spans = {span.id for span in result.strategy.spans}
    assert set(surplus.element_refs) == spans
    assert surplus.params["n"] == len(spans)


# --- 5 · what the author is refused ---------------------------------------------

@pytest.mark.parametrize("credits, expected", [
    ({"handle": "hinges"}, "not a piece contained in this slot"),
    ({"hinge": "nowhere"}, "no spec of this model declares"),
    ({"hinge": "kit"}, "credits its own container"),
    ({"hinge": "rail"}, "drawn at a position"),
    # crediting a piece that ALSO arrives in a box. It saves nothing — nothing
    # is bought for a contained member — and it is not harmless: it deletes that
    # member from the panel, so the sheet says one latch fewer than the box
    # holds. Silent, and only ever visible to the fitter with the leftover.
    ({"hinge": "kit/latch"}, "no purchase to credit"),
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


def test_a_contained_piece_that_says_nothing_about_itself_is_refused():
    """It would reach the instruction sheet as a nameless row and the credit's
    agreement check as `""` — the same refusal a slot naming no part and
    declaring no product already earns, one level down."""
    library = _parts()
    kit = next(p for p in library.parts if p.id == "kit-gate")
    kit.contains = [ContainedPart(key="mystery", qty=1)]
    errors = validate_model(_model(_spec(4, credits={})), demo_catalog(), library)
    assert any("kit/mystery" in e and "declares no role" in e for e in errors), errors


def test_an_authored_slot_key_may_not_spell_a_path():
    """A key holding the separator could spell a path some container also
    produces, and then one string addresses two different pieces — the identity
    failure the whole scheme exists to avoid, arriving by the front door."""
    spec = _spec(4)
    spec.fixings[1].key = "kit/hinge"
    errors = validate_model(_model(spec), demo_catalog(), _parts())
    assert any("reserved" in e for e in errors)


def test_two_slots_sharing_one_key_is_a_duplicate():
    """Held to the same uniqueness a slot key always had, because it IS one.

    Named for what it checks. It was called "a contained path that collides with
    a slot key", which cannot happen and so was not what it built: an authored
    key may not contain the separator (the test above), so no authored key can
    ever spell a path. The widened walk over `spec_members` is belt-and-braces
    against that rule being relaxed, and this case — two authored keys the same —
    is what it shares with the check that predates containment.
    """
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
    ignored would price a panel nobody asked for.

    Its OWN code, deliberately: `sku_not_eligible` ends "choose one of the
    products offered for that part", and no product is ever offered for a
    contained piece — advice impossible to follow on a refusal the user causes
    by clicking."""
    from fenceai.core.errors import RequestRefused

    resolved, _ = resolve_model_parts(_model(), _parts())
    ctx = PanelContext(centre_width_mm=1500, clear_width_mm=1500, height_mm=1800,
                       slot_skus={"kit/hinge": "HINGE-SET"})
    with pytest.raises(RequestRefused) as caught:
        resolve_panel(resolved.default_spec, ctx)
    assert caught.value.code == "slot_not_purchasable"


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


# --- 7 · the two defects the architecture review found --------------------------

def test_a_credited_slots_own_contents_expand_from_what_the_panel_buys():
    """The regression for the ordering defect: credits settle BEFORE contents are
    expanded.

    A hinge ships two washers. The panel wants four hinges and the kit supplies
    two, so the panel buys two hinges (four washers) and the kit brings two (four
    washers) — eight washers for four hinges. Expanding the contents first read
    the count the panel WOULD have bought and produced twelve, and nothing
    downstream could have caught it: a contained member is not a purchase, so it
    never reaches the BOM or the parts ledger.
    """
    library = _parts()
    hinge = next(p for p in library.parts if p.id == "fix-hinge")
    hinge.contains = [ContainedPart(key="washer", part_id="fix-washer", qty=2)]
    panel = _panel(_model(_spec(4)), library)

    assert _slot(panel, "hinges").qty == 2          # bought
    assert _slot(panel, "hinges/washer").qty == 4   # ... and THEIR washers
    assert _slot(panel, "kit/hinge").qty == 2       # in the box
    assert _slot(panel, "kit/hinge/washer").qty == 4
    washers = sum(s.qty for s in panel.slots if s.slot_key.endswith("/washer"))
    assert washers == 8, "four hinges hold eight washers, however they arrived"


def test_a_credit_may_not_target_a_slot_that_is_drawn_at_a_position():
    """The regression for the elevation defect.

    A contained piece has an identity but no PLACE, and a frame slot's count is
    what `report/elevation.py` weights every fastener by. Crediting one made the
    drawing report three fasteners instead of five and invent two
    `fixings_unplaced`, on a fence that had not changed. Refused at authoring
    instead — hardware is what this feature is for, and a fixing has no drawn
    extent.
    """
    errors = validate_model(_model(_spec(4, credits={"hinge": "rail"})),
                            demo_catalog(), _parts())
    assert any("drawn at a position" in e for e in errors), errors


def test_crediting_a_fixing_leaves_the_drawing_alone():
    """The other half of the rule above: the case that IS allowed must not move
    the elevation. All eight screws are still fitted — four of them merely came
    in a box — so the drawing shows exactly what it always did."""
    from fenceai.report.elevation import panel_elevation

    def elevation(credits):
        spec = _spec(4, credits=credits, screws=True)
        return panel_elevation(_panel(_model(spec), _parts()), 1500, 1800)

    plain = elevation({})
    credited = elevation({"hinge": "hinges"})
    # The absolute list, because comparing two derived lists to each other passes
    # just as happily when BOTH are empty — which is what a mutation that stops
    # emitting fixings altogether produces.
    assert [(f.slot_key, f.qty) for f in plain.fixings] == \
        [("kit", 1), ("hinges", 4), ("screws", 4)]
    assert [(f.slot_key, f.qty) for f in credited.fixings] == \
        [(f.slot_key, f.qty) for f in plain.fixings]
    assert credited.fixings_unplaced == plain.fixings_unplaced == []


def test_a_credit_chain_is_refused_rather_than_answered_by_accident_of_order():
    """Crediting a container would change how many boxes the panel buys, which
    changes how many pieces are in them, which changes the credit. One resolution
    pass would answer that by whichever slot happened to resolve first."""
    spec = _spec(4)
    spec.fixings.append(FixingRule(
        key="outer", basis="per_panel", qty_per_basis=1,
        requirement=PartRequirement(part_id="kit-gate", credits={"latch": "kit"}),
    ))
    errors = validate_model(_model(spec), demo_catalog(), _parts())
    assert any("order the slots happen to resolve in" in e for e in errors), errors


def test_a_model_validates_the_same_with_and_without_a_part_library():
    """A step naming a contained path is checked against a vocabulary that only
    exists once the parts are resolved. Without a library that vocabulary is
    empty, and the same document was refused for a piece nobody had looked up —
    reachable as a `GenerationFailure` through `generate(..., parts=None)`."""
    model = _model(assembly=[
        AssemblyStep(key="fit", slots=["rail", "kit", "kit/hinge", "hinges"]),
    ])
    assert validate_model(model, demo_catalog(), _parts()) == []
    assert validate_model(model, demo_catalog(), None) == []
    # ... and an authored key that is simply wrong is still refused either way
    bad = _model(assembly=[AssemblyStep(key="fit", slots=["nonexistent"])])
    assert validate_model(bad, demo_catalog(), None) != []


# --- 8 · what the test review found untested ------------------------------------

def _two_kits(hinges_wanted: int) -> PanelSpec:
    """Two containers, each shipping two hinges, into one slot."""
    spec = _spec(hinges_wanted)
    spec.fixings.append(FixingRule(
        key="kitB", basis="per_panel", qty_per_basis=1,
        requirement=PartRequirement(part_id="kit-gate", credits={"hinge": "hinges"}),
    ))
    return spec


def test_two_containers_crediting_one_slot_spend_what_is_LEFT_not_what_was_asked():
    """The property with the sharpest failure and no test at all until now.

    Each credit is capped by what REMAINS on the target, not by the original
    requirement. Capping against the original lets both kits spend the full
    amount: three hinges wanted, four credited, `qty == -1`. That is not a small
    number, it is a broken one — and it is invisible, because `demand/derive.py`
    skips a slot at or below zero, so the panel buys nothing and places four.
    """
    panel = _panel(_model(_two_kits(3)), _parts())
    hinges = _slot(panel, "hinges")
    # 3 wanted; the first kit spends 2, the second is capped at the 1 that is
    # left. Capping both against the original 3 gives 4 credited and qty == -1.
    assert hinges.qty == 0
    assert hinges.credited_qty == 3
    assert hinges.qty >= 0
    # BOTH sources named, in the order they were spent. `credited_by` is a list
    # for exactly this case, and a `= [path]` in place of the append keeps only
    # whichever happened to be applied last.
    assert hinges.credited_by == ["kit/hinge", "kitB/hinge"]
    # the second kit had one hinge left over, and it saves nothing
    assert [(n.kind, n.contained_key, n.qty) for n in panel.credit_notes] == \
        [("surplus", "kitB/hinge", 1)]
    assert _slot(panel, "kit/hinge").credited_qty == 2
    assert _slot(panel, "kitB/hinge").credited_qty == 1


def test_two_containers_are_explained_by_ONE_node_whose_arithmetic_adds_up():
    """Per TARGET, not per credit. Two nodes each said "needs 4, 2 ship inside X,
    so the panel buys 0" — false twice, and said twice."""
    from fenceai.decisions.explain import explain_node

    result, _, _ = _priced(_model(_two_kits(4)), _parts())
    nodes = [n for n in result.graph.nodes if n.action == "credit_contained"]
    per_bay = {n.scope_refs[0] for n in nodes}
    assert len(nodes) == len(per_bay)          # one per bay, not one per source
    node = nodes[0]
    assert node.payload["of"] - node.payload["qty"] == node.payload["remaining"]
    assert node.payload["contained"] == "kit/hinge, kitB/hinge"
    for lang in ("en", "he"):
        line = explain_node(result.graph, node, lang=lang)
        assert "kit/hinge, kitB/hinge" in line and "None" not in line


def test_the_credit_node_carries_three_numbers_that_are_not_the_same_number():
    """4 wanted / 2 shipped makes `of`, `qty` and `remaining` read 4, 2, 2 — and
    2 is also `2 * 1`, so any of the three can be computed from the wrong field
    and still pass. Five wanted and two shipped tells them apart."""
    result, _, _ = _priced(_model(_spec(5)), _parts())
    node = next(n for n in result.graph.nodes if n.action == "credit_contained")
    assert (node.payload["of"], node.payload["qty"], node.payload["remaining"]) \
        == (5, 2, 3)


def test_the_stored_graph_carries_what_the_panel_did_with_containment():
    """`_panel_slots_payload`'s containment block could be deleted whole with a
    green suite: the compatibility gate pins `requirements` and `bom` and the
    decision graph is byte-compared nowhere."""
    result, _, _ = _priced(_model(_spec(4)), _parts())
    node = next(n for n in result.graph.nodes if n.action == "resolve_panel")
    by_key = {s["key"]: s for s in node.payload["slots"]}
    assert by_key["kit/hinge"]["contained_in"] == "kit"
    assert by_key["kit/hinge"]["credits"] == "hinges"
    assert by_key["hinges"]["credited_qty"] == 2
    assert by_key["hinges"]["credited_by"] == ["kit/hinge"]
    # a slot containment never touched says nothing about it
    assert "contained_in" not in by_key["rail"]
    assert "credited_qty" not in by_key["rail"]


def test_both_containment_warnings_render_in_both_languages():
    """They are graph nodes — `builder.add("conflict", warning.code, ...)` — and
    `test_explain_i18n` only walks the demo graph, which has no containment. So
    their templates existed, were key-paired, and were rendered by nothing."""
    from fenceai.decisions.explain import explain_node

    spec = _spec(1)
    spec.fixings.append(FixingRule(
        key="spare", basis="per_panel", qty_per_basis=1,
        requirement=PartRequirement(part_id="kit-gate", credits={"latch": "latches"}),
    ))
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

    seen = set()
    for warning in result.strategy.warnings:
        if not warning.code.startswith("contained_credit_"):
            continue
        node = next(n for n in result.graph.nodes if n.id == warning.decision_ref)
        for lang in ("en", "he"):
            line = explain_node(result.graph, node, lang=lang)
            assert line and "{" not in line and "None" not in line
            assert warning.params["slot"] in line
        seen.add(warning.code)
    assert seen == {"contained_credit_surplus", "contained_credit_unmatched"}


def test_resolution_never_writes_on_the_callers_part_library():
    """`_resolve_contained` fills `role` and `contains` onto contained pieces. If
    those are the LIBRARY's own objects rather than copies, resolving one model
    edits every other model that names the same part — and edits the object
    `library_at` hands back for a pinned snapshot, so a stored run would be
    re-read against a library this session mutated."""
    library = _parts()
    before = library.model_dump_json()
    resolve_model_parts(_model(), library)
    assert library.model_dump_json() == before


def test_a_nested_piece_can_be_the_source_of_a_credit():
    """`PartRequirement.credits` documents relative paths like `hinge/pin`, so
    the deep case has to work rather than merely be describable."""
    library = _parts()
    hinge = next(p for p in library.parts if p.id == "fix-hinge")
    hinge.contains = [ContainedPart(key="washer", part_id="fix-washer", qty=2)]
    spec = _spec(4, credits={"hinge/washer": "screws"}, screws=True)
    panel = _panel(_model(spec), library)

    # 1 kit x 2 hinges x 2 washers = 4, against a slot wanting 4 screws
    assert _slot(panel, "kit/hinge/washer").qty == 4
    assert _slot(panel, "kit/hinge/washer").credits_slot_key == "screws"
    assert _slot(panel, "screws").qty == 0
    assert _slot(panel, "screws").credited_by == ["kit/hinge/washer"]


def test_a_contained_piece_naming_a_part_that_does_not_exist_is_refused_by_name():
    """The panel would place a member nothing says anything about. Refused where
    the author can still fix it, rather than resolving to a roleless row."""
    library = _parts()
    library.parts = [p for p in library.parts if p.id != "fix-latch"]
    errors = validate_model(_model(), demo_catalog(), library)
    assert any("fix-latch" in e and "no active version" in e for e in errors), errors


def test_a_run_re_read_through_its_own_snapshot_resolves_the_same_contained_pieces():
    """What stamping contained parts is FOR. `library_at` pins the versions the
    run recorded; without the hinge in that snapshot the re-read resolves today's
    part into a fence that was priced against another one."""
    from fenceai.parts.resolve import library_at

    result, _, _ = _priced(_model(), _parts())
    pinned = library_at(_parts(), result.run.part_snapshot)
    replayed = _panel(_model(), pinned)
    original = result.strategy.spans[0].panel

    assert {(s.slot_key, s.qty) for s in replayed.slots if s.contained_in} == \
        {(s.slot_key, s.qty) for s in original.slots if s.contained_in}


def test_a_part_may_not_hold_two_pieces_with_one_key():
    """One path would name both, and every reader addresses a member by its
    path."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="two pieces called"):
        Part(id="kit", version=1, type="gate_kit",
             spec=[SpecField(key="sku", value=["GATE-KIT-1000"], agree="among")],
             contains=[ContainedPart(key="hinge", role="fixing"),
                       ContainedPart(key="hinge", role="fixing")])
    # ... at every depth, not only the top one
    with pytest.raises(ValidationError, match="two pieces called"):
        ContainedPart(key="hinge", role="fixing",
                      contains=[ContainedPart(key="pin", role="fixing"),
                                ContainedPart(key="pin", role="fixing")])


def test_a_contained_piece_must_bring_at_least_one_of_itself():
    """`qty=0` is a piece that is in the box and not in the box."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContainedPart(key="hinge", role="fixing", qty=0)


def test_the_structure_sheet_lists_what_was_BOUGHT_and_the_plan_what_is_PLACED():
    """The one place the two documents deliberately disagree, asserted so a
    change in either direction is loud.

    `report/structure.py` builds a bay's parts by INVERTING pegs, and a contained
    member has none — it is not a purchase. So `kit/hinge` is absent there and
    present in the assembly plan, and the pair is the whole point rather than a
    gap: the sheet answers "what did this bay cost", the plan answers "what does
    a fitter put in it".
    """
    from fenceai.report.structure import build_structure

    model = _model(assembly=[
        AssemblyStep(key="fit", slots=["rail", "kit", "kit/hinge", "hinges"]),
    ])
    result, resolution, bom = _priced(model, _parts())
    report = build_structure(straight_topology(3000), result.strategy,
                             resolution.requirements, bom, run_id=result.run.id)

    bay = next(b for section in report.sections for b in section.bays)
    sheet = {part.slot_key for part in bay.parts}
    assert "kit" in sheet and "hinges" in sheet     # bought, so they are costed
    assert not any(k.startswith("kit/") for k in sheet)

    placed = {p.slot_key for step in assembly_plan(model, result.strategy.spans[0].panel).steps
              for p in step.parts}
    assert "kit/hinge" in placed


def test_a_model_carrying_credits_survives_the_round_trip_the_editor_makes():
    """The editor PUTs the whole document back. A field the schema has and the
    round trip drops is a credit that silently stops applying on the next save —
    and `credits` is authored, so it is the half that cannot be refilled from a
    part."""
    from fenceai.fencemodel.model import FenceModel

    model = _model()
    back = FenceModel.model_validate(model.model_dump())
    assert back == model
    assert back.default_spec.fixings[0].requirement.credits == {"hinge": "hinges"}
