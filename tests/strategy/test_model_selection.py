"""Choosing which model a stretch of fence is built to.

The generator hard-coded M-LEGACY until now, under a comment saying an event
would one day pick another. This is that event, plus the project default behind
it, plus the two things a per-interval model forces: a structural boundary where
the model changes, and per-segment resolution of everything scoped to it.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import GenerationFailure
from fenceai.fencemodel.demo import demo_models, legacy_model
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import DefaultComponent, KnowledgeVersion, SetParam
from fenceai.strategy.generator import generate
from fenceai.topology.model import FenceModelPayload
from tests.conftest import add_interval_event, straight_topology


def library() -> FenceModelLibrary:
    return FenceModelLibrary(models=list(demo_models().values()))


def other_model_id() -> str:
    """Whichever built-in is not the compatibility model. Named this way so the
    test does not silently pass by choosing M-LEGACY twice."""
    ids = sorted(m for m in demo_models() if m != "M-LEGACY")
    assert ids, "there must be a second built-in model to choose"
    return ids[0]


def models_of(result) -> list[str]:
    return sorted({u.model_id for u in result.run.model_snapshot})


# --- the default path is untouched -------------------------------------------

def test_no_choice_anywhere_still_builds_the_compatibility_model():
    result = generate(straight_topology(3000), demo_knowledge(), demo_catalog())
    assert models_of(result) == ["M-LEGACY"]
    assert all(s.panel.model_ref == "M-LEGACY@v1" for s in result.strategy.spans)


def test_the_library_being_present_changes_nothing_on_its_own():
    """A library is a menu, not an instruction. Handing the generator every model
    in existence must not move a single number until something chooses one."""
    topo, kb = straight_topology(3000), demo_knowledge()
    bare = generate(topo, kb, demo_catalog())
    with_library = generate(topo, kb, demo_catalog(), models=library())
    assert bare.run.id == with_library.run.id


# --- project default ----------------------------------------------------------

def test_the_project_default_picks_the_model():
    chosen = other_model_id()
    result = generate(
        straight_topology(3000), demo_knowledge(), demo_catalog(),
        models=library(), default_model=FenceModelChoice(model_id=chosen),
    )
    assert models_of(result) == [chosen]
    assert all(s.panel.model_ref.startswith(chosen + "@") for s in result.strategy.spans)


def test_choosing_a_model_changes_the_run_id():
    topo, kb = straight_topology(3000), demo_knowledge()
    a = generate(topo, kb, demo_catalog(), models=library())
    b = generate(topo, kb, demo_catalog(), models=library(),
                 default_model=FenceModelChoice(model_id=other_model_id()))
    assert a.run.id != b.run.id


def test_the_option_values_are_in_the_run_id():
    """Options are inert until the resolver reads them, but they are recorded
    from here on: a run stamped without them could be regenerated under a
    different colour and INSERT OR IGNORE would serve the older document."""
    topo, kb, chosen = straight_topology(3000), demo_knowledge(), other_model_id()
    a = generate(topo, kb, demo_catalog(), models=library(),
                 default_model=FenceModelChoice(model_id=chosen))
    b = generate(topo, kb, demo_catalog(), models=library(),
                 default_model=FenceModelChoice(model_id=chosen,
                                                options={"post_finish": "RAL7016"}))
    assert a.run.id != b.run.id


def test_an_unknown_model_is_a_named_refusal_not_a_crash():
    with pytest.raises(GenerationFailure) as exc:
        generate(straight_topology(3000), demo_knowledge(), demo_catalog(),
                 models=library(), default_model=FenceModelChoice(model_id="M-NOPE"))
    assert exc.value.code == "fence_model_not_found"
    assert exc.value.params["model_id"] == "M-NOPE"


def test_a_pin_to_a_version_that_does_not_exist_is_refused():
    with pytest.raises(GenerationFailure) as exc:
        generate(straight_topology(3000), demo_knowledge(), demo_catalog(),
                 models=library(),
                 default_model=FenceModelChoice(model_id=other_model_id(), version_pin=99))
    assert exc.value.code == "fence_model_not_found"


# --- the interval event -------------------------------------------------------

def test_an_interval_event_beats_the_project_default():
    chosen = other_model_id()
    topo = straight_topology(3000)
    add_interval_event(topo, "run1", "ev_m", 0, 3000,
                       FenceModelPayload(model_id=chosen))
    result = generate(topo, demo_knowledge(), demo_catalog(), models=library(),
                      default_model=FenceModelChoice(model_id="M-LEGACY"))
    assert models_of(result) == [chosen]


def test_a_model_change_forces_a_post_and_no_bay_straddles_it():
    """Span properties are sampled at the mid-point, so without a boundary
    station a bay laid across the change silently becomes one model's panel at
    the place where the fence visibly becomes the other's."""
    chosen = other_model_id()
    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id=chosen))
    result = generate(topo, demo_knowledge(), demo_catalog(), models=library())

    assert 2500 in {p.station_mm for p in result.strategy.posts if p.run_ref == "run1"}
    for span in result.strategy.spans:
        assert not (span.start_station_mm < 2500 < span.end_station_mm), \
            f"{span.id} straddles the model change"

    left = [s for s in result.strategy.spans if s.end_station_mm <= 2500]
    right = [s for s in result.strategy.spans if s.start_station_mm >= 2500]
    assert left and right
    assert all(s.panel.model_ref.startswith(chosen + "@") for s in left)
    assert all(s.panel.model_ref == "M-LEGACY@v1" for s in right)
    assert models_of(result) == sorted({chosen, "M-LEGACY"})


def test_two_models_on_one_run_each_get_their_own_decision_nodes():
    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id=other_model_id()))
    graph = generate(topo, demo_knowledge(), demo_catalog(), models=library()).graph
    selects = [n for n in graph.nodes if n.action == "select_model"]
    assert len(selects) == 2
    assert {n.payload["source"] for n in selects} == {"event", "builtin"}
    # the numbers resolved under a model's scope are attributed to that model's
    # bays, never pooled into one run-wide node
    quantities = [n for n in graph.nodes if n.action == "resolve_span_quantities"]
    assert len(quantities) == 2
    assert not (set(quantities[0].scope_refs) & set(quantities[1].scope_refs))


def test_one_model_run_keeps_exactly_one_of_each_node():
    """The memo is what keeps a single-model run's explanation the size it was."""
    graph = generate(straight_topology(5000), demo_knowledge(), demo_catalog()).graph
    for label in ("select_model", "resolve_max_span", "resolve_span_quantities"):
        assert len([n for n in graph.nodes if n.action == label]) == 1


# --- `series`, the dimension a model id makes available -----------------------

def series_rule(model_id: str, param: str, value: int,
                type_: str = "company_rule") -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id=f"K-SERIES-{param}", version=1, type=type_,  # type: ignore[arg-type]
        title=f"{param} for {model_id}",
        scope={"series": model_id},
        actions=[SetParam(param=param, value=value)],
    )


def test_a_rule_scoped_to_a_series_binds_to_that_model_only():
    """The blocked dimension: until a model id was a fact of generation there was
    nothing for `series` to match, so a rule scoped to a product line fired
    nowhere."""
    chosen = other_model_id()
    kb = demo_knowledge()
    kb.versions.append(series_rule(chosen, "rails_per_span", 3))

    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id=chosen))
    result = generate(topo, kb, demo_catalog(), models=library())

    left = [s for s in result.strategy.spans if s.end_station_mm <= 2500]
    right = [s for s in result.strategy.spans if s.start_station_mm >= 2500]
    assert all(s.rail_count == 3 for s in left), "the series rule did not bind"
    assert all(s.rail_count == 2 for s in right), "the series rule leaked"


def test_max_span_resolves_per_segment_under_the_model_scope():
    """The manufacturer's max span is a hard_constraint, so a model-specific one
    has to be a hard_constraint too — same authority, and specificity (the bound
    `series`) then breaks the tie. This is the resolution that had to move inside
    the segment loop: resolved once per run, a per-interval model could not be
    honoured at all."""
    chosen = other_model_id()
    kb = demo_knowledge()
    kb.versions.append(series_rule(chosen, "max_span_mm", 1000, type_="hard_constraint"))

    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id=chosen))
    result = generate(topo, kb, demo_catalog(), models=library())

    left = [s for s in result.strategy.spans if s.end_station_mm <= 2500]
    right = [s for s in result.strategy.spans if s.start_station_mm >= 2500]
    assert left and right
    assert max(s.width_mm for s in left) <= 1000
    assert max(s.width_mm for s in right) > 1000, \
        "the tighter maximum leaked past the model boundary"


def test_a_series_company_rule_cannot_undercut_a_manufacturer_hard_constraint():
    """Scoping a rule to a product line does not promote it. Authority is the
    first tier and specificity only breaks ties within it — otherwise naming a
    series would be a way to talk past a safety limit."""
    chosen = other_model_id()
    kb = demo_knowledge()
    kb.versions.append(series_rule(chosen, "max_span_mm", 1000, type_="company_rule"))

    topo = straight_topology(5000)
    add_interval_event(topo, "run1", "ev_m", 0, 2500,
                       FenceModelPayload(model_id=chosen))
    result = generate(topo, kb, demo_catalog(), models=library())
    left = [s for s in result.strategy.spans if s.end_station_mm <= 2500]
    assert max(s.width_mm for s in left) > 1000


# --- the M-LEGACY seam --------------------------------------------------------

def test_choosing_m_legacy_explicitly_still_follows_the_knowledge_rail():
    """M-LEGACY is rebuilt from the run's resolved demand skus rather than served
    from the library: a stored document naming RAIL-3000 would quietly outrank a
    DefaultComponent rule that changed the rail."""
    kb = demo_knowledge()
    kb.versions.append(KnowledgeVersion(
        object_id="K-RAIL-SWAP", version=1, type="company_rule",
        title="a different rail",
        actions=[DefaultComponent(role="rail", sku="RAIL-ALT")],
    ))
    catalog = demo_catalog()
    catalog.products["RAIL-ALT"] = catalog.products["RAIL-3000"].model_copy(
        update={"sku": "RAIL-ALT"})

    result = generate(straight_topology(3000), kb, catalog, models=library(),
                      default_model=FenceModelChoice(model_id="M-LEGACY"))
    rails = [slot for s in result.strategy.spans for slot in s.panel.slots
             if slot.role == "rail"]
    assert rails
    assert all(m.sku == "RAIL-ALT" for slot in rails for m in slot.eligibility.members)


def test_the_stored_legacy_document_is_the_one_the_generator_would_build():
    """If these ever diverge, choosing M-LEGACY from the menu builds a different
    fence from choosing nothing — the seam above would be hiding a real drift."""
    stored = library().resolve("M-LEGACY", None)
    assert stored is not None
    assert stored.default_spec == legacy_model().default_spec
