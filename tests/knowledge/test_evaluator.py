"""Evaluator precedence & conflict-surfacing tests (test-review finding 2)."""

from __future__ import annotations

from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.evaluator import applicable_firings, resolve_param
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion, SetParam


def kv(obj_id: str, *, type_: str = "preference", version: int = 1, scope=None,
       value: int = 1000, condition=None, overrides=None, status: str = "active") -> KnowledgeVersion:
    return KnowledgeVersion(
        object_id=obj_id, version=version, type=type_, scope=scope or {},
        condition=condition, actions=[SetParam(param="max_span_mm", value=value)],
        overrides_objects=overrides or [], status=status,
    )


CTX = {"scope": {}, "run": {"length_mm": 5000, "slope_pct": 0}}


def test_authority_tier_wins_silently_but_recorded():
    kb = KnowledgeBase(versions=[
        kv("HARD", type_="hard_constraint", value=1800),
        kv("PREF", type_="preference", value=2400),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert res.winner.version.object_id == "HARD"
    assert res.conflicts == []  # strict structural win: silent but...
    loser = next(f for f in res.firings if f.version.object_id == "PREF")
    assert loser.defeated_by == ["HARD@v1"]  # ...recorded


def test_scope_specificity_wins_within_tier():
    kb = KnowledgeBase(versions=[
        kv("GLOBAL", type_="company_rule", value=1800),
        kv("PROJ", type_="company_rule", value=1600, scope={"project_id": "p1"}),
    ])
    ctx = {**CTX, "scope": {"project_id": "p1"}}
    res = resolve_param(kb, ctx, "max_span_mm")
    assert res.winner.version.object_id == "PROJ"
    assert res.conflicts == []


def test_explicit_overrides_link_beats_peer():
    kb = KnowledgeBase(versions=[
        kv("A", type_="company_rule", value=1800),
        kv("B", type_="company_rule", value=1500, overrides=["A"]),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert res.winner.version.object_id == "B"
    loser = next(f for f in res.firings if f.version.object_id == "A")
    assert "B@v1" in loser.defeated_by
    assert res.conflicts == []


def test_same_tier_preference_conflict_is_surfaced_not_fatal():
    kb = KnowledgeBase(versions=[
        kv("R1", type_="preference", value=1800),
        kv("R2", type_="preference", value=1500),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert len(res.conflicts) == 1
    assert set(res.conflicts[0].contenders) == {"R1@v1", "R2@v1"}
    assert res.winner is not None  # generation continues with the flagged pick


def test_hard_tier_tie_with_disagreement_is_generation_failure():
    import pytest

    from fenceai.core.errors import GenerationFailure

    kb = KnowledgeBase(versions=[
        kv("R1", type_="company_rule", value=1800),
        kv("R2", type_="company_rule", value=1500),
    ])
    with pytest.raises(GenerationFailure):
        resolve_param(kb, CTX, "max_span_mm")


def test_agreeing_values_are_not_a_conflict():
    kb = KnowledgeBase(versions=[
        kv("R1", type_="company_rule", value=1800),
        kv("R2", type_="company_rule", value=1800),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert res.conflicts == []  # DMN ANY semantics


def test_agreeing_values_are_corroboration_not_defeat():
    kb = KnowledgeBase(versions=[
        kv("R1", type_="company_rule", value=1800),
        kv("R2", type_="company_rule", value=1800),
        kv("R3", type_="company_rule", value=1800),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert res.conflicts == []
    for loser in (f for f in res.firings if f is not res.winner):
        assert loser.defeated_by == []  # nothing here was beaten
        assert loser.corroborated_by == [res.winner.version.ref]


def test_newer_version_wins_same_object():
    kb = KnowledgeBase(versions=[
        kv("R", version=1, value=1800, status="retired"),
        kv("R", version=2, value=1600),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert res.winner.version.version == 2


def test_candidates_never_fire():
    kb = KnowledgeBase(versions=[
        kv("CAND", type_="candidate", value=99, status="active"),
        kv("HARD", type_="hard_constraint", value=1800),
    ])
    firings = applicable_firings(kb, CTX)
    assert [f.version.object_id for f in firings] == ["HARD"]


def test_proposed_status_never_fires():
    kb = KnowledgeBase(versions=[
        kv("P", type_="company_rule", value=99, status="proposed"),
    ])
    assert applicable_firings(kb, CTX) == []


def test_missing_context_field_means_not_applicable():
    cond = Cmp(cmp=">", left=FieldRef(path="run.frost_depth_mm"), right=Lit(value=500))
    kb = KnowledgeBase(versions=[kv("R", condition=cond)])
    assert applicable_firings(kb, CTX) == []


def test_condition_false_means_not_applicable():
    cond = Cmp(cmp=">", left=FieldRef(path="run.slope_pct"), right=Lit(value=15))
    kb = KnowledgeBase(versions=[kv("R", condition=cond)])
    assert applicable_firings(kb, CTX) == []
    ctx_steep = {**CTX, "run": {"length_mm": 5000, "slope_pct": 20}}
    assert len(applicable_firings(kb, ctx_steep)) == 1


def test_scope_mismatch_means_not_applicable():
    kb = KnowledgeBase(versions=[kv("R", scope={"project_id": "other"})])
    assert applicable_firings(kb, {**CTX, "scope": {"project_id": "p1"}}) == []


def published(obj_id: str, *values: int, param: str = "max_span_mm") -> KnowledgeVersion:
    """A `hard_constraint` row from a Knowledge Platform snapshot.

    Published rather than authored because these tests are about a tie that
    SURVIVES: two authored rules tying with disagreeing outputs raise
    (`test_hard_tier_tie_with_disagreement_is_generation_failure`), and the whole
    point here is what the graph and the review tasks say afterwards.
    """
    return KnowledgeVersion.from_published(
        object_id=obj_id, version=1, type="hard_constraint",
        actions=[SetParam(param=param, value=v) for v in values])


def test_one_dissenter_does_not_defeat_the_rows_that_agree():
    """Agreement is PAIRWISE. It used to be one boolean over the whole set.

    `resolve_param` computed `len({a.effective_milli() ...}) <= 1` across every
    relevant firing and handed it to `resolve`, which then applied that one
    answer to every pair. Add a single dissenting row to four that state the same
    limit and all four became losers: four `defeated_by` edges and four
    `hard=True` conflicts — conflicts BETWEEN ROWS THAT STATE THE SAME NUMBER,
    shipped to the publisher as review tasks saying two of their byte-identical
    rows contradict each other.

    One row dissented. Exactly one contest happened.
    """
    kb = KnowledgeBase(versions=[
        published("A", 1800), published("B", 1800), published("C", 1800),
        published("D", 1800), published("E", 1500),
    ])
    res = resolve_param(kb, CTX, "max_span_mm")
    by_id = {f.version.object_id: f for f in res.firings}
    winner = res.winner.version.object_id
    agreeing = [o for o in "ABCD" if o != winner]

    assert [by_id[o].corroborated_by for o in agreeing] == [[f"{winner}@v1"]] * 3
    assert all(by_id[o].defeated_by == [] for o in agreeing)
    assert by_id["E"].defeated_by == [f"{winner}@v1"]  # the only row that lost
    assert by_id["E"].corroborated_by == []

    assert [c.contenders for c in res.conflicts] == [[f"{winner}@v1", "E@v1"]]
    assert [c.hard for c in res.conflicts] == [True]


def test_a_row_stating_two_numbers_does_not_corroborate_one_stating_one():
    """What "the value of a firing" means when it carries several actions for
    one slot: everything it states, in its own order, compared whole.

    The set-based predicate pooled every action of every firing, so a single row
    stating both 1800 and 1500 was indistinguishable from two rows stating one
    each. It is not the same thing, and the difference is load-bearing: the
    consumer reads the FIRST matching action, so a row stating `(1800, 1500)`
    and a row stating `(1500, 1800)` build different fences.

    Corroboration is the claim that a second source independently said the SAME
    thing. A source that also said something else did not, so it falls through
    to the conflict branch — the conservative direction, and a review task about
    a row that genuinely needs one.
    """
    kb = KnowledgeBase(versions=[published("A", 1800), published("B", 1800, 1500)])
    res = resolve_param(kb, CTX, "max_span_mm")
    loser = next(f for f in res.firings if f is not res.winner)
    assert loser.corroborated_by == []
    assert loser.defeated_by == [res.winner.version.ref]
    assert [c.hard for c in res.conflicts] == [True]

    # ...and order is part of the statement, for the same reason.
    kb = KnowledgeBase(versions=[published("A", 1800, 1500),
                                 published("B", 1500, 1800)])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert next(f for f in res.firings if f is not res.winner).corroborated_by == []

    # two rows that state the same pair, in the same order, DID say the same thing
    kb = KnowledgeBase(versions=[published("A", 1800, 1500),
                                 published("B", 1800, 1500)])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert next(f for f in res.firings if f is not res.winner).corroborated_by == [
        res.winner.version.ref]
    assert res.conflicts == []


def test_pairwise_agreement_holds_for_tokens_too():
    """`resolve_token` had the same set-level flag and the same defect."""
    from fenceai.knowledge.evaluator import resolve_token
    from fenceai.knowledge.model import SetToken

    def tok(obj_id: str, value: str) -> KnowledgeVersion:
        return KnowledgeVersion.from_published(
            object_id=obj_id, version=1, type="hard_constraint",
            actions=[SetToken(param="slope_method", value=value)])

    kb = KnowledgeBase(versions=[tok("A", "stepped_only"), tok("B", "stepped_only"),
                                 tok("C", "raked")])
    res = resolve_token(kb, CTX, "slope_method")
    by_id = {f.version.object_id: f for f in res.firings}
    other = next(o for o in "AB" if o != res.winner.version.object_id)
    assert by_id[other].corroborated_by == [res.winner.version.ref]
    assert by_id["C"].defeated_by == [res.winner.version.ref]
    assert len(res.conflicts) == 1


def test_a_row_that_agrees_below_the_millimetre_still_corroborates():
    """The pairwise fix does not loosen `38a2c6b`: agreement is still measured at
    `effective_milli()`, so two rows that round to the same millimetre from
    DIFFERENT thousandths are still a conflict, not corroboration."""
    from fenceai.knowledge.model import SetParam as SP

    def milli(obj_id: str, value: int, value_milli: int) -> KnowledgeVersion:
        return KnowledgeVersion.from_published(
            object_id=obj_id, version=1, type="hard_constraint",
            actions=[SP(param="max_span_mm", value=value, value_milli=value_milli)])

    kb = KnowledgeBase(versions=[milli("A", 2464, 2463800), milli("B", 2464, 2464200)])
    res = resolve_param(kb, CTX, "max_span_mm")
    loser = next(f for f in res.firings if f is not res.winner)
    assert loser.corroborated_by == []
    assert [c.hard for c in res.conflicts] == [True]

    kb = KnowledgeBase(versions=[milli("A", 2464, 2463800), milli("B", 2464, 2463800)])
    res = resolve_param(kb, CTX, "max_span_mm")
    assert next(f for f in res.firings
                if f is not res.winner).corroborated_by == [res.winner.version.ref]
    assert res.conflicts == []
