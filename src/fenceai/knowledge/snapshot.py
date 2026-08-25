"""`Snapshot` — the whole of what Planning receives, and the door it comes in by.

Integration contract §1.2. The type is theirs; what we do with it is ours.

**Nothing has ever been published through this door.** The Knowledge Platform is
still designing, so every field below is the contract's shape rather than
something observed, and `docs/integration-contract/fixtures/` holds a fixture
that is deliberately obviously a fixture. Building against a design before it is
implemented is not speculation — it is the fastest way to tell the designer
whether the design works, which is the argument `docs/superpowers/specs/
2026-08-23-frontend-design.md` §8 already makes for its own step 1. What WOULD be
speculation is treating what we learn here as settled: this file's shapes are a
hypothesis with good tests behind it, and the first real snapshot is what turns
any of it into a fact.

**Only the parts this engine can act on are modelled.** `parameters` becomes
knowledge through `parameters.expand`; `gaps` are carried through as the
contract's own `Gap`. The rest — `parts`, `models`, `procedures`, `warnings`,
`combinations`, `rules` — are accepted, counted and NOT parsed into private
types. A field parsed into a shape we invented is a shape nobody agreed to, and
this repo has already made that mistake once, under the contract's own type name.
They arrive as opaque payloads and are reported as unconsumed, which is an honest
statement of what this engine does with them today.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel

from fenceai.core.gaps import Gap
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion
from fenceai.knowledge.parameters import ParameterTable, expand

# §1.2 BINDING: a snapshot serves exactly ONE standards regime and declares it.
Regime = Literal["us_astm", "cn_gb"]

# What this engine consumes today. Everything else in the payload is carried,
# counted and left alone — see the module docstring.
CONSUMED = ("parameters", "gaps")
CARRIED = ("part_types", "parts", "models", "procedures", "warnings",
           "combinations", "source_docs", "rules")


class Snapshot(BaseModel):
    """§1.2, field for field."""

    snapshot_id: str
    tenant: str = ""
    spine_version: str = ""
    contract_version: str = ""
    policy_version: str = ""
    retain_until: str = ""
    regime: Regime = "us_astm"

    parameters: list[ParameterTable] = []
    gaps: list[Gap] = []

    # Accepted and NOT parsed. `Any` is the honest type for a payload this engine
    # does not act on: a private model here would be a shape nobody agreed to,
    # and it would look like support.
    part_types: list[Any] = []
    parts: list[Any] = []
    models: list[Any] = []
    procedures: list[Any] = []
    warnings: list[Any] = []
    combinations: list[Any] = []
    source_docs: list[Any] = []
    rules: list[Any] = []

    def unconsumed(self) -> dict[str, int]:
        """What arrived that this engine does nothing with, by count.

        Reported rather than hidden. A snapshot carrying 40 warnings into an
        engine with no warning consumer is a fact the operator should be able to
        see — and, while the other team is designing, it is the most useful thing
        we can tell them about their own payload.
        """
        return {name: len(getattr(self, name))
                for name in CARRIED if getattr(self, name)}


class Ingested(BaseModel):
    """What a snapshot became, and everything it could not become.

    `gaps` merges two sources deliberately: the ones the platform PUBLISHED
    (§3.1.8 — "gaps that cannot be expressed are published as gaps, with
    evidence, rather than approximated into a type that nearly fits") and the
    ones expansion DISCOVERED (a row that does not conform to its table's own
    `value_type`, a point no row covers, an authority that lapsed before this
    run's `as_of`). They are the same type by contract, so they are one list —
    but `discovered` counts the second kind, because "your table declares a hole"
    and "your table contradicts itself" are different messages to send back.
    """

    knowledge: KnowledgeBase
    gaps: list[Gap] = []
    discovered: int = 0
    unconsumed: dict[str, int] = {}
    snapshot_id: str = ""
    regime: Regime = "us_astm"


def ingest(snapshot: Snapshot, *, as_of: str = "") -> Ingested:
    """A published snapshot, as knowledge this engine already knows how to use.

    Every parameter table expands into ordinary `KnowledgeVersion`s through the
    existing loader, so published rows resolve beside authored ones in the one
    evaluator, at their own authority, with the same precedence and the same
    conflict reporting. That is the whole design: there is no second selection
    path, and a published table needs no privileged channel into the generator.

    `as_of` is the run's pinned date (obligation 16). Passed in, never read from
    a clock: generation is a pure function, and a clock here would make the same
    project against the same snapshot warn differently on different days.
    """
    versions: list[KnowledgeVersion] = []
    discovered: list[Gap] = []
    for table in snapshot.parameters:
        expanded, gaps = expand(table, as_of=as_of, tenant=snapshot.tenant)
        versions.extend(expanded)
        discovered.extend(gaps)
    return Ingested(
        knowledge=KnowledgeBase(versions=versions),
        # published first: they are what the other side chose to tell us, and a
        # reader scanning the list should meet those before our findings about
        # their data
        gaps=[*snapshot.gaps, *discovered],
        discovered=len(discovered),
        unconsumed=snapshot.unconsumed(),
        snapshot_id=snapshot.snapshot_id,
        regime=snapshot.regime,
    )


def snapshot_id_for(snapshot: Snapshot) -> str:
    """`sha256` over the canonical member list (§1.2).

    Computed here so a fixture can be checked against its own declared id, which
    is the one property of a snapshot this side can verify without trusting the
    sender.
    """
    members = json.dumps(
        [t.model_dump(mode="json") for t in snapshot.parameters],
        sort_keys=True, default=str,
    )
    return hashlib.sha256(members.encode()).hexdigest()
