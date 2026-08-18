"""The defects the architecture review of the panel waves found.

Each test names the failure it prevents. Several of these passed a green suite
before the review, which is the point of writing them down.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import GenerationFailure
from fenceai.fencemodel.demo import M_SLAT, slat_model
from fenceai.fencemodel.fit import fit_pattern
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import Member, PartRequirement, Eligibility, EligibleItem
from fenceai.fencemodel.preview import PreviewRequest, preview_panel
from fenceai.fencemodel.resolve import PanelContext, resolve_panel
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeVersion, SetParam
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.parts.resolve import resolve_model_parts
from fenceai.report.elevation import panel_elevation
from fenceai.strategy.generator import generate
from fenceai.strategy.layout import layout_segment
from tests.conftest import straight_topology


# The library the built-in models name. A width and a face height are the part's
# now, so a test that hands `resolve_panel` an authored document hands it a member
# 0 mm wide — resolution is where those numbers arrive, upstream of everything here.
PARTS = PartLibrary(parts=demo_parts())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCEAI_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("FENCEAI_AI", "stub")
    with TestClient(app) as c:
        yield c


# --- BLOCKER 1: two projects collided on one run id ---------------------------

def test_two_projects_with_the_same_fence_do_not_share_a_run_id():
    """`project_id` is bound as a scope dimension, so a project-scoped rule
    changes the fence without changing any other digest input. Colliding ids +
    INSERT OR IGNORE meant the second project's user pressed Generate, saw their
    own answer, and every later read served the FIRST project's fence."""
    topo, catalog = straight_topology(6000), demo_catalog()
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-PROJ", version=1, type="company_rule", title="3 rails for A",
        scope={"project_id": "proj_a"},
        actions=[SetParam(param="rails_per_span", value=3)]))

    a = generate(topo, kb, catalog, project_id="proj_a")
    b = generate(topo, kb, catalog, project_id="proj_b")

    assert a.strategy.spans[0].rail_count == 3
    assert b.strategy.spans[0].rail_count == 2
    assert a.run.id != b.run.id, "two different fences under one id"


def test_the_same_project_regenerated_keeps_its_id():
    """The digest must still be a content address, not a nonce."""
    topo, kb, catalog = straight_topology(6000), demo_knowledge(), demo_catalog()
    assert generate(topo, kb, catalog, project_id="p").run.id == \
        generate(topo, kb, catalog, project_id="p").run.id


def test_two_projects_both_keep_their_run(client):
    pids = [client.post("/api/projects", json={"name": n}).json()["id"]
            for n in ("A", "B")]
    for pid in pids:
        client.put(f"/api/projects/{pid}/topology", json={
            "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                      {"id": "n2", "x_mm": 6000, "y_mm": 0}],
            "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}]})
        client.post(f"/api/projects/{pid}/generate")
    for pid in pids:
        assert client.get(f"/api/projects/{pid}/runs").json(), f"{pid} lost its run"


# --- BLOCKER 2: the M-LEGACY seam ignored the library and the pin -------------

def test_the_compatibility_model_id_cannot_be_authored(client):
    """Its eligibility is rebuilt per run from resolved demand SKUs, so a
    published v2 would be offered by the picker, priced by the preview and
    reported on by the impact preview — and then ignored at generation."""
    body = {"id": "M-LEGACY", "version": 1, "name_i18n": {"en": "x", "he": "x"},
            "default_spec": {"frame": []}}
    r = client.post("/api/fence-models", json=body)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "fence_model_reserved"
    assert client.put("/api/fence-models/M-LEGACY/draft",
                      json=body).status_code == 409


def test_a_pin_to_a_legacy_version_that_cannot_exist_is_refused():
    """Silently falling back to v1 is how the picker, the preview and the fence
    end up disagreeing."""
    with pytest.raises(GenerationFailure) as exc:
        generate(straight_topology(3000), demo_knowledge(), demo_catalog(),
                 models=FenceModelLibrary(models=[M_SLAT]),
                 default_model=FenceModelChoice(model_id="M-LEGACY", version_pin=2))
    assert exc.value.code == "fence_model_not_found"


def test_pinning_the_legacy_version_that_does_exist_still_works():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog(),
                      default_model=FenceModelChoice(model_id="M-LEGACY", version_pin=1))
    assert result.strategy.spans[0].panel.model_ref == "M-LEGACY@v1"


# --- MAJOR 3: a multi-member pattern drew a wrong picture ---------------------

def two_member_model():
    # RESOLVED, then edited: the widths below are the subject of this test, and a
    # second resolution would overwrite them with the part's. That is the same
    # order generation runs in — resolve, then read — with the edit standing in for
    # a part that declares 200.
    model, _ = resolve_model_parts(slat_model(), PARTS)
    narrow = Member(
        key="narrow", width_mm=50, gap_after_mm=20,
        requirement=PartRequirement(
            role="infill", qty=1, length_rule="panel_height",
            eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")])),
    )
    model.default_spec.infill.pattern[0].width_mm = 200
    model.default_spec.infill.pattern.append(narrow)
    return model


def test_a_two_member_pattern_draws_exactly_what_it_bought():
    """The walk needs EVERY member of the cycle, because a position depends on
    everything before it. Approximating the cycle as this member repeated drew
    thirteen wide slats where seven were bought, running clean out of the panel."""
    ctx = PanelContext(centre_width_mm=2000, clear_width_mm=2000, height_mm=1800)
    panel = resolve_panel(two_member_model().default_spec, ctx)
    elevation = panel_elevation(panel, 2000, 1800)

    for slot in panel.slots:
        if slot.fit is None:
            continue
        drawn = [m for m in elevation.members if m.slot_key == slot.slot_key]
        assert len(drawn) == slot.qty, f"{slot.slot_key}: drew {len(drawn)}, bought {slot.qty}"

    infill = sorted((m for m in elevation.members if m.role == "infill"),
                    key=lambda m: m.x_mm)
    assert infill[-1].x_mm + infill[-1].w_mm <= 2000, "a member runs out of the panel"
    for a, b in zip(infill, infill[1:]):
        assert b.x_mm >= a.x_mm + a.w_mm, "two members occupy the same millimetres"
    assert {m.w_mm for m in infill} == {200, 50}, "both member widths must be drawn"


# --- MAJOR 4: the sphere test missed the openings against the posts -----------

def test_the_openings_include_the_two_against_the_posts():
    """A hole is a hole whether it is between two slats or between a slat and a
    post. `center` justification folds the whole residual into the margins and
    zeroes `residual_mm`, so measuring gaps alone saw nothing."""
    fit = fit_pattern(2000, [300], [50], justification="center",
                      excess="truncate", edge_margin_mm=0)
    assert max(fit.gaps_mm) == 50, "the between-member gaps look innocent"
    assert max(fit.openings_mm) > 100, "and the real openings do not"
    assert sum(fit.openings_mm) + 300 * fit.count == 2000, "the openings must tile the axis"


def test_a_truncated_residual_at_the_far_end_is_an_opening_too():
    fit = fit_pattern(2000, [300], [50], justification="start",
                      excess="truncate", edge_margin_mm=0)
    assert fit.residual_mm > 100
    assert max(fit.openings_mm) == fit.residual_mm


def test_a_gap_against_a_post_trips_the_sphere_test():
    model, _ = resolve_model_parts(slat_model(), PARTS)
    model.default_spec.infill.justification = "center"
    model.default_spec.infill.excess = "truncate"
    model.default_spec.infill.pattern[0].width_mm = 300
    model.default_spec.infill.pattern[0].gap_after_mm = 50
    result = generate(
        straight_topology(5000), demo_knowledge(), demo_catalog(),
        models=FenceModelLibrary(models=[model]),
        default_model=FenceModelChoice(model_id="M-SLAT"),
    )
    assert "clear_gap_exceeded" in [w.code for w in result.strategy.warnings]


# --- MAJOR 5: an exact width lost to a min() with nothing recorded ------------

def test_an_exact_width_over_the_maximum_is_a_conflict_not_a_clamp():
    """Clamping produced bays of NEITHER width and then reported the width nobody
    used. Two rules of different kinds, both stated: that is a conflict."""
    result = layout_segment(5000, 1800, exact_mm=2400)
    assert result.exact_over_max
    assert result.remainder_mm is None
    assert max(result.widths) <= 1800


def test_the_conflict_reaches_the_user_citing_both_rules():
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-EXACT", version=1, type="company_rule", title="2400 bays",
        scope={"series": "M-SLAT"},
        actions=[SetParam(param="exact_span_mm", value=2400)]))
    result = generate(
        straight_topology(5000), kb, demo_catalog(),
        models=FenceModelLibrary(models=[M_SLAT]),
        default_model=FenceModelChoice(model_id="M-SLAT"))

    warning = next(w for w in result.strategy.warnings
                   if w.code == "exact_span_over_max")
    assert warning.params["exact_mm"] == 2400 and warning.params["max_mm"] == 1800
    assert "span_not_exact" not in [w.code for w in result.strategy.warnings], \
        "the remainder warning would report a width nobody used"
    node = next(n for n in result.graph.nodes if n.action == "exact_span_over_max")
    refs = {e.knowledge_ref for e in result.graph.in_edges(node.id)}
    assert len(refs) == 2, f"a conflict must cite both contenders, cited {refs}"


# --- MAJOR 7: the preview's money column double-counted -----------------------

def test_the_preview_rows_sum_to_the_total_when_two_slots_share_a_product():
    """A frame with named top and bottom rail slots is the ordinary case, and
    `fulfill()` emits one line per SKU. Handing that line to both rows made the
    visible column add to twice the total printed beneath it."""
    model = slat_model().model_copy(deep=True)
    frame = model.default_spec.frame[0]
    top = frame.model_copy(deep=True, update={"key": "rail_top"})
    bottom = frame.model_copy(deep=True, update={"key": "rail_bottom"})
    model.default_spec.frame = [top, bottom]

    preview = preview_panel(model, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    rows = {p.slot_key: p for p in preview.parts}
    assert {"rail_top", "rail_bottom"} <= set(rows)
    assert sum(p.total_cents for p in preview.parts) == preview.total_cents
    assert rows["rail_top"].shares_sku_with == ["rail_bottom"]
    # the bar count belongs to one row: half a bar bought is not a thing
    assert rows["rail_bottom"].purchase_qty == 0


def test_the_ordinary_one_slot_per_product_panel_is_unchanged():
    preview = preview_panel(M_SLAT, PreviewRequest(height_mm=1800, width_mm=2500),
                            demo_catalog(), part_library=PARTS)
    assert preview.parts
    assert sum(p.total_cents for p in preview.parts) == preview.total_cents
    assert all(p.shares_sku_with == [] for p in preview.parts)
    assert all(p.purchase_qty > 0 for p in preview.parts)


# --- MINOR 12/13: honesty of the two read models ------------------------------

def test_the_preview_reports_that_the_model_it_drew_is_invalid():
    """A model using an unbuilt feature previewed as though the feature worked —
    exactly what the unsupported-feature table exists to prevent."""
    model = slat_model().model_copy(deep=True)
    model.default_spec.infill.supply = "assembly"     # still refused at load
    preview = preview_panel(model, PreviewRequest(), demo_catalog(),
                            part_library=PARTS)
    assert preview.invalid, "the preview claims a model generation would refuse"
    assert preview.parts, "and still shows what it can"


def test_the_bay_drawing_names_its_products_like_the_preview_does(client):
    """One read model with two truths is how a client ends up branching on which
    endpoint it came from."""
    pid = client.post("/api/projects", json={"name": "drawn"}).json()["id"]
    client.put(f"/api/projects/{pid}/topology", json={
        "nodes": [{"id": "n1", "x_mm": 0, "y_mm": 0},
                  {"id": "n2", "x_mm": 3000, "y_mm": 0}],
        "runs": [{"id": "run1", "start_node_id": "n1", "end_node_id": "n2"}]})
    client.put(f"/api/projects/{pid}/fence-model", json={"model_id": "M-SLAT"})
    run_id = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]

    report = client.get(f"/api/runs/{run_id}/structure").json()
    members = [m for section in report["sections"] for bay in section["bays"]
               for m in bay["elevation"]["members"]]
    assert members
    slats = [m for m in members if m["slot_key"] == "slat"]
    assert slats and all(m["sku"] == "SLAT-100" for m in slats)


# --- the two-tier visualizer review ------------------------------------------
#
# A second review, of the arc that put the fence on two drawings. Its findings
# are about what the GRAPH and the READ MODEL say, so they are tested here beside
# the panel-wave defects rather than in the drawing that consumes them.

def _channel_run():
    """A section built entirely to M-SLAT@v2 — the model whose slats are cut to
    1665 instead of 1800, which is the whole reason the version exists."""
    from fenceai.fencemodel.demo import M_LEGACY, M_SLAT_V2

    library = FenceModelLibrary(models=[M_LEGACY, M_SLAT, M_SLAT_V2])
    return generate(straight_topology(6000), demo_knowledge(), demo_catalog(),
                    models=library, parts=PARTS,
                    default_model=FenceModelChoice(model_id="M-SLAT", version_pin=2))


def test_the_length_a_slat_is_cut_to_is_derivable_from_the_decision_graph():
    """MAJOR 3. `/explain` said "Panel M-SLAT@v2 built from 12 infill" and could
    not say 1665 — the number the version exists for. `panel_height` and
    `centre_to_centre` are functions of `create_span`'s payload, which is an
    input edge of the panel node; `between_frame` is a function of the frame
    slots' positions, their face heights and the two engagements, and none of
    those appeared in any node.

    Hand-derived, in a 1500 mm bay 1800 mm high:

        start = 50 (channel centreline) + 60//2 (its face) − 15 (engagement) = 65
        end   = 1750 (rail centreline)  − 40//2 (its face) + 0               = 1730
        slat  = 1730 − 65                                                    = 1665
    """
    from fenceai.decisions.explain import explain_node

    result = _channel_run()
    node = next(n for n in result.graph.nodes if n.action == "resolve_panel")
    slat = next(s for s in node.payload["slots"] if s["key"] == "slat")

    assert (slat["length_mm"], slat["span_start_mm"]) == (1665, 65)
    base, top = slat["between"]["base"], slat["between"]["top"]
    assert (base["slot"], base["position_mm"], base["thickness_mm"],
            base["engagement_mm"]) == ("bottom_channel", 50, 60, 15)
    assert (top["slot"], top["position_mm"], top["thickness_mm"],
            top["engagement_mm"]) == ("top_rail", 1750, 40, 0)
    # the reported terms ARE the subtraction, so a reader can redo it
    start = base["position_mm"] + base["thickness_mm"] // 2 - base["engagement_mm"]
    end = top["position_mm"] - top["thickness_mm"] // 2 + top["engagement_mm"]
    assert (start, end - start) == (slat["span_start_mm"], slat["length_mm"])
    assert all(isinstance(v, int) for v in (start, end, slat["length_mm"]))

    for lang, cut in (("en", "1665 mm"), ("he", '1665 מ"מ')):
        assert cut in explain_node(result.graph, node, lang=lang)


def test_the_rule_that_set_the_rail_count_reaches_the_panel_it_measured():
    """MAJOR 3, the other half. `positions_mm` under a `Distributed` slot depend
    on `rails_per_span`, so the rail count sits upstream of a `between_frame` cut
    length — but `resolve_span_quantities` was emitted AFTER the span loop, and
    the chain from a slat's length back to the rule that set the count existed
    only as a shared `scope_refs`, which nothing can walk.
    """
    kb = demo_knowledge()
    # scoped to the project, so it beats the demo's own K-RAILS on specificity
    # rather than tying with it
    kb.versions.append(KnowledgeVersion(
        object_id="K-THREE-RAILS", version=1, type="company_rule",
        title="three rails", scope={"project_id": "proj_rails"},
        actions=[SetParam(param="rails_per_span", value=3)]))
    result = generate(straight_topology(6000), kb, demo_catalog(),
                      project_id="proj_rails")

    panel = next(n for n in result.graph.nodes if n.action == "resolve_panel")
    quantities = next(n for n in result.graph.nodes
                      if n.action == "resolve_span_quantities")
    assert quantities.payload["rails_per_span"] == 3
    inputs = [e.from_id for e in result.graph.in_edges(panel.id)]
    assert quantities.id in inputs
    # and the bay whose height the other length rules read, which reached this
    # node only through a variant node — i.e. never, on a model without variants
    span_node = next(n for n in result.graph.nodes_for_element(
        result.strategy.spans[0].id) if n.action == "create_span")
    assert span_node.id in inputs
    # and so the governing version is reachable FROM the panel, not merely nearby
    refs = {e.knowledge_ref for anc in result.graph.ancestors(panel.id)
            for e in result.graph.in_edges(anc.id) if e.type == "governed_by"}
    assert "K-THREE-RAILS@v1" in refs


def test_the_embedment_that_is_drawn_cites_the_version_that_decided_it():
    """MAJOR 6. `post_embed_mm` was resolved with its refs and written onto every
    post, but `embed_refs` was cited ONLY in the failure branch — so in the
    ordinary case no node recorded that 600 mm had been decided, or by which
    rule. This arc promoted `embed_mm` to a persisted field and then to a
    dimension on a drawing, so two versions of the rule drew two different
    footings with no `defeated` edge anywhere.
    """
    from fenceai.decisions.explain import explain_node

    result = generate(straight_topology(6000), demo_knowledge(), demo_catalog())
    buried = [p.id for p in result.strategy.posts if p.mounting == "ground"]
    node = next(n for n in result.graph.nodes
                if n.action == "resolve_post_embedment")

    assert node.payload["embed_mm"] == 600
    assert sorted(node.scope_refs) == sorted(buried)
    assert all(p.embed_mm == 600 for p in result.strategy.posts if p.id in buried)
    governed = {e.knowledge_ref for e in result.graph.in_edges(node.id)
                if e.type == "governed_by"}
    assert governed == {"K-POST-EMBED@v1"}
    for lang in ("en", "he"):
        assert "600" in explain_node(result.graph, node, lang=lang)


def test_a_wall_mounted_fence_records_no_embedment_it_never_spent():
    """The other side of that node: a post bolted to a wall embeds nothing, so a
    node claiming 600 mm underground would explain a footing that is not there."""
    from fenceai.topology.model import BasePayload
    from tests.conftest import add_interval_event

    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "b", 0, 6000, BasePayload(surface="masonry_wall"))
    result = generate(topo, demo_knowledge(), demo_catalog())

    assert all(p.mounting == "masonry" for p in result.strategy.posts)
    assert all(p.embed_mm == 0 for p in result.strategy.posts)
    assert not [n for n in result.graph.nodes
                if n.action == "resolve_post_embedment"]


def test_the_post_the_sheet_draws_is_the_post_the_length_check_measured():
    """MAJOR 4. The macro drawing computed a post's top as `max(adjacent bay
    tops)` in JS — the same question `_check_post_lengths` answers, minus the
    tilt correction it does not have — so a run that warns a post is short drew
    a post that looks fine.

    Hand-derived: 1800 mm panels on flat ground, posts leaning 30°. The top sits
    at 1800, but reaching it takes 1800 / cos 30° = 2078 mm of post, and with
    600 mm buried that is 2678 mm against a 2600 mm POST-S.
    """
    from fenceai.fulfillment.pipeline import price_strategy
    from fenceai.report.structure import build_structure
    from fenceai.topology.model import PostTiltPayload
    from tests.conftest import add_interval_event

    topo = straight_topology(6000)
    add_interval_event(topo, "run1", "tilt", 0, 6000,
                       PostTiltPayload(mode="custom", tilt_deg=30))
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    priced = price_strategy(result.strategy, catalog, None,
                            demand_skus=result.run.demand_skus)
    report = build_structure(topo, result.strategy, priced.requirements, priced.bom,
                             run_id="run-tilt", catalog=catalog)

    stations = {s.element_id: s for s in report.sections[0].setting_out}
    leaning = stations["post@run1:1500"]
    assert (leaning.top_z_mm, leaning.exposed_mm, leaning.embed_mm) == (1800, 2078, 600)
    # the sheet's number and the warning's number are one number
    warning = next(w for w in result.strategy.warnings
                   if w.params.get("element") == "post@run1:1500")
    assert warning.code == "insufficient_post_length"
    assert warning.params["required_mm"] == leaning.exposed_mm + leaning.embed_mm
    # and a plumb node post reaches the same top with less post
    assert (stations["post@node:n1"].top_z_mm,
            stations["post@node:n1"].exposed_mm) == (1800, 1800)


def test_a_post_with_no_bay_to_carry_says_nothing_rather_than_zero():
    """`_check_post_lengths` skips a post with no adjacent span — the node post
    of a run whose first bay is a gate — so nothing measured it. Reported as
    None, because 0 would draw a post flush with the ground, which is a claim."""
    from fenceai.fulfillment.pipeline import price_strategy
    from fenceai.report.structure import build_structure
    from fenceai.topology.model import GatePayload
    from tests.conftest import add_point_event

    topo = straight_topology(6000)
    add_point_event(topo, "run1", "g", 0,
                    GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    priced = price_strategy(result.strategy, catalog, None,
                            demand_skus=result.run.demand_skus)
    report = build_structure(topo, result.strategy, priced.requirements, priced.bom,
                             run_id="run-gate", catalog=catalog)

    stations = {s.element_id: s for s in report.sections[0].setting_out}
    hanging = stations["post@node:n1"]
    assert (hanging.exposed_mm, hanging.top_z_mm) == (None, None)
    assert hanging.embed_mm == 600, "it is still buried, and still drawn buried"
    assert stations["post@run1:1000"].exposed_mm == 1800, "its neighbour carries a bay"
