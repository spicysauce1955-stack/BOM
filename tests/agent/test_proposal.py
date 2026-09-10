# tests/agent/test_proposal.py
"""The rationale types. Spec §5.1.

A marker without its evidence is the failure `conversation.md` ground rule 2
exists to prevent: one side asserted from memory that a table read `NON HVHZ`
and it did not, and the only difference a reader could see when it was later
true was that the second claim arrived with a query attached.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.agent.proposal import Claim


def test_a_measured_claim_carries_the_query_that_produced_it():
    claim = Claim(marker="measured", text="window spans 2200-2900 mm",
                  evidence="landmark:lm_7.extent_mm")
    assert claim.evidence == "landmark:lm_7.extent_mm"


def test_a_measured_claim_without_evidence_is_refused():
    with pytest.raises(ValidationError, match="must carry its evidence"):
        Claim(marker="measured", text="window spans 2200-2900 mm")


def test_a_read_claim_without_evidence_is_refused():
    with pytest.raises(ValidationError, match="must carry its evidence"):
        Claim(marker="read", text="600 mm clear of a window")


def test_an_inferred_claim_carries_none_and_says_so():
    claim = Claim(marker="inferred", text="a centred bay looks better")
    assert claim.evidence is None


def test_an_inferred_claim_carrying_evidence_is_refused():
    """Forbidden rather than optional. A citation on a reasoning claim reads as
    observed, and nothing downstream can tell that it supports the reasoning
    rather than the fact."""
    with pytest.raises(ValidationError, match="carries no evidence"):
        Claim(marker="inferred", text="looks better", evidence="landmark:lm_7")


def test_empty_string_evidence_is_not_evidence():
    with pytest.raises(ValidationError, match="must carry its evidence"):
        Claim(marker="measured", text="window at 2200", evidence="")


from fenceai.agent.proposal import (
    Declined, NoStanding, Proposal, TaskResult, ViewDigest, proposal_id,
)


def test_the_same_proposal_gets_the_same_id_every_run():
    """Random ids break the rejection record: "a rejection suppresses
    re-proposal" needs the system to recognise a re-proposal as the SAME
    proposal. `conversation.md` T46 §8 is the measured cost of getting identity
    wrong — 0 of 67 gap ids survived a cut and a consumer saw total churn."""
    a = proposal_id("rank_choice_set", "select_choice_point",
                    {"choice_set": "bay_layout", "scope": "gap:run1:0", "point_id": "p2"},
                    "gap:run1:0")
    b = proposal_id("rank_choice_set", "select_choice_point",
                    {"scope": "gap:run1:0", "point_id": "p2", "choice_set": "bay_layout"},
                    "gap:run1:0")
    assert a == b, "key order must not change the id"
    assert a.startswith("prop_")


def test_a_different_answer_is_a_different_proposal():
    a = proposal_id("rank_choice_set", "select_choice_point", {"point_id": "p2"}, "s")
    b = proposal_id("rank_choice_set", "select_choice_point", {"point_id": "p3"}, "s")
    assert a != b


def test_a_proposal_is_always_an_ai_proposal():
    """`ai_proposal` is a SourceClass in the integration contract's closed
    registry, and §1.4's BINDING block makes it proposal-only on every task. We
    do not invent provenance for agent output."""
    p = Proposal(id="prop_x", task_id="t", project_id="pr",
                 kind="select_choice_point", payload={}, scope="s")
    assert p.source_class == "ai_proposal"
    assert p.status == "proposed"


def test_a_task_that_looked_and_found_nothing_is_not_a_task_that_did_not_look():
    """Vacuous green. This repo shipped the other bug once — audit B01, a cached
    null painting a clean bill of health — and the eight-step road makes it a
    rule: unknown is never folded into done."""
    looked = TaskResult(task_id="t", evaluated=True)
    did_not = TaskResult(task_id="t", evaluated=False)
    assert looked.proposals == did_not.proposals == []
    assert looked.evaluated is not did_not.evaluated


def test_a_declined_action_carries_the_claims_that_ruled_it_out():
    d = Declined(kind="select_choice_point",
                 claims=[Claim(marker="inferred", text="costs one more post")])
    assert d.claims[0].marker == "inferred"


def test_no_standing_is_not_the_same_as_needing_information():
    """T54 §2: the Knowledge team left DECLARED_ASSOCIATIONS deliberately empty
    rather than assert a product identity they do not hold. `needs` means "I
    lack information"; `no_standing` means "I have the answer and it is not
    mine to state"."""
    r = TaskResult(
        task_id="t", evaluated=True,
        needs=["the window position is not recorded"],
        no_standing=[NoStanding(about="this fence is a CertainTeed Chesterfield",
                                whose="whoever sets the job up",
                                claims=[Claim(marker="inferred", text="the slat pitch matches")])],
    )
    assert r.needs and r.no_standing
    assert r.no_standing[0].whose


def test_a_view_digest_records_identity_not_payload():
    d = ViewDigest(slices=["choice_sets"], run_id="run_1",
                   topology_revision=4, knowledge_hash="abc123")
    assert d.topology_revision == 4
