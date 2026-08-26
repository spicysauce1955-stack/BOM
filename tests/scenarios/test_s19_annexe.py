"""S19 — a footnote at the foot of fourteen pages, in the annexe once.

Boundary contract obligation 10 and §3.3.5. The obligation replaced v0.1's "a
warning is attached to its step" because a census of all 81,794 elements
falsified it: only 19.9% of 1,038 warning instances sit inside a step that does
something, and about 68% are document-scoped. Enforced literally the old rule
publishes one warning in five and misattributes the rest.

So this file is mostly about where a warning does NOT appear. It is a scenario
rather than a unit test because the property spans the whole spine — the document,
the run, the BOM, and the two read models that render a plan — and because the
failure it guards against is invisible in any one of them: every individual
surface looks fine while the freeze-thaw footnote shouts at a fitter forty times.

See docs/scenarios/golden-scenarios.md §S19 for the numbers.
"""

from __future__ import annotations

import pytest

from fenceai.core.gaps import SourceRef
from fenceai.core.warnings import DocumentWarning, WarningTarget
from fenceai.fencemodel.demo import M_VINYL
from fenceai.fencemodel.library import FenceModelLibrary
from fenceai.fencemodel.model import validate_model
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.report.annexe import place_for_plan, place_warnings
from fenceai.strategy.generator import generate
from tests.conftest import straight_topology

LIBRARY = FenceModelLibrary(models=[M_VINYL])
PARTS = PartLibrary(parts=demo_parts())
VINYL = FenceModelChoice(model_id="M-VINYL")


def _run(knowledge, catalog):
    return generate(straight_topology(6000), knowledge, catalog,
                    models=LIBRARY, parts=PARTS, default_model=VINYL)


@pytest.fixture
def priced(knowledge, catalog):
    result = _run(knowledge, catalog)
    return result, price_strategy(result.strategy, catalog, None)


@pytest.fixture
def placement(priced):
    """What every surface of this plan is handed — one placement over the
    documents the RUN was built to, and the skus it actually buys."""
    result, priced_run = priced
    return place_for_plan([M_VINYL],
                          skus=[line.sku for line in priced_run.requirements])


def test_the_run_is_four_bays_and_the_safety_box_appears_once(placement, priced):
    """The scenario's own numbers first, because the property is about a ratio:
    four bays and one footnote. Against four bays a repeated notice is already
    noise; against forty it is what teaches a reader to skip warnings.

    Four 1500 mm bays, not the three 2000 mm ones the straight demo run gets:
    M-VINYL's rails are routed through the post and its span limit is its own
    (S16). The first draft of this scenario asserted 2000 and the doc was
    corrected, not the number — a scenario that borrows another model's layout is
    asserting the wrong fence."""
    result, _ = priced
    assert len(result.strategy.spans) == 4
    assert [s.width_mm for s in result.strategy.spans] == [1500] * 4

    annexe = placement.at("annexe")
    assert len(annexe) == 2          # the safety box and the warranty condition
    assert all(p.instances == 1 for p in annexe)
    assert "frost line" in annexe[0].warning.text_raw


def test_the_document_scoped_warning_is_on_no_bay_and_no_line(placement, priced):
    """Said as a negative because that is the obligation. The bays exist, the
    lines exist, and the footnote is attached to neither."""
    _, priced_run = priced
    for p in placement.at("annexe"):
        assert p.ref == ""
    on_lines = {p.ref for p in placement.at("product")}
    assert "frost line" not in " ".join(
        p.warning.text_raw for p in placement.placements if p.where != "annexe")
    # the one product-scoped warning IS on a line, and it is a line this fence buys
    assert on_lines == {"SLAT-V-150"}
    assert "SLAT-V-150" in {line.sku for line in priced_run.requirements}


def test_the_step_scoped_warning_lands_on_the_step_that_earns_it(placement):
    """M-VINYL's `cure` step is the one the guide warns about, and the warning is
    on that step rather than on the panel sheet's head — 19.9% of real warnings
    are step warnings and they must still reach their step."""
    on_step = placement.at("step", "cure")
    assert len(on_step) == 1
    assert "cured" in on_step[0].warning.text_raw
    assert placement.at("step", "rails") == []
    assert placement.at("step", "set_posts") == []


def test_eighty_three_printings_collapse_to_one_entry_that_counts_them(catalog):
    """The corpus's own number. One entry, `instances=83`, and the count is
    published — "shown once" then reads as a decision rather than as all there
    was. A second document quoting the same sentence stays a second entry."""
    footnote = DocumentWarning(
        text_raw="CAUTION: set footings below the local frost line.",
        lang="en", severity_lexeme="CAUTION",
        attaches_to=WarningTarget(kind="document"),
        cites=SourceRef(id="DEMO-src-vinyl-1", belongs_to="sha256:doc-a"))
    elsewhere = footnote.model_copy(
        update={"cites": SourceRef(id="OTHER-src-1", belongs_to="sha256:doc-b")})

    one_doc = place_warnings([footnote] * 83)
    assert len(one_doc.at("annexe")) == 1
    assert one_doc.at("annexe")[0].instances == 83
    assert len(place_warnings([footnote, elsewhere]).at("annexe")) == 2


def test_nothing_is_dropped_even_when_it_belongs_to_somebody_else(placement):
    """`Σ instances + not_in_plan ≡ the warnings carried` — the same shape as
    `Σ(parts) ≡ BOM` and `unplaced`. Checkable from the returned object alone,
    which is what would catch a future surface filtering a kind it cannot draw.
    """
    assert placement.carried() == len(M_VINYL.warnings)
    assert placement.not_in_plan == 0

    stranger = DocumentWarning(
        text_raw="Torque the carriage bolts to 20 Nm.", lang="en",
        attaches_to=WarningTarget(kind="product", ref="SOMEONE-ELSES-SKU"))
    procedure = DocumentWarning(
        text_raw="Read the gate-hanging procedure before cutting.", lang="en",
        attaches_to=WarningTarget(kind="procedure", ref="PROC-gate-1"))
    mixed = place_warnings([*M_VINYL.warnings, stranger, procedure],
                           steps=[s.key for s in M_VINYL.assembly],
                           skus=["SLAT-V-150"], model_refs=[M_VINYL.ref])
    assert mixed.carried() == len(M_VINYL.warnings) + 2
    # a stranger's notice is counted and never printed on this plan...
    assert mixed.not_in_plan == 1
    assert stranger.text_raw not in " ".join(
        p.warning.text_raw for p in mixed.placements)
    # ...and a procedure this engine does not model is REPORTED, not filed away
    assert [p.ref for p in mixed.at("unplaceable")] == ["PROC-gate-1"]


def test_the_publishers_words_survive_the_whole_spine(placement):
    """Verbatim through the run, the pricing and the placement: the text, the
    language, and the publisher's own severity word. `CAUTION` and `WARNING` are
    terms of art with different legal weight, so neither is mapped onto this
    engine's `info | warning | error` — and nothing here has a field to map them
    into."""
    words = {p.warning.severity_lexeme for p in placement.placements}
    assert {"CAUTION", "WARNING"} <= words
    for p in placement.placements:
        original = [w for w in M_VINYL.warnings
                    if w.text_raw == p.warning.text_raw]
        assert original and original[0].lang == p.warning.lang == "en"
        assert not hasattr(p.warning, "severity")


def test_a_warning_nobody_can_trace_is_marked_and_not_hidden(placement):
    """§1.1 makes `SourceRef.id` opaque and forbids building one, so a curator
    authoring a warning in the model editor cannot mint a citation. One of
    M-VINYL's four has none, and it must reach the surface AS unattributed: a
    sentence nobody can trace must not look like one an engineer confirmed
    against a drawing."""
    cited = [p for p in placement.placements if p.warning.cites is not None]
    uncited = [p for p in placement.placements if p.warning.cites is None]
    assert len(uncited) == 1 and cited
    assert uncited[0].warning.text_raw.startswith("This section is not rated")
    assert all(p.warning.cites.id.startswith("DEMO-src-") for p in cited)


def test_carrying_a_warning_moves_no_cost_no_line_and_no_decision(knowledge, catalog):
    """A warning is a note on an answer, not an input to one. The same run built
    to a document stripped of its warnings must produce the identical BOM,
    requirement lines and decision graph — otherwise a curator recording what the
    manufacturer said would silently reprice a job."""
    silent = M_VINYL.model_copy(deep=True, update={"warnings": []})
    with_warnings = _run(knowledge, catalog)
    without = generate(straight_topology(6000), knowledge, catalog,
                       models=FenceModelLibrary(models=[silent]), parts=PARTS,
                       default_model=VINYL)

    a = price_strategy(with_warnings.strategy, catalog, None)
    b = price_strategy(without.strategy, catalog, None)
    # Compared WHOLE, not projected. The first version of this test compared
    # `[n.kind for n in graph.nodes]` and `(sku, engineering_qty)` per line, and
    # the test review showed four plausible "helpfully record what the document
    # warns" leaks surviving it: a `document_warns` payload key, a suffixed
    # `model_ref`, an extra `assumption_of` edge, and `confidence="inferred"`.
    # Every one of those changes the explanation of every run built to the
    # document while the projection stays identical — and the scenario doc says
    # byte-identical, which is the claim that deserves the strong comparison.
    #
    # `generate()` is pure and deterministic (ADR-0004), so a full dump is
    # available and stable; there is no reason to compare less.
    assert a.bom.model_dump() == b.bom.model_dump()
    assert [line.model_dump() for line in a.requirements] \
        == [line.model_dump() for line in b.requirements]
    assert with_warnings.graph.model_dump() == without.graph.model_dump()
    # ...and the warnings are not smuggled in as engine warnings either
    assert [w.model_dump() for w in with_warnings.strategy.warnings] \
        == [w.model_dump() for w in without.strategy.warnings]


def test_a_warning_pointing_at_nothing_is_refused_while_the_author_can_fix_it(catalog):
    """At render time a target that is not in the plan is indistinguishable from
    another document's warning — correctly, because most of them are. That makes
    a mistyped step key silent on every job built to the model, so it is refused
    here instead, where the person holding the document can see it."""
    def _with(target: WarningTarget) -> list[str]:
        model = M_VINYL.model_copy(deep=True, update={"warnings": [
            DocumentWarning(text_raw="mind the gap", lang="en",
                            attaches_to=target)]})
        return validate_model(model, catalog, PARTS)

    assert _with(WarningTarget(kind="step", ref="cure")) == []
    assert _with(WarningTarget(kind="step", ref="cur"))
    assert _with(WarningTarget(kind="product", ref="SLAT-V-15O"))
    assert _with(WarningTarget(kind="model", ref="M-SLAT@v2"))
    # and the document as shipped is valid, or the surfaces see none of this
    assert validate_model(M_VINYL, catalog, PARTS) == []
