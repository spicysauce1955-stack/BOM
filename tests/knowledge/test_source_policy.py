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

from fenceai.knowledge.source_policy import (
    SHIPPED_DEFAULT, AdmittedBy, Candidate, SourcePolicyRow, admit, resolve,
)


def _candidate(**kw) -> Candidate:
    base = dict(source_class="sealed_approval", version_status="active",
                curation_level=2)
    return Candidate(**{**base, **kw})


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
    rank 1st for `installation_step`. With curation level equal too, the tie
    breaks on the fourth criterion — lexicographic `source_class` — because
    this side has no `issue_date` to compare and is not guessing one (see the
    module docstring on why that step is skipped, not silently mis-ordered)."""
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

def test_the_first_real_publishs_provenance_is_admissible_at_rank_1():
    """`footing_depth_mm`'s rows carry `source_class: sealed_approval`,
    `curation_level: 2` — exactly what the shipped default admits at rank 1
    for `structural_parameter`. The real data and the shipped policy agree
    without either side being adjusted to fit the other."""
    c = _candidate(source_class="sealed_approval", version_status="unknown",
                    curation_level=2, label="f650c3f14efedaae")
    admitted = admit(SHIPPED_DEFAULT, "structural_parameter", c)
    assert admitted is not None
    assert admitted.rank == 1


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
