"""Where each quoted warning lands — `report/annexe.py`.

Contract §3.3.5. The obligation names its own failure ("a document-scoped warning
shown on every line is noise that trains a reader to ignore warnings"), so these
tests are mostly about what does NOT appear where.
"""

from __future__ import annotations

from fenceai.core.gaps import SourceRef
from fenceai.core.warnings import DocumentWarning, WarningTarget
from fenceai.fencemodel.demo import routed_vinyl_model
from fenceai.report.annexe import place_for_plan, place_warnings


def _w(kind: str, ref: str = "", text: str = "watch out", **kw) -> DocumentWarning:
    return DocumentWarning(
        text_raw=text, lang="en", severity_lexeme="CAUTION",
        attaches_to=WarningTarget(kind=kind, ref=ref), **kw)


def test_each_kind_goes_to_the_one_place_the_contract_names():
    """The whole of the §3.3.5 table, in one assertion, because the table is the
    obligation: get one row wrong and a warning is either invisible or on forty
    lines."""
    placement = place_warnings(
        [_w("step", "rails"), _w("procedure"), _w("product", "RAIL-V-3000"),
         _w("model", "M-VINYL@v1"), _w("document"), _w("warranty"),
         _w("maintenance")],
        steps=["rails"], skus=["RAIL-V-3000"], model_refs=["M-VINYL@v1"],
    )
    assert [(p.where, p.ref) for p in placement.placements] == [
        ("step", "rails"), ("procedure", ""), ("product", "RAIL-V-3000"),
        ("model", "M-VINYL@v1"), ("annexe", ""), ("annexe", ""), ("annexe", ""),
    ]


def test_a_document_warning_is_in_the_annexe_and_on_no_line():
    """Said as a negative, because the positive is not the property that matters:
    the failure is not "the annexe is empty", it is "the footnote is also on
    every bay row"."""
    placement = place_warnings([_w("document")], steps=["rails"],
                               skus=["RAIL-V-3000"])
    assert len(placement.at("annexe")) == 1
    for where in ("step", "product", "model", "procedure", "unplaceable"):
        assert placement.at(where) == [], where


def test_the_freeze_thaw_footnote_becomes_one_entry_carrying_its_count():
    """83 instances of one sentence, printed at the foot of fourteen pages. One
    annexe entry, and the count is published rather than discarded — "shown once"
    is then a decision the reader can see instead of looking like all there was.
    """
    footnote = _w("document", text="CAUTION: set footings below the frost line.")
    placement = place_warnings([footnote] * 83)
    entries = placement.at("annexe")
    assert len(entries) == 1
    assert entries[0].instances == 83
    assert placement.carried() == 83


def test_the_same_sentence_from_two_documents_stays_two_entries():
    """Identity includes the citation. Collapsing on text alone would have shown
    one entry for two manufacturers' notices and sent a reader checking the
    wrong document."""
    a = _w("document", cites=SourceRef(id="s1", belongs_to="doc-a"))
    b = _w("document", cites=SourceRef(id="s2", belongs_to="doc-b"))
    assert len(place_warnings([a, b]).at("annexe")) == 2


def test_nothing_is_ever_dropped():
    """The invariant, and the same shape as `Σ(parts) ≡ BOM` and `unplaced`:

        Σ instances + not_in_plan ≡ the warnings handed in

    A future surface that cannot draw a kind can then be caught filtering it,
    which is the whole reason the sum is checkable from the returned object."""
    warnings = [
        _w("step", "rails"), _w("step", "not-a-step"),
        _w("product", "RAIL-V-3000"), _w("product", "SOMEONE-ELSES-SKU"),
        _w("model", "M-VINYL@v1"), _w("model", "M-OTHER@v9"),
        _w("procedure", "FIXTURE-procedure-1"),
        _w("document"), _w("document"), _w("warranty"), _w("maintenance"),
    ]
    placement = place_warnings(
        warnings, steps=["rails"], skus=["RAIL-V-3000"],
        model_refs=["M-VINYL@v1"])
    assert placement.carried() == len(warnings)


def test_a_warning_about_another_job_is_counted_and_not_printed():
    """A stranger's safety notice must not appear on this plan — but a surface
    that showed three notices while silently holding four more would be worse
    than one that showed none, so the count is published."""
    placement = place_warnings(
        [_w("product", "SOMEONE-ELSES-SKU"), _w("step", "not-a-step")],
        steps=["rails"], skus=["RAIL-V-3000"])
    assert placement.placements == []
    assert placement.not_in_plan == 2


def test_a_warning_on_a_procedure_we_do_not_model_is_reported_not_filed_away():
    """§1.2 publishes `procedures` as step sequences that own no panel. This
    engine models none, so the honest answer is "yours, and we have nowhere to
    put it" — and `not_in_plan` would have said "not yours", which is how a gap
    turns into a silent filter."""
    placement = place_warnings([_w("procedure", "PROC-gate-hanging")])
    assert [p.where for p in placement.placements] == ["unplaceable"]
    assert placement.not_in_plan == 0


def test_a_procedure_warning_with_no_ref_belongs_to_its_own_document():
    """"The procedure of the document this warning came with" — the head of its
    own assembly sheet, which is a surface we have. An empty ref is the common
    case in a guide that contains exactly one procedure, and on the authored path
    it is the ONLY legitimate form: a curator cannot mint a procedure id, so
    `validate_model` refuses a named one.

    A model ref used to be read here as its own procedure's id. That branch is
    gone: a model ref is never a procedure id, so it could not have fired on real
    data, and it made an empty ref look like one case of two. A named ref this
    engine holds no procedure for is `unplaceable`, which is the honest answer
    and the one the architecture review asked for."""
    assert place_warnings([_w("procedure")]).at("procedure")
    stray = place_warnings([_w("procedure", "M-VINYL@v1")],
                           model_refs=["M-VINYL@v1"])
    assert [p.where for p in stray.placements] == ["unplaceable"]


def test_the_procedures_seam_turns_an_unplaceable_warning_into_a_placed_one():
    """The parameter exists before the feature does, and this is what it buys:
    when this engine models a published procedure, the warning stops being
    stranded and nothing else in the module changes."""
    placement = place_warnings([_w("procedure", "PROC-1")], procedures=["PROC-1"])
    assert [p.where for p in placement.placements] == ["procedure"]


def test_authored_order_survives_placement():
    """A front safety box is printed first because it is read first. Sorting the
    annexe — by severity, by text, by anything — would lose the one ordering the
    document actually asserted."""
    first = _w("document", text="FIRST: read this before you begin.")
    second = _w("document", text="Then: check the frost line.")
    entries = place_warnings([first, second]).at("annexe")
    assert [e.warning.text_raw for e in entries] == [first.text_raw, second.text_raw]


def test_placement_reads_the_vocabularies_off_the_documents():
    """`place_for_plan` exists so a surface cannot forget one. A route that
    passed skus and forgot steps would turn every step-scoped warning into
    "belongs to another job" — obligation 10's misattribution, arrived at from
    the other direction."""
    model = routed_vinyl_model()
    placement = place_for_plan([model], skus=["SLAT-V-150"])
    assert placement.carried() == len(model.warnings)
    assert placement.not_in_plan == 0
    # M-VINYL's own document: the cure note on its step, the pool notice on the
    # sku, the safety box and the warranty in the annexe
    assert [p.where for p in placement.placements] == [
        "annexe", "step", "product", "annexe"]
    assert placement.at("step", "cure")


def test_a_plan_built_to_two_documents_shares_one_annexe():
    """A run with two sections carries two product lines and a boundary post
    belongs to both. One placement over both documents, so a footnote they share
    — same sentence, same citation — is one entry and not two."""
    shared = _w("document", text="CAUTION: this assembly is not a pool barrier.",
                cites=SourceRef(id="s1", belongs_to="doc-a"))
    a = routed_vinyl_model()
    b = a.model_copy(deep=True, update={"id": "M-OTHER"})
    a.warnings = [shared]
    b.warnings = [shared]
    assert len(place_for_plan([a, b]).at("annexe")) == 1


def test_a_model_scoped_warning_needs_the_plan_to_be_built_to_that_model():
    """"A document warns about itself" is enforced at authoring; this is the read
    side of it. A model ref no bay was built to is another job's."""
    placement = place_warnings([_w("model", "M-VINYL@v1")],
                               model_refs=["M-SLAT@v2"])
    assert placement.placements == [] and placement.not_in_plan == 1


def test_a_warranty_note_and_a_maintenance_note_are_never_one_entry():
    """All three annexe kinds share one bucket, so keying the collapse on the
    bucket alone conflated them — and a reader told "the document warns" would
    have lost that one of the two was a condition on their warranty. It is the
    same sentence and it is not the same claim."""
    text = "Do not pressure-wash this assembly."
    placement = place_warnings([_w("warranty", text=text),
                                _w("maintenance", text=text)])
    assert len(placement.at("annexe")) == 2


def test_one_sentence_on_two_steps_stays_two_warnings():
    """The mutation the test review found: drop `ref` from the collapse key and
    the whole suite stayed green while the second step silently lost its warning
    — and the invariant still balanced, because the loss became an `instances`
    count. That is this module's own "carried and never rendered" failure
    arriving through the collapse instead of through the target.

    `ref` was the one component of the key with no test. `kind` has one above,
    and `identity()` has one; this is the third."""
    same = "WARNING: mind your hands."
    placement = place_warnings(
        [_w("step", "rails", text=same), _w("step", "boards", text=same)],
        steps=["rails", "boards"])
    assert [(p.ref, p.instances) for p in placement.at("step")] == [
        ("rails", 1), ("boards", 1)]

    # ...and the same for a sku, because a notice about two products is two
    # notices however identically they read
    placement = place_warnings(
        [_w("product", "RAIL-3000", text=same), _w("product", "SLAT-100", text=same)],
        skus=["RAIL-3000", "SLAT-100"])
    assert [(p.ref, p.instances) for p in placement.at("product")] == [
        ("RAIL-3000", 1), ("SLAT-100", 1)]


def test_a_step_key_is_local_to_the_document_that_named_it():
    """Both reviewers found this from opposite ends. `rails`, `cure` and `frame`
    are generic keys, so pooling the step vocabularies across a two-product-line
    plan placed manufacturer A's warning on manufacturer B's `cure` step — which
    is obligation 10's misattribution reached by a third route.

    A step ref only THIS document has is placed; one only the other document has
    belongs to another job. `validate_model` cannot catch it (it is per-document,
    correctly), so the read model has to."""
    a = routed_vinyl_model().model_copy(deep=True, update={
        "id": "M-A", "assembly": [], "warnings": [_w("step", "cure")]})
    b = routed_vinyl_model().model_copy(deep=True, update={
        "id": "M-B", "warnings": []})
    assert b.assembly and any(s.key == "cure" for s in b.assembly)

    placement = place_for_plan([a, b])
    assert placement.at("step") == []
    assert placement.not_in_plan == 1
    assert placement.carried() == 1


def test_a_placement_says_which_document_each_sentence_came_out_of():
    """`owner`, and the reason it is not cosmetic: without it two documents'
    warnings on the same generic step key are indistinguishable downstream, so a
    surface drawing step warnings has no way to draw them under the right
    document."""
    a = routed_vinyl_model().model_copy(deep=True, update={
        "id": "M-A", "warnings": [_w("step", "cure", text="A says wait")]})
    b = routed_vinyl_model().model_copy(deep=True, update={
        "id": "M-B", "warnings": [_w("step", "cure", text="B says wait")]})
    owners = {(p.owner, p.warning.text_raw) for p in place_for_plan([a, b]).at("step")}
    assert owners == {("M-A@v1", "A says wait"), ("M-B@v1", "B says wait")}

    # ...and the annexe still ignores the owner, so one footnote two product
    # lines quote from one source doc is ONE entry
    shared = _w("document", text="CAUTION: not a pool barrier.",
                cites=SourceRef(id="s1", belongs_to="doc-a"))
    c = a.model_copy(deep=True, update={"id": "M-C", "warnings": [shared]})
    d = b.model_copy(deep=True, update={"id": "M-D", "warnings": [shared]})
    entries = place_for_plan([c, d]).at("annexe")
    assert len(entries) == 1 and entries[0].instances == 2


def test_place_for_plan_forgets_no_vocabulary_including_the_ones_it_has_no_test_for():
    """`model_refs=[]` survived the whole suite, because the fixture that pins
    "you cannot forget a vocabulary" only exercised the vocabularies M-VINYL
    happens to use. Under that mutant a model-scoped warning became
    `not_in_plan` — "belongs to another job" — in the function whose docstring
    exists to prevent exactly that."""
    model = routed_vinyl_model()
    model = model.model_copy(deep=True, update={"warnings": [
        *model.warnings,
        _w("model", model.ref, text="This line is discontinued."),
        _w("procedure", text="Read the whole guide before you start."),
    ]})
    placement = place_for_plan(model.warnings and [model], skus=["SLAT-V-150"])
    assert placement.not_in_plan == 0
    assert placement.carried() == len(model.warnings)
    assert [p.ref for p in placement.at("model")] == [model.ref]
    assert placement.at("procedure")


def test_a_carried_but_defective_warning_is_still_placed_in_the_annexe():
    """`ingest` deliberately CARRIES a warning that contradicts its own schema —
    a document-scoped one that names a line — and reports the defect rather than
    dropping it. So this input is reachable in production, and the mutant that
    let an annexe entry keep that `ref` survived everything.

    An annexe entry has no ref by definition. The defective twin must land beside
    its clean one and collapse with it, not open a second entry keyed on a line
    the annexe does not have."""
    clean = _w("document", text="CAUTION: mind the frost line.")
    defective = clean.model_copy(deep=True)
    defective.attaches_to.ref = "SOME-LINE"

    entries = place_warnings([clean, defective]).at("annexe")
    assert len(entries) == 1
    assert entries[0].ref == "" and entries[0].instances == 2
