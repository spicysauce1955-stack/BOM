"""The fence model's document shapes (static/js/panel-model.js), in node —
and then validated by the REAL schema they have to satisfy.

The browser suite can only see what a whole authoring session produces. What
breaks silently is smaller and earlier: the shape of the row the "+ Add" button
appends. Every one of these is a defect the editor can ship without an error
message anywhere:

  * an eligibility member without `kind` — `Eligibility.members` is a
    discriminated union, so the whole save comes back 422 `union_tag_not_found`
    and the author is told only "the action failed";
  * a variant whose starting condition is not valid `Expr`, which is the first
    thing an author meets after pressing "+ Add variant";
  * a draft copy that carries the version it was copied FROM, which is how
    "Edit" would rewrite a published version that a run — and an accepted quote
    — was priced against;
  * an infill member default whose net advance is not positive, which
    `fit_pattern` cannot lay out at all.

So node builds the documents exactly as the buttons do, and pydantic and
`validate_model` judge them. A test that only compared JSON to a fixture would
agree with itself while the schema moved.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import FenceModel, Variant, validate_model
from fenceai.parts.model import PartLibrary

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"


def _placement_kinds() -> set[str]:
    """The arms of the `Placement` union, from the union — never retyped here,
    or a fifth arm added to the schema leaves every test that names them green."""
    from typing import get_args

    from fenceai.fencemodel.model import Placement

    annotated_union, _ = get_args(Placement)
    return {
        arm.model_fields["kind"].default for arm in get_args(annotated_union)
    }


def _js_const(name: str) -> set[str]:
    """A `const NAME = [...]` array out of panel-model.js — the values the
    editor OFFERS, read from the vocabulary rather than restated."""
    import re

    src = (STATIC / "js" / "panel-model.js").read_text()
    body = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
    assert body, f"{name} is no longer a const array in panel-model.js"
    return set(re.findall(r'"([a-z_]+)"', body.group(1)))

SCRIPT = """
import {
  SWATCH_RE, blankModel, defaultAxis, defaultEligibleMember, defaultFixing,
  defaultInfill, defaultMember, defaultPlacement, defaultSlot, defaultVariant,
  draftCopyOf, duplicateOf, freeId, idCollision, specOf,
} from "{module}";

// No stubs: `panel-model.js` reaches nothing stateful. It used to need a fake
// `localStorage` and a fake `document`, because these shapes lived beside the
// editor's DOM — and a stub that is no longer needed is a claim about the module
// that would stop being true silently.

// what "+ Add slot", "+ Add product", "+ Add infill" and "+ Add fixing" build,
// assembled into the smallest model an author can actually publish
const authored = blankModel("M-AUTHORED");
authored.name_i18n = {en: "Authored", he: "מחובר"};
const slot = defaultSlot("rail");
slot.requirement.length_rule = "centre_to_centre";
slot.requirement.eligibility.members.push(defaultEligibleMember("RAIL-3000"));
authored.default_spec.frame.push(slot);

const fixing = defaultFixing("screw");
fixing.requirement.eligibility.members.push(defaultEligibleMember("SCREW-S10"));
authored.default_spec.fixings.push(fixing);

authored.default_spec.infill = defaultInfill();
const member = authored.default_spec.infill.pattern[0];
member.requirement.eligibility.members.push(defaultEligibleMember("SLAT-100"));

// board-on-board: the gap is NEGATIVE, and the editor must not clamp it
const boardOnBoard = defaultMember("board");
boardOnBoard.width_mm = 140;
boardOnBoard.gap_after_mm = -40;

// a variant, an axis, and the spec pointer the picker uses
authored.variants.push(defaultVariant());
authored.option_axes.push(defaultAxis("colour"));

// a published v3 opened for editing: the copy must share NOTHING with the
// document that was loaded, or typing in the editor edits the library's copy
const published = {...blankModel("M-PUB"), version: 3, status: "active"};
published.default_spec.frame.push(defaultSlot("rail"));
const copy = draftCopyOf(published);
copy.default_spec.frame[0].key = "edited";
copy.name_i18n.en = "edited";

console.log(JSON.stringify({
  authored,
  board_on_board: boardOnBoard,
  variant: defaultVariant(),
  placements: ["distributed", "from_bottom", "from_top", "fraction"]
    .map(defaultPlacement),
  draft_copy: copy,
  source_after_editing_the_copy: published,
  duplicate: duplicateOf({...blankModel("M-PUB"), version: 3, status: "active"}, "M-PUB-COPY"),
  // the four session kinds, against a library that already holds two models
  id_collisions: (() => {
    const rows = [{id: "M-SLAT"}, {id: "M-SMOKE"}];
    const at = (isNew, version, id) => idCollision({isNew, version, model: {id}}, rows);
    return {
      new_free: at(true, null, "M-NEW-1"),
      new_taken: at(true, null, "M-SLAT"),
      new_after_first_save: at(true, 1, "M-NEW-1"),
      duplicate_free: at(true, null, "M-SLAT-COPY"),
      published_copy: at(false, null, "M-SMOKE"),
      existing_draft: at(false, 2, "M-SMOKE"),
    };
  })(),
  // duplicating twice before either copy is saved: the second id must not
  // collide, or POST turns it into v2 of the first copy instead of a new model
  free_ids: (() => {
    const listing = [{id: "M-A"}, {id: "M-A-COPY"}, {id: "M-A-COPY-2"}];
    return [freeId("M-A-COPY", listing), freeId("M-B", listing)];
  })(),
  spec_default_is_the_default: specOf(authored, -1) === authored.default_spec,
  spec_0_is_the_variants: specOf(authored, 0) === authored.variants[0].spec,
  swatches: {
    good: ["#a1b2c3", "#FFFFFF"].map((v) => SWATCH_RE.test(v)),
    bad: ["red", "#ab", "#12345g", "#fff", "#a1b2c3;background:url(x)",
          " #a1b2c3", "#a1b2c3 "].map((v) => SWATCH_RE.test(v)),
  },
}));
"""


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    if not shutil.which("node"):
        pytest.skip("node not available")
    module = (STATIC / "js" / "panel-model.js").as_posix()
    script = tmp_path_factory.mktemp("panel-model") / "run.mjs"
    script.write_text(SCRIPT.replace("{module}", module))
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_smallest_authored_model_is_one_the_backend_accepts(out):
    """Everything the "+ Add" buttons build, judged by the loader that has to
    take it. `validate_model` is the publish gate, so a green here is the claim
    that a model authored from defaults CAN be published."""
    model = FenceModel.model_validate(out["authored"])
    assert validate_model(model, demo_catalog(), PartLibrary()) == []


def test_every_eligibility_member_carries_its_discriminator(out):
    """`Eligibility.members` is a discriminated union: a member without `kind`
    is a 422 on the whole document, not a defaulted field.

    Judged against the value `defaultEligibleMember` RETURNS — the same function
    the "+ Add product" button calls. An earlier version of this test wrote the
    member literal itself and then asserted the literal had `kind`, which stayed
    green with the discriminator deleted from the editor."""
    members = [
        m
        for spec in [out["authored"]["default_spec"]]
        for part in [*spec["frame"], *spec["fixings"], *spec["infill"]["pattern"]]
        for m in part["requirement"]["eligibility"]["members"]
    ]
    assert len(members) == 3
    assert all(m["kind"] == "catalog_item" for m in members)
    # and the whole member, so a dropped `approval` or `priority` is caught too
    assert members[0] == {"kind": "catalog_item", "sku": "RAIL-3000",
                          "priority": 1, "approval": "auto"}


def test_the_requirement_the_editor_builds_carries_every_field_the_schema_has(out):
    """`defaultRequirement` is what "+ Add slot" writes and, with `part_id` filled
    in, what the slot pane PUTs. Parsing it proves the server takes it; the KEY SET
    proves neither side has drifted — a field added to `PartRequirement` that the
    builder never learned is a key the editor silently omits on every save, and a
    key the builder writes that the schema dropped is a value silently discarded.

    Its Python-side twin is
    `tests/api/test_authoring_gaps.py::test_the_editors_payload_for_a_part_named_slot_validates`,
    which pins the same set against the part-named shape."""
    from fenceai.fencemodel.model import PartRequirement

    built = out["authored"]["default_spec"]["frame"][0]["requirement"]
    assert set(built) == set(PartRequirement.model_fields)


def test_a_new_variants_condition_is_valid_ast(out):
    """The first thing an author meets after "+ Add variant" is this condition.
    An empty or hand-waved one makes their first experience a 422 about a
    discriminator they never chose."""
    variant = Variant.model_validate(out["variant"])
    assert variant.condition.op == "cmp"


def test_every_placement_kind_builds_the_arm_it_names(out):
    """The `Placement` union is discriminated on `kind`; choosing an arm in the
    select must build THAT arm's fields, not rename the previous one's.

    Each arm goes through the real union rather than through key spotting: an
    `offset_mm` that is present but misspelled, or a fifth arm added to the
    schema and not to the editor, is not visible to `"x" in d`."""
    from pydantic import TypeAdapter

    from fenceai.fencemodel.model import Placement

    adapter = TypeAdapter(Placement)
    built = {p["kind"]: adapter.validate_python(p) for p in out["placements"]}
    # every arm the schema has, and no arm it does not
    assert sorted(built) == sorted(_placement_kinds())
    # a knowledge param, present and answerable — rail count stays defeasible
    assert built["distributed"].count > 0 and built["distributed"].count_param is None


def test_a_negative_gap_is_offered_by_the_control_itself(out):
    """A negative `gap_after_mm` is an OVERLAP, and board-on-board and shadowbox
    are exactly that. The claim is about the CONTROL: it now shows a checkbox
    and a POSITIVE amount, so the one thing that keeps an overlap reachable is
    that the sign comes from `gapForOverlap` and no `min` bounds the amount.
    Asserting that a value the test itself set to -40 is still -40 proves
    nothing and stays green through exactly the "tidy" the module header warns
    about.

    The bound that does exist is on the member's net advance, and it lives in
    `validate_model` — checked here against the same numbers."""
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    body = src[src.index("export function gapControl"):]
    body = body[:body.index("\n}\n")]
    assert "gapForOverlap(" in body, (
        "the sign must come from the shared helper, not from a second rule here")
    assert "min" not in body, (
        "a min on the gap amount deletes board-on-board and shadowbox from the editor")

    board = out["board_on_board"]
    model = FenceModel.model_validate(out["authored"])
    member = model.default_spec.infill.pattern[0]
    member.width_mm, member.gap_after_mm = board["width_mm"], board["gap_after_mm"]
    assert member.gap_after_mm < 0
    assert validate_model(model, demo_catalog(), PartLibrary()) == []
    # ... and the bound that IS real still bites: an overlap that swallows the
    # member whole makes `fit_pattern` stand still
    member.gap_after_mm = -member.width_mm
    assert any("never advance" in e for e in validate_model(model, demo_catalog(), PartLibrary()))


def test_duplicating_twice_does_not_collide(out):
    """`freeId`'s own comment names the hazard: a POST reusing an existing id
    opens the next VERSION of that model, so a second duplicate landing on the
    first copy's id would become v2 of it rather than a new model."""
    assert out["free_ids"] == ["M-A-COPY-3", "M-B"]


def test_editing_a_published_version_edits_a_copy_that_shares_nothing_with_it(out):
    """An active version is never mutated. "Edit" opens a DEEP copy — a shallow
    one shares `default_spec`, so the first keystroke rewrites the document the
    library handed over, and every other surface reading that object (the Panel
    tab's preview among them) starts describing a panel nobody published.

    The copy keeps the id, because it is the next version OF this model, and its
    version number is the server's to assign: the editor sends it to POST
    /api/fence-models, which always lands a draft at the next free version."""
    copy = out["draft_copy"]
    assert copy["status"] == "draft" and copy["id"] == "M-PUB"
    assert copy["default_spec"]["frame"][0]["key"] == "edited"
    source = out["source_after_editing_the_copy"]
    assert source["status"] == "active" and source["version"] == 3
    assert source["default_spec"]["frame"][0]["key"] == "rail"
    assert source["name_i18n"] == {}
    duplicate = out["duplicate"]
    assert duplicate["id"] == "M-PUB-COPY" and duplicate["version"] == 1
    assert duplicate["status"] == "draft"


def test_the_spec_pointer_selects_the_live_object(out):
    """The row editors mutate whatever `specOf` returns. A copy there would let
    an author edit a variant and save the default panel unchanged."""
    assert out["spec_default_is_the_default"] is True
    assert out["spec_0_is_the_variants"] is True


def test_the_swatch_field_refuses_anything_but_plain_hex(out):
    """A swatch reaches a CSS/SVG colour, where esc() is not enough. The backend
    validates it at model load and the field must not be looser — least of all
    for a value carrying a `;`.

    The pattern must also match the backend's exactly: two whitelists that drift
    apart are a field that accepts what the loader then refuses, or worse."""
    import re

    from fenceai.fencemodel.model import _SWATCH

    assert out["swatches"]["good"] == [True, True]
    assert out["swatches"]["bad"] == [False] * 7
    for value, expected in [("#a1b2c3", True), ("#FFFFFF", True), ("red", False),
                            ("#ab", False), ("#fff", False),
                            ("#a1b2c3;background:url(x)", False)]:
        assert bool(_SWATCH.match(value)) is expected, value

    # and EVERY style assignment is guarded by it. The regex being correct is
    # not the claim — a `style.background` reaching an unchecked string is the
    # defect, and it leaves SWATCH_RE untouched. Scanned across the whole module
    # rather than one function, because this surface grew a SECOND sink (the
    # product chip beside each preference row, painted from `attrs.colour`) and
    # a scan aimed at one function by name cannot see the next one.
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    sinks = re.findall(r"\.style\.background\s*=\s*([^;]+);", src)
    assert len(sinks) >= 2, ("every colour sink must be scanned; found", sinks)
    for sink in sinks:
        assert "SWATCH_RE.test" in sink, (
            "the colour written to style must be one that matched the pattern, "
            f"got: {sink.strip()}")


def test_the_editor_and_the_backend_agree_on_the_vocabularies():
    """Each select offers a vocabulary the backend defines. A value the editor
    offers and the backend rejects is a save that 422s; one the backend has and
    the editor lacks is a product line nobody can author.

    EQUALITY in both directions, and every expected set derived rather than
    retyped — a subset assertion passes with the editor's array emptied, and a
    hand-copied set passes when a new arm is added to the backend alone.

    **Two of the five moved.** Length rules and fixing bases used to be `Literal`s
    in `model.py` and are REGISTRIES now (`core/registry.py`), so a new one is a
    registration rather than a type edit plus a branch plus a release. The
    property this test defends is unchanged; only where truth lives moved, and
    it is derived from the new home rather than retyped here.

    Which leaves the editor as the closed half: registering `per_corner` makes it
    authorable through the API and this test then FAILS until the editor's array
    names it too. That failure is correct and is the point — it is the reminder
    that a vocabulary served to a browser as a hardcoded array is not open yet.
    Closing it means serving `FIXING_BASES.names()` from a route the editor reads.
    """
    from typing import get_args

    from fenceai.fencemodel.bases import FIXING_BASES
    from fenceai.fencemodel.lengths import LENGTH_RULES
    from fenceai.fencemodel.model import EligibleItem, InfillSpec

    assert _js_const("LENGTH_RULES") == set(LENGTH_RULES.names())
    assert _js_const("BASES") == set(FIXING_BASES.names())
    assert _js_const("JUSTIFICATIONS") == set(
        get_args(InfillSpec.model_fields["justification"].annotation))
    assert _js_const("APPROVALS") == set(
        get_args(EligibleItem.model_fields["approval"].annotation))
    assert _js_const("PLACEMENT_KINDS") == _placement_kinds()


def test_the_editor_offers_every_role_the_ui_can_name_and_no_other():
    """`PartRequirement.role` is a free `str` in the schema, so nothing there
    bounds this list. What DOES bound it is the UI: `roleWord` renders a role
    through `role.<value>`, so a role the bundles cannot name renders as raw
    English inside a Hebrew sentence, and a role missing from the editor is a
    part nobody can author. `gate_kit` is the one exclusion, and deliberate: a
    gate kit is placed by the gate tool, never by a panel slot."""
    from tests.web.test_locale_bundles import ROLE_VOCABULARY

    assert _js_const("ROLES") == set(ROLE_VOCABULARY) - {"gate_kit"}


def test_the_editor_offers_only_the_axis_kinds_the_resolver_honours():
    """Nothing reads `Axis.kind`: resolution answers every axis out of its
    declared `values`, so a `numeric` axis published as numeric would behave as
    an enum of whatever was listed. W4 added the `_unsupported_features` entry
    and narrowed the select in the same change; this is what keeps the two
    halves together, exactly as the `excess` test below does."""
    from typing import get_args

    from fenceai.fencemodel.model import Axis, FenceModel, _unsupported_features

    schema = set(get_args(Axis.model_fields["kind"].annotation))
    unbuilt = {
        kind for kind in schema
        if _unsupported_features(FenceModel(
            id="M-X", version=1,
            option_axes=[Axis(key="a", kind=kind)]))
    }
    assert unbuilt, "if every axis kind is honoured, delete the entry AND widen the select"
    assert _js_const("AXIS_KINDS") == schema - unbuilt


def test_the_editor_offers_only_the_excess_modes_the_resolver_honours():
    """`trim_last` and `extension_clip` are schema-expressible and unbuilt
    (`_unsupported_features`): offering them would author a model the publish
    gate then refuses, for a reason the author cannot fix except by undoing the
    choice the editor invited. When a wave turns one on, this test is what makes
    removing the entry and widening the select the same change."""
    import re
    from typing import get_args

    from fenceai.fencemodel.model import InfillSpec, _unsupported_features

    src = (STATIC / "js" / "panel-model.js").read_text()
    offered = set(re.findall(
        r'"([a-z_]+)"', re.search(r"const EXCESS = \[(.*?)\];", src, re.S).group(1)))
    schema = set(get_args(InfillSpec.model_fields["excess"].annotation))
    unbuilt = set()
    for value in schema:
        model = FenceModel.model_validate({
            "id": "M-X", "version": 1,
            "default_spec": {"infill": {"orientation": "vertical", "excess": value}},
        })
        if _unsupported_features(model):
            unbuilt.add(value)
    assert offered == schema - unbuilt


def test_only_a_session_creating_a_model_refuses_a_taken_id(out):
    """The rule that broke, so it is pinned as a truth table.

    Four session kinds start without a version — New, Duplicate, Edit-a-draft
    and Edit-a-published-copy — and only the first two are choosing an id. The
    obvious guard ("no version yet means new") refuses the published copy, which
    is exactly the save "Edit" exists to make: the copy carries the shipped
    model's id ON PURPOSE, because that is what lands it as the next version of
    that model. And a guard that never expires refuses every save after the
    first, since a created model's own id is in the library by then."""
    collisions = out["id_collisions"]
    assert collisions["new_taken"] == "M-SLAT", "a new model may not seize a shipped id"
    assert collisions["new_free"] is None
    assert collisions["duplicate_free"] is None
    assert collisions["new_after_first_save"] is None, (
        "the id a save just created is in the library — asking again refuses "
        "every later save of it")
    assert collisions["published_copy"] is None, (
        "editing a published version must save under its own id, or Edit cannot "
        "produce the next version")
    assert collisions["existing_draft"] is None


# ---- the four deletions the pane was measured against ------------------------
#
# Describing ONE board took eighteen controls; the trade describes a whole panel
# with about six. Each test below pins one of the four cuts, and each is a cut
# that reads as harmless to restore.


def _rename_through_the_module(was: str, now: str) -> dict:
    """Run the real `applyRename` over a spec whose board names a rail twice."""
    import json as _json
    import subprocess as _sp

    module = (STATIC / "js" / "panel-inspector.js").as_posix()
    script = f"""
globalThis.localStorage = {{ getItem: () => null, setItem: () => {{}} }};
globalThis.document = {{ getElementById: () => null, querySelectorAll: () => [],
  querySelector: () => null, documentElement: {{}},
  createElement: () => ({{ style: {{}}, classList: {{ add(){{}}, toggle(){{}} }},
    append(){{}}, appendChild(){{}}, addEventListener(){{}}, setAttribute(){{}} }}),
  createElementNS: () => ({{ setAttribute(){{}}, appendChild(){{}} }}) }};
import {{ applyRename }} from "{module}";
const spec = {{
  frame: [{{key: "{was}", orientation: "horizontal",
           placement: {{kind: "distributed", count: 2}},
           requirement: {{role: "rail"}}}}],
  infill: {{orientation: "vertical", pattern: [
    {{key: "slat", width_mm: 100, gap_after_mm: 20,
      base_ref: "{was}", top_ref: "{was}",
      requirement: {{role: "infill", length_rule: "between_frame"}}}}]}},
  fixings: [],
}};
applyRename(spec, "frame", "{was}", "{now}");
console.log(JSON.stringify(spec));
"""
    proc = _sp.run(["node", "--input-type=module", "-e", script],
                   capture_output=True, text=True, cwd=STATIC)
    assert proc.returncode == 0, proc.stderr
    return _json.loads(proc.stdout)


def _judge_renamed(spec: dict) -> None:
    """The renamed document, through the gate that refuses a dangling ref."""
    model = FenceModel.model_validate({
        "id": "M-RENAME", "version": 1,
        "default_spec": {
            **spec,
            "frame": [{**spec["frame"][0], "requirement": {
                "role": "rail", "length_rule": "centre_to_centre",
                "eligibility": {"members": [
                    {"kind": "catalog_item", "sku": "RAIL-3000"}]}}}],
            "infill": {**spec["infill"], "pattern": [{
                **spec["infill"]["pattern"][0],
                "requirement": {"role": "infill", "length_rule": "between_frame",
                                "eligibility": {"members": [
                                    {"kind": "catalog_item", "sku": "SLAT-100"}]}}}]},
        },
    })
    assert validate_model(model, demo_catalog(), PartLibrary()) == [], (
        "a rename that orphans a ref authors a document the gate refuses")


def test_the_key_is_no_longer_a_field_and_the_rename_still_carries_its_refs():
    """Nothing in the trade names a board, so the `key` stopped being a field:
    it is generated, displayed as "Rail"/"Board 2", and renamed behind a
    double-click on the chip.

    What must NOT be lost with it is what the old `keyField` did. A board names
    the rails it starts and stops at BY KEY, so a rename that leaves those
    behind authors a document `validate_model` refuses — with English authoring
    text, for an edit that looked like a rename. And a key minted twice is
    silently the FIRST of the two everywhere that addresses an element by name.
    """
    inspector = (STATIC / "js" / "panel-inspector.js").read_text()
    editor = (STATIC / "js" / "model-editor.js").read_text()

    assert "function keyField" not in inspector, (
        "the permanent key field is the control this pane was cut down to lose")
    # RUN it, do not grep it. `applyRename` is exported and is a pure transform
    # over a plain object, and asserting that the word "reref(" appears in its
    # body stayed green with the `top_ref` half of reref deleted — which is the
    # exact defect this test is named for.
    renamed = _rename_through_the_module("rail", "top-rail")
    member = renamed["infill"]["pattern"][0]
    assert renamed["frame"][0]["key"] == "top-rail"
    assert member["base_ref"] == "top-rail", "base_ref left behind by the rename"
    assert member["top_ref"] == "top-rail", "top_ref left behind by the rename"
    # ... and the document it produces is one the publish gate takes, which is
    # the property the refs exist for
    _judge_renamed(renamed)
    # ... and uniqueness, which belongs to the module holding the whole key set
    rename = editor[editor.index("function finishRename"):]
    rename = rename[:rename.index("\n}\n")]
    assert "freeId(" in rename and "applyRename(" in rename
    assert "dblclick" in editor, "the rename has to be reachable from the chip"


def test_all_eight_spacing_pairs_stay_reachable_after_the_segmented_control():
    """`justification` x `excess` is eight combinations for one decision, and two
    segments say four of them. The other four are not a capability the editor
    gets to delete: a value the editor cannot show is a document it would
    silently rewrite.

    So the raw pair is still offered, over the WHOLE vocabulary — which is what
    makes "reachable" true rather than merely "preserved". The narrowed
    REMAINDERS list is fine; it is a subset of one segment, not the source of
    the select.
    """
    import re

    src = (STATIC / "js" / "panel-inspector.js").read_text()
    assert "export function spacingMode" in src
    assert re.search(r'"justification",\s*JUSTIFICATIONS', src), (
        "the raw justification select must offer the whole vocabulary")
    assert re.search(r'"excess",\s*EXCESS', src), (
        "the raw excess select must offer the whole vocabulary")
    # the segments themselves, so a control that quietly stopped writing one of
    # the pairs it claims is not green
    mode = src[src.index("export function spacingMode"):]
    mode = mode[:mode.index("\n}\n")]
    assert '"spread_to_fit"' in mode and '"space"' in mode and '"truncate"' in mode


def test_a_zero_is_shown_as_the_figure_the_panel_actually_produced():
    """A field reading `0` for an edge margin teaches nothing: the fit spread the
    leftover and the boards stand 37 mm off the post. The derived readout is
    what says so — and the one thing that must stay true of it is that DISPLAYING
    a derived value never AUTHORS it. `derivedNum` writes to `input.value`; only
    the change listener inside `num()` writes to the document."""
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    body = src[src.index("function derivedNum"):]
    body = body[:body.index("\n}\n")]
    assert "input.value" in body and "obj[key] =" not in body, (
        "a derived figure that writes itself into the document rewrites every "
        "model merely opened in the editor")
    # and the two the requirement names by hand
    assert "drawnMargin(" in src and "model.derived.rails" in src


def test_the_deferred_fields_are_deferred_and_not_removed():
    """Advanced is a disclosure, not a delete. Every field that left the default
    screen is still authored somewhere, and the summary counts what is set —
    a field an author cannot find is a field they have lost."""
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    for f in ("role", "length_rule", "overlap_mm", "option_axis", "sku_by_option",
              "face_offset_mm", "thickness_mm", "base_ref", "top_ref"):
        assert f in src, f
    assert "function advancedBox" in src and "function advancedCount" in src
    badge = src[src.index("function advancedBox"):]
    badge = badge[:badge.index("\n}\n")]
    assert "model.advanced_set" in badge, (
        "a disclosure holding something the author set must say so")
