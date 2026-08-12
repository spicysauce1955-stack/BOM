"""Panel gaps and rail spacing, and what a violation costs.

Every gap a fence model introduces is regulated somewhere. The numbers are
jurisdictional and the demo's are foreign, so they live in knowledge; what does
NOT live in knowledge is the consequence, which is read off the governing
object's tier. It would be incoherent for a 1801 mm span to be fatal while a
130 mm child-head gap is a note.
"""

from __future__ import annotations

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.core.errors import GenerationFailure
from fenceai.fencemodel.demo import M_SLAT, slat_model
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeVersion, SetParam
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

SLAT = FenceModelChoice(model_id="M-SLAT")


def limit(param: str, value: int, type_: str = "company_rule") -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id=f"K-LIMIT-{param}", version=2, type=type_,  # type: ignore[arg-type]
        title=f"{param} = {value}", scope={"series": "M-SLAT"},
        actions=[SetParam(param=param, value=value)],
    )


def run(kb=None, models=None, length=5000):
    return generate(
        straight_topology(length), kb or demo_knowledge(), demo_catalog(),
        models=models or FenceModelLibrary(models=[M_SLAT]), default_model=SLAT,
    )


def codes(result) -> list[str]:
    return [w.code for w in result.strategy.warnings]


# --- the gap, and why it is max() ---------------------------------------------

def test_the_demo_slat_panel_passes_the_seeded_sphere_test():
    """20 mm gaps against a 100 mm limit. If this ever fails, the demo model and
    the demo rules have drifted apart and one of them is wrong."""
    assert "clear_gap_exceeded" not in codes(run())


def test_a_gap_over_the_limit_is_reported_against_the_widest_opening():
    """Not against an average, and not against one rounded value. A fit spreads
    its residual a millimetre at a time, so a bay's gaps differ by one — and a
    single rounded gap of 23 would pass a 23 mm limit while several real openings
    measured 24. That is the sphere test defeated by a return type, which is why
    fit_pattern returns a list."""
    kb = demo_knowledge()
    kb.versions.append(limit("max_clear_gap_mm", 19))
    result = run(kb)
    warning = next(w for w in result.strategy.warnings if w.code == "clear_gap_exceeded")

    gaps = [g for span in result.strategy.spans for slot in span.panel.slots
            if slot.fit for g in slot.fit.gaps_mm]
    assert warning.params["value_mm"] == max(gaps)
    assert max(gaps) > min(gaps), "the fixture must have uneven gaps to be worth testing"
    assert warning.params["limit_mm"] == 19


def test_the_warning_is_one_per_section_not_one_per_bay():
    """A systemic gap on a long fence is one thing to go fix, not one per bay."""
    kb = demo_knowledge()
    kb.versions.append(limit("max_clear_gap_mm", 19))
    result = run(kb, length=20000)
    assert len(result.strategy.spans) > 5
    assert codes(result).count("clear_gap_exceeded") == 1


# --- the tier decides the consequence -----------------------------------------

def test_a_company_rule_violation_is_a_warning_the_job_survives():
    kb = demo_knowledge()
    kb.versions.append(limit("max_clear_gap_mm", 19, type_="company_rule"))
    result = run(kb)
    assert "clear_gap_exceeded" in codes(result)
    assert result.strategy.spans, "the job still generated"


def test_the_same_violation_under_a_hard_constraint_stops_the_job():
    """Same check, same number, different tier. ADR-0005: a violated hard
    constraint is a generation failure, and a jurisdiction pack that seeds these
    as hard constraints gets that with no code change."""
    kb = demo_knowledge()
    kb.versions.append(limit("max_clear_gap_mm", 19, type_="hard_constraint"))
    with pytest.raises(GenerationFailure) as exc:
        run(kb)
    assert exc.value.code == "clear_gap_exceeded"
    assert exc.value.params["value_mm"] > 19
    assert exc.value.constraint_refs, "the refusal must name the rule that caused it"


def test_a_limit_nobody_stated_is_not_a_limit_of_zero():
    """No rule, no check. A missing limit read as 0 would fail every fence."""
    kb = demo_knowledge()
    kb.versions = [v for v in kb.versions if v.object_id != "K-CLEAR-GAP"]
    assert "clear_gap_exceeded" not in codes(run(kb))


# --- the anti-ladder rule -----------------------------------------------------

def test_two_rails_are_never_a_ladder():
    """Two rails are the top and the bottom of the frame; the rule is about a
    MIDDLE rail a child could stand on."""
    assert "rail_separation_insufficient" not in codes(run())


def test_three_rails_too_close_together_are_reported():
    kb = demo_knowledge()
    kb.versions.append(limit("rails_per_span", 3))
    result = run(kb)
    warning = next(w for w in result.strategy.warnings
                   if w.code == "rail_separation_insufficient")
    # 1800 mm panel, three rails inclusive of both ends: 0, 900, 1800
    assert warning.params["value_mm"] == 900
    assert warning.params["limit_mm"] == 1143


def test_a_tall_enough_panel_puts_the_middle_rail_clear():
    kb = demo_knowledge()
    kb.versions.append(limit("rails_per_span", 3))
    kb.versions.append(KnowledgeVersion(
        object_id="K-TALL", version=1, type="company_rule", title="tall",
        actions=[SetParam(param="max_fence_height_mm", value=9000)]))
    topo = straight_topology(3000)
    from tests.conftest import add_interval_event
    from fenceai.topology.model import HeightIntentPayload
    add_interval_event(topo, "run1", "ev_h", 0, 3000,
                       HeightIntentPayload(height_mm=2400))
    result = generate(topo, kb, demo_catalog(),
                      models=FenceModelLibrary(models=[M_SLAT]), default_model=SLAT)
    # 2400 mm panel: rails at 0, 1200, 2400 — 1200 clears the 1143 limit
    assert "rail_separation_insufficient" not in codes(result)


# --- the residual -------------------------------------------------------------

def test_a_truncating_pattern_that_leaves_too_much_is_reported():
    kb = demo_knowledge()
    kb.versions.append(limit("max_pattern_residual_mm", 5))
    truncating = slat_model().model_copy(deep=True)
    truncating.default_spec.infill.excess = "truncate"
    result = run(kb, models=FenceModelLibrary(models=[truncating]))
    assert "pattern_residual_large" in codes(result)


def test_the_default_spreading_pattern_leaves_no_residual_to_report():
    """`excess: space` widens the gaps to absorb it, which is the whole point."""
    kb = demo_knowledge()
    kb.versions.append(limit("max_pattern_residual_mm", 5))
    assert "pattern_residual_large" not in codes(run(kb))


# --- a manufactured bay width --------------------------------------------------

def test_an_exact_width_tiles_the_segment_and_reports_the_odd_bay():
    """For a model that ships as a pre-assembled panel, span width is not the
    layout's to choose — an off-size bay has no panel to put in it. The remainder
    is REPORTED rather than absorbed: stretching every bay to make it come out
    even would put a panel in a bay it does not fit."""
    kb = demo_knowledge()
    kb.versions.append(limit("exact_span_mm", 1500))
    result = run(kb, length=5000)

    widths = sorted(s.width_mm for s in result.strategy.spans)
    assert widths == [500, 1500, 1500, 1500]
    warning = next(w for w in result.strategy.warnings if w.code == "span_not_exact")
    assert warning.params["remainder_mm"] == 500
    assert warning.params["exact_mm"] == 1500


def test_a_segment_that_divides_exactly_reports_nothing():
    kb = demo_knowledge()
    kb.versions.append(limit("exact_span_mm", 1500))
    result = run(kb, length=4500)
    assert [s.width_mm for s in result.strategy.spans] == [1500, 1500, 1500]
    assert "span_not_exact" not in codes(result)


def test_an_exact_width_beats_the_free_layout_and_records_what_it_gave_up():
    """Not a preference competing with one: it says the bays are a manufactured
    size, so it wins outright — and the layout it displaced is on the node."""
    kb = demo_knowledge()
    kb.versions.append(limit("exact_span_mm", 1500))
    result = run(kb, length=5000)
    node = next(n for n in result.graph.nodes if n.action == "layout_spans")
    assert node.payload["widths"] == [1500, 1500, 1500, 500]
    assert node.payload["alternatives"], "the free layout is not recorded"


def test_an_exact_width_is_still_clamped_by_the_hard_maximum():
    """A manufacturer's maximum span is a hard constraint; a panel size cannot
    talk past it."""
    kb = demo_knowledge()
    kb.versions.append(limit("exact_span_mm", 5000))   # over the 1800 demo maximum
    result = run(kb, length=5000)
    assert max(s.width_mm for s in result.strategy.spans) <= 1800
