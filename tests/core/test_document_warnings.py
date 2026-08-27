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


def test_an_annexe_scoped_warning_may_not_name_a_line():
    """The failure obligation 10 exists to prevent, arrived at from the other
    side. A document-scoped warning that names a line is claiming a scope it has
    not got, and the reader who gets a freeze-thaw footnote on all forty bays is
    the reader who learns to skip warnings."""
    for kind in sorted(ANNEXE_SCOPES):
        errors = warning_errors(
            [_w(attaches_to=WarningTarget(kind=kind, ref="rails"))], where="w")
        assert len(errors) == 1, kind
        assert "renders once in the annexe" in errors[0]


def test_a_line_scoped_warning_must_name_the_line():
    """The same rule from the other end: without a ref there is no step, sku or
    model to put it on, so it would be carried and rendered nowhere. `procedure`
    is the one exception and has its own meaning for an empty ref — the procedure
    of the document it came with."""
    for kind in ("step", "product", "model"):
        errors = warning_errors(
            [_w(attaches_to=WarningTarget(kind=kind))], where="w")
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


def test_every_error_names_where_it_came_from():
    """One shared checker serves a curated model and a published snapshot, so the
    string has to say which document the reader should open."""
    errors = warning_errors([_w(text_raw="")], where="published")
    assert errors and errors[0].startswith("published warning 0:")
