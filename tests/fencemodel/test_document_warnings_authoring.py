"""A quoted warning on a fence model, refused while the author is holding it.

`_warning_errors` in `fencemodel/model.py`. The type's own rules live in
`tests/core/test_document_warnings.py`; these are the ones only this document can
answer — whether the step, sku or model the warning points at exists.

The reason they are refusals rather than render-time notes is worth stating,
because the alternative is live and correct for its own case:
`report/annexe.py` counts a warning whose target is not in the plan as
`not_in_plan` and says nothing, because a warning about a sku this fence does not
buy really does belong to another job. That makes a MISTYPED step key
indistinguishable from another document's warning — silently, on every job built
to the model. The author is the only person who can tell those two apart.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.core.warnings import DocumentWarning, WarningTarget
from fenceai.fencemodel.demo import routed_vinyl_model
from fenceai.fencemodel.model import (
    AssemblyStep, Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot,
    PanelSpec, PartRequirement, validate_model,
)

CATALOG = demo_catalog()


def _model(*warnings: DocumentWarning) -> FenceModel:
    return FenceModel(
        id="M-WARN", version=1, warnings=list(warnings),
        assembly=[AssemblyStep(key="frame", slots=["rail"],
                               text_i18n={"en": "Seat both rails."})],
        default_spec=PanelSpec(
            frame=[FrameSlot(
                key="rail", orientation="horizontal", placement=Distributed(count=2),
                requirement=PartRequirement(
                    role="rail", qty=1, length_rule="centre_to_centre",
                    eligibility=Eligibility(
                        members=[EligibleItem(sku="RAIL-3000")])))]),
    )


def _w(kind: str, ref: str = "") -> DocumentWarning:
    return DocumentWarning(
        text_raw="CAUTION: mind the frost line.", lang="en",
        severity_lexeme="CAUTION", attaches_to=WarningTarget(kind=kind, ref=ref))


def test_a_model_may_warn_about_nothing():
    """Empty is NO OPINION, exactly as `assembly` and `post` are. Every model
    shipped before obligation 10 carried no warnings, and none of them became
    invalid the day the field arrived."""
    assert validate_model(_model(), CATALOG) == []


def test_the_four_places_a_warning_may_legitimately_point():
    """A step of this model, a sku in the catalog, this model itself, and the
    whole job. Accepted together, so a later narrowing has to break this test to
    happen."""
    model = _model(_w("step", "frame"), _w("product", "RAIL-3000"),
                   _w("model", "M-WARN@v1"), _w("document"))
    assert validate_model(model, CATALOG) == []


def test_a_warning_on_a_step_this_model_has_not_got_is_refused():
    """Otherwise it is carried on every job built to the model and rendered on
    none — the failure this check exists for, and the one a render-time count
    cannot distinguish from a warning that simply belongs elsewhere."""
    errors = validate_model(_model(_w("step", "fram")), CATALOG)
    assert len(errors) == 1
    assert "has no step by that key" in errors[0]


def test_a_warning_about_a_product_nothing_can_buy_is_refused():
    """A sku outside the catalog reaches no BOM line, so the notice reaches no
    reader. `RAIL-3O00` with a letter O is the version of this that happens."""
    errors = validate_model(_model(_w("product", "RAIL-3O00")), CATALOG)
    assert len(errors) == 1 and "not in the catalog" in errors[0]


def test_a_document_may_only_warn_about_itself():
    """A model-scoped warning naming ANOTHER line is a claim this document has no
    standing to make — and it would appear on a plan built to that other line
    while its own author never wrote it."""
    errors = validate_model(_model(_w("model", "M-OTHER@v3")), CATALOG)
    assert len(errors) == 1 and "no standing" in errors[0]
    # its own id, unversioned, is the same document and is accepted
    assert validate_model(_model(_w("model", "M-WARN")), CATALOG) == []


def test_the_shared_type_rules_run_here_too():
    """One checker, two doors. A params bag with no code is refused on a curated
    model exactly as it is on a published snapshot, because it is a property of
    the type and not of the door."""
    bad = DocumentWarning(
        text_raw="mind the gap", lang="en",
        attaches_to=WarningTarget(kind="document"), params={"n": 2})
    errors = validate_model(_model(bad), CATALOG)
    assert len(errors) == 1 and "params with no code" in errors[0]


def test_the_demo_document_that_exercises_all_of_it_is_valid():
    """M-VINYL carries four warnings across four kinds — the document, a step, a
    product and the warranty — because a surface nothing reaches is a surface
    nobody notices is wrong. If this model stops validating, the browser suite
    stops seeing the feature at all."""
    model = routed_vinyl_model()
    assert validate_model(model, CATALOG) == []
    assert {w.attaches_to.kind for w in model.warnings} == {
        "document", "step", "product", "warranty"}
    # ...and one of them is deliberately unattributed, which is the second
    # rendering the surfaces have to get right
    assert any(not w.cites for w in model.warnings)
    assert any(w.cites for w in model.warnings)
