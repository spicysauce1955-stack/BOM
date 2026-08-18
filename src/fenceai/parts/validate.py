"""Refusals a part earns at authoring time.

The same guardrail `validate_model` already applies to a slot with no eligible
product, at the same moment and for the same reason: a part that publishes cleanly
and then reports `no_eligible_item` on every bay of every job built to it has told
the author nothing, at the one moment they could still have fixed it.
"""

from __future__ import annotations

from collections import Counter

from fenceai.catalog.model import Catalog
from fenceai.fencemodel.match import match_eligibility
from fenceai.fencemodel.model import Eligibility
from fenceai.parts.compile import compile_spec
from fenceai.parts.model import Part


def matching_skus(part: Part, catalog: Catalog, facts: dict | None = None) -> list[str]:
    """Which products this part's spec admits, sorted by SKU.

    Asks the MATCHER rather than walking the catalog itself, which is not a
    tidying: this function used to carry its own copy of `match_eligibility`'s
    walk, copy-pasted reasoning and all, and two copies of the covering rule are
    how the two would eventually disagree about what counts as a match — a part
    publishing clean here and reporting `no_eligible_item` on every bay there. It
    is the same defect the branch already fixed once by promoting `_requirements`
    to `spec_requirements`.

    The sort comes from the matcher for the same reason the matcher sorts:
    `resolve_supply` groups by the members' (sku, priority, approval) signature and
    grouping decides which product is chosen — cut planning is not additive — so a
    varying order would change the answer and not merely the JSON.
    """
    matched = match_eligibility(
        Eligibility(predicate=compile_spec(part)), catalog, facts or {})
    return [m.sku for m in matched.members]


def validate_part(part: Part, catalog: Catalog) -> list[str]:
    errors: list[str] = []

    duplicates = [k for k, n in Counter(f.key for f in part.spec).items() if n > 1]
    for key in sorted(duplicates):
        errors.append(
            f"{part.ref}: {key!r} is declared twice — two authorities over one field, "
            "so the part would draw one number and buy another"
        )

    if part.status == "draft":
        # A draft may hold anything. That is what lets an author write a spec before
        # the item exists, and it is the same bargain a draft model already has.
        return errors

    if not part.spec:
        errors.append(
            f"{part.ref}: the spec is empty, which is a conjunction of nothing and "
            "therefore true of every product — a part that matches everything is not "
            "a specification"
        )
        return errors

    if not matching_skus(part, catalog):
        errors.append(
            f"{part.ref}: no product in the catalog covers this spec, so every slot "
            "naming it would report no_eligible_item on every bay of every job"
        )
    return errors
