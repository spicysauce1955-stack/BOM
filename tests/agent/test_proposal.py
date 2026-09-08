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
