"""A SupplyRun's id names what a BOM was priced AGAINST. Every input that can
change the money has to be inside it, or a stored quote silently means something
else after the engine changes under it."""

import pytest

from fenceai.fulfillment.fulfill import Inventory, InventoryItem
from fenceai.fulfillment.supply_run import (
    SUPPLY_BEHAVIOR_VERSION, inventory_hash, supply_id,
)


def test_the_inventory_hash_is_stable_and_sized():
    inv = Inventory()
    assert inventory_hash(inv) == inventory_hash(Inventory())
    assert len(inventory_hash(inv)) == 16


def test_a_different_yard_hashes_differently():
    a = Inventory()
    b = Inventory(items=[InventoryItem(id="i1", sku="BAR-POST-LINE", qty=3)])
    assert inventory_hash(a) != inventory_hash(b)


def test_identical_inputs_give_the_identical_supply_id():
    args = ("run_abc", "inv0000000000000", "cat0000000000000", "least_cost")
    assert supply_id(*args) == supply_id(*args)
    assert supply_id(*args).startswith("sup_")
    assert len(supply_id(*args)) == len("sup_") + 12


@pytest.mark.parametrize("position", [0, 1, 2, 3])
def test_every_input_moves_the_supply_id(position):
    """Each argument is load-bearing. A parametrized sweep rather than four
    hand-written cases, because the failure this guards against is one input
    being dropped from the digest and nobody noticing."""
    base = ["run_abc", "inv0000000000000", "cat0000000000000", "least_cost"]
    moved = list(base)
    moved[position] = moved[position] + "X"
    assert supply_id(*base) != supply_id(*moved)


def test_the_supply_behaviour_version_is_part_of_the_supply_id(monkeypatch):
    """The point of the run-identity argument applied to the half that was left
    out. PLANNING_BEHAVIOR_VERSION covers generation; nothing covered cut
    planning, supply resolution or allocation. A change to the FFD packer must
    produce a different supply id or a stored quote silently means something
    else."""
    from fenceai.fulfillment import supply_run

    before = supply_id("run_abc", "inv0", "cat0", "least_cost")
    monkeypatch.setattr(supply_run, "SUPPLY_BEHAVIOR_VERSION", "supply-vNEXT")
    assert supply_id("run_abc", "inv0", "cat0", "least_cost") != before


def test_the_version_constant_is_named_not_blank():
    assert SUPPLY_BEHAVIOR_VERSION.startswith("supply-")
