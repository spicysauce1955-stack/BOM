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
    case in a guide that contains exactly one procedure."""
    assert place_warnings([_w("procedure")]).at("procedure")
    assert place_warnings(
        [_w("procedure", "M-VINYL@v1")], model_refs=["M-VINYL@v1"]).at("procedure")


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
