"""The `Gap` type against the contract's own shape (§1.1, §1.2.1).

These test the RECEIVE side, which the generator never exercises. A run-produced
gap cites nothing and is never `disputed`, so every field the Knowledge Platform
fills and this engine only reads was, until this file, asserted by nothing — and
the first review of the slice found two of them wrong for exactly that reason.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.core.gaps import Because, Gap, GapSubject, SourceRef


def _gap(**kw):
    base = dict(id="g1", kind="uncovered_condition",
                subject=GapSubject(kind="param", id="footing_depth_mm"),
                because=Because(code="c"),
                would_close="a footing row for exposure C at 6 ft")
    return Gap(**{**base, **kw})


def test_source_ref_is_the_contracts_shape():
    """§1.1: `SourceRef { id, belongs_to }`, and the BINDING clause says
    `belongs_to` is the ONE field this side may read — without it an opaque id
    carries zero admissibility bits into a pinned snapshot."""
    ref = SourceRef(id="opaque-123", belongs_to="sha256:abc")
    assert (ref.id, ref.belongs_to) == ("opaque-123", "sha256:abc")


def test_a_published_gap_parses_from_the_wire():
    """The direction the generator never exercises, and therefore the one that
    will first be handed real data."""
    gap = Gap.model_validate({
        "id": "kp-gap-9", "kind": "unquantified",
        "subject": {"kind": "entity", "id": "part:rail-16ft", "tenant": "acme"},
        "because": {"code": "stated_in_prose", "params": {"doc": "BUF-2019"}},
        "cites": [{"id": "src-4", "belongs_to": "sha256:def"}],
        "would_close": "a number for the rail's maximum unsupported span",
        "closes_by": "knowledge", "severity": "warns_line",
    })
    assert gap.cites[0].belongs_to == "sha256:def"
    assert (gap.subject.id, gap.subject.tenant) == ("part:rail-16ft", "acme")
    assert (gap.because.code, gap.because.params) == (
        "stated_in_prose", {"doc": "BUF-2019"})


@pytest.mark.parametrize("kind", ["unmodellable_entity", "unmapped_part_kind"])
def test_a_schema_change_gap_cannot_claim_a_curator_closes_it(kind):
    """BINDING (§1.2.1): these two close by a schema change in the Planning repo.
    A queue showing a curator work only an engineer can do is a queue whose items
    are not actionable — the one property it has to have."""
    with pytest.raises(ValidationError):
        _gap(kind=kind, closes_by="knowledge")
    assert _gap(kind=kind, closes_by="planning").closes_by == "planning"


def test_the_invariant_survives_a_round_trip():
    """A stored run is re-read with `model_validate_json`. An invariant that only
    fired in `__init__` would let a bad gap in through the database."""
    good = _gap(kind="unmodellable_entity", closes_by="planning")
    assert Gap.model_validate_json(good.model_dump_json()).closes_by == "planning"

    tampered = good.model_dump_json().replace('"planning"', '"knowledge"')
    with pytest.raises(ValidationError):
        Gap.model_validate_json(tampered)


def test_disputed_must_say_what_is_disputed():
    """`disputed{ on: value | conditions }`. 33.3% of the platform's human-gated
    facts carry a note that readers disagreed on the applicability BRACKET — the
    value certain, the conditions not. A bare "disputed" discards that half."""
    with pytest.raises(ValidationError):
        _gap(kind="disputed")
    assert _gap(kind="disputed", on="conditions").on == "conditions"


def test_on_is_rejected_on_the_other_seven_kinds():
    with pytest.raises(ValidationError):
        _gap(kind="missing_value", on="value")


def test_would_close_is_required():
    """BINDING: a gap that only says something is missing sends a curator hunting."""
    with pytest.raises(ValidationError):
        Gap(id="g", kind="missing_value",
            subject=GapSubject(kind="param", id="x"), because=Because(code="c"))


def test_because_is_required_and_so_is_its_own_code():
    """`because` is a `Gap`'s ONLY rendering mechanism — there is no `text_raw` the
    way a `DocumentWarning` has, and no `message` fallback the way a
    `StrategyWarning` has. Every other test in this module builds `because`
    explicitly, but none pins that it cannot be skipped or given a default —
    a future "helpful" `Because(code="") ` default would sail through the whole
    suite silently."""
    with pytest.raises(ValidationError):
        Gap(id="g", kind="missing_value", subject=GapSubject(kind="param", id="x"),
            would_close="a value for x")
    with pytest.raises(ValidationError):
        Because()


# -- the `origin` seam ---------------------------------------------------------

def test_from_published_stamps_the_origin():
    """The seam that keeps the snapshot loader from forgetting.

    `origin` defaults to `authored` — the safe direction — so a loader that
    builds rows through the plain constructor produces a base that looks
    home-grown, and two published rows that tie then RAISE. That is the defect
    the field exists to close, reinstated with nothing failing, because
    `demo_knowledge()` holds no published rows to notice.
    """
    from fenceai.knowledge.model import KnowledgeVersion

    v = KnowledgeVersion.from_published(object_id="P-1", version=1, type="fact")
    assert v.origin == "published"

    with pytest.raises(ValueError):
        KnowledgeVersion.from_published(object_id="P-1", version=1, type="fact",
                                        origin="authored")
