"""Cross-scenario invariants (docs/scenarios/golden-scenarios.md, mission §15)."""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.demand.derive import derive_requirements
from fenceai.fulfillment.fulfill import Inventory, InventoryItem, fulfill
from fenceai.fulfillment.supply import resolve_supply
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam
from fenceai.project.model import SiteConditions
from fenceai.strategy.generator import generate
from fenceai.strategy.overrides import ForceVertical, Override, PinPost
from fenceai.topology.model import (
    BasePayload,
    ElevationSamplePayload,
    GatePayload,
    Node,
    Run,
    Topology,
)
from fenceai.fencemodel.demo import M_SLAT, demo_models
from fenceai.fencemodel.model import (
    AssemblyStep, Distributed, FenceModel, FixingRule, FrameSlot, PanelSpec,
    PartRequirement, Variant,
)
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import ContainedPart, Part, PartLibrary, SpecField
from tests.conftest import add_interval_event, add_point_event, straight_topology
from tests.scenarios.continuity_fixture import (
    MAX_SPAN_MM, RUN_MM, board_library, catalog_with_two_colours, white_choice,
)

KIT = FenceModelChoice(model_id="M-KIT")
# --- the containment shape, so the batteries below can see one ------------------
#
# Every invariant in this file — Sigma(parts) = BOM, BOM line -> requirement ->
# element -> decision, determinism, cut-plan conservation — and the byte-compared
# compatibility gate beside it ran over a portfolio in which NO model contained
# anything. So the one shape where "what you buy" and "what you place" stop being
# the same list was outside the net that exists to catch exactly that class of
# drift, and the architecture review found two defects in it by hand.
#
# `M-KIT` is a bracket-kit line: a kit that ships two hinges, a panel that wants
# four, and a credit that makes it buy two. Its numbers are arithmetic a reader
# can check, and the gate now pins them.

def _kit_parts() -> list[Part]:
    return [
        Part(id="fix-hinge-set", version=1, type="fixing",
             name_i18n={"en": "Hinge set", "he": "סט צירים"},
             spec=[SpecField(key="sku", value=["HINGE-SET"], agree="among")]),
        Part(id="fix-latch", version=1, type="fixing",
             name_i18n={"en": "Latch", "he": "בריח"},
             spec=[SpecField(key="sku", value=["LATCH"], agree="among")]),
        # The container. What ships inside it is the PART's fact, which is why
        # nothing here reads `AssemblyKit.components` off the product: a kit's
        # component list is what the BOM note prints, and reading it as a claim
        # about this panel's members would credit hinges nobody asked it to place.
        Part(id="kit-hardware", version=1, type="gate_kit",
             name_i18n={"en": "Hardware kit", "he": "ערכת פרזול"},
             spec=[SpecField(key="sku", value=["GATE-KIT-1000"], agree="among")],
             contains=[
                 ContainedPart(key="hinge", part_id="fix-hinge-set", qty=2),
                 ContainedPart(key="latch", part_id="fix-latch", qty=1),
             ]),
    ]


def _kit_model() -> FenceModel:
    return FenceModel(
        id="M-KIT", version=1, name_i18n={"en": "Hardware kit line"},
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal",
                placement=Distributed(count=2, count_param="rails_per_span"),
                requirement=PartRequirement(part_id="rail-rail-3000",
                                            length_rule="centre_to_centre"),
            )],
            fixings=[
                FixingRule(key="kit", basis="per_panel", qty_per_basis=1,
                           requirement=PartRequirement(part_id="kit-hardware",
                                                       credits={"hinge": "hinges"})),
                # four wanted, two in the box: the panel buys two
                FixingRule(key="hinges", basis="per_panel", qty_per_basis=4,
                           requirement=PartRequirement(part_id="fix-hinge-set")),
            ],
        ),
        # every member placed or reported, which is obligation 9's own test —
        # `kit/latch` is deliberately named by no step
        assembly=[AssemblyStep(key="fit", slots=["rail", "kit", "kit/hinge"])],
    )


LIBRARY = FenceModelLibrary(models=[*demo_models().values(), _kit_model()])
# The part library those models name. Supplied at every `generate` that supplies a
# model library, because that is what the API does: a slot names a part, and a run
# with no library resolves a panel of 0 mm members.
PARTS = PartLibrary(parts=[*demo_parts(), *_kit_parts()])
SLAT = FenceModelChoice(model_id="M-SLAT")
VINYL = FenceModelChoice(model_id="M-VINYL")


def _fixtures():
    plain = straight_topology(6000)

    slope = straight_topology(6000)
    add_point_event(slope, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(slope, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    mixed = straight_topology(7000)
    add_interval_event(mixed, "run1", "base", 4000, 7000, BasePayload(surface="masonry_wall"))

    gated = straight_topology(5000)
    add_point_event(gated, "run1", "gate", 2000, GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))

    # A RAKED run. The suite had none: the demo KB carries an unscoped
    # PreferVertical(stepped) (K-STEP-SLOPE), so every sloped fixture above
    # resolves to stepped and `grep -rn raked tests/` found nothing. Raked is
    # the only mode that puts a span on `rail_cut_basis="slope"`, so the
    # slope-length branch in fencemodel/resolve.py was reachable by no test at
    # all — deleting it left the suite green while rails were cut to plan width
    # instead of slope length.
    raked = straight_topology(6000)
    add_point_event(raked, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(raked, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    # A fence whose rails are DERIVED continuous (contract obligation 14): four
    # 2400 mm bays under a 97 in maximum, 16 ft stock, so one piece crosses one
    # intermediate post. It is here rather than only in S18 because none of the
    # invariants below had ever run over a strategy containing a `MemberRun` —
    # a demand line pegged to TWO elements is a new shape for the traceability
    # chain, and a 4800 mm piece in a 4877 mm bar is a new one for the cut-plan
    # conservation check. It brings its own catalog and library; see the module
    # docstring in `continuity_fixture.py` for why it must not use the shared one.
    through_rail = straight_topology(RUN_MM)

    lshape = Topology(
        nodes=[
            Node(id="n1", x_mm=0, y_mm=0),
            Node(id="n2", x_mm=4000, y_mm=0),
            Node(id="n3", x_mm=4000, y_mm=3000),
        ],
        runs=[
            Run(id="runA", start_node_id="n1", end_node_id="n2"),
            Run(id="runB", start_node_id="n2", end_node_id="n3"),
        ],
    )
    # SLAT fixtures. Every shape above is M-LEGACY — two rails and eight screws —
    # so the whole infill path (a fitted pattern, a spread residual, per-crossing
    # fixings, a member cut to the panel height) sat outside this battery. Proved
    # by mutation: dropping infill lines from `BomLine.pegs` left the suite green
    # while the BOM -> requirement -> element -> decision chain was broken. The
    # raked one matters separately — it is the only mode that puts a span on
    # `rail_cut_basis="slope"` WITH members that must NOT follow the grade.
    slat_plain = straight_topology(6000)
    slat_raked = straight_topology(6000)
    add_point_event(slat_raked, "run1", "z0", 0, ElevationSamplePayload(z_mm=0))
    add_point_event(slat_raked, "run1", "z1", 6000, ElevationSamplePayload(z_mm=1000))

    # M-VINYL (S16). The only fixture whose POST and CAP are chosen by a
    # predicate rather than named, and the only one with no fixings at all — so
    # the traceability chain over a spec-matched post, and the Sigma(parts) = BOM
    # identity over a panel that buys no screws, are outside this battery
    # without it.
    vinyl = straight_topology(6000)

    return {
        "plain": (plain, [], None),
        "slope": (slope, [], None),
        "slat": (slat_plain, [], None, SLAT),
        "vinyl": (vinyl, [], None, VINYL),
        # containment: a kit shipping two of the four hinges this panel wants
        "kit": (straight_topology(6000), [], None, KIT),
        "slat_raked": (
            slat_raked,
            [Override(id="ov_rake", run_id="run1",
                      directive=ForceVertical(start_station_mm=0, end_station_mm=6000,
                                              mode="raked"))],
            None, SLAT,
        ),
        "raked": (
            raked,
            [Override(id="ov_rake", run_id="run1",
                      directive=ForceVertical(start_station_mm=0, end_station_mm=6000,
                                              mode="raked"))],
            None,
        ),
        "mixed_base": (mixed, [], None),
        "gated": (gated, [], None),
        "lshape": (lshape, [], None),
        "pinned": (straight_topology(6000), [Override(id="ov1", run_id="run1", directive=PinPost(station_mm=2000))], None),
        "with_inventory": (
            straight_topology(1200), [],
            Inventory(items=[InventoryItem(id="rem1", sku="RAIL-3000", kind="remnant", length_mm=1250)]),
        ),
        # A fence whose span limit came from a SITE rule rather than an
        # unconditioned one. Without it no invariant in this battery ever walked
        # a site-conditioned run: not traceability, not determinism, not
        # span-never-exceeds-max — while the exposure path produces a different
        # bay AND post count through `_segment_view`, and emits a decision-node
        # kind (`gap`) that `test_decision_edges_reference_existing_nodes` had
        # never seen.
        "site_exposure_c": (straight_topology(6000), [], None, SLAT,
                            SiteConditions(exposure_category="C")),
        # A fence whose PANEL — not its span limit — came from the site. The
        # fixture above conditions a knowledge RULE on the site; this one
        # conditions a fence model's own `Variant`, which is a different decision
        # path entirely: `select_variant`, the post matched at its own station
        # against the variant's rails, and the panel the run stores.
        #
        # Nothing in this battery had ever walked it. No demo model declares a
        # variant at all, so `select_variant` appeared in no scenario and no gate
        # run — which meant unbinding `site` from the condition context moved
        # nothing the release gate watches.
        "site_variant": (straight_topology(6000), [], None, SLAT,
                         SiteConditions(hvhz=True), None, site_variant_library()),
        "through_rail": (through_rail, [], None, white_choice(), None,
                         catalog_with_two_colours(), board_library()),
    }


def site_variant_library() -> FenceModelLibrary:
    """M-SLAT with one variant, conditioned on the site.

    Built from M-SLAT's own spec with a WIDER slat gap, so the variant's panel
    differs in slat count, slat positions, screw count and therefore in the BOM —
    while every slot key stays the one the model already declares, so nothing
    else about the document changes and the fixture tests the variant rather than
    a second model.
    """
    model = M_SLAT.model_copy(deep=True)
    wide = M_SLAT.default_spec.model_copy(deep=True)
    wide.infill.pattern[0].gap_after_mm = 60
    model.variants = [Variant(
        condition=Cmp(cmp="==", left=FieldRef(path="site.hvhz"),
                      right=Lit(value=True)),
        spec=wide,
    )]
    return FenceModelLibrary(models=[
        *(m for m in LIBRARY.models if m.id != model.id), model,
    ])


# The demo base plus one exposure-conditioned maximum. Separate from
# `demo_knowledge()` so every other fixture keeps resolving exactly what it did.
EXPOSURE_KB = KnowledgeBase(versions=[
    *demo_knowledge().versions,
    KnowledgeVersion(
        object_id="K-EXPOSURE-C", version=1, type="hard_constraint",
        title="max span 1200 on exposure C",
        condition=Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
                      right=Lit(value="C")),
        actions=[SetParam(param="max_span_mm", value=1200)],
    ),
])


@pytest.fixture(params=list(_fixtures()))
def spine(request):
    topo, overrides, inventory, *rest = _fixtures()[request.param]
    choice = rest[0] if rest else None
    site = rest[1] if len(rest) > 1 else None
    # A fixture may bring its OWN catalog and model library. Only the continuity
    # one does: its two rail stocks must not join the shared catalog, where they
    # would sit in front of every predicate eligibility in the portfolio (S15
    # records the same constraint for the same reason).
    catalog = rest[2] if len(rest) > 2 and rest[2] is not None else demo_catalog()
    library = rest[3] if len(rest) > 3 and rest[3] is not None else LIBRARY
    knowledge = EXPOSURE_KB if site is not None else demo_knowledge()
    result = generate(topo, knowledge, catalog, overrides=overrides,
                      models=library, parts=PARTS, default_model=choice, site=site)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog, inventory).requirements
    bom = fulfill(reqs, catalog, inventory)
    return result, reqs, bom, catalog, (topo, overrides, inventory, knowledge,
                                       choice, site, library)


@pytest.fixture()
def rerun(spine):
    """Regenerate the whole spine from the same inputs (real determinism check)."""
    _, _, _, catalog, (topo, overrides, inventory, knowledge,
                       choice, site, library) = spine
    result = generate(topo, knowledge, catalog, overrides=overrides,
                      models=library, parts=PARTS, default_model=choice, site=site)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog, inventory).requirements
    bom = fulfill(reqs, catalog, inventory)
    return result, reqs, bom


def test_span_never_exceeds_hard_max(spine):
    """1800 mm for every fixture built to the demo knowledge base; the
    continuity fixture carries its own maximum as a `layout_policy` contribution
    (97 in), which is the point of that fixture and not an exception to this
    rule."""
    result, _, _, _, rest = spine
    limit = MAX_SPAN_MM if rest[4] is not None and rest[4].model_id == "M-BOARD" else 1800
    assert all(sp.width_mm <= limit for sp in result.strategy.spans)


def test_cut_plans_feasible_and_conserving(spine):
    result, reqs, bom, catalog, _ = spine
    for sku, plan in bom.cut_plans.items():
        sem = catalog.product(sku).consumption
        demanded = sorted(
            r.cut_length_mm for r in reqs if r.sku == sku for _ in range(r.engineering_qty)
        )
        planned = sorted(p.length_mm for b in plan.bars for p in b.pieces)
        assert planned == demanded  # piece conservation
        for bar in plan.bars:
            physical = sum(p.length_mm for p in bar.pieces) + sem.kerf_mm * (len(bar.pieces) - 1)
            assert physical <= bar.stock_length_mm
            if bar.leftover_reusable:
                assert bar.leftover_mm >= sem.min_reusable_remnant_mm


def test_packages_never_undersupply(spine):
    result, reqs, bom, catalog, _ = spine
    for line in bom.lines:
        sem = catalog.product(line.sku).consumption
        if sem.kind == "packaged_discrete":
            supplied = line.purchase_qty * sem.qty_per_package
            allocated = sum(a.qty for a in bom.allocations if a.sku == line.sku)
            assert supplied + allocated >= line.engineering_qty
        elif sem.kind == "coverage_based":
            # purchase * den >= applications * num  <=>  supply covers demand exactly
            assert (
                line.purchase_qty * sem.qty_per_application.den
                >= line.engineering_qty * sem.qty_per_application.num
            )


def test_full_traceability_chain(spine):
    result, reqs, bom, _, _ = spine
    req_ids = {r.id for r in reqs}
    element_ids = set(result.strategy.element_ids())
    for r in reqs:
        assert r.pegs and all(e in element_ids for e in r.pegs)
        for e in r.pegs:
            assert result.graph.nodes_for_element(e)
    covered = {p for l in bom.lines for p in l.pegs} | {p for a in bom.allocations for p in a.pegs}
    assert covered == req_ids


def test_decision_edges_reference_existing_nodes(spine):
    result, _, _, _, _ = spine
    graph = result.graph
    node_ids = {n.id for n in graph.nodes}
    for e in graph.edges:
        assert e.from_id in node_ids and e.to_id in node_ids


def test_projected_remnants_meet_threshold(spine):
    result, _, bom, catalog, _ = spine
    for item in bom.projected_remnants:
        sem = catalog.product(item.sku).consumption
        assert item.length_mm >= sem.min_reusable_remnant_mm


def test_determinism(spine, rerun):
    """Real double-run: regenerate the whole spine from the same inputs and demand
    byte-identical output — across every fixture shape (test-review finding 1)."""
    result, reqs, bom, _, _ = spine
    result2, reqs2, bom2 = rerun
    assert result2.strategy.model_dump() == result.strategy.model_dump()
    assert result2.graph.model_dump() == result.graph.model_dump()
    assert result2.run.id == result.run.id
    assert [r.model_dump() for r in reqs2] == [r.model_dump() for r in reqs]
    assert bom2.model_dump() == bom.model_dump()


def test_knowledge_refs_resolve_to_snapshot(spine):
    """Every governed_by/defeated edge cites a version the run PINNED.

    Two pins, because there are two kinds of governing version and only one of
    them is a knowledge object. A model's `layout_policy` enters the evaluator as
    a synthesised version whose ref reads `M-BOARD#max_span_mm@v1`, and
    `_policy_knowledge` says outright that those "are never stored — the run's
    model snapshot (id, version, content hash) is what makes them reproducible".
    So the property is *pinned somewhere*, not *pinned in one list*.

    Widened when the `through_rail` fixture arrived: it is the first fixture in
    this battery to carry a `layout_policy` at all, and the assertion as written
    read a by-design ref as a dangling one. The narrower version was not
    protecting anything the wider one gives up — an unpinned ref still fails.
    """
    result, _, _, _, _ = spine
    snapshot = {f"{oid}@v{ver}" for oid, ver in result.run.knowledge_snapshot}
    models = {f"{m.model_id}@v{m.version}" for m in result.run.model_snapshot}
    for e in result.graph.edges:
        if e.knowledge_ref is None:
            continue
        ref = e.knowledge_ref
        if "#" in ref:      # a model policy contribution, pinned by its MODEL
            model_id, _, param_and_version = ref.partition("#")
            version = param_and_version.split("@")[-1]
            assert f"{model_id}@{version}" in models, ref
        else:
            assert ref in snapshot, ref


def test_no_panel_slot_asks_for_a_negative_quantity(spine):
    """A count below zero is not a small number, it is a broken one.

    The only thing in this engine that SUBTRACTS from a resolved quantity is a
    kit credit, and every way of getting one wrong ends here: crediting against
    the original requirement instead of what is left, letting two containers each
    spend the full amount, double-applying one source. All of them are invisible
    downstream — `demand/derive.py` skips a slot at or below zero, so the panel
    quietly buys nothing and places pieces nobody ordered, which is the "saving
    that leaves no mark" this whole feature is built to refuse.

    One assertion over every slot of every bay of every fixture, because the
    property is cheap to state and the failure is expensive to find.
    """
    result, _, _, _, _ = spine
    for span in result.strategy.spans:
        if span.panel is None:
            continue
        for slot in span.panel.slots:
            assert slot.qty >= 0, f"{span.id} {slot.slot_key} resolved to {slot.qty}"
            assert slot.credited_qty >= 0
            # what a credit moved can never exceed what was asked for
            assert slot.credited_qty <= slot.qty + slot.credited_qty


def test_coverage_and_cap_quantities_plain():
    """S01 spine: 5 posts -> 5 caps; 5 soil footings at 0.5 bag -> 3 bags (odd
    round-up boundary) — coverage semantics numerically pinned (finding 2/3)."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(6000), knowledge, catalog)
    reqs = derive_requirements(result.strategy, catalog)
    reqs = resolve_supply(reqs, catalog).requirements
    bom = fulfill(reqs, catalog)
    caps = next(l for l in bom.lines if l.sku == "POST-CAP")
    assert caps.engineering_qty == 5 and caps.purchase_qty == 5
    conc = next(l for l in bom.lines if l.sku == "CONC-25")
    assert conc.engineering_qty == 5  # applications
    assert conc.purchase_qty == 3     # ceil(5 * 1/2)


def test_sliver_span_warning_cites_preference():
    """Run shorter than the preferred minimum span -> surfaced sliver warning
    citing K-SLIVER (test-review finding 4)."""
    knowledge, catalog = demo_knowledge(), demo_catalog()
    result = generate(straight_topology(400), knowledge, catalog)
    assert [sp.width_mm for sp in result.strategy.spans] == [400]
    warning = next(w for w in result.strategy.warnings if w.code == "sliver_span")
    node = result.graph.node(warning.decision_ref)
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id) if e.type == "governed_by"}
    assert "K-SLIVER@v1" in refs


def test_missing_hard_knowledge_is_a_gap_not_a_generation_failure():
    """A run is never failed over a GAP (integration contract §3.2.4, ratified
    v1.1; docs/scenarios/golden-scenarios.md "Never-block").

    This invariant asserted the opposite until 2026-08-25, and the reversal is
    the point rather than a relaxation. Reading it the old way, an exposure
    category no published row covered produced no plan AT ALL — on `max_span_mm`,
    the single most important parameter in the system — and the exposure grew
    with every row the Knowledge Platform published. A bill of materials that
    visibly lacks something is more useful than no bill of materials.

    What still refuses is unchanged and is asserted in
    `tests/strategy/test_never_block.py`: a violated hard constraint, and input
    that cannot be carried out.
    """
    empty = KnowledgeBase(versions=[])
    result = generate(straight_topology(3000), empty, demo_catalog())

    assert result.strategy.spans, "a plan is produced with the holes named"
    # and the holes ARE named — every one addressable, and every one carrying the
    # sentence that makes it a work item rather than a filing
    kinds = {g.kind for g in result.strategy.gaps}
    assert {"uncovered_condition", "missing_value"} <= kinds
    assert all(g.would_close for g in result.strategy.gaps)
    assert all(g.closes_by == "knowledge" for g in result.strategy.gaps)
    # each gap is visible on the drawing too, never only in a report
    codes = {w.code for w in result.strategy.warnings}
    assert {g.because.code for g in result.strategy.gaps} <= codes


@pytest.mark.parametrize("name", sorted(_fixtures()))
def test_no_generated_run_carries_a_pinned_product(name):
    """`ResolvedSlot.pinned_sku` is a PREVIEW concept living on a persisted type.

    A drawer can ask "what would this panel cost in cedar", and the resolver
    narrows the slot's eligibility to answer — request-scoped, refused rather
    than bypassed, and labelled a what-if on screen. What it must never be is a
    product override that reached a stored run: it carries no `Override` record,
    no anchor and no decision node, so a run holding one would price a product
    nothing in the graph chose. The invariant was written down as a comment on
    the field; the architecture review pointed out that a comment is not an
    enforcement, and that a future caller wiring `slot_skus` into generation
    would create exactly the fifth category the architecture forbids.
    """
    topo, overrides, inventory, *rest = _fixtures()[name]
    catalog = rest[2] if len(rest) > 2 and rest[2] is not None else demo_catalog()
    library = rest[3] if len(rest) > 3 and rest[3] is not None else LIBRARY
    site = rest[1] if len(rest) > 1 else None
    result = generate(topo, EXPOSURE_KB if site is not None else demo_knowledge(),
                      catalog, overrides=overrides, models=library, parts=PARTS,
                      default_model=rest[0] if rest else None, site=site)
    pinned = [(sp.id, slot.slot_key, slot.pinned_sku)
              for sp in result.strategy.spans
              for slot in (sp.panel.slots if sp.panel else [])
              if slot.pinned_sku]
    assert not pinned, pinned
