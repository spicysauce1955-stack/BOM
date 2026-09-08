"""What an agent task produces, and how it must justify it.

A rationale is never prose. Every claim carries HOW it is known — the
convention `docs/integration-contract/conversation.md` ground rule 2 adopted
after one side asserted from memory that a table read `NON HVHZ` and it did
not: "the only difference a reader can see is that the second one arrives with
a query attached. Make that difference visible by construction rather than by
trust."

It pays for itself twice. A `measured` claim can be re-checked before a person
sees the proposal (`run.py`); an `inferred` one cannot, so it renders as
reasoning. The agent can neither advise on a number it invented nor pass an
opinion off as an observation.

Design: docs/superpowers/specs/2026-09-08-agent-framework-design.md §5.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

Marker = Literal["measured", "read", "inferred"]


class Claim(BaseModel):
    """One statement, and how it is known.

    `evidence` is REQUIRED for `measured` and `read` and FORBIDDEN for
    `inferred`. Forbidden rather than merely absent: a citation on a reasoning
    claim reads as observed, and nothing downstream can tell that it supports
    the reasoning rather than the fact.
    """

    marker: Marker
    text: str
    evidence: str | None = None

    @model_validator(mode="after")
    def _evidence_matches_marker(self) -> "Claim":
        if self.marker == "inferred":
            if self.evidence is not None:
                raise ValueError("an inferred claim carries no evidence")
        elif not self.evidence:
            raise ValueError(f"a {self.marker} claim must carry its evidence")
        return self
