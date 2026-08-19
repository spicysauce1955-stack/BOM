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


def test_a_resolved_part_carries_a_content_hash():
    """Every `PartUse` carries a content hash, the same precaution `ModelUse`
    already takes — not because an ACTIVE version can move (it cannot, by
    immutability), but so the shape is uniform and a future caller never has to
    ask which kind of use it is holding.

    NOTE: as literally specified, the brief paired this test with a lone-draft
    library and asserted resolution SUCCEEDS with a hash — but `latest_active`
    (exercised by `test_it_resolves_latest_active_not_latest`) and the explicit
    `test_a_part_with_no_active_version_is_refused_by_name` both require a
    lone-draft library to be REFUSED. Those two cannot both hold, so this test
    keeps the hash assertion (the part of the intent every other test agrees
    with) against a resolvable library instead of the contradictory one."""
    lib = library(rail(version=1, status="active"))
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


def test_a_declared_dimension_lands_on_the_slot_and_a_bare_one_leaves_it_undeclared():
    """`FrameSlot.thickness_mm` already defaults to 0, so a test that only ever
    authors a bare part passes even if the write in `_apply_dimensions` were
    deleted outright — a 0-by-construction assertion this codebase has been
    bitten by before. This exercises both halves: a part that DOES declare
    `thickness_mm` must land its actual value, and only a genuinely bare part
    reads as 0 — which is what the elevation renders as `declared=False`, a
    flag, not a nominal band that reads as measured."""
    declared = Part(id="rail-38", version=1, type="rail",
                     spec=[SpecField(key="thickness_mm", value=19, agree="==", unit="mm")])
    resolved, _ = resolve_model_parts(model(), library(declared))
    assert resolved.default_spec.frame[0].thickness_mm == 19

    bare = Part(id="rail-38", version=1, type="rail",
                spec=[SpecField(key="material", value="vinyl", agree="==")])
    resolved_bare, _ = resolve_model_parts(model(), library(bare))
    assert resolved_bare.default_spec.frame[0].thickness_mm == 0


def test_the_stored_model_is_not_mutated():
    """generate() is pure (ADR-0004). Resolution returns a new document —
    including `_apply_dimensions`'s write, which `predicate` alone would not
    catch: a leak there writes THROUGH to the original's `width_mm`/
    `thickness_mm` without ever touching `eligibility`."""
    from fenceai.fencemodel.model import InfillSpec, Member
    original = model()
    original.default_spec.infill = InfillSpec(orientation="vertical", pattern=[
        Member(key="slat", requirement=PartRequirement(part_id="rail-38"))])
    resolve_model_parts(original, library(rail()))
    assert original.default_spec.frame[0].requirement.eligibility.predicate is None
    assert original.default_spec.infill.pattern[0].width_mm == 0


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
                # authors no width: a slot naming a part authors none of the
                # dimensions the part fills (`Member._dimensions_are_the_parts`)
                Member(key="slat",
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


def test_resolution_leaves_no_members_behind_it():
    """The part is the authority, so nothing a slot was carrying may survive it.

    Assigned rather than authored: `PartRequirement` now refuses `part_id` beside
    an authored member list, and this is the one way a slot can be carrying members
    when it reaches resolution — a document that has already been through the
    MATCHER, which fills `members` and clears `predicate`. Resolving that document
    again without clearing them would hand the panel a stale candidate set beside a
    fresh predicate, and `_predicate_errors` reads exactly that pair as the "says it
    both ways" refusal.
    """
    from fenceai.fencemodel.model import EligibleItem

    m = model()
    req = m.default_spec.frame[0].requirement
    req.eligibility.members = [EligibleItem(sku="STALE", approval="suggest_only")]
    req.eligibility.predicate = None

    resolved, _ = resolve_model_parts(m, library(rail()))
    after = resolved.default_spec.frame[0].requirement.eligibility
    assert after.members == []
    assert after.predicate is not None
    # and the caller's document is untouched — `generate()` is pure
    assert [x.sku for x in req.eligibility.members] == ["STALE"]
