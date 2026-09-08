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

import hashlib
import json
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
    # SEAM (slice 2): `text` says nothing about WHAT it is, so the renderer
    # cannot know whether "2500 · 2500" is a millimetre list to convert into
    # the reader's display units or a string to leave alone — today
    # `js/agent-advice.js` sniffs the shape and deliberately converts nothing
    # ambiguous. The field that closes it belongs here, authored by whoever
    # authored the number: `value_kind: Literal["prose", "mm", "mm_list"]`.
    # It arrives with the Claude adapter, because that is when a claim's text
    # stops being one deterministic string the stub wrote.

    @model_validator(mode="after")
    def _evidence_matches_marker(self) -> "Claim":
        if self.marker == "inferred":
            if self.evidence is not None:
                raise ValueError("an inferred claim carries no evidence")
        elif not self.evidence:
            raise ValueError(f"a {self.marker} claim must carry its evidence")
        return self


def proposal_id(task_id: str, kind: str, payload: dict, scope: str) -> str:
    """Content-derived, never random — `core/ids.py`'s existing distinction.

    Two things break under a random id, and the second is not obvious. A re-run
    shows a person "all new suggestions" when nothing changed; and
    `advisory-agent-design.md` §3's "a rejection suppresses re-proposal" stops
    working entirely, because nothing can tell a re-proposal is the same
    proposal. `conversation.md` T46 §8 measured that from the other side of the
    boundary: 0 of 67 ids survived and the consumer saw 67 removed, 403 added,
    when "the gaps themselves did not all change; their identity did."
    """
    body = json.dumps(
        {"task": task_id, "kind": kind, "payload": payload, "scope": scope},
        sort_keys=True, separators=(",", ":"),
    )
    return "prop_" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


class ViewDigest(BaseModel):
    """What a task read, by IDENTITY rather than by payload.

    The same identity a `GenerationRun` already stamps. A replay against a
    matching digest is provably the same situation; against a copy of the
    payload it would only be a similar one.
    """

    slices: list[str] = []
    run_id: str | None = None
    topology_revision: int | None = None
    knowledge_hash: str = ""


class Declined(BaseModel):
    """An action considered and not proposed, with the claims that ruled it out.

    Evidenced exactly as a proposal is — a rejection nobody can check is not a
    reason. It is also the record that stops the same idea arriving next week.
    """

    kind: str
    claims: list[Claim] = []


class NoStanding(BaseModel):
    """Something the task could assert and may not.

    NOT a variant of `needs`. `needs` means *I lack information*; this means *I
    have the answer and it is not mine to state*. T54 §2 is the case: the
    Knowledge team could see which of our fence models their product family
    mapped to, and left the table empty rather than "assert a product identity
    we do not hold". An agent will always be able to produce a plausible
    mapping, so it needs somewhere to put one that is not a proposal.
    """

    about: str
    whose: str
    claims: list[Claim] = []


class Proposal(BaseModel):
    """One thing the agent suggests, and everything needed to check it."""

    id: str
    task_id: str
    project_id: str
    kind: str
    payload: dict = {}
    scope: str = ""
    claims: list[Claim] = []
    saw: ViewDigest = ViewDigest()
    # Fixed. `SourceClass` is a closed registry vocabulary in the integration
    # contract, and §1.4's BINDING block states `ai_proposal` is proposal-only
    # on every task — so `knowledge/source_policy.py` refuses it as authority
    # everywhere, independently of our own review gate.
    source_class: Literal["ai_proposal"] = "ai_proposal"
    agent_id: str = "stub"
    status: Literal["proposed", "kept", "reversed"] = "proposed"
    created_at: str = ""


class TaskResult(BaseModel):
    """Ledger-shaped, from `conversation.md` ground rule 3: no decision may live
    only in prose.

    `evaluated` is separate from an empty `proposals` list, and the separation
    is the point — "I did not look" is not "nothing to report".
    """

    task_id: str
    evaluated: bool
    proposals: list[Proposal] = []
    declined: list[Declined] = []
    measured: list[Claim] = []
    needs: list[str] = []
    no_standing: list[NoStanding] = []
    # Counted from the first run, never added later (spec §8b): an agent whose
    # proposals nobody keeps looks exactly like an agent that is working.
    # `produced`/`dropped` share ONE denominator — proposals — exactly as
    # §8b's table does (`shown`, `kept / reversed`, `never rendered` are all
    # proposal-shaped too), so `produced - dropped` is always the survivor
    # count. A claim refused on `measured`, `declined[]` or `no_standing[]` is
    # a real agent defect and gets counted too (§8b's guard applies there as
    # much as here), but under its OWN name below rather than folded into
    # `dropped`, which would make the two proposal counters stop agreeing
    # with each other.
    produced: int = 0
    dropped: int = 0
    # A `Claim` refused by check 2 on `measured`, `declined[]` or
    # `no_standing[]` — never a proposal, which is what `dropped` counts.
    claims_refused: int = 0
