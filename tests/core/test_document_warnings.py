"""The quoted-warning type, and the four ways it refuses to be improved.

`core/warnings.py`. Contract obligation 10: "every warning declares what it
attaches to, and its text is primary". These tests are about the second half —
the type is deliberately unable to normalise, translate or summarise what it
carries, and each assertion below is one thing it must not do.
"""

from __future__ import annotations

from fenceai.core.gaps import SourceRef
from fenceai.core.warnings import (
    ANNEXE_SCOPES, DocumentWarning, WarningTarget, warning_errors,
)
from fenceai.report.annexe import place_warnings


def _w(**kw) -> DocumentWarning:
    base = dict(text_raw="CAUTION: set footings below the frost line.",
                lang="en", severity_lexeme="CAUTION",
                attaches_to=WarningTarget(kind="document"))
    return DocumentWarning(**{**base, **kw})


def test_the_publishers_severity_word_survives_unchanged():
    """`CAUTION` and `WARNING` are terms of art with different legal weight in
    North American product literature. The type holds the word, not a mapping
    onto our info/warning/error — a normalisation here would be this engine
    editing a liability notice, and it would be invisible afterwards."""
    assert _w(severity_lexeme="CAUTION").severity_lexeme == "CAUTION"
    assert _w(severity_lexeme="WARNING").severity_lexeme == "WARNING"
    assert _w(severity_lexeme="AVERTISSEMENT").severity_lexeme == "AVERTISSEMENT"
    # ...and it is NOT one of our severities, which is why it has its own field
    assert not hasattr(_w(), "severity")


def test_a_warning_with_no_citation_is_legal_and_says_so():
    """The departure from this repo's own spec, asserted so it stays deliberate.

    `docs/superpowers/specs/2026-08-23-bom-engine-design.md` declared `cites`
    REQUIRED. It cannot be on this side: §1.1 makes `SourceRef.id` opaque and
    forbids building one, so a curator authoring a warning in the model editor
    has no way to mint a citation and the Discovery surface that would hand them
    a real one is unimplemented. Requiring the field would be enforced by
    fabricating ids."""
    assert _w().cites == []
    assert warning_errors([_w()], where="model M-X") == []


def test_a_code_is_carried_and_never_promoted_over_the_text():
    """`code` + `params` are the publisher's optional overlay — 142 of the 226
    distinct warnings in the corpus appear exactly once. The text is what
    renders; the code is for grouping."""
    w = _w(code="not_pool_rated", params={"standard": "IRC AG105.2"})
    assert w.code == "not_pool_rated" and w.text_raw
    # the overlay is not required to be in our closed registry, and nothing here
    # looks it up: this type holds no localization machinery at all
    assert not hasattr(w, "message")


def test_params_without_a_code_is_refused():
    """A params bag interpolates into a code's sentence. A quoted warning's text
    is never interpolated — it is quoted — so params alone are values with
    nowhere to go, which is a mistake worth catching while somebody can fix it."""
    errors = warning_errors([_w(params={"n": 3})], where="model M-X")
    assert len(errors) == 1 and "params with no code" in errors[0]


def test_text_and_lang_are_both_required_in_substance_not_only_in_shape():
    """Pydantic makes them present. These make them mean something: a warning
    that IS its text cannot have blank text, and `lang` is what sets the
    direction the quoted sentence runs in on an RTL page."""
    assert warning_errors([_w(text_raw="   ")], where="w")
    assert warning_errors([_w(lang=" ")], where="w")


def test_an_annexe_scoped_warning_naming_its_own_document_is_not_a_defect():
    """The regression for the rule that flagged 276 of the first real snapshot's
    289 warnings.

    This checker used to refuse ANY annexe-scoped warning carrying a ref, on the
    reasoning that a document-scoped sentence "belongs to the whole job" so a ref
    could only be it naming a line. The first real published snapshot
    (`3ae88642…`) is 274 `document`-scoped and 2 `warranty`-scoped warnings that
    all carry one, and in every one of the 276 the ref is that document's own
    `content_hash` — all 276 resolve to an entry in the snapshot's `source_docs`.
    It is what lets the annexe group 274 quoted sentences by the guide they came
    from, which is half of what a reader needs to go and check one.

    The old rule survived only because the sole data it had ever met was a
    fixture this side authored with empty refs — the failure mode
    `plan/current-status.md` already names: a rule that passes only against data
    its implementer authored is not a rule anyone has tested."""
    for kind in sorted(ANNEXE_SCOPES):
        w = _w(attaches_to=WarningTarget(kind=kind, ref="hash-of-the-guide"))
        assert warning_errors([w], where="published",
                              known_docs={"hash-of-the-guide"}) == [], kind


def test_an_annexe_scoped_ref_that_names_no_document_in_hand_is_reported():
    """What is left of the scope rule once it is narrowed to something checkable.

    An annexe-scoped ref names the DOCUMENT the sentence was quoted from. A ref
    that resolves to none of the documents that came with it is the same class of
    defect `validate_model` already refuses one function over — a step warning
    naming a step this model has not got — and it is a defect for the same
    reason: the annexe would carry the sentence and be unable to say who said
    it."""
    for kind in sorted(ANNEXE_SCOPES):
        errors = warning_errors(
            [_w(attaches_to=WarningTarget(kind=kind, ref="rails"))],
            where="published", known_docs={"hash-of-the-guide"})
        assert len(errors) == 1, kind
        assert "not one of the documents that came with it" in errors[0]


def test_an_annexe_scoped_ref_is_not_judged_by_a_caller_who_cannot_resolve_it():
    """Silence is the honest answer for a caller holding no document list.

    A curator authoring a warning in the model editor has no `source_docs` to
    check against, and a caller with no way to resolve a ref has no standing to
    call it dangling. The old rule's mistake was giving a verdict anyway — with
    no documents in hand it read every ref as "naming a line". So with no
    `known_docs` the ref is not judged at all, and the other checks still run."""
    w = _w(attaches_to=WarningTarget(kind="document", ref="hash-of-the-guide"))
    assert warning_errors([w], where="model M-X") == []
    # ...not judged is not "not checked": the rest of the type's rules still hold
    assert warning_errors([_w(attaches_to=WarningTarget(
        kind="document", ref="hash-of-the-guide"), params={"n": 3})],
        where="model M-X")
    # ...and "I cannot resolve refs" is not "there are no documents". A sender
    # that ships annexe warnings with an empty `source_docs` has refs that really
    # do dangle, and the empty set says so — the absent/blank distinction this
    # module already keeps for `severity_lexeme`.
    assert len(warning_errors([w], where="published", known_docs=set())) == 1


def test_a_line_scoped_warning_must_name_the_line():
    """The same rule from the other end: without a ref there is no step, sku or
    model to put it on, so it would be carried and rendered nowhere. `procedure`
    is the one exception and has its own meaning for an empty ref — the procedure
    of the document it came with.

    Unchanged by the narrowing of the annexe-ref rule, and asserted both with and
    without `known_docs` because a document list says nothing about a step key: a
    fix that made the missing-ref check conditional on it too would have traded
    one over-broad rule for one that goes quiet."""
    for kind in ("step", "product", "model"):
        errors = warning_errors(
            [_w(attaches_to=WarningTarget(kind=kind))], where="w")
        assert len(warning_errors(
            [_w(attaches_to=WarningTarget(kind=kind))], where="w",
            known_docs={"hash-of-the-guide"})) == 1, kind
        assert len(errors) == 1, kind
        assert "names none" in errors[0]
    assert warning_errors(
        [_w(attaches_to=WarningTarget(kind="procedure"))], where="w") == []


def test_two_documents_saying_the_same_sentence_are_two_warnings():
    """Identity is the whole quoted payload including the citation, so the annexe
    collapses 83 printings of ONE document's footnote and keeps two documents'
    identical sentences apart. Which document said it is half of what a reader
    needs in order to go and check it."""
    a = _w(cites=[SourceRef(id="s1", belongs_to="hash-a")])
    b = _w(cites=[SourceRef(id="s2", belongs_to="hash-b")])
    assert a.identity() != b.identity()
    assert a.identity() == _w(cites=[SourceRef(id="s1", belongs_to="hash-a")]).identity()


def test_a_warning_can_cite_more_than_one_source():
    """`cites` is a LIST because a sentence printed on fourteen pages of two
    documents genuinely cites several — 76 of 282 of the Knowledge team's
    published warnings do. A warning with two citations must carry both, not
    silently keep the first."""
    w = _w(cites=[SourceRef(id="s1", belongs_to="hash-a"),
                  SourceRef(id="s2", belongs_to="hash-b")])
    assert [c.belongs_to for c in w.cites] == ["hash-a", "hash-b"]
    # ...and identity folds the WHOLE list in, so a warning citing {s1, s2} is not
    # the same warning as one citing {s1} alone
    assert w.identity() != _w(cites=[SourceRef(id="s1", belongs_to="hash-a")]).identity()


def test_identity_separates_the_publishers_own_severity_word():
    """"CAUTION: keep clear" and "DANGER: keep clear" are not one warning printed
    twice. Collapsing on text alone would have shown one of them and silently
    dropped the more serious."""
    assert _w(severity_lexeme="CAUTION").identity() \
        != _w(severity_lexeme="DANGER").identity()


def test_a_document_ref_changes_where_the_warning_is_checked_not_where_it_renders():
    """§3.3.5, held steady across the narrowing. The rule that made annexe refs
    illegal was also, accidentally, the reason no annexe-scoped warning ever
    reached `place_warnings` carrying one. Legalising the ref puts a shape
    through that function it had never been given, so the contract's own sentence
    — "for `document`, `warranty` and `maintenance`, once in the plan's annexe
    and never on a line" — is asserted against exactly that shape.

    The ref is what the sentence was quoted FROM, never what it renders on: the
    step key `rails` here is a real step of the plan, and a document-scoped
    warning naming it must still land in the annexe and nowhere near it."""
    warnings = [_w(attaches_to=WarningTarget(kind=kind, ref="rails"))
                for kind in sorted(ANNEXE_SCOPES)]
    placement = place_warnings(warnings, steps=["rails"], skus=["P-1"])

    assert {p.where for p in placement.placements} == {"annexe"}
    assert all(p.ref == "" for p in placement.placements)
    assert placement.not_in_plan == 0
    # three kinds, three entries, each once — the annexe keeps them apart (a
    # warranty condition and a maintenance note that read alike are two facts)
    assert len(placement.placements) == 3
    assert [p.instances for p in placement.placements] == [1, 1, 1]


def test_one_footnote_quoted_off_one_document_collapses_however_often_it_is_sent():
    """The freeze-thaw footnote is printed at the foot of fourteen pages and
    resolves to 83 instances of one sentence; the annexe holds it once. Now that
    the ref is carried, it must not become an 84th thing that distinguishes two
    printings of the same sentence — `_place_into` drops it for annexe kinds
    precisely so this collapse survives."""
    w = _w(attaches_to=WarningTarget(kind="document", ref="hash-of-the-guide"))
    placement = place_warnings([w] * 83, steps=["rails"])
    assert len(placement.placements) == 1
    assert placement.placements[0].instances == 83
    assert placement.carried() == 83


def test_every_error_names_where_it_came_from():
    """One shared checker serves a curated model and a published snapshot, so the
    string has to say which document the reader should open."""
    errors = warning_errors([_w(text_raw="")], where="published")
    assert errors and errors[0].startswith("published warning 0:")
