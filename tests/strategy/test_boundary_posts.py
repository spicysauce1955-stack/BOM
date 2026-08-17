"""A post between two models, and the three ways a post spec can fail.

`generator.py`: "a segment is the smallest stretch that has one model." So a post
at a `fence_model` interval boundary — or a node post shared by two runs — is
adjacent to bays built to two DIFFERENT models, and both of their post specs
apply to the one post that stands between them.

This is not an arbitration. The candidate set is the INTERSECTION of the two
matched sets: an item covering both is the ordinary case and the whole point of
matching by spec, and an empty intersection is a true fact about that fence.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import (
    Capabilities, Catalog, IndivisibleDiscrete, Product,
)
from fenceai.core.errors import GenerationFailure
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, PostSlot,
)
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from fenceai.topology.model import FenceModelPayload, Node, Run, Topology
from tests.conftest import add_interval_event, straight_topology


# The demo catalog's own products, kept to the ones generation needs from
# knowledge. Deliberately NOT the whole demo catalog: `sole_excluding_term` asks
# which single term of a predicate excluded EVERYBODY, so an unrelated product
# that happens to satisfy one term changes the answer — the demo's own routed
# vinyl posts made a two-term predicate look like it had two discriminators.
_KEEP = ("POST-S", "POST-CAP", "CONC-25", "RAIL-3000", "SCREW-S10")


def _catalog(*posts: tuple[str, dict]):
    """What knowledge asks for, plus posts declaring whatever this test needs."""
    demo = demo_catalog()
    catalog = Catalog.of(*(demo.products[sku] for sku in _KEEP))
    for sku, attrs in posts:
        catalog.products[sku] = Product(
            sku=sku, name=sku, consumption=IndivisibleDiscrete(), price_cents=9000,
            attrs=attrs, capabilities=Capabilities(length_mm=2600, face_width_mm=100),
        )
    return catalog


def _model(model_id: str, predicate, cap=None) -> FenceModel:
    return FenceModel(
        id=model_id, version=1,
        post=PostSlot(
            key="post",
            requirement=PartRequirement(
                role="post", eligibility=Eligibility(predicate=predicate)),
            cap=cap,
        ),
        default_spec=PanelSpec(frame=[FrameSlot(
            key="rail", orientation="horizontal",
            placement=Distributed(count=2, count_param="rails_per_span",
                                  bottom_inset_mm=150, top_inset_mm=150),
            requirement=PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
        )]),
    )


def _is(field: str, value) -> Cmp:
    return Cmp(cmp="==", left=FieldRef(path=f"item.{field}"), right=Lit(value=value))


def _boundary_topology() -> Topology:
    """6000 mm, model A over 0–3000 and model B over 3000–6000. The model change
    is a structural boundary, so a post stands exactly at 3000."""
    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "mA", 0, 3000,
                       FenceModelPayload(model_id="M-A"))
    add_interval_event(topo, "run1", "mB", 3000, 6000,
                       FenceModelPayload(model_id="M-B"))
    return topo


def _run(models, catalog, topo=None, default=None):
    return generate(
        topo or _boundary_topology(), demo_knowledge(), catalog,
        models=FenceModelLibrary(models=models), default_model=default,
    )


# --- the intersection ---------------------------------------------------------

def test_the_boundary_post_is_one_both_lines_accept():
    """Model A wants the alpha material, model B wants a heavy grade; POST-BOTH
    is both. POST-A is alpha and light, POST-B is heavy and beta — each is
    acceptable to exactly one side, and neither may stand at the boundary."""
    catalog = _catalog(
        ("POST-A", {"material": "alpha", "grade": "light"}),
        ("POST-B", {"material": "beta", "grade": "heavy"}),
        ("POST-BOTH", {"material": "alpha", "grade": "heavy"}),
    )
    result = _run([_model("M-A", _is("material", "alpha")),
                   _model("M-B", _is("grade", "heavy"))], catalog)
    at = {p.station_mm: p.sku for p in result.strategy.posts}
    assert at[3000] == "POST-BOTH"
    # and the interior posts, claimed by one model each, keep their own answer
    assert at[1500] == "POST-A"
    assert at[4500] == "POST-B"


def test_a_side_with_no_opinion_leaves_the_other_sides_spec():
    """`post=None` is NO OPINION, not "must come from knowledge" — it is what
    every model shipped before this carried, so a boundary between an opinionated
    line and a legacy one resolves to the opinionated one rather than to a
    conflict."""
    catalog = _catalog(("POST-A", {"material": "alpha"}))
    plain = _model("M-B", _is("material", "alpha"))
    plain.post = None
    result = _run([_model("M-A", _is("material", "alpha")), plain], catalog)
    assert {p.station_mm: p.sku for p in result.strategy.posts}[3000] == "POST-A"


def test_neither_side_opinionated_leaves_the_knowledge_path_untouched():
    """The behaviour every run had before a model could own a post at all."""
    a, b = _model("M-A", _is("material", "x")), _model("M-B", _is("material", "x"))
    a.post = b.post = None
    result = _run([a, b], _catalog())
    assert {p.sku for p in result.strategy.posts} == {"POST-S"}


def test_a_node_post_intersects_every_run_that_touches_it():
    """A corner is one physical post and both runs' models claim it, for exactly
    the reason a `fence_model` boundary does."""
    topo = Topology(
        nodes=[Node(id="n1", x_mm=0, y_mm=0),
               Node(id="n2", x_mm=4000, y_mm=0, kind="junction"),
               Node(id="n3", x_mm=4000, y_mm=3000)],
        runs=[Run(id="runA", start_node_id="n1", end_node_id="n2"),
              Run(id="runB", start_node_id="n2", end_node_id="n3")],
    )
    add_interval_event(topo, "runA", "mA", 0, 4000, FenceModelPayload(model_id="M-A"))
    add_interval_event(topo, "runB", "mB", 0, 3000, FenceModelPayload(model_id="M-B"))
    catalog = _catalog(
        ("POST-A", {"material": "alpha", "grade": "light"}),
        ("POST-BOTH", {"material": "alpha", "grade": "heavy"}),
    )
    result = _run([_model("M-A", _is("material", "alpha")),
                   _model("M-B", _is("grade", "heavy"))], catalog, topo=topo)
    corner = next(p for p in result.strategy.posts if p.run_ref == "node:n2")
    assert corner.sku == "POST-BOTH"


# --- the three failures -------------------------------------------------------

def test_an_empty_intersection_is_a_conflict_naming_both_models():
    """Each side found candidates and no product satisfies both. Not a tie to be
    broken: a genuine disagreement between two product lines about the post that
    has to serve them both."""
    catalog = _catalog(("POST-A", {"material": "alpha", "grade": "light"}),
                       ("POST-B", {"material": "beta", "grade": "heavy"}))
    with pytest.raises(GenerationFailure) as exc:
        _run([_model("M-A", _is("material", "alpha")),
              _model("M-B", _is("grade", "heavy"))], catalog)
    assert exc.value.code == "post_spec_conflict"
    assert exc.value.params["station_mm"] == 3000
    assert "M-A@v1" in exc.value.params["models"]
    assert "M-B@v1" in exc.value.params["models"]


def test_routing_alone_excluding_everything_says_both_position_sets():
    """The diagnostic the split exists for. Both catalog posts pass the
    material term, so it admits somebody and ROUTING is the sole discriminator — which
    is what lets the sentence say "the panel wants 150, 1650; these are routed at
    200, 1700" instead of "no post found"."""
    catalog = _catalog(
        ("POST-V-A", {"material": "alpha", "routed_at_mm": [200, 1700]}),
        ("POST-V-B", {"material": "alpha", "routed_at_mm": [250, 1750]}),
    )
    routed = And(items=[
        _is("material", "alpha"),
        Cmp(cmp="==", left=FieldRef(path="item.routed_at_mm"),
            right=FieldRef(path="panel.rail_positions_mm")),
    ])
    with pytest.raises(GenerationFailure) as exc:
        generate(straight_topology(3000), demo_knowledge(), catalog,
                 models=FenceModelLibrary(models=[_model("M-V", routed)]),
                 default_model=FenceModelChoice(model_id="M-V"))
    assert exc.value.code == "post_routing_mismatch"
    assert exc.value.params["wanted"] == "150, 1650"
    assert exc.value.params["routed"] == "200, 1700; 250, 1750"


def test_when_routing_is_not_the_sole_cause_the_generic_code_answers():
    """`no_item_covers_part_spec`, and the distinction is honest rather than
    cosmetic: nothing in this catalog passes the material term AND nothing is
    routed where the panel wants it, so naming routing would send the reader to fix the wrong
    thing."""
    catalog = _catalog(("POST-X", {"material": "beta", "routed_at_mm": [200, 1700]}))
    routed = And(items=[
        _is("material", "alpha"),
        Cmp(cmp="==", left=FieldRef(path="item.routed_at_mm"),
            right=FieldRef(path="panel.rail_positions_mm")),
    ])
    with pytest.raises(GenerationFailure) as exc:
        generate(straight_topology(3000), demo_knowledge(), catalog,
                 models=FenceModelLibrary(models=[_model("M-V", routed)]),
                 default_model=FenceModelChoice(model_id="M-V"))
    assert exc.value.code == "no_item_covers_part_spec"
    assert exc.value.params["role"] == "post"
    assert exc.value.params["model"] == "M-V@v1"


def test_a_cap_nothing_covers_is_a_warning_and_the_fence_is_still_built():
    """The asymmetry the spec draws, and the reason for it: every other unsupplied
    slot is a panel visibly one part short, and a post is not a line item —
    without one there is no fence to be short of. A cap is cosmetic."""
    catalog = _catalog(("POST-A", {"material": "alpha"}))
    cap = PartRequirement(role="cap", eligibility=Eligibility(predicate=Cmp(
        cmp="==", left=FieldRef(path="item.fits_face_mm"),
        right=FieldRef(path="post.face_width_mm"))))   # nothing declares 100
    result = generate(
        straight_topology(3000), demo_knowledge(), catalog,
        models=FenceModelLibrary(
            models=[_model("M-A", _is("material", "alpha"), cap=cap)]),
        default_model=FenceModelChoice(model_id="M-A"),
    )
    assert {p.sku for p in result.strategy.posts} == {"POST-A"}
    assert all(p.cap_sku == "" for p in result.strategy.posts)
    warned = [w for w in result.strategy.warnings
              if w.code == "no_item_covers_part_spec"]
    assert warned and all(w.severity == "warning" for w in warned)
    assert warned[0].params["role"] == "cap"
