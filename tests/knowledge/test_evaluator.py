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
