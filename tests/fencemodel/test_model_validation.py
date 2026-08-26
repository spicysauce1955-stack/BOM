"""Load-time validation. A model is authored data, so it is checked once when it
loads rather than trusted at every resolution."""

from fenceai.catalog.demo import demo_catalog
from fenceai.knowledge.ast import And, Cmp, FieldRef, Lit
from fenceai.parts.model import PartLibrary
from fenceai.fencemodel.model import (
    Distributed, Eligibility, EligibleItem, FenceModel, FrameSlot, PanelSpec,
    PartRequirement, PostSlot, Variant, site_condition_paths, validate_model,
)


def _slot(**kw) -> FrameSlot:
    req = kw.pop("requirement", PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    ))
    return FrameSlot(key="rail", orientation="horizontal",
                     placement=Distributed(count=2), requirement=req, **kw)


def _model(spec: PanelSpec) -> FenceModel:
    return FenceModel(id="M-TEST", version=1, name_i18n={"en": "Test"},
                      default_spec=spec)


def test_a_wellformed_model_validates_clean():
    assert validate_model(_model(PanelSpec(frame=[_slot()])), demo_catalog()) == []


def test_an_eligible_sku_missing_from_the_catalog_is_rejected():
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="NOPE", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("NOPE" in e for e in errs)


def test_a_length_requirement_needs_a_member_that_can_supply_a_length():
    """POST-CAP is indivisible with no length_mm attribute, so it cannot be cut
    to a rail length. Consumption semantics live on the product (foundation §5)
    and the model is checked against them rather than restating them."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="POST-CAP", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("POST-CAP" in e and "length" in e for e in errs)


def test_sku_by_option_must_name_an_eligible_member():
    """An option value can NARROW eligibility; it can never smuggle in a product
    the slot does not allow. Still refused now that options RESOLVE: this is the
    check that makes "narrows, never bypasses" true rather than aspirational."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="frame_finish", sku_by_option={"black": "POST-S"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("frame_finish" in e and "POST-S" in e for e in errs)


def test_sku_by_option_key_must_be_a_declared_axis_value():
    """The flip side of the eligible-member check: an option VALUE that no
    `OptionValue` declares can never be selected, so it narrows nothing — the
    same dangling-reference error the eligible-sku and option_axis checks
    already catch."""
    from fenceai.fencemodel.model import Axis, OptionValue

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="frame_finish", sku_by_option={"TYPO_VALUE": "RAIL-3000"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    model = FenceModel(
        id="M-TEST", version=1, name_i18n={"en": "Test"},
        default_spec=PanelSpec(frame=[_slot(requirement=req)]),
        option_axes=[Axis(key="frame_finish", kind="enum", values=[
            OptionValue(key="black", label_i18n={"en": "Black"}),
        ])],
    )
    errs = validate_model(model, demo_catalog())
    assert any("frame_finish" in e and "TYPO_VALUE" in e for e in errs)


def test_duplicate_slot_keys_are_rejected():
    """slot_key is an override anchor dimension; two slots sharing one key would
    make an override ambiguous."""
    errs = validate_model(_model(PanelSpec(frame=[_slot(), _slot()])), demo_catalog())
    assert any("duplicate" in e.lower() for e in errs)


def test_a_swatch_must_be_a_plain_hex_colour():
    """The swatch reaches an SVG fill, which is a style context where esc() is not
    sufficient — so it is constrained at load, not escaped at render."""
    from fenceai.fencemodel.model import Axis, OptionValue

    model = FenceModel(
        id="M-TEST", version=1, name_i18n={"en": "T"},
        default_spec=PanelSpec(frame=[_slot()]),
        option_axes=[Axis(key="finish", kind="enum", values=[
            OptionValue(key="x", label_i18n={"en": "X"}, swatch="url(javascript:0)"),
        ])],
    )
    assert any("swatch" in e for e in validate_model(model, demo_catalog()))


# ---- a pattern that never advances (fix wave, finding A) ---------------------

def _infill_model(**member_kw) -> FenceModel:
    """A model whose single infill member is authored by the caller."""
    from fenceai.fencemodel.model import InfillSpec, Member

    base = dict(key="slat", width_mm=90, gap_after_mm=20)
    return _model(PanelSpec(infill=InfillSpec(
        orientation="vertical",
        pattern=[Member(**{**base, **member_kw}, requirement=PartRequirement(
            role="infill", qty=1, length_rule="centre_to_centre",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
        ))],
    )))


# The three rules below are part-DERIVED — a member's width and a frame member's
# face arrive from the part the slot names — so `validate_model` skips them without
# a library rather than refusing the whole portfolio for numbers it has not looked
# up yet. These fixtures name no part, so resolution leaves their authored numbers
# exactly as written; the empty library is how the caller says "I can answer that".
_RESOLVED = PartLibrary()


def test_a_zero_width_member_is_rejected():
    """`fit_pattern` places members while the next one still fits; a member with
    no width fits for ever. Nothing bounded width_mm before."""
    errs = validate_model(_infill_model(width_mm=0), demo_catalog(), _RESOLVED)
    assert any("width_mm must be positive" in e for e in errs)


def test_a_member_whose_overlap_swallows_it_whole_is_rejected():
    """A negative gap is a documented feature (board-on-board). A negative gap
    at least as big as the member is a pattern that never advances — infinitely
    many slats in one bay, which used to hang generate()."""
    errs = validate_model(_infill_model(width_mm=100, gap_after_mm=-100),
                          demo_catalog(), _RESOLVED)
    assert any("never advance" in e for e in errs)


def test_an_ordinary_overlap_is_still_accepted():
    """The bound is on the member's NET advance, not on the sign of the gap —
    board-on-board must keep working."""
    assert validate_model(_infill_model(width_mm=100, gap_after_mm=-25),
                          demo_catalog()) == []


# ---- validated-then-ignored features (fix wave, finding G) -------------------

def test_a_model_with_variants_validates_clean_now_that_they_resolve():
    """Turned on in W3: `choose_variant` is called per bay by the generator, so a
    variant condition is evaluated rather than ignored. The entry that refused
    this left `_unsupported_features` in the same change."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import Variant

    model = _model(PanelSpec(frame=[_slot()]))
    model.variants = [Variant(
        condition=Cmp(cmp="<", left=FieldRef(path="panel.height_mm"), right=Lit(value=1200)),
        spec=PanelSpec(frame=[_slot()]),
    )]
    assert validate_model(model, demo_catalog()) == []


def test_a_variants_own_spec_is_validated_like_the_default_one():
    """A variant spec reaches `resolve_panel` exactly as `default_spec` does, so
    an unstocked sku inside one is the same wrong BOM."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import Variant

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(members=[EligibleItem(sku="NOPE", priority=1)]),
    )
    model = _model(PanelSpec(frame=[_slot()]))
    model.variants = [Variant(
        condition=Cmp(cmp="<", left=FieldRef(path="panel.height_mm"), right=Lit(value=1200)),
        spec=PanelSpec(frame=[_slot(requirement=req)]),
    )]
    assert any("NOPE" in e for e in validate_model(model, demo_catalog()))


def test_option_axes_validate_clean_now_that_a_chosen_value_is_read():
    from fenceai.fencemodel.model import Axis, OptionValue

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        option_axis="finish", sku_by_option={"black": "RAIL-3000"},
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    model = _model(PanelSpec(frame=[_slot(requirement=req)]))
    model.option_axes = [Axis(key="finish", kind="enum",
                              values=[OptionValue(key="black", swatch="#101010")])]
    assert validate_model(model, demo_catalog()) == []


def test_an_axis_with_available_when_is_still_refused():
    """The one part of the axis feature W3 did NOT build: nothing evaluates
    `available_when`, so an axis that is supposed to disappear would still be
    answerable and the answer would still narrow a slot."""
    from fenceai.fencemodel.model import Axis, OptionValue
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit

    model = _model(PanelSpec(frame=[_slot()]))
    model.option_axes = [Axis(
        key="finish", kind="enum", values=[OptionValue(key="black")],
        available_when=Cmp(cmp=">", left=FieldRef(path="panel.height_mm"),
                           right=Lit(value=1200)),
    )]
    errs = validate_model(model, demo_catalog())
    assert any("available_when" in e and "not yet supported" in e for e in errs)


def test_a_restricted_height_support_validates_clean_now_that_it_is_checked():
    """Generation compares each bay's height against the ladder and reports the
    ones it cannot build, per section — so declaring a ladder is no longer an
    ask that goes nowhere."""
    from fenceai.fencemodel.model import Discrete

    model = _model(PanelSpec(frame=[_slot()]))
    model.height_support = Discrete(heights_mm=[1000, 1200])
    assert validate_model(model, demo_catalog()) == []


def test_the_permissive_default_height_support_is_not_flagged():
    """Only a model that ASKS for something unbuilt is refused; the default asks
    for nothing, so M-LEGACY and every phase-1 model stay clean."""
    assert validate_model(_model(PanelSpec(frame=[_slot()])), demo_catalog()) == []


def test_a_layout_policy_over_series_scoped_params_validates_clean():
    """Each contribution becomes a knowledge version scoped to `series=<model>`,
    resolved by the same evaluator as everything else."""
    from fenceai.fencemodel.model import PolicyContribution

    model = _model(PanelSpec(frame=[_slot()]))
    model.layout_policy = [
        PolicyContribution(param="max_span_mm", value=1500,
                           knowledge_type="hard_constraint"),
        PolicyContribution(param="rails_per_span", value=3,
                           knowledge_type="preference"),
    ]
    assert validate_model(model, demo_catalog()) == []


def test_a_contribution_to_a_param_no_model_scope_reaches_is_refused():
    """`post_embed_mm` is resolved once for the whole topology, from a scope with
    no `series` bound. A contribution naming it would enter the evaluator and
    match nothing — accepted, emitted, and silently without effect, which is the
    exact shape this table exists to refuse."""
    from fenceai.fencemodel.model import PolicyContribution

    model = _model(PanelSpec(frame=[_slot()]))
    model.layout_policy = [PolicyContribution(
        param="post_embed_mm", value=900, knowledge_type="hard_constraint")]
    errs = validate_model(model, demo_catalog())
    assert any("post_embed_mm" in e and "not yet supported" in e for e in errs)


def test_a_predicate_beside_authored_members_is_still_refused():
    """This slot used to be refused because NOTHING evaluated a predicate. The
    matcher evaluates it now, and freezes what it selects — so the refusal that
    remains is the narrow one: a slot says what it needs, or which products it
    accepts, never both.

    Kept as the same shape the old refusal test used, because that shape (a
    predicate riding along beside a members list) is exactly what an editor
    produces when someone converts a slot from one mode to the other and does not
    clear the field they left behind."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit

    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(
            members=[EligibleItem(sku="RAIL-3000", priority=1)],
            predicate=Cmp(cmp="==", left=FieldRef(path="item.finish"),
                          right=Lit(value="black")),
        ),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("predicate" in e and "members" in e for e in errs)


def test_trim_last_and_extension_clip_are_refused_for_their_own_reasons():
    """Both were labelled "not yet supported (phase 2)", and neither is.

    `trim_last` rips the last member NARROWER, which is 2D cutting — the standing
    non-goal, not a queued feature; the cut planner cuts to length and nothing
    can price a part whose width changed. `extension_clip` is undesigned rather
    than unbuilt: `InfillSpec` has nowhere to name the clip product, and how many
    clips a residual needs depends on the justification. A refusal that names the
    wrong reason sends the next reader to the wrong place."""
    from fenceai.fencemodel.model import InfillSpec, Member

    for excess in ("trim_last", "extension_clip"):
        model = _model(PanelSpec(infill=InfillSpec(
            orientation="vertical", excess=excess,
            pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                            requirement=PartRequirement(
                                role="infill", qty=1, length_rule="centre_to_centre",
                                eligibility=Eligibility(members=[
                                    EligibleItem(sku="RAIL-3000")])))],
        )))
        errs = validate_model(model, demo_catalog())
        reason = {"trim_last": "2D cutting", "extension_clip": "not designed yet"}[excess]
        assert any(excess in e and reason in e for e in errs), (excess, errs)
        assert not any("phase 2" in e for e in errs), \
            "neither of these is waiting on phase 2"


def test_an_assembly_infill_is_refused_because_resolve_panel_buys_the_parts():
    """`supply="assembly"` means the infill is BOUGHT as one pre-made unit rather
    than as N members. `resolve_panel` unconditionally emits a component slot per
    member and nothing reads the field, so authoring it passed validation and
    silently produced a different set of purchased SKUs. It was classified as
    geometry-only in the first pass; it is not geometry, it is the BOM."""
    from fenceai.fencemodel.model import InfillSpec, Member

    model = _model(PanelSpec(infill=InfillSpec(
        orientation="vertical", supply="assembly",
        pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-3000")])))],
    )))
    errs = validate_model(model, demo_catalog())
    assert any("supply=" in e and "not yet supported" in e for e in errs), errs


def test_the_default_components_infill_supply_is_not_flagged():
    """The rejection must be of the UNBUILT value, not of the field existing —
    or every infill model in phase 2 starts life invalid."""
    from fenceai.fencemodel.model import InfillSpec, Member

    model = _model(PanelSpec(infill=InfillSpec(
        orientation="vertical",
        pattern=[Member(key="slat", width_mm=90, gap_after_mm=20,
                        requirement=PartRequirement(
                            role="infill", qty=1, length_rule="centre_to_centre",
                            eligibility=Eligibility(members=[
                                EligibleItem(sku="RAIL-3000")])))],
    )))
    assert validate_model(model, demo_catalog()) == []


def test_a_named_eligibility_group_is_refused_because_it_could_change_the_answer():
    """`resolve_supply` groups by the members' (sku, priority, approval)
    signature and never reads `Eligibility.group`. That is not cosmetic:
    grouping decides which lines are costed TOGETHER, and cut planning is not
    additive, so it decides which product wins. See
    test_grouping_changes_which_product_wins in tests/fulfillment/test_supply.py
    for the measurement."""
    req = PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(
            group="rails", members=[EligibleItem(sku="RAIL-3000", priority=1)]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("Eligibility.group" in e and "not yet supported" in e for e in errs)


# ---- joint geometry (two-tier visualizer, W2) --------------------------------
#
# These are not "invalid data" in the schema sense — every one of them loads,
# resolves, and produces an integer. They are refused because the integer would
# be wrong on every bay of every job built to the model, and would arrive on a
# cut list looking exactly like a measured one. So each test below asserts BOTH
# halves: the mistake is caught, and the same model without it is clean.

def _jointed(frame_kw=None, top_kw=None, member_kw=None, member_req=None) -> FenceModel:
    """A slat panel seated into a bottom channel and butted under a top rail —
    the shape M-SLAT@v2 has — with each part open to the caller so a test can
    change exactly one thing."""
    from fenceai.fencemodel.model import FromBottom, FromTop, InfillSpec, Member

    def rail(key, placement, **kw):
        return FrameSlot(**{
            "key": key, "orientation": "horizontal", "placement": placement,
            "requirement": PartRequirement(
                role="rail", qty=1, length_rule="centre_to_centre",
                eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
            ),
            **kw,
        })

    base = dict(thickness_mm=60, joint="channel", channel_depth_mm=20,
                insertion_margin_mm=3)
    member = dict(base_ref="bottom_channel", top_ref="top_rail",
                  joint="channel", base_engagement_mm=15)
    req = member_req or PartRequirement(
        role="infill", qty=1, length_rule="between_frame",
        eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")]),
    )
    return _model(PanelSpec(
        frame=[rail("bottom_channel", FromBottom(offset_mm=50),
                    **{**base, **(frame_kw or {})}),
               rail("top_rail", FromTop(offset_mm=50),
                    **{**dict(thickness_mm=40), **(top_kw or {})})],
        infill=InfillSpec(orientation="vertical", pattern=[Member(
            key="slat", width_mm=100, gap_after_mm=20,
            **{**member, **(member_kw or {})}, requirement=req)]),
    ))


def test_a_jointed_panel_validates_clean():
    """The baseline every refusal below is a single edit away from. Without it,
    a test asserting "some error is reported" would pass on a fixture that was
    broken for an unrelated reason."""
    assert validate_model(_jointed(), demo_catalog()) == []


def test_between_frame_without_refs_has_nothing_to_measure_between():
    errs = validate_model(
        _jointed(member_kw={"base_ref": None, "top_ref": None, "joint": "butt",
                            "base_engagement_mm": 0}),
        demo_catalog())
    assert any("nothing to measure between" in e for e in errs), errs


def test_a_ref_must_name_a_frame_slot_of_the_same_spec():
    """A fixing key, an infill key, or a frame slot of a DIFFERENT variant are
    all plausible things to type, and none of them has a placement."""
    errs = validate_model(_jointed(member_kw={"base_ref": "screw"}), demo_catalog())
    assert any("'screw' is not a frame slot of this spec" in e for e in errs), errs


def test_a_ref_may_not_reach_into_another_variants_frame():
    """"of this spec" is the whole check. Each variant is resolved on its own —
    `resolve_panel` sees one spec and the frame slots IN it — so a default-spec
    member naming a slot that exists only in the variant's frame is measured
    against nothing, in whichever bays the variant does not win."""
    from fenceai.knowledge.ast import Cmp, FieldRef, Lit
    from fenceai.fencemodel.model import FromBottom, InfillSpec, Member, Variant

    variant_only = FrameSlot(
        key="mid_rail", orientation="horizontal", placement=FromBottom(offset_mm=900),
        thickness_mm=40,
        requirement=PartRequirement(
            role="rail", qty=1, length_rule="centre_to_centre",
            eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")])),
    )
    model = _jointed(member_kw={"top_ref": "mid_rail"})
    model.variants = [Variant(
        condition=Cmp(cmp="<", left=FieldRef(path="panel.height_mm"), right=Lit(value=1200)),
        spec=PanelSpec(frame=[*model.default_spec.frame, variant_only],
                       infill=InfillSpec(orientation="vertical", pattern=[
                           Member(key="slat", width_mm=100, gap_after_mm=20,
                                  base_ref="bottom_channel", top_ref="mid_rail",
                                  requirement=PartRequirement(
                                      role="infill", qty=1, length_rule="between_frame",
                                      eligibility=Eligibility(members=[
                                          EligibleItem(sku="SLAT-100")])))])),
    )]

    errs = validate_model(model, demo_catalog())
    assert any("'mid_rail' is not a frame slot of this spec" in e for e in errs), errs
    # the variant's OWN member names it legitimately, and is not flagged
    assert sum("mid_rail" in e for e in errs) == 1


def test_an_engagement_deeper_than_the_channel_cuts_the_member_too_long():
    """20 mm of slat into a 12 mm channel that keeps 3 mm of insertion clearance
    under it: the seat on offer is 9 mm, so the member stands 11 mm proud — on
    every bay, in a number that reads as measured.

    Measured against depth MINUS margin, not against the depth alone: a 12 mm
    seat in that same 12 mm channel bottoms out in the clearance the channel
    exists to keep, and a depth-only check called that clean."""
    errs = validate_model(
        _jointed(frame_kw={"channel_depth_mm": 12},
                 member_kw={"base_engagement_mm": 20}),
        demo_catalog())
    assert any("11 mm too long" in e for e in errs), errs
    assert any("12 mm less 3 mm of insertion clearance" in e for e in errs), errs

    # 12 into a 12 mm channel with 3 mm of clearance is still refused ...
    assert validate_model(
        _jointed(frame_kw={"channel_depth_mm": 12},
                 member_kw={"base_engagement_mm": 12}), demo_catalog()) != []
    # ... and 9 — exactly what the channel offers — is the deepest that is not
    assert validate_model(
        _jointed(frame_kw={"channel_depth_mm": 12},
                 member_kw={"base_engagement_mm": 9}), demo_catalog()) == []


def test_a_channel_inside_an_undeclared_member_has_no_datum():
    """`thickness_mm=0` is "undeclared" everywhere else in this schema, so a
    depth measured into it is measured from a face the model does not have."""
    errs = validate_model(_jointed(frame_kw={"thickness_mm": 0}), demo_catalog(),
                          _RESOLVED)
    assert any("thickness_mm is undeclared" in e for e in errs), errs


def test_a_margin_that_reaches_the_bottom_of_the_channel_is_refused():
    """The margin is the clearance under the seated end. At or past the depth it
    swallows the seat, and the member rests on nothing."""
    errs = validate_model(_jointed(frame_kw={"insertion_margin_mm": 20}),
                          demo_catalog())
    assert any("swallows the whole seat" in e for e in errs), errs
    # 19 leaves 1 mm of seat, which the fixture's 15 mm engagement then overruns
    # — so the clean case has to shorten the member too, rather than pretending
    # the margin alone was the whole rule
    assert validate_model(
        _jointed(frame_kw={"insertion_margin_mm": 19},
                 member_kw={"base_engagement_mm": 1}), demo_catalog()) == []


def test_a_joint_kind_with_no_numbers_behind_it_is_refused_at_both_ends():
    """The kind is what the drawing and the shop read; the millimetres are what
    the cut list reads. A `channel` with neither a depth nor an engagement is a
    butt joint wearing a better name — and it would be DRAWN as a housed one."""
    frame_errs = validate_model(
        _jointed(top_kw={"joint": "groove"}), demo_catalog())
    assert any("joint='groove'" in e and "channel_depth_mm=0" in e
               for e in frame_errs), frame_errs

    # A member is only bare if BOTH ends are: no engagement of its own AND no
    # channel in either slot it names — the conjunction the spec states.
    member_errs = validate_model(
        _jointed(frame_kw={"joint": "butt", "channel_depth_mm": 0,
                           "insertion_margin_mm": 0},
                 member_kw={"joint": "groove", "base_engagement_mm": 0}),
        demo_catalog())
    assert any("joint='groove'" in e and "no engagement at either end" in e
               for e in member_errs), member_errs
    # and a member that seats nothing itself but names a slot that DOES house it
    # is not bare — the mechanic is the channel's
    assert validate_model(
        _jointed(member_kw={"joint": "groove", "base_engagement_mm": 0}),
        demo_catalog()) == []


def test_a_joint_kind_the_schema_cannot_express_is_refused_as_unbuilt():
    """`bracket` and `overlap` are in the vocabulary because the spec named them,
    and neither has a field that could make it mean anything: a bracket's
    mechanic is a product, an overlap's is a lap length. Refused with the reason
    they cannot be authored, rather than with advice ("give the channel its
    depth") that is impossible to follow for a joint with no channel."""
    for kind in ("bracket", "overlap"):
        errs = validate_model(_jointed(top_kw={"joint": kind}), demo_catalog())
        assert any(f"joint={kind!r}" in e and "not yet supported" in e
                   for e in errs), (kind, errs)
        member = validate_model(_jointed(member_kw={"joint": kind}), demo_catalog())
        assert any(f"joint={kind!r}" in e and "not yet supported" in e
                   for e in member), (kind, member)


def test_a_channel_deeper_than_the_member_it_is_cut_into_is_refused():
    """The mirror of the engagement check, and it was missing: refusing a seat
    deeper than its channel while accepting a channel deeper than the rail it is
    cut into is an inconsistent pair, and the second one comes out the far
    side."""
    errs = validate_model(
        _jointed(frame_kw={"thickness_mm": 40, "channel_depth_mm": 60}),
        demo_catalog())
    assert any("come out the far side" in e for e in errs), errs
    assert validate_model(
        _jointed(frame_kw={"thickness_mm": 40, "channel_depth_mm": 20}),
        demo_catalog()) == []


def test_an_engagement_under_another_length_rule_is_refused_too():
    """The other half of the refs gap, and it was still open: `_length_for` adds
    an engagement under `between_frame` and under no other rule, so an author who
    says the slat seats 15 mm into the channel and cuts it to `panel_height` gets
    a member cut as though it seated into nothing."""
    errs = validate_model(
        _jointed(member_kw={"base_ref": None, "top_ref": None},
                 member_req=PartRequirement(
                     role="infill", qty=1, length_rule="panel_height",
                     eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")]),
                 )),
        demo_catalog())
    assert any("base_engagement_mm" in e and "not yet supported" in e
               for e in errs), errs


def test_a_ref_must_name_a_frame_slot_the_member_actually_crosses():
    """`placement_positions` places a horizontal slot up the HEIGHT and a
    vertical one across the CLEAR WIDTH, and `_between_frame_length` reads
    positions without asking which axis they are on — deliberately, since it is
    the same arithmetic either way. So a vertical slat referred to a vertical
    stile is cut to a distance measured across the bay, on a part that runs up
    it, and the resulting integer looks like every other length in the list.
    """
    errs = validate_model(
        _jointed(top_kw={"orientation": "vertical",
                         "joint": "channel", "channel_depth_mm": 20}),
        demo_catalog())
    assert any("never cross" in e for e in errs), errs
    # and the same model with the stile turned back into a rail is clean, so
    # this is the orientation being read and not the fixture being broken
    assert validate_model(_jointed(), demo_catalog()) == []


def test_a_frame_slot_may_not_declare_between_frame():
    """It is a member-to-frame rule and a frame slot has no refs, so the slot
    would resolve to no cut length at all — and a divisible rail asked for with
    no length plans no bars, prices nothing, and reads as covered from stock."""
    req = PartRequirement(
        role="rail", qty=1, length_rule="between_frame",
        eligibility=Eligibility(members=[EligibleItem(sku="RAIL-3000")]),
    )
    errs = validate_model(_model(PanelSpec(frame=[_slot(requirement=req)])),
                          demo_catalog())
    assert any("has no base_ref/top_ref to measure between" in e for e in errs), errs


def test_refs_under_any_other_length_rule_are_refused_as_unbuilt():
    """The gap this wave closed, kept closed from the other side. `_length_for`
    reads the refs under `between_frame` and under no other rule, so a member
    that declares "starts at the bottom rail" and is cut to `panel_height` runs
    past it to the ground — while the editor shows both selects, answered."""
    errs = validate_model(
        _jointed(member_kw={"joint": "butt", "base_engagement_mm": 0},
                 member_req=PartRequirement(
                     role="infill", qty=1, length_rule="panel_height",
                     eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")]),
                 )),
        demo_catalog())
    assert any("base_ref and top_ref" in e and "not yet supported" in e
               for e in errs), errs

    # ONE ref is the same wrong answer and the easier one to miss — an author
    # who names only where the member starts still gets a part cut to the panel
    # height, and a check written as "both refs set" would pass it.
    one = validate_model(
        _jointed(member_kw={"joint": "butt", "base_engagement_mm": 0,
                            "top_ref": None},
                 member_req=PartRequirement(
                     role="infill", qty=1, length_rule="panel_height",
                     eligibility=Eligibility(members=[EligibleItem(sku="SLAT-100")]),
                 )),
        demo_catalog())
    assert any("base_ref with" in e and "not yet supported" in e for e in one), one


# --- spec-declared eligibility (the matcher) ----------------------------------

RAIL_IS_ALUMINIUM = Cmp(cmp="==", left=FieldRef(path="item.material"),
                        right=Lit(value="aluminium"))
NOTHING_IS_UNOBTAINIUM = Cmp(cmp="==", left=FieldRef(path="item.material"),
                             right=Lit(value="unobtainium"))


def _predicate_slot(predicate, **kw) -> FrameSlot:
    return _slot(requirement=PartRequirement(
        role="rail", qty=2, length_rule="centre_to_centre",
        eligibility=Eligibility(predicate=predicate, **kw),
    ))


RAIL_SUPPLIES_A_LENGTH = And(items=[
    RAIL_IS_ALUMINIUM,
    Cmp(cmp=">=", left=FieldRef(path="item.stock_length_mm"), right=Lit(value=0)),
])


def test_a_slot_may_declare_what_it_needs_instead_of_naming_skus():
    """The refusal `_unsupported_features` carried since phase 1 is gone: the
    matcher evaluates the predicate and freezes the members it selects."""
    errs = validate_model(
        _model(PanelSpec(frame=[_predicate_slot(RAIL_SUPPLIES_A_LENGTH)])),
        demo_catalog())
    assert errs == []


def test_a_predicate_admitting_a_product_that_cannot_be_cut_is_refused():
    """The length_rule check is about the SLOT, not about how it said its
    eligibility. `item.material == "aluminium"` beside `centre_to_centre` admits
    this catalog's gate kit, its leaf, its hinge set and its cap — four products
    the slot would ask for a cut length and none of which has one — and a
    predicate slot used to walk past this check entirely, because the loop
    `continue`d before reaching it. After resolution that branch is EVERY
    part-named slot, so the check was off for the whole portfolio."""
    errs = validate_model(
        _model(PanelSpec(frame=[_predicate_slot(RAIL_IS_ALUMINIUM)])), demo_catalog())
    assert sorted(e for e in errs if "cannot supply a length" in e) == [
        "slot rail: GATE-KIT-1000 cannot supply a length "
        "(not divisible, declares no capabilities.length_mm)",
        "slot rail: GATE-LEAF-1000 cannot supply a length "
        "(not divisible, declares no capabilities.length_mm)",
        "slot rail: HINGE-SET cannot supply a length "
        "(not divisible, declares no capabilities.length_mm)",
        "slot rail: POST-CAP cannot supply a length "
        "(not divisible, declares no capabilities.length_mm)",
    ], errs


def test_a_slot_cannot_both_name_skus_and_declare_a_predicate():
    """Two modes, never combined. "Intersect the typed list with the matched
    list" has two defensible readings and neither is needed."""
    errs = validate_model(
        _model(PanelSpec(frame=[_predicate_slot(
            RAIL_IS_ALUMINIUM, members=[EligibleItem(sku="RAIL-3000")])])),
        demo_catalog())
    assert any("predicate" in e and "members" in e for e in errs)


def test_a_predicate_no_item_in_the_catalog_covers_is_refused_at_authoring():
    """The same guardrail an empty `members` list already gets, and for the same
    reason: a slot nothing can supply publishes cleanly and then reports
    `no_eligible_item` on every bay of every job built to it. The author is the
    only person who can say what belongs there, and now is when they can."""
    errs = validate_model(
        _model(PanelSpec(frame=[_predicate_slot(NOTHING_IS_UNOBTAINIUM)])),
        demo_catalog())
    assert any("no item" in e.lower() for e in errs)


# --- a condition on the site ---------------------------------------------------
#
# `site.*` is bound into the fence model's condition context, so a variant or a
# predicate may read it. What it may NOT read is a dimension that does not
# exist: the context never carries the key, `MissingField` reads as *not
# applicable*, and the variant falls through to the default spec — the exact
# silence the binding was built to end, reinstated by a typo.

HVHZ = Cmp(cmp="==", left=FieldRef(path="site.hvhz"), right=Lit(value=True))
HVZH = Cmp(cmp="==", left=FieldRef(path="site.hvzh"), right=Lit(value=True))


def _variant_model(condition) -> FenceModel:
    model = _model(PanelSpec(frame=[_slot()]))
    model.variants = [Variant(condition=condition,
                              spec=PanelSpec(frame=[_slot()]))]
    return model


def test_a_variant_conditioned_on_a_real_site_dimension_validates_clean():
    """The capability, pinned from the authoring side. Refusing this was the
    alternative to binding, and it would have left the model author with no way
    to say the one thing site conditions exist for."""
    assert validate_model(_variant_model(HVHZ), demo_catalog()) == []


def test_a_variant_conditioned_on_a_site_dimension_that_does_not_exist_is_refused():
    """Same class as a slot naming an option axis the model does not declare, and
    it fails the same way if uncaught: nothing satisfies it ever, so the variant
    is dead and the fence is built to the default with nobody told.

    The message NAMES the known dimensions, because `hvzh` is a transposition and
    the repair is a character, not a category.
    """
    errs = validate_model(_variant_model(HVZH), demo_catalog())
    assert len(errs) == 1, errs
    assert "site.hvzh is not a site condition" in errs[0]
    assert "site.hvhz" in errs[0]


def test_a_predicate_reading_a_site_dimension_that_does_not_exist_is_refused():
    """The same refusal over an eligibility predicate, which fails one level down
    but just as quietly: the predicate admits nothing and the slot falls through
    to the company default."""
    predicate = And(items=[RAIL_IS_ALUMINIUM, HVZH])
    errs = validate_model(
        _model(PanelSpec(frame=[_predicate_slot(predicate)])), demo_catalog())
    assert any("site.hvzh is not a site condition" in e for e in errs)


def test_the_known_dimensions_are_SiteConditions_own_fields():
    """One definition. A hand-written list here would go stale in the direction
    that never fires — a dimension the model gains and this set does not is a
    condition refused at authoring for being real."""
    from fenceai.project.model import SITE_DIMENSIONS, SiteConditions

    assert SITE_DIMENSIONS == frozenset(SiteConditions.model_fields) - {"revision"}
    # A legal value PER dimension, because a closed dimension refuses one outside
    # its domain (`_site_domain_errors`) — which is the next test down. Comparing
    # every dimension to the same `1` would test the domain check here by
    # accident and hide whichever of the two actually failed.
    legal = {"exposure_category": "C", "hvhz": True, "frost_depth_mm": 900,
             "jurisdiction": "Miami-Dade", "code_edition": "ASCE 7-16"}
    assert set(legal) == set(SITE_DIMENSIONS), "a dimension has no legal value here"
    for dim, value in sorted(legal.items()):
        reads = Cmp(cmp="==", left=FieldRef(path=f"site.{dim}"),
                    right=Lit(value=value))
        assert validate_model(_variant_model(reads), demo_catalog()) == [], dim


def test_a_closed_dimension_refuses_a_value_it_can_never_hold():
    """The refusal a NAME check alone lets past, and the likeliest of the three
    to be typed by somebody who knows the field exists: `exposure_category` is
    `Literal["B","C","D"]`, so `== "Z"` is supplied, evaluated, and never true.

    Dead exactly like an unknown dimension is dead — the variant falls through to
    the default spec, the model looks authored — but the name is spelled right,
    so nothing else in the stack ever objects.
    """
    dead = Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
               right=Lit(value="Z"))
    errs = validate_model(_variant_model(dead), demo_catalog())
    assert len(errs) == 1, errs
    assert "site.exposure_category cannot be 'Z'" in errs[0]
    assert "'B', 'C', 'D'" in errs[0]


def test_an_open_dimension_is_not_second_guessed():
    """`jurisdiction` is free text and a frost depth is a number: "can never be
    true" is not decidable for either, so neither is refused. A validator that
    guessed here would refuse real sites."""
    for path, value in (("site.jurisdiction", "Nowhere County"),
                        ("site.frost_depth_mm", 999999)):
        reads = Cmp(cmp="==", left=FieldRef(path=path), right=Lit(value=value))
        assert validate_model(_variant_model(reads), demo_catalog()) == [], path


def test_a_nested_site_path_is_refused():
    """A dimension is a scalar. `lookup` raises `MissingField` on the second hop,
    so `site.hvhz.enabled` is the same silent fall-through by a third route —
    and the head is spelled correctly, so the dimension check passes it."""
    nested = Cmp(cmp="==", left=FieldRef(path="site.hvhz.enabled"),
                 right=Lit(value=True))
    errs = validate_model(_variant_model(nested), demo_catalog())
    assert len(errs) == 1, errs
    assert "site.hvhz is a single value, not a record" in errs[0]
    assert "'enabled'" in errs[0]


def test_a_dead_value_buried_in_a_conjunction_is_still_found():
    """The walk is structural (`ast.walk`), so a term inside an `And` is read.
    A predicate is where this matters most: the dead conjunct makes the whole
    predicate unsatisfiable while every other term looks fine."""
    buried = And(items=[
        RAIL_IS_ALUMINIUM,
        Cmp(cmp="==", left=FieldRef(path="site.exposure_category"),
            right=Lit(value="Q")),
    ])
    errs = validate_model(
        _model(PanelSpec(frame=[_predicate_slot(buried)])), demo_catalog())
    assert any("site.exposure_category cannot be 'Q'" in e for e in errs), errs


def test_site_condition_paths_reads_the_whole_document():
    """Both callers depend on this being one walk: `validate_model` refuses an
    unknown dimension and the generator reports an unanswered one, and a walk
    that missed the post would refuse in one voice and report in the other."""
    model = _variant_model(HVHZ)
    model.default_spec = PanelSpec(frame=[_predicate_slot(
        And(items=[RAIL_IS_ALUMINIUM,
                   Cmp(cmp=">=", left=FieldRef(path="site.frost_depth_mm"),
                       right=Lit(value=1000))]))])
    # ...and the POST and its CAP, which the docstring claims and nothing pinned:
    # dropping either from the walk left the suite green.
    model.post = PostSlot(
        key="post",
        requirement=PartRequirement(
            role="post",
            eligibility=Eligibility(predicate=Cmp(
                cmp="==", left=FieldRef(path="site.exposure_category"),
                right=Lit(value="D")))),
        cap=PartRequirement(
            role="cap",
            eligibility=Eligibility(predicate=Cmp(
                cmp="==", left=FieldRef(path="site.jurisdiction"),
                right=Lit(value="Miami-Dade")))),
    )
    assert site_condition_paths(model) == {
        "hvhz", "frost_depth_mm", "exposure_category", "jurisdiction"}

