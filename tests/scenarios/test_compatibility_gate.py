"""The phase's acceptance gate, as a committed artifact.

The whole claim of the fence-model phase is that behind `M-LEGACY` the existing
shapes produce **identical requirement lines and an identical BOM**. That was
proven once by a throwaway script that no longer exists, so nothing in the
committed suite would have caught a regression. Two mutations made the point:

  * deleting the slope-length branch in `fencemodel/resolve.py`
    (`if ctx.length_basis == "slope" ...`), so raked rails are cut to plan width
    instead of slope length — **511 passed**, because no test in the suite
    generated a raked span at all;
  * `legacy_model()` ignoring the knowledge-resolved `demand_skus` — **509
    passed**.

So the gate is pinned here as data: for every fixture shape, the exact
`RequirementLine` list and the exact `Bom`, byte-compared against JSON committed
beside this file. A pin is only as good as its coverage, so `_fixtures()` in
`test_invariants.py` gained the raked shape the suite entirely lacked — raked is
the only mode that puts a span on `rail_cut_basis="slope"`.

This is deliberately a golden-file test rather than a set of hand-written
assertions: the property being defended is "nothing moved", and enumerating what
must not move is exactly the enumeration that missed the slope branch. It is NOT
a substitute for the behavioural tests around it, which say *why* each number is
what it is.

REGENERATING: run this module as a script —

    PYTHONPATH=. uv run python tests/scenarios/test_compatibility_gate.py

— and read the diff. A change here is a change to what every existing job costs;
if you cannot explain each line of the diff, the change is wrong. Never
regenerate to make a red test green.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fulfillment.pipeline import price_strategy
from fenceai.knowledge.demo import demo_knowledge
from fenceai.strategy.generator import generate
from tests.scenarios.test_invariants import _fixtures

GOLDEN_DIR = Path(__file__).resolve().parent / "compatibility_gate"


def _spine(name: str) -> dict:
    """One fixture, all the way to a priced BOM, as plain JSON-ready data."""
    topo, overrides, inventory = _fixtures()[name]
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog, overrides=overrides)
    priced = price_strategy(result.strategy, catalog, inventory,
                            demand_skus=result.run.demand_skus,
                            preset=result.run.objective_preset)
    return {
        "requirements": [r.model_dump() for r in priced.requirements],
        "bom": priced.bom.model_dump(),
    }


@pytest.mark.parametrize("name", sorted(_fixtures()))
def test_requirements_and_bom_match_the_committed_gate(name):
    golden = json.loads((GOLDEN_DIR / f"{name}.json").read_text())
    assert _spine(name) == golden, (
        f"{name}: requirements or BOM moved. This is the phase's acceptance "
        "gate — behind M-LEGACY these must not change. Regenerate ONLY once you "
        "can explain every line of the diff."
    )


def test_the_gate_covers_a_raked_span():
    """A pin that pins nothing is worse than no pin. The slope-length branch is
    only reachable through a raked span, so assert one exists in the fixtures
    rather than trusting the fixture list to keep containing it."""
    topo, overrides, _ = _fixtures()["raked"]
    result = generate(topo, demo_knowledge(), demo_catalog(), overrides=overrides)
    spans = result.strategy.spans
    assert spans and all(s.vertical == "raked" for s in spans)
    assert all(s.rail_cut_basis == "slope" for s in spans)
    # and the rails are genuinely cut LONGER than the plan width, which is the
    # whole difference the deleted branch made
    for span in spans:
        rail = next(s for s in span.panel.slots if s.role == "rail")
        assert rail.length_mm == span.slope_len_mm > span.width_mm


def test_every_fixture_has_a_committed_gate_file():
    """A new fixture must arrive with its gate, not silently skip it."""
    committed = {p.stem for p in GOLDEN_DIR.glob("*.json")}
    assert committed == set(_fixtures())


if __name__ == "__main__":  # regeneration entry point — see the module docstring
    GOLDEN_DIR.mkdir(exist_ok=True)
    for fixture in sorted(_fixtures()):
        path = GOLDEN_DIR / f"{fixture}.json"
        path.write_text(json.dumps(_spine(fixture), indent=2, sort_keys=True) + "\n")
        print(f"wrote {path}")
