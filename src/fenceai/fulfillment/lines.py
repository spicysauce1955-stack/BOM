"""The supply side of a demand line, in its own module for the same reason
`fencemodel/selection.py` is: two modules that must not import each other both
need this type.

`supply.py` produces a `ResolvedSupplyLine` and needs `fulfill.engineering_unit_for`
to do it; `fulfill.py` consumes one. Putting the type in either would make the
pair circular, so it lives here with no fulfillment imports at all.
"""

from __future__ import annotations

from pydantic import Field

from fenceai.demand.derive import DemandLine


class ResolvedSupplyLine(DemandLine):
    """A demand line that has been given a product — the only thing `fulfill()`
    accepts.

    `sku` and `unit` are REQUIRED and non-empty, which is what makes the
    invariant structural rather than conventional. It used to be a runtime check
    inside `fulfill()`, whose own comment records the convention being broken at
    all three routes by a three-word edit that produced zero test failures. A
    type cannot be edited around.

    The two are always set together by `of()`: the unit is a property of the
    CHOSEN product, so a line that has one has both — otherwise the parts ledger
    balances a demand against a purchase that counted something else.
    """

    sku: str = Field(min_length=1)
    unit: str = Field(min_length=1)

    @classmethod
    def of(cls, line: DemandLine, sku: str, unit: str) -> "ResolvedSupplyLine":
        """A NEW object, never a mutation of the demand line. One object carried
        across the boundary is how `unresolved` and `requirements` could come to
        disagree about the same line — and it is why the two states were
        indistinguishable in the first place."""
        return cls(**line.model_dump(), sku=sku, unit=unit)
