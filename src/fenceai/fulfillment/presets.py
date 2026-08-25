"""Objective presets — what "best product" means, as data rather than a branch.

Was `Preset = Literal["least_cost", "honour_priority"]` plus `if preset ==
"honour_priority"` inside the ranking closure. See `core/registry.py` for the
rule this moves across.

**The signature is the contract**: `(RankInputs) -> tuple`, a sort key, lowest
wins. Every preset ranks the SAME candidates on the same measured facts and
differs only in what it puts first, so a preset is exactly a key function and
nothing more.

What a preset may NOT do is decide feasibility. `_choose` filters infeasible
candidates before any preset runs, so a preset only ever sees products already
proved buildable — which is what makes it structurally impossible for a new
preset to accidentally rank an unsuppliable sku first.
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from fenceai.core.registry import Registry
from fenceai.core.units import Cents, Mm


class RankInputs(BaseModel):
    """The measured facts a preset ranks on.

    `sku` is last in every key here and should stay that way: it is the
    tie-break that makes the answer deterministic when two products are
    genuinely indistinguishable, and a preset that ranked on it earlier would be
    choosing by name.
    """

    sku: str
    priority: int
    cost_cents: Cents
    waste_mm: Mm


PresetFn = Callable[[RankInputs], tuple]

PRESETS: Registry[PresetFn] = Registry("objective preset")


@PRESETS.register("least_cost")
def _least_cost(r: RankInputs) -> tuple:
    return (r.cost_cents, r.waste_mm, r.priority, r.sku)


@PRESETS.register("honour_priority")
def _honour_priority(r: RankInputs) -> tuple:
    """The company's stated preference order first, cost only as a tie-break."""
    return (r.priority, r.cost_cents, r.waste_mm, r.sku)
