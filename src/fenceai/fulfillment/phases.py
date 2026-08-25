"""The pricing pipeline as a declared list of steps — the second extension seam.

`docs/superpowers/specs/2026-08-25-engine-architecture.md` §4:

> **A declared phase list** — instead of `derive → resolve → fulfil` hardcoded,
> declare an ordered list of named steps, each with its input and output type, so
> inserting *credit kits against assemblies* or *certify combinations* is a row.

Both beneficiaries are real and pending — kit credit is build order item 10, and
`certify()` for `Combination` is contract obligation 17, where the shape is agreed
and the seam is named but nothing reads one yet. Both are steps in the MIDDLE of
this chain, which is where a hardcoded call order costs most: a middle insert
means reading three statements, working out what each one hands the next, and
hoping the mental model matches.

**A phase declares what it reads and what it writes**, which is what makes a row
safe to add. `check_order` refuses a step placed before the thing it reads
exists, so a row in the wrong position fails a test rather than quietly pricing
an empty list. That is the "input and output type" the spec asks for, expressed
as the field names on the shared state rather than as static types — the state is
one object precisely so a new step can add a field without changing the signature
of every step around it.

**What this is NOT.** It is not a general workflow engine and there is no
registry of phases: the order IS the design, so it lives in one declared tuple
that a reader can see whole. `PIPELINE` is a default a caller may override
(the tests do), not a mutable global that a plugin edits at import time — a
pricing chain assembled by import order is a job priced differently depending on
what was imported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fenceai.catalog.model import Catalog
from fenceai.demand.derive import DemandLine, derive_requirements
from fenceai.fulfillment.fulfill import Bom, Inventory, fulfill
from fenceai.fulfillment.lines import ResolvedSupplyLine
from fenceai.fulfillment.supply import SupplyDecision, resolve_supply
from fenceai.strategy.model import Strategy, StrategyWarning


@dataclass
class PipelineState:
    """Everything the chain carries, in one object.

    Inputs first and never written by a phase; the rest accumulate. A mutable
    dataclass rather than a threaded tuple of return values because that is what
    lets a new step ADD a field — `credits`, `certifications` — without changing
    the signature of every step around it, which is the churn the seam exists to
    remove.

    Purity is preserved where it matters: `strategy`, `catalog` and `inventory`
    are the caller's objects and no phase mutates them (`resolve_supply` deep-
    copies the lines it works on, as it always did).
    """

    # -- inputs -----------------------------------------------------------
    strategy: Strategy
    catalog: Catalog
    inventory: Inventory | None = None
    demand_skus: dict | None = None
    preset: str = "least_cost"

    # -- accumulated by the phases ----------------------------------------
    demand: list[DemandLine] = field(default_factory=list)
    requirements: list[ResolvedSupplyLine] = field(default_factory=list)
    unresolved: list[DemandLine] = field(default_factory=list)
    warnings: list[StrategyWarning] = field(default_factory=list)
    decisions: list[SupplyDecision] = field(default_factory=list)
    bom: Bom | None = None


PhaseFn = Callable[[PipelineState], None]

# The fields a phase may declare as input without any earlier phase writing them:
# they are the caller's, present before the chain starts.
_INPUTS = frozenset({"strategy", "catalog", "inventory", "demand_skus", "preset"})


@dataclass(frozen=True)
class Phase:
    """One named step, and the state it reads and writes.

    `reads`/`writes` are the declaration `check_order` enforces. They are not
    plumbing — a phase is handed the whole state and could touch anything — they
    are the statement of intent that makes a misplaced row a test failure instead
    of an empty list downstream.
    """

    name: str
    fn: PhaseFn
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()


def check_order(phases: tuple[Phase, ...]) -> None:
    """Refuse a chain where a step reads something nothing has written yet.

    The failure this prevents is quiet: a `credit_kits` step placed before
    `resolve_supply` reads `requirements`, finds the empty list it was
    initialised with, credits nothing, and prices a job that looks fine. Order
    errors in a hardcoded chain are at least visible as three statements in a
    row; in a declared list they need this.
    """
    available = set(_INPUTS)
    for phase in phases:
        missing = [r for r in phase.reads if r not in available]
        if missing:
            raise ValueError(
                f"phase {phase.name!r} reads {', '.join(missing)} before any earlier "
                f"phase writes it; available here: {', '.join(sorted(available))}"
            )
        available.update(phase.writes)


# --- the three steps ---------------------------------------------------------

def _derive_demand(state: PipelineState) -> None:
    state.demand = derive_requirements(state.strategy, state.catalog, state.demand_skus)


def _resolve_supply(state: PipelineState) -> None:
    resolution = resolve_supply(
        state.demand, state.catalog, state.inventory, preset=state.preset)
    state.requirements = resolution.requirements
    state.unresolved = resolution.unresolved
    state.warnings = resolution.warnings
    state.decisions = resolution.decisions


def _fulfil(state: PipelineState) -> None:
    state.bom = fulfill(state.requirements, state.catalog, state.inventory)
    # the BOM carries the supply warnings, as it did when this was three
    # statements: a reader holding only the BOM must still see why a line is
    # missing from it
    state.bom.warnings = state.warnings


PIPELINE: tuple[Phase, ...] = (
    Phase(name="derive_demand", fn=_derive_demand,
          reads=("strategy", "catalog", "demand_skus"), writes=("demand",)),
    Phase(name="resolve_supply", fn=_resolve_supply,
          reads=("demand", "catalog", "inventory", "preset"),
          writes=("requirements", "unresolved", "warnings", "decisions")),
    Phase(name="fulfil", fn=_fulfil,
          reads=("requirements", "catalog", "inventory", "warnings"),
          writes=("bom",)),
)

check_order(PIPELINE)  # the declared order is checked at import, not at first use
