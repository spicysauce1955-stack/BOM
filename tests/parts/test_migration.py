"""Migration moves where a spec is written, not what it says."""

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.demo import demo_model_versions
from fenceai.parts.demo import demo_parts
from fenceai.parts.model import PartLibrary
from fenceai.parts.resolve import part_requirements, resolve_model_parts
from fenceai.parts.validate import matching_skus, validate_part


def library() -> PartLibrary:
    return PartLibrary(parts=demo_parts())


def test_every_demo_part_is_valid_against_the_demo_catalog():
    catalog = demo_catalog()
    for part in demo_parts():
        assert validate_part(part, catalog) == [], part.ref


def test_every_slot_of_every_demo_model_names_a_part_that_resolves():
    lib = library()
    for model in demo_model_versions():
        resolve_model_parts(model, lib)   # raises if any part_id has no active version


def test_a_migrated_part_emits_no_type_row():
    """Product.type is empty on every existing product, so a `type ==` agreement
    would match nothing and every migrated slot would resolve to no eligible item —
    the gate would not merely move, it would collapse. The SKU list is already the
    whole constraint."""
    for part in demo_parts():
        assert not any(f.key == "type" for f in part.spec), part.ref


def test_a_migrated_part_carries_its_type_on_the_entity():
    assert {p.type for p in demo_parts()} >= {"rail", "screw", "infill"}


def test_the_sku_list_migrated_as_among_not_covers():
    """`covers` asks about a set the ITEM declares. A two-SKU list compiled that way
    would collapse to equality against one of them."""
    for part in demo_parts():
        sku_fields = [f for f in part.spec if f.key == "sku"]
        for f in sku_fields:
            assert f.agree == "among", part.ref


def test_the_width_a_model_drew_is_now_a_fact_on_the_product():
    """The model was already claiming that slat is 100 wide. Migration writes the
    number onto the product, where it belongs, so the part and the item agree
    because they quote the same fact."""
    catalog = demo_catalog()
    assert catalog.product("SLAT-100").attrs["width_mm"] == 100
    assert catalog.product("SLAT-V-150").attrs["width_mm"] == 150


def test_no_product_is_drawn_at_two_widths():
    """Two models drawing one SKU at two widths is a real contradiction in existing
    data, and migration reports it rather than picking."""
    from tools.migrate_parts import width_conflicts
    assert width_conflicts(demo_model_versions()) == {}


def test_a_migrated_part_still_admits_exactly_the_sku_it_used_to_name():
    catalog = demo_catalog()
    for part in demo_parts():
        sku_fields = [f for f in part.spec if f.key == "sku"]
        if sku_fields:
            assert set(matching_skus(part, catalog)) >= set(sku_fields[0].value), part.ref


def test_the_demo_seeds_one_part_with_several_eligible_items():
    """The previous arc found every demo slot naming ONE product made the drawer's
    alternatives untested — `buttons == len(options) - 1` was `0 == 0`, and deleting
    the offer button passed eighteen tests. One part must admit several."""
    catalog = demo_catalog()
    assert any(len(matching_skus(p, catalog)) > 1 for p in demo_parts())


def test_no_demo_slot_carried_a_suggest_only_member():
    """Promoting one to `auto` would let the system substitute a product a human said
    needs sign-off. Migration refuses rather than converting."""
    from tools.migrate_parts import approval_losses
    assert approval_losses(demo_model_versions()) == []


# --- the two refusals, against data that actually trips them -----------------
#
# The two tests above ask the refusals about ALREADY-MIGRATED models, where every
# slot has an empty member list and both answers are empty by construction. That is
# worth asserting — it is how we know the migration left nothing behind — but on its
# own it would pass just as happily against functions that returned `{}` and `[]`
# unconditionally. These build the pre-migration shape the tool was written for.

def _pre_migration_model(ref_id: str, sku: str, width: int, approval: str = "auto"):
    from fenceai.fencemodel.model import (
        Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, InfillSpec,
        Member, PanelSpec, PartRequirement,
    )
    return FenceModel(
        id=ref_id, version=1,
        default_spec=PanelSpec(
            frame=[FrameSlot(key="rail", orientation="horizontal",
                             placement=Distributed(count=2),
                             requirement=PartRequirement(
                                 role="rail", length_rule="centre_to_centre",
                                 eligibility=Eligibility(members=[
                                     EligibleItem(sku="RAIL-3000", priority=1)])))],
            infill=InfillSpec(orientation="vertical", pattern=[
                Member(key="slat", width_mm=width, gap_after_mm=20,
                       requirement=PartRequirement(
                           role="infill", length_rule="panel_height",
                           eligibility=Eligibility(members=[
                               EligibleItem(sku=sku, priority=1,
                                            approval=approval)])))]),
        ),
    )


def test_width_conflicts_names_the_sku_the_widths_and_the_models():
    from tools.migrate_parts import width_conflicts
    conflicts = width_conflicts([
        _pre_migration_model("A", "SLAT-100", 100),
        _pre_migration_model("B", "SLAT-100", 120),
    ])
    assert conflicts == {"SLAT-100": {100: ["A@v1"], 120: ["B@v1"]}}


def test_one_sku_drawn_at_one_width_by_two_models_is_not_a_conflict():
    """The dedup's whole payoff. Two models agreeing is what becomes ONE part."""
    from tools.migrate_parts import parts_for, width_conflicts
    models = [_pre_migration_model("A", "SLAT-100", 100),
              _pre_migration_model("B", "SLAT-100", 100)]
    assert width_conflicts(models) == {}
    assert len(parts_for(models)) == 2      # one rail part, one infill part


def test_a_suggest_only_member_is_reported_rather_than_promoted():
    from tools.migrate_parts import approval_losses
    losses = approval_losses(
        [_pre_migration_model("A", "SLAT-100", 100, approval="suggest_only")])
    assert losses == [("A@v1", "slat", "SLAT-100")]


def test_the_tool_builds_the_same_spec_the_demo_library_holds():
    """`parts/demo.py` is hand-written and `migrate_parts.py` is mechanical, and the
    two must agree or one of them is wrong about what a migrated part is."""
    from tools.migrate_parts import parts_for
    built = {p.id: p for p in parts_for(demo_model_versions() + [
        _pre_migration_model("A", "SLAT-100", 100)]).values()}
    demo = {p.id: p for p in demo_parts()}
    assert "infill-slat-100" in built
    assert built["infill-slat-100"].spec == demo["infill-slat-100"].spec
    assert built["infill-slat-100"].type == demo["infill-slat-100"].type


def test_the_tool_leaves_m_legacy_alone():
    """Its eligibility is knowledge's, rebuilt per run. A part would freeze a SKU in
    front of the `DefaultComponent` rule that supplies it."""
    from tools.migrate_parts import rewrite, parts_for
    models = demo_model_versions()
    rewritten = rewrite(models, parts_for(models))
    assert "M-LEGACY" not in {m.id for m in rewritten}


def test_migration_leaves_no_slot_naming_both_a_part_and_a_sku():
    """Two authorities over what may fill a slot is the defect the entity removes."""
    for model in demo_model_versions():
        for key, req in part_requirements(model):
            assert not (req.part_id and req.eligibility.members), f"{model.ref} {key}"
            assert not (req.part_id and req.eligibility.predicate), f"{model.ref} {key}"


def test_the_only_slots_naming_no_part_are_the_two_that_cannot():
    """M-LEGACY's, whose eligibility knowledge supplies per run, and M-VINYL's post
    and cap, whose predicates agree with a fact about the BAY — a `SpecField` is
    always `item.<key> <agree> <literal>`, so no part can express them.

    Pinned by name so that a slot losing its part_id by accident is a failure rather
    than a silently unmigrated model.
    """
    unnamed = {(m.id, key) for m in demo_model_versions()
               for key, req in part_requirements(m) if not req.part_id}
    assert unnamed == {
        ("M-LEGACY", "rail"), ("M-LEGACY", "screw"),
        ("M-VINYL", "post"), ("M-VINYL", "post.cap"),
    }


def test_a_slot_naming_no_part_keeps_the_predicate_it_was_authored_with():
    """The refusal that makes the exception safe rather than convenient: resolution
    must leave an unnamed slot exactly as it found it. Overwriting M-VINYL's post
    with the conjunction of nothing would admit every vinyl post at every station."""
    vinyl = next(m for m in demo_model_versions() if m.id == "M-VINYL")
    resolved, _ = resolve_model_parts(vinyl, library())
    before = vinyl.post.requirement.eligibility.predicate
    assert resolved.post.requirement.eligibility.predicate == before
    assert resolved.post.cap.eligibility.predicate == vinyl.post.cap.eligibility.predicate


def test_a_slot_that_names_nothing_and_declares_nothing_is_refused():
    """The one thing the empty `part_id` default must not become: a silent way to
    author a slot nothing could ever be bought for."""
    from fenceai.fencemodel.model import (
        Distributed, FenceModel, FrameSlot, PanelSpec, PartRequirement, validate_model,
    )
    model = FenceModel(id="M", version=1, default_spec=PanelSpec(frame=[
        FrameSlot(key="rail", orientation="horizontal", placement=Distributed(count=2),
                  requirement=PartRequirement(length_rule="centre_to_centre"))]))
    errors = validate_model(model, demo_catalog())
    assert any("names no part" in e for e in errors), errors


def test_resolution_fills_the_role_from_the_parts_type():
    """`role` left AUTHORING, not the system: `ResolvedSlot.role` is required and the
    BOM, the requirements and the decision graph all read it. The part's `type` is
    the one authority on what a piece is, so resolution is where role comes from."""
    slat = next(m for m in demo_model_versions() if m.id == "M-SLAT")
    assert slat.default_spec.frame[0].requirement.role == ""     # not authored
    resolved, _ = resolve_model_parts(slat, library())
    assert resolved.default_spec.frame[0].requirement.role == "rail"
    assert resolved.default_spec.infill.pattern[0].requirement.role == "infill"
    assert resolved.default_spec.fixings[0].requirement.role == "screw"


def test_the_part_supplies_the_dimension_the_panel_draws():
    """The number left the slot with the SKU, and for the same reason: keeping the
    width here while the products came from elsewhere is what let a model draw 38
    while buying 45."""
    slat = next(m for m in demo_model_versions() if m.id == "M-SLAT")
    assert slat.default_spec.infill.pattern[0].width_mm == 0      # not authored
    resolved, _ = resolve_model_parts(slat, library())
    assert resolved.default_spec.infill.pattern[0].width_mm == 100

    v2 = next(m for m in demo_model_versions() if m.ref == "M-SLAT@v2")
    resolved2, _ = resolve_model_parts(v2, library())
    frame = {s.key: s for s in resolved2.default_spec.frame}
    assert frame["bottom_channel"].thickness_mm == 60
    assert frame["top_rail"].thickness_mm == 40


def test_one_sku_declaring_two_faces_stays_two_parts():
    """RAIL-3000 with a 40 mm face is not the same declaration as RAIL-3000 with
    none, and one part for both would write a face onto a slot that had declared
    nothing — an undeclared band renders `declared=False`, not as a measurement."""
    parts = {p.id: p for p in demo_parts()}
    assert parts["rail-rail-3000"].thickness_mm is None
    assert parts["rail-rail-3000-40"].thickness_mm == 40
    catalog = demo_catalog()
    assert matching_skus(parts["rail-rail-3000"], catalog) == ["RAIL-3000"]
    assert matching_skus(parts["rail-rail-3000-40"], catalog) == ["RAIL-3000"]


def test_the_multi_item_part_names_no_sku_and_admits_more_than_one():
    """Specified by what it IS — width and material — rather than by SKU, which is
    the only way a part has alternatives to offer at all."""
    part = next(p for p in demo_parts() if p.id == "rail-38-vinyl")
    assert not any(f.key == "sku" for f in part.spec)
    assert matching_skus(part, demo_catalog()) == ["RAIL-V-3000", "RAIL-V-3600"]


def test_a_fresh_store_seeds_the_library_its_models_name(tmp_path):
    from fenceai.store.db import Store
    store = Store(str(tmp_path / "t.db"))
    lib = store.part_library()
    assert {p.id for p in lib.parts} == {p.id for p in demo_parts()}
    for model in store.fence_model_library().models:
        resolve_model_parts(model, lib)


def test_reopening_a_store_does_not_overwrite_an_edited_part(tmp_path):
    """A part is EDITABLE — that is the shared entity's whole point — so re-seeding
    would undo a published fix on every restart."""
    from fenceai.store.db import Store
    path = str(tmp_path / "t.db")
    store = Store(path)
    store.save_part(store.load_part("rail-rail-3000", 1)
                    .model_copy(update={"version": 2, "status": "draft"}))
    store.set_part_status("rail-rail-3000", 2, "active")
    store.close()

    reopened = Store(path)
    assert reopened.load_part("rail-rail-3000", 1).status == "retired"
    assert reopened.part_library().latest_active("rail-rail-3000").version == 2


# --- the CLI, over a real database -------------------------------------------

def test_the_tool_migrates_a_stored_model_and_leaves_it_resolvable(tmp_path):
    """A migration nobody can run is a document. This one opens a `.db`, rewrites
    what it finds, and the result has to resolve against the library it wrote."""
    from fenceai.store.db import Store
    from tools.migrate_parts import main

    path = str(tmp_path / "m.db")
    store = Store(path)
    store.save_fence_model(_pre_migration_model("M-OLD", "SLAT-100", 100))
    store.close()

    assert main([path]) == 0                       # dry run writes nothing
    assert Store(path).load_fence_model("M-OLD", 1) \
        .default_spec.frame[0].requirement.part_id == ""

    assert main([path, "--write"]) == 0
    store = Store(path)
    migrated = store.load_fence_model("M-OLD", 1)
    named = {key: req.part_id for key, req in part_requirements(migrated)}
    assert named == {"rail": "rail-rail-3000", "slat": "infill-slat-100"}
    assert all(not req.eligibility.members
               for _key, req in part_requirements(migrated))
    resolve_model_parts(migrated, store.part_library())


def test_the_tool_refuses_a_contradiction_and_writes_nothing(tmp_path):
    """The refusal is the part of this that is not mechanical, so it is the part
    worth running end to end: nothing is half-migrated behind a stop."""
    from fenceai.store.db import Store
    from tools.migrate_parts import main

    path = str(tmp_path / "m.db")
    store = Store(path)
    store.save_fence_model(_pre_migration_model("M-A", "SLAT-100", 100))
    store.save_fence_model(_pre_migration_model("M-B", "SLAT-100", 120))
    store.close()

    assert main([path, "--write"]) == 1
    reopened = Store(path)
    for model_id in ("M-A", "M-B"):
        stored = reopened.load_fence_model(model_id, 1)
        assert all(req.part_id == "" for _key, req in part_requirements(stored)), \
            f"{model_id} was rewritten behind a refusal"


def test_the_tool_publishes_a_second_version_without_leaving_two_active(tmp_path):
    """The branch a fresh database can never reach, and the one that mattered.

    On any store whose part already says something else, migration takes the
    "spec differs -> new version" path. It saved that version with `Part.status`'s
    default — `active` — beside an active predecessor, committed it, and only then
    called `set_part_status(..., "active")`, which raised
    `illegal status transition active -> active`. The tool aborted AFTER the write:
    two active versions of one id, and the models never rewritten.
    """
    from fenceai.parts.model import SpecField
    from fenceai.store.db import Store
    from tools.migrate_parts import main

    path = str(tmp_path / "m.db")
    store = Store(path)
    # the store's seeded `rail-rail-3000@v1` says exactly what migration would
    # write, so move it: v2 declares a material the migrated spec does not
    seeded = store.load_part("rail-rail-3000", 1)
    store.save_part(seeded.model_copy(update={
        "version": 2, "status": "draft",
        "spec": [*seeded.spec, SpecField(key="material", value="aluminium")]}))
    store.set_part_status("rail-rail-3000", 2, "active")
    store.save_fence_model(_pre_migration_model("M-OLD", "SLAT-100", 100))
    store.close()

    assert main([path, "--write"]) == 0
    store = Store(path)
    versions = {p.version: p.status for p in store.part_library().parts
                if p.id == "rail-rail-3000"}
    assert versions == {1: "retired", 2: "retired", 3: "active"}
    # and the models really were rewritten, which is what the abort used to lose
    migrated = store.load_fence_model("M-OLD", 1)
    assert {key: req.part_id for key, req in part_requirements(migrated)} == {
        "rail": "rail-rail-3000", "slat": "infill-slat-100"}
    resolve_model_parts(migrated, store.part_library())
