"""The extension seams: a new basis, length rule or preset is a REGISTRATION.

`docs/superpowers/specs/2026-08-25-engine-architecture.md` §3 states the rule:

> A vocabulary is **open** when a general mechanism reads it, and **closed** when
> `if kind == "…"` branches on it somewhere.

These three were closed — a `Literal` naming the members plus a branch that knew
what each meant — while part types, knowledge rules and warning codes were rows in
a table. Nothing about the concepts made a fixing basis harder to extend; one was
data and the other was a branch.

Each test below adds a vocabulary member WITHOUT editing a type or a branch, and
asserts the engine uses it. That is the property; the registry is only how.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.core.registry import Registry
from fenceai.fencemodel.bases import FIXING_BASES, PanelCounts
from fenceai.fencemodel.lengths import LENGTH_RULES
from fenceai.fulfillment.presets import PRESETS, RankInputs


@pytest.fixture()
def clean():
    """Register into the real registries and remove afterwards — the point is to
    prove the PRODUCTION registry is open, so a stub would test nothing."""
    added: list[tuple[Registry, str]] = []

    def add(registry: Registry, name: str, fn):
        registry.add(name, fn)
        added.append((registry, name))

    yield add
    for registry, name in added:
        registry._fns.pop(name, None)


# -- the registry itself -------------------------------------------------------

def test_a_duplicate_registration_is_refused():
    """Two implementations of one name would be resolved by import order, and a
    fence counted by whichever module happened to load last is the failure this
    type would otherwise introduce."""
    r: Registry = Registry("thing")
    r.add("a", lambda: 1)
    with pytest.raises(ValueError, match="already registered"):
        r.add("a", lambda: 2)


def test_re_registering_the_same_function_is_not_a_conflict():
    """An idempotent import is not two implementations."""
    r: Registry = Registry("thing")
    fn = lambda: 1  # noqa: E731
    r.add("a", fn)
    r.add("a", fn)
    assert len(r) == 1


def test_an_unknown_name_names_the_alternatives():
    """The message reaches an author who mistyped, so "KeyError: 'per_membr'" is
    not good enough."""
    r: Registry = Registry("fixing basis")
    r.add("per_member", lambda: 1)
    with pytest.raises(KeyError, match="per_member"):
        r.get("per_membr")


def test_names_are_sorted_not_insertion_ordered():
    """They are interpolated into a refusal an author reads; an order that varied
    with import order would make one mistake read differently on two machines."""
    r: Registry = Registry("thing")
    for name in ("zebra", "apple", "mango"):
        r.add(name, lambda: 1)
    assert r.names() == ["apple", "mango", "zebra"]


# -- a new FIXING BASIS, with no type edit and no branch ------------------------

def test_a_new_fixing_basis_is_a_registration(clean):
    """The spec's own example: `BASES["per_corner"] = fn`, a function with the
    EXISTING signature, therefore configuration rather than a release."""
    from fenceai.fencemodel.model import FixingRule, PartRequirement

    clean(FIXING_BASES, "per_second_member", lambda c: c.placed_count // 2)

    # ...it is authorable, which a `Literal` would have refused
    rule = FixingRule(key="clip", basis="per_second_member", qty_per_basis=1,
                      requirement=PartRequirement(role="fixing"))
    assert rule.basis == "per_second_member"
    # ...and the engine counts with it
    assert FIXING_BASES.get(rule.basis)(PanelCounts(placed_count=9)) == 4


def test_an_unregistered_basis_is_refused_at_the_boundary(clean):
    """Validation was moved, not given up — and the message is better than the
    `Literal`'s, because it names what IS registered."""
    from fenceai.fencemodel.model import FixingRule, PartRequirement

    with pytest.raises(ValidationError, match="per_member"):
        FixingRule(key="clip", basis="per_unicorn", qty_per_basis=1,
                   requirement=PartRequirement(role="fixing"))


def test_every_shipped_basis_is_registered():
    """The six the demo models author, so a rename cannot quietly orphan one."""
    assert set(FIXING_BASES.names()) >= {
        "per_panel", "per_frame_member", "per_member",
        "per_end_member", "per_gap", "per_member_crossing",
    }


# -- a new LENGTH RULE ---------------------------------------------------------

def test_a_new_length_rule_is_a_registration(clean):
    from fenceai.fencemodel.lengths import along_grade
    from fenceai.fencemodel.model import PartRequirement

    clean(LENGTH_RULES, "centre_to_centre_less_hardware",
          lambda req, ctx: along_grade(ctx.centre_width_mm - 12, ctx))

    req = PartRequirement(role="rail", length_rule="centre_to_centre_less_hardware")
    assert req.length_rule == "centre_to_centre_less_hardware"


def test_an_unregistered_length_rule_is_refused_at_the_boundary():
    from fenceai.fencemodel.model import PartRequirement

    with pytest.raises(ValidationError, match="centre_to_centre"):
        PartRequirement(role="rail", length_rule="as_long_as_a_piece_of_string")


def test_between_frame_answers_none_and_that_is_an_answer():
    """It measures against the panel's own frame, so it is not answerable from
    the bay — `resolve_panel` answers it separately with the frame passed IN."""
    assert LENGTH_RULES.get("between_frame")(None, None) is None


# -- a new PRESET --------------------------------------------------------------

def test_a_new_preset_is_a_registration(clean):
    """"What does best mean" is a key function and nothing more, which is why a
    preset can be a row: every preset ranks the SAME candidates on the same
    measured facts and differs only in what it puts first."""
    from fenceai.fulfillment.supply import resolve_supply

    clean(PRESETS, "least_waste", lambda r: (r.waste_mm, r.cost_cents, r.sku))
    assert "least_waste" in PRESETS
    # ...and the boundary check that used to read a Literal now reads the registry
    resolve_supply([], catalog=None, preset="least_waste")


def test_an_unregistered_preset_is_still_a_loud_error():
    """The silent fallback this check exists to prevent: every value other than
    `honour_priority` used to fall through as least-cost with nobody told."""
    from fenceai.fulfillment.supply import resolve_supply

    with pytest.raises(ValueError, match="unknown objective preset"):
        resolve_supply([], catalog=None, preset="cheapest-ish")


def test_the_shipped_presets_rank_as_they_say():
    cheap_but_low_priority = RankInputs(sku="A", priority=9, cost_cents=100, waste_mm=0)
    dear_but_preferred = RankInputs(sku="B", priority=1, cost_cents=900, waste_mm=0)

    least_cost = PRESETS.get("least_cost")
    assert min([cheap_but_low_priority, dear_but_preferred], key=least_cost).sku == "A"

    honour = PRESETS.get("honour_priority")
    assert min([cheap_but_low_priority, dear_but_preferred], key=honour).sku == "B"


def test_a_preset_never_sees_an_infeasible_candidate():
    """`_choose` filters feasibility BEFORE any preset runs, which is what makes
    it structurally impossible for a new preset to rank an unsuppliable product
    first — the guarantee a registry has to preserve to be safe to open."""
    import inspect

    from fenceai.fulfillment import supply

    source = inspect.getsource(supply._choose)
    assert source.index("feasible = [") < source.index("PRESETS.get(")
