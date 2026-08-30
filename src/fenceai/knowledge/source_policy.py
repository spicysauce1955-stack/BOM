"""`SourcePolicy` — contract §1.4: what a source is worth, and to whom.

> **BINDING — CHANGED IN v0.4.** Planning applies the source policy, not this
> platform, and records `admitted_by` **on the run** rather than on the
> published row. Admissibility depends on the *task* a value is being used
> for, and only the planner knows the task — asking this platform to decide
> it was asking it to guess. Two consequences: a snapshot carries every
> admissible row including the ones a policy will reject, so a decision graph
> can say *"a spec sheet was inadmissible for a structural parameter"* rather
> than the value silently never existing; and `source_class` on a row becomes
> load-bearing rather than informational.

So this module is Planning's, start to finish: the table, the admission test,
and the ranking. `TaskCode` and `SourceClass` are the two of the three closed
vocabularies this side reads (`RoleCode` already exists in `core/warnings.py`'s
sibling registries); Knowledge owns adding entries to them (§2's registry
table), the operator owns the rows.

**One mechanism covers four things that would otherwise be separate
concerns**: which sources an actor can see, which sources may back an accepted
value, how competing sources rank, and how checked a value must be before it
counts (§1.4's own summary).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# §1.4: "TaskCode, SourceClass and RoleCode are closed vocabularies in the
# registries" — Knowledge adds entries, the operator configures rows against
# them. These four and eight are what the shipped default table names; a task
# or class this engine has not seen yet is simply inadmissible everywhere
# until a row names it, which is the safe default for an unrecognised axis
# value (see `_row_for`).
TaskCode = Literal[
    "structural_parameter", "component_dimension",
    "installation_step", "product_description",
]
SourceClass = Literal[
    "sealed_approval", "tested_report", "industry_standard",
    "manufacturer_installation_instruction", "spec_sheet",
    "marketing", "company_authored", "ai_proposal",
]
VersionStatus = Literal["active", "superseded", "unknown"]


class SourcePolicyRow(BaseModel):
    """§1.4, field for field. One row is one (task, source_class) cell."""

    task: TaskCode
    source_class: SourceClass
    # None = any, matching the contract's own "null = any" for both fields.
    version_status: VersionStatus | None = None
    role: str | None = None
    admissible: bool
    # Meaningless when `admissible` is False; `0` is a valid rank so it is
    # never read as a sentinel — `admit()` checks `admissible` first, always.
    rank: int = 0
    min_curation: Literal[0, 1, 2] = 0


class Candidate(BaseModel):
    """One admissible source competing to back a value for a task.

    `label` is the caller's own identifier for the thing this candidate came
    from (an authority hash, a row index) — carried through so a caller can
    say which citation won without this module inventing an identity scheme
    for what is, to it, an opaque competitor.
    """

    source_class: SourceClass
    version_status: VersionStatus
    curation_level: int
    role: str | None = None
    label: str = ""


class AdmittedBy(BaseModel):
    """§1.4: deliberately not a field on `Provenance` — this is a RUN's answer,
    computed here, never read off published data."""

    rank: int
    source_class: SourceClass
    curation_level: int
    version_status: VersionStatus
    label: str = ""


class Resolution(BaseModel):
    """Every admissible candidate for one task, and the one that won.

    Carrying the full admissible set (not just the winner) is what lets a
    decision graph say *"three sources were admissible; the sealed approval
    won over the industry standard"* rather than rendering a value with no
    account of what it beat — the same "every admissible row, not just the
    winner" argument §1.4 makes about the snapshot itself, kept one hop
    further into the run.
    """

    admitted: list[AdmittedBy] = []
    winner: AdmittedBy | None = None


# The shipped default (§1.4, "revised"). Quoted inline because the table is
# the row-configuration format §1.4 declares the operator edits — this is that
# edit, not a paraphrase of it.
#
# Two ties are IN the shipped table, not introduced by this side:
# `component_dimension`'s industry_standard/manufacturer_installation_instruction
# both rank 3rd, and `installation_step`'s manufacturer_installation_instruction/
# company_authored both rank 1st. §1.4's own BINDING clause exists for exactly
# this — "where an operator's edit creates a tie" — so `resolve()` below is
# exercised by the shipped default itself, not only by a hypothetical future one.
#
# `product_description`'s "ok" cells (sealed_approval, industry_standard,
# manufacturer_installation_instruction, spec_sheet) are not further ranked in
# the contract's own table — read here as one shared, low-priority rank behind
# the two sources authored FOR describing a product (marketing,
# company_authored), which the table does rank 1st. A `—` cell (tested_report
# on installation_step and product_description) is not a row at all: no row
# for a (task, source_class) pair means inadmissible, the same as an
# unrecognised axis value — see `_row_for`.
SHIPPED_DEFAULT: list[SourcePolicyRow] = [
    # -- structural_parameter: admissible at rank 4, and only at level 2 --
    SourcePolicyRow(task="structural_parameter", source_class="sealed_approval",
                     admissible=True, rank=1, min_curation=2),
    SourcePolicyRow(task="structural_parameter", source_class="tested_report",
                     admissible=True, rank=2, min_curation=2),
    SourcePolicyRow(task="structural_parameter", source_class="industry_standard",
                     admissible=True, rank=3, min_curation=2),
    SourcePolicyRow(task="structural_parameter",
                     source_class="manufacturer_installation_instruction",
                     admissible=True, rank=4, min_curation=2),
    SourcePolicyRow(task="structural_parameter", source_class="spec_sheet",
                     admissible=False),
    SourcePolicyRow(task="structural_parameter", source_class="marketing",
                     admissible=False),
    SourcePolicyRow(task="structural_parameter", source_class="company_authored",
                     admissible=False),

    # -- component_dimension --
    SourcePolicyRow(task="component_dimension", source_class="sealed_approval",
                     admissible=True, rank=1),
    SourcePolicyRow(task="component_dimension", source_class="tested_report",
                     admissible=True, rank=2),
    SourcePolicyRow(task="component_dimension", source_class="industry_standard",
                     admissible=True, rank=3),
    SourcePolicyRow(task="component_dimension",
                     source_class="manufacturer_installation_instruction",
                     admissible=True, rank=3),
    SourcePolicyRow(task="component_dimension", source_class="spec_sheet",
                     admissible=True, rank=4),
    SourcePolicyRow(task="component_dimension", source_class="marketing",
                     admissible=False),
    SourcePolicyRow(task="component_dimension", source_class="company_authored",
                     admissible=True, rank=2),

    # -- installation_step: a spec sheet outranking an install manual on how
    # to install something was the v0.1 default's own defect --
    SourcePolicyRow(task="installation_step", source_class="sealed_approval",
                     admissible=True, rank=2),
    SourcePolicyRow(task="installation_step", source_class="industry_standard",
                     admissible=True, rank=3),
    SourcePolicyRow(task="installation_step",
                     source_class="manufacturer_installation_instruction",
                     admissible=True, rank=1),
    SourcePolicyRow(task="installation_step", source_class="spec_sheet",
                     admissible=True, rank=2),
    SourcePolicyRow(task="installation_step", source_class="marketing",
                     admissible=True, rank=4),
    SourcePolicyRow(task="installation_step", source_class="company_authored",
                     admissible=True, rank=1),

    # -- product_description --
    SourcePolicyRow(task="product_description", source_class="sealed_approval",
                     admissible=True, rank=2),
    SourcePolicyRow(task="product_description", source_class="industry_standard",
                     admissible=True, rank=2),
    SourcePolicyRow(task="product_description",
                     source_class="manufacturer_installation_instruction",
                     admissible=True, rank=2),
    SourcePolicyRow(task="product_description", source_class="spec_sheet",
                     admissible=True, rank=2),
    SourcePolicyRow(task="product_description", source_class="marketing",
                     admissible=True, rank=1),
    SourcePolicyRow(task="product_description", source_class="company_authored",
                     admissible=True, rank=1),

    # `ai_proposal` is proposal-only on every task (§1.4: "omitted from the
    # table for width") — no row anywhere admits it, which is the correct
    # behaviour under `_row_for`'s "no row -> inadmissible" default. Named
    # here so a reader does not go looking for a missing case.
]


def _row_for(
    policy: list[SourcePolicyRow], task: TaskCode, source_class: SourceClass,
) -> SourcePolicyRow | None:
    for row in policy:
        if row.task == task and row.source_class == source_class:
            return row
    return None


def admit(
    policy: list[SourcePolicyRow], task: TaskCode, candidate: Candidate,
) -> AdmittedBy | None:
    """One candidate, judged. `None` means inadmissible for this task —
    silently, from this function's point of view; a caller that must say WHY
    (a warned line, a decision-graph note) reads `row.admissible` /
    `min_curation` off the policy directly rather than this collapsing them.
    """
    row = _row_for(policy, task, candidate.source_class)
    if row is None or not row.admissible:
        return None
    if row.version_status is not None and row.version_status != candidate.version_status:
        return None
    if row.role is not None and row.role != candidate.role:
        return None
    if candidate.curation_level < row.min_curation:
        return None
    return AdmittedBy(
        rank=row.rank, source_class=candidate.source_class,
        curation_level=candidate.curation_level,
        version_status=candidate.version_status, label=candidate.label,
    )


def resolve(
    policy: list[SourcePolicyRow], task: TaskCode, candidates: list[Candidate],
) -> Resolution:
    """Every admissible candidate, then the one that wins.

    Lower `rank` wins (§1.4). A rank tie breaks by higher `curation_level`,
    then — per the BINDING clause — by later `issue_date`. That third step is
    not built: this platform has no `Date` type yet (candidate amendment C6,
    logged 2026-08-30) and neither side has agreed one, and Planning has no
    `issue_date` field to compare even if it did. Writing a parser for it here
    would be inventing the same comparator §1.4 asks an operator's edit to
    resolve, unilaterally and untested against a real date. So a tie that
    survives `curation_level` breaks on the fourth criterion, lexicographic
    `source_class`, which needs no date at all — deterministic either way,
    and honest about which step is missing rather than guessing at it.
    """
    admitted = [ab for c in candidates
                if (ab := admit(policy, task, c)) is not None]
    if not admitted:
        return Resolution(admitted=[], winner=None)

    best_rank = min(ab.rank for ab in admitted)
    tied = [ab for ab in admitted if ab.rank == best_rank]
    if len(tied) > 1:
        best_level = max(ab.curation_level for ab in tied)
        tied = [ab for ab in tied if ab.curation_level == best_level]
    winner = min(tied, key=lambda ab: ab.source_class)
    return Resolution(admitted=admitted, winner=winner)
