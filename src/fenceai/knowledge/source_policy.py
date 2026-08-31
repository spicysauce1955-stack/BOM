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

from fenceai.core.dates import Date, all_orderable, latest

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
    for what is, to it, an opaque competitor. It is also the final tie-break
    in `resolve()`, which is the second half of the same purpose: an opaque
    identifier the caller already has is the only thing left to order by once
    every criterion the contract names has tied.

    `issue_date` is §1.4's third criterion, and it defaults to `None` because
    absent is the normal case — 72 of the 75 source documents in the first
    published snapshot carry no `issue_date`. A caller that has one passes it;
    every caller that does not keeps working unchanged, and gets the same
    resolution it got before this field existed.
    """

    source_class: SourceClass
    version_status: VersionStatus
    curation_level: int
    role: str | None = None
    label: str = ""
    issue_date: Date | None = None
    # §1.4's final tie-break step (amendment 005). Empty where the caller holds
    # no `SourceDoc` — a test, not a run.
    content_hash: str = ""


class AdmittedBy(BaseModel):
    """§1.4: deliberately not a field on `Provenance` — this is a RUN's answer,
    computed here, never read off published data.

    It carries every input the tie-break actually reads — rank, curation
    level, `issue_date`, `label` — because the point of recording the answer
    on the run is that a decision graph can render WHY this source won, and a
    rendering that cannot see the date the comparison turned on (or that the
    date was absent, so the step was skipped) is back to asserting a result.
    """

    rank: int
    source_class: SourceClass
    curation_level: int
    version_status: VersionStatus
    label: str = ""
    issue_date: Date | None = None
    # §1.4's final tie-break step (amendment 005). Empty where the caller holds
    # no `SourceDoc` — a test, not a run.
    content_hash: str = ""


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
    policy: list[SourcePolicyRow], task: TaskCode, candidate: Candidate,
) -> SourcePolicyRow | None:
    """The policy row governing this candidate — MOST SPECIFIC match wins.

    This used to take a bare `source_class` and return the first row matching
    `(task, source_class)`, which meant a table could hold only ONE row per pair.
    That silently broke the axis §1.4's own BINDING paragraph requires:

    > `version_status` is a policy axis. A superseded approval and its
    > replacement are otherwise the *same* source class, the same role and the
    > same task — the policy would rank them identically.

    Expressing that means several rows per `(task, source_class)`, one per
    status. Under the old lookup only the first was ever consulted, and
    `admit()`'s own status check then rejected every candidate the first row did
    not name — so an operator writing exactly the table the contract describes
    got two of three statuses reported **inadmissible** rather than ranked. The
    failure was invisible because `SHIPPED_DEFAULT` has one row per pair.

    Specificity order: a row naming both `version_status` and `role` beats one
    naming a single axis, which beats the `null`-on-both catch-all. Within one
    specificity level the first row wins, so an operator's ordering still
    decides between genuine duplicates rather than this inventing a rule.
    """
    best: SourcePolicyRow | None = None
    best_score = -1
    for row in policy:
        if row.task != task or row.source_class != candidate.source_class:
            continue
        if row.version_status is not None \
                and row.version_status != candidate.version_status:
            continue
        if row.role is not None and row.role != candidate.role:
            continue
        score = (row.version_status is not None) + (row.role is not None)
        if score > best_score:
            best, best_score = row, score
    return best


def admit(
    policy: list[SourcePolicyRow], task: TaskCode, candidate: Candidate,
) -> AdmittedBy | None:
    """One candidate, judged. `None` means inadmissible for this task —
    silently, from this function's point of view; a caller that must say WHY
    (a warned line, a decision-graph note) reads `row.admissible` /
    `min_curation` off the policy directly rather than this collapsing them.

    The `version_status`/`role` axes are matched by `_row_for` now rather than
    re-checked here: a row that does not apply to this candidate is not the
    candidate's row, and treating it as one is what made the axis unusable.
    """
    row = _row_for(policy, task, candidate)
    if row is None or not row.admissible:
        return None
    if candidate.curation_level < row.min_curation:
        return None
    return AdmittedBy(
        rank=row.rank, source_class=candidate.source_class,
        curation_level=candidate.curation_level,
        version_status=candidate.version_status, label=candidate.label,
        issue_date=candidate.issue_date, content_hash=candidate.content_hash,
    )


def resolve(
    policy: list[SourcePolicyRow], task: TaskCode, candidates: list[Candidate],
) -> Resolution:
    """Every admissible candidate, then the one that wins.

    The chain, in order:

    1. lower `rank` (§1.4);
    2. higher `curation_level`;
    3. later `issue_date` — **only when every candidate still tied carries an
       `iso`**, otherwise skipped entirely (see below);
    4. lexicographic `source_class`;
    5. lexicographic `SourceDoc.content_hash` — §1.4's own terminator since
       v1.3 (amendment 005);
    6. lexicographic `label` — a local determinism guarantee, NOT a contract
       criterion, and reachable only by a caller holding no `content_hash`
       (see below).

    **Step 3, and why it is all-or-skip.** §1.4 words the criterion "later
    `issue_date` where both carry one". Read pairwise, as literally worded,
    the relation is intransitive and therefore not an ordering at all. The
    counterexample is three candidates tied on rank and curation:
    `A(industry_standard, iso null)`, `B(sealed_approval, 2024-01-01)`,
    `C(company_authored, 2020-01-01)`. A beats B (no shared date, so
    lexicographic), B beats C (both dated, later wins), C beats A (no shared
    date, so lexicographic) — a 3-cycle, in which no candidate is the winner
    and the "answer" is whichever comparison order the implementation happened
    to use. Nor can a sort key rescue it: a key-based implementation must put
    an undated candidate *somewhere*, and every position on the date axis is
    either "earliest" or "latest" — both forbidden by §1.1's BINDING null rule
    ("a null `iso` is never ordered, and never treated as earliest or
    latest"). All-or-skip is the only reading that is a total order AND never
    positions a null date, so it is the reading implemented here: when the
    whole tied set is dated, the latest wins; when any member is undated, the
    date step does not happen and resolution moves to `source_class`.

    This was implemented as a READING of the v1.2 clause and filed as amendment
    005 (trigger B). **005 was ratified as proposed in v1.3**, so all-or-skip is
    now the contract's own wording rather than our reading of it, and steps 4–5
    below are the contract's too.

    **Step 5, and why `label` is in the key at all.** Steps 1–4 are not a
    total order: two candidates can share a rank, a curation level, a date
    (or a shared absence of one) and a `source_class`. That is not
    hypothetical — the first published snapshot's two competing footing
    authorities are both `sealed_approval`, both curation 2, both rank 1, one
    `superseded` and undated and one `unknown` dated 2025-04-24. With `min()`
    over a non-total key, the winner was whichever of them the caller listed
    first: reordering the input changed the answer, one ordering silently
    preferred the superseded document (the exact outcome §1.4's BINDING clause
    exists to prevent), and two implementations of this contract would stamp
    different `admitted_by` and hash differently. `label` is the caller's own
    opaque identifier, already carried for citation, so appending it makes the
    key total without inventing an identity scheme. It is a local determinism
    guarantee only: it can never fire until every criterion the contract names
    has tied, and it must never be read as the contract expressing a
    preference between two otherwise-equal sources. It does not say which
    source is better. It says the same one wins every time.
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
    if len(tied) > 1:
        dates = [ab.issue_date for ab in tied]
        # `all_orderable` is the all-or-skip test itself: False the moment one
        # candidate is undated, and the whole step is then skipped rather than
        # applied to the dated subset — comparing only the dated members would
        # reintroduce exactly the pairwise reading that does not order.
        if all_orderable(dates):
            newest = latest([d for d in dates if d is not None])
            if newest is not None:
                tied = [ab for ab in tied
                        if ab.issue_date is not None
                        and ab.issue_date.iso == newest.iso]
    # §1.4's last two steps, in order. `content_hash` is the contract's own
    # terminator (amendment 005): every `SourceDoc` carries one, §1.2.1's closure
    # rule already guarantees it resolves, and it is stable across re-cuts of the
    # same document — so both sides compute the same winner rather than each
    # inventing a tiebreak. `label` sits behind it only for a caller holding no
    # source doc at all, which is a test, not a run.
    #
    # What this does NOT promise, and the Knowledge team was right to make us say
    # so: a content hash has no relation to recency. Once every named criterion
    # has tied, this can rank a superseded document ahead of its replacement —
    # deterministically, on both sides, but still the older one. Keeping that
    # pairing from tying in the first place is `version_status`'s job, and
    # `SHIPPED_DEFAULT` does not currently use it (see its own note).
    winner = min(tied, key=lambda ab: (ab.source_class, ab.content_hash, ab.label))
    return Resolution(admitted=admitted, winner=winner)
