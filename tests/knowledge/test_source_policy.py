"""`SourcePolicy` — contract §1.4, applied by Planning.

Two things are being defended. **The mechanism**: admission and ranking are
generic over whatever table an operator configures, so the same four
functions serve every task without a branch per source class. **The shipped
default**: it is a data table, not a design, so it deserves the same
behavioural coverage as any other registry — including the two rank ties
already built into it, which the contract's own BINDING clause exists to
resolve rather than forbid.
"""

from __future__ import annotations

from fenceai.core.dates import Date, precedes
from fenceai.knowledge.source_policy import (
    SHIPPED_DEFAULT, AdmittedBy, Candidate, SourcePolicyRow, admit, resolve,
)


def _candidate(**kw) -> Candidate:
    base = dict(source_class="sealed_approval", version_status="active",
                curation_level=2)
    return Candidate(**{**base, **kw})


def _tied_policy(*classes: str) -> list[SourcePolicyRow]:
    """A one-task table in which every named class ties at rank 1.

    §1.4's BINDING tie-break clause is written about "where an operator's edit
    creates a tie", so an operator's edit is what these tests hand it. Two
    such ties are already in the shipped default and are covered above; this
    builds the wider ones (three-way, and pairs the shipped table happens not
    to contain) without pretending the shipped table contains them.
    """
    return [SourcePolicyRow(task="component_dimension", source_class=c,
                            admissible=True, rank=1) for c in classes]


# -- admission ------------------------------------------------------------

def test_an_inadmissible_class_never_admits_however_well_curated():
    """`spec_sheet` is inadmissible for `structural_parameter` — the v0.1
    default's own defect (48.4% of structural facts filed under it, per the
    audit), fixed by naming the row rather than by curation level alone."""
    c = _candidate(source_class="spec_sheet", curation_level=2)
    assert admit(SHIPPED_DEFAULT, "structural_parameter", c) is None


def test_structural_parameter_gates_on_curation_level_2():
    """The one task the contract calls out by name: admissible at rank 4,
    and ONLY at level 2 — the ranking is more permissive than strict
    exclusion so the admissible set is not empty on a first snapshot, but the
    bar is real."""
    low = _candidate(source_class="sealed_approval", curation_level=1)
    high = _candidate(source_class="sealed_approval", curation_level=2)
    assert admit(SHIPPED_DEFAULT, "structural_parameter", low) is None
    assert admit(SHIPPED_DEFAULT, "structural_parameter", high) is not None


def test_a_null_version_status_row_admits_any_status():
    """`component_dimension`'s rows carry no `version_status`, so `active` and
    `superseded` are both admissible — the axis is `null` = any for this row,
    not silently coerced to one value."""
    for status in ("active", "superseded", "unknown"):
        c = _candidate(source_class="sealed_approval", version_status=status)
        assert admit(SHIPPED_DEFAULT, "component_dimension", c) is not None


def test_an_unrecognised_task_or_class_pair_is_inadmissible_not_a_crash():
    """No row for a (task, source_class) pair — `tested_report` on
    `installation_step` — means inadmissible, the same default an
    unrecognised axis value gets. Absence is a policy answer, not an error."""
    c = _candidate(source_class="tested_report")
    assert admit(SHIPPED_DEFAULT, "installation_step", c) is None


def test_admitted_by_carries_the_callers_label_through():
    """`label` is opaque to this module — a caller's own identifier for what
    won, so it can say WHICH citation was admitted without this module
    inventing an identity scheme for a candidate it never inspects again."""
    c = _candidate(label="authority:f650c3f1")
    admitted = admit(SHIPPED_DEFAULT, "structural_parameter", c)
    assert admitted.label == "authority:f650c3f1"


# -- ranking, and the ties the shipped default already contains -----------

def test_lower_rank_wins_outright():
    sealed = _candidate(source_class="sealed_approval")
    tested = _candidate(source_class="tested_report")
    resolution = resolve(SHIPPED_DEFAULT, "structural_parameter", [tested, sealed])
    assert resolution.winner.source_class == "sealed_approval"
    assert {ab.source_class for ab in resolution.admitted} == {
        "sealed_approval", "tested_report"}


def test_component_dimensions_own_rank_tie_breaks_on_curation_level():
    """`industry_standard` and `manufacturer_installation_instruction` both
    rank 3rd for `component_dimension` IN THE SHIPPED TABLE — not a case this
    test invents. Higher curation level wins the tie."""
    standard = _candidate(source_class="industry_standard", curation_level=1)
    install = _candidate(
        source_class="manufacturer_installation_instruction", curation_level=2)
    resolution = resolve(SHIPPED_DEFAULT, "component_dimension",
                         [standard, install])
    assert resolution.winner.source_class == "manufacturer_installation_instruction"


def test_installation_steps_own_rank_tie_breaks_lexicographically_when_level_also_ties():
    """`manufacturer_installation_instruction` and `company_authored` both
    rank 1st for `installation_step`. With curation level equal too, and
    neither candidate dated, the `issue_date` step is skipped and the tie
    breaks on the fourth criterion — lexicographic `source_class`. Undated is
    the ordinary case (72 of 75 documents in the first snapshot), so this is
    the path most real resolutions take, not a degenerate one."""
    install = _candidate(source_class="manufacturer_installation_instruction")
    authored = _candidate(source_class="company_authored")
    resolution = resolve(SHIPPED_DEFAULT, "installation_step",
                         [install, authored])
    # "company_authored" < "manufacturer_installation_instruction" lexically
    assert resolution.winner.source_class == "company_authored"


def test_no_admissible_candidate_resolves_to_no_winner_not_a_crash():
    inadmissible = _candidate(source_class="marketing")
    resolution = resolve(SHIPPED_DEFAULT, "structural_parameter", [inadmissible])
    assert resolution.winner is None
    assert resolution.admitted == []


# -- the real snapshot (`3ae88642…`, 2026-08-30) ---------------------------

def test_the_first_real_publishs_provenance_is_admissible_at_the_top_rank():
    """`footing_depth_mm`'s rows carry `source_class: sealed_approval`,
    `curation_level: 2` — exactly what the shipped default admits at the top
    rank for `structural_parameter`. The real data and the shipped policy agree
    without either side being adjusted to fit the other.

    Asserted as "no admissible class outranks it" rather than as a literal
    number, because the number is not the property. The shipped ranks step in
    tens so a superseded document can sit one below its own replacement, and a
    test pinned to `== 1` fails on a renumbering that changes no ordering at
    all."""
    c = _candidate(source_class="sealed_approval", version_status="unknown",
                    curation_level=2, label="f650c3f14efedaae")
    admitted = admit(SHIPPED_DEFAULT, "structural_parameter", c)
    assert admitted is not None
    best = min(r.rank for r in SHIPPED_DEFAULT
               if r.task == "structural_parameter" and r.admissible)
    assert admitted.rank == best


def test_the_snapshots_two_footing_authorities_resolve_identically_in_either_input_order():
    """The regression for a real, silent, order-dependent winner.

    `footing_depth_mm` in the first published snapshot is backed by two
    competing authorities that agree on every criterion the contract names:
    both `sealed_approval`, both `curation_level: 2`, therefore both rank 1
    for `structural_parameter`. One is `superseded` and undated, the other
    `unknown` and dated 2025-04-24, so the `issue_date` step is skipped and
    `source_class` ties as well. Before `label` entered the sort key, `min()`
    over that non-total key returned whichever candidate the caller listed
    FIRST: reordering the list changed the winner, one ordering silently
    preferred the superseded document — the outcome §1.4's BINDING clause
    exists to prevent — and two implementations would stamp different
    `admitted_by` and hash differently.

    **These two no longer tie at all**, and that is the point of the shipped
    policy now using `version_status` as an axis on `structural_parameter`: the
    superseded approval ranks one step below its replacement rather than beside
    it. So this pair never reaches the tie-break, and the RIGHT document wins
    rather than merely a consistent one.

    Both properties are asserted, because they fail differently. Order
    independence is the original regression and must hold whatever the ranks
    are. Preferring the replacement is the new behaviour, and would silently
    revert if a future edit dropped the `superseded` rows.
    """
    superseded = _candidate(
        source_class="sealed_approval", version_status="superseded",
        curation_level=2, label="authority:9d21be07c4a15f38")
    dated = _candidate(
        source_class="sealed_approval", version_status="unknown",
        curation_level=2, label="authority:f650c3f14efedaae",
        issue_date=Date(iso="2025-04-24"))

    forward = resolve(SHIPPED_DEFAULT, "structural_parameter",
                      [superseded, dated])
    reversed_ = resolve(SHIPPED_DEFAULT, "structural_parameter",
                        [dated, superseded])

    assert forward.winner == reversed_.winner
    # ...and it is the replacement, not whichever hash sorts first. Under the
    # old single-row table this assertion read `9d21be07…` — the superseded one.
    assert forward.winner.label == "authority:f650c3f14efedaae"
    assert forward.winner.version_status != "superseded"
    # both are still ADMITTED — a snapshot carries every admissible row, and a
    # decision graph has to be able to say what the winner beat (§1.4)
    assert {ab.label for ab in forward.admitted} == {ab.label for ab in reversed_.admitted}
    assert len(forward.admitted) == 2


# -- the `issue_date` step: all-or-skip (§1.4 read via `amendments/005`) ---

def test_the_date_step_fires_when_every_tied_candidate_is_dated_and_the_later_wins():
    """§1.4's third criterion, doing actual work.

    The two candidates are arranged so that `source_class` — the criterion
    AFTER the date — would pick the opposite winner: `company_authored` sorts
    before `industry_standard`, so if the date step were absent or inert the
    older document would win. It does not, in either input order.
    """
    policy = _tied_policy("industry_standard", "company_authored")
    older = _candidate(source_class="company_authored",
                       issue_date=Date(iso="2019-05-02"))
    newer = _candidate(source_class="industry_standard",
                       issue_date=Date(iso="2024-11-30"))

    for order in ([older, newer], [newer, older]):
        resolution = resolve(policy, "component_dimension", order)
        assert resolution.winner.source_class == "industry_standard"
        assert resolution.winner.issue_date.iso == "2024-11-30"


def test_one_undated_candidate_skips_the_date_step_entirely_rather_than_placing_the_null():
    """§1.1 BINDING: a null `iso` is never ordered, and never treated as
    earliest or latest. The two halves of that sentence need two setups,
    because a single test can only be wrong in one direction at a time.

    In both halves exactly one candidate is undated and the other is dated,
    so the step is skipped and lexicographic `source_class` decides — which
    means the undated candidate wins one half and loses the other, on grounds
    that have nothing to do with its missing date. If null were read as
    "earliest" the first half would flip; if null were read as "latest" the
    second would.
    """
    policy = _tied_policy("industry_standard", "company_authored")

    # Half one: the UNDATED candidate wins, because "company_authored" sorts
    # first. A null read as "earliest" would have handed this to the dated one.
    undated_wins = resolve(policy, "component_dimension", [
        _candidate(source_class="company_authored"),
        _candidate(source_class="industry_standard",
                   issue_date=Date(iso="2024-11-30")),
    ])
    assert undated_wins.winner.source_class == "company_authored"
    assert undated_wins.winner.issue_date is None

    # Half two: the DATED candidate wins, on the same lexicographic grounds.
    # A null read as "latest" would have handed this to the undated one.
    dated_wins = resolve(policy, "component_dimension", [
        _candidate(source_class="industry_standard"),
        _candidate(source_class="company_authored",
                   issue_date=Date(iso="2019-05-02")),
    ])
    assert dated_wins.winner.source_class == "company_authored"
    assert dated_wins.winner.issue_date.iso == "2019-05-02"


def test_the_intransitive_three_candidate_set_still_has_exactly_one_winner():
    """The counterexample that decided the reading, kept as a test.

    Applied PAIRWISE as §1.4 literally words it ("later `issue_date` where
    both carry one"), these three tied candidates form a 3-cycle: A beats B
    (no shared date, so lexicographic), B beats C (both dated, later wins),
    C beats A (no shared date, so lexicographic). A relation with a cycle is
    not an ordering, so under a pairwise implementation "the winner" is
    whichever candidate the comparison order reached last — six input orders,
    up to three different answers, all defensible.

    Under all-or-skip the date step does not fire at all here (A is undated),
    `source_class` decides, and every one of the six permutations agrees.
    """
    from itertools import permutations

    policy = _tied_policy("industry_standard", "sealed_approval",
                          "company_authored")
    a = _candidate(source_class="industry_standard", label="A")
    b = _candidate(source_class="sealed_approval", label="B",
                   issue_date=Date(iso="2024-01-01"))
    c = _candidate(source_class="company_authored", label="C",
                   issue_date=Date(iso="2020-01-01"))

    winners = {resolve(policy, "component_dimension", list(order)).winner.label
               for order in permutations([a, b, c])}
    assert winners == {"C"}


def test_a_date_whose_iso_is_null_never_orders_and_is_indistinguishable_from_no_date():
    """A `Date` carrying only `value_raw` is not a weaker date — it is an
    unordered one. `"05/04/2023"` is ambiguous on its face and normalising it
    by house convention would manufacture a fact, so the raw text survives
    beside a null `iso` for a curator to resolve. Until they do, it must
    behave in this module exactly as a missing date does: `precedes` answers
    None (not False, which a caller would read as "no, so the other is
    later"), and the tied resolution is byte-identical to the one where the
    field was never set.
    """
    ambiguous = Date(value_raw=["05/04/2023"])
    real = Date(iso="2023-04-05")
    assert precedes(ambiguous, real) is None
    assert precedes(real, ambiguous) is None
    assert precedes(ambiguous, ambiguous) is None
    assert ambiguous.orderable is False
    assert ambiguous.raw() == "05/04/2023"

    policy = _tied_policy("industry_standard", "company_authored")
    dated = _candidate(source_class="company_authored",
                       issue_date=Date(iso="2019-05-02"))
    with_raw_only = resolve(policy, "component_dimension", [
        _candidate(source_class="industry_standard", issue_date=ambiguous),
        dated,
    ])
    with_no_field = resolve(policy, "component_dimension", [
        _candidate(source_class="industry_standard"),
        dated,
    ])
    assert with_raw_only.winner.source_class == with_no_field.winner.source_class
    assert with_raw_only.winner.issue_date == with_no_field.winner.issue_date


def test_a_custom_policy_row_is_just_data_no_code_change_needed():
    """The escalation test (`core/registry.py`'s own argument, applied here):
    an operator adding a new source class to a task is a row, not a release."""
    custom = SourcePolicyRow(task="product_description", source_class="ai_proposal",
                              admissible=True, rank=1)
    c = _candidate(source_class="ai_proposal", curation_level=0)
    assert admit([custom], "product_description", c) is not None
    # ...and `ai_proposal` admits nowhere in the shipped default itself —
    # proposal-only on every task, per §1.4.
    assert admit(SHIPPED_DEFAULT, "product_description", c) is None


def test_the_exhausted_chain_terminates_on_the_contracts_own_content_hash():
    """§1.4's final step since v1.3 (amendment 005). Every named criterion has
    tied, so something has to decide — and it has to be a value BOTH sides
    compute the same way, or two implementations stamp different `admitted_by`
    and hash differently, which is the failure the paragraph exists to prevent.
    `content_hash` is on every `SourceDoc` and §1.2.1's closure rule already
    guarantees it resolves.

    The last assertion is the honest limit, and the Knowledge team's disposition
    of 005 is what made us write it down: **a content hash has no relation to
    recency.** Whatever wins here wins because it sorts first, not because it is
    newer. Keeping a superseded document and its replacement from reaching this
    chain tied at all is `version_status`'s job, not this chain's.

    Both candidates share a `version_status` deliberately. The shipped policy now
    separates `superseded` from everything else, so a superseded/replacement pair
    is decided at `rank` and never arrives here. Exhausting the chain takes two
    documents alike in every named respect — two undated approvals of the same
    class, which is the ordinary case rather than a contrived one.
    """
    one = Candidate(source_class="sealed_approval", version_status="unknown",
                    curation_level=2, content_hash="aaa", label="one")
    two = Candidate(source_class="sealed_approval", version_status="unknown",
                    curation_level=2, content_hash="bbb", label="two")

    # deterministic under both input orders — the point of having a terminator
    assert resolve(SHIPPED_DEFAULT, "structural_parameter",
                   [one, two]).winner.content_hash == "aaa"
    assert resolve(SHIPPED_DEFAULT, "structural_parameter",
                   [two, one]).winner.content_hash == "aaa"

    # ...and the honest limit: `aaa` won because it sorts first. Nothing here
    # knows which document is newer, and a hash never will.
    assert resolve(SHIPPED_DEFAULT, "structural_parameter",
                   [one, two]).winner.label == "one"


def test_a_superseded_structural_source_loses_to_its_replacement_and_to_nothing_else():
    """The shipped policy's `version_status` axis, and the exact scope of it.

    §1.4 BINDING: *"A superseded approval and its replacement are otherwise the
    same source class, the same role and the same task — the policy would rank
    them identically."* It did, and the first published snapshot contains that
    pair. The axis fixes it.

    The Knowledge team supplied the corpus fact that decides the direction
    (`conversation.md` T31): here `superseded` means a NAMED, citable replacement
    exists, where `unknown` means nobody established anything — so "a specific
    other document replaced this" is stronger negative evidence than "unrated".

    **Both halves are asserted, and the second is the decision.** They proposed
    that a superseded structural value should lose to *anything* not known to be
    superseded, including a lower class. That was not taken: a stamped approval
    does not stop being engineering evidence the day it is renewed, and 40.7% of
    this corpus's human-gated facts come from a superseded document. So the
    demotion is exactly one step — below its own class's replacement, above the
    class beneath it."""
    def rank(source_class, status):
        got = admit(SHIPPED_DEFAULT, "structural_parameter",
                    _candidate(source_class=source_class, version_status=status,
                               curation_level=2))
        return None if got is None else got.rank

    # half one: superseded loses to its own replacement, in every class
    for source_class in ("sealed_approval", "tested_report", "industry_standard",
                         "manufacturer_installation_instruction"):
        assert rank(source_class, "superseded") > rank(source_class, "active")
        assert rank(source_class, "superseded") > rank(source_class, "unknown")

    # half two: and to NOTHING else — a superseded sealed approval still beats an
    # active tested report, an industry standard and an installation manual
    assert rank("sealed_approval", "superseded") < rank("tested_report", "active")
    assert rank("tested_report", "superseded") < rank("industry_standard", "active")
    assert rank("industry_standard", "superseded") < \
        rank("manufacturer_installation_instruction", "active")

    # the demotion changes admissibility for nobody — every class the table
    # admits is still admitted, superseded or not
    assert rank("sealed_approval", "superseded") is not None
    assert rank("spec_sheet", "active") is None, "inadmissible stays inadmissible"


def test_the_version_status_axis_is_scoped_to_structural_parameter_on_purpose():
    """It is where a superseded approval and its replacement actually compete
    over a number that decides how deep somebody digs. A product description
    does not get safer for knowing which brochure was reprinted, and a policy
    that demotes documents everywhere for no stated reason is harder to justify
    to an operator than one that does it where it matters.

    Pinned so that extending it later is a deliberate edit with a reason, not a
    drive-by consistency fix."""
    axis_tasks = {r.task for r in SHIPPED_DEFAULT if r.version_status is not None}
    assert axis_tasks == {"structural_parameter"}


def test_version_status_is_usable_as_a_policy_axis():
    """§1.4 BINDING: *"`version_status` is a policy axis. A superseded approval
    and its replacement are otherwise the same source class, the same role and
    the same task — the policy would rank them identically."*

    Expressing that requires SEVERAL rows per `(task, source_class)`, one per
    status. The lookup used to return the first row matching the pair and ignore
    the status, so only one was ever consulted and `admit()` then reported every
    candidate that row did not name as **inadmissible** — an operator writing
    exactly the table the contract describes got two of three statuses silently
    excluded rather than ranked.

    Invisible until now because `SHIPPED_DEFAULT` carries one row per pair, and
    the Knowledge team's recommendation on `superseded` is unimplementable
    without it."""
    policy = [
        SourcePolicyRow(task="structural_parameter", source_class="sealed_approval",
                        version_status="active", admissible=True, rank=1, min_curation=2),
        SourcePolicyRow(task="structural_parameter", source_class="sealed_approval",
                        version_status="unknown", admissible=True, rank=2, min_curation=2),
        SourcePolicyRow(task="structural_parameter", source_class="sealed_approval",
                        version_status="superseded", admissible=True, rank=3, min_curation=2),
    ]
    ranks = {}
    for status in ("active", "unknown", "superseded"):
        got = admit(policy, "structural_parameter",
                    Candidate(source_class="sealed_approval", version_status=status,
                              curation_level=2))
        assert got is not None, f"{status} must rank, not vanish"
        ranks[status] = got.rank
    assert ranks == {"active": 1, "unknown": 2, "superseded": 3}

    # ...and the replacement now beats the document it superseded, which is the
    # real pair in `3ae88642` and the whole point of the axis
    sup = Candidate(source_class="sealed_approval", version_status="superseded",
                    curation_level=2, content_hash="aaa", label="1c487c73")
    rep = Candidate(source_class="sealed_approval", version_status="unknown",
                    curation_level=2, content_hash="bbb", label="f650c3f1")
    for order in ([sup, rep], [rep, sup]):
        assert resolve(policy, "structural_parameter", order).winner.label == "f650c3f1"


def test_a_more_specific_policy_row_wins_over_the_catch_all():
    """An operator demoting one status should not have to restate every other.
    A `null` `version_status` row is the catch-all §1.4 calls "any", and a row
    naming a status is more specific — so the two coexist rather than the
    ordering of the list deciding which is consulted."""
    policy = [
        SourcePolicyRow(task="structural_parameter", source_class="sealed_approval",
                        admissible=True, rank=1, min_curation=2),
        SourcePolicyRow(task="structural_parameter", source_class="sealed_approval",
                        version_status="superseded", admissible=True, rank=9,
                        min_curation=2),
    ]
    def rank_of(status):
        return admit(policy, "structural_parameter",
                     Candidate(source_class="sealed_approval", version_status=status,
                               curation_level=2)).rank
    assert rank_of("active") == 1, "the catch-all still governs an unnamed status"
    assert rank_of("superseded") == 9, "the specific row wins wherever it is listed"
