"""What KIND of site a project's fence is being built on.

Deliberately its own tiny module with no imports beyond pydantic and the unit
alias, for `fencemodel/selection.py`'s reason turned around. That one lives in
`fencemodel/` because `topology/` and `project/` both need to say "this fence is
built to that model"; this one lives in `project/` because the site is a fact
about the PROJECT — and `fencemodel/model.py` needs to say "that condition names
a dimension that does not exist".

Without the split, `fencemodel.model` — a pure leaf validator — would import the
project aggregate and pull `topology.model`, `strategy.overrides` and `ai.records`
in behind it, or would have to defer the import inside a function and leave the
layering invisible. Neither is worth a comment claiming a direction the code does
not take: `project` depends on `fencemodel`, and the one thing `fencemodel` needs
back is a vocabulary, so the vocabulary is what moves.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fenceai.core.units import Mm


class SiteConditions(BaseModel):
    """What KIND of site this is — the prerequisite for anything conditional.

    Nothing conditional works until a project can say this. `exposure_category`
    is not expressible at any layer without it, so every `ParameterTable` the
    Knowledge Platform publishes would arrive with nothing to match against.

    **On the PROJECT, because these are whole-site facts.** Anything that varies
    ALONG a run belongs in the topology instead, as an interval payload — the
    pattern `ElevationSamplePayload`, `WallProfilePayload` and `PostTiltPayload`
    already establish. Soil class is the likely first case and goes there, not
    here.

    `None` means *nobody has said*, and it is a different claim from any value:
    a rule conditioned on an unset dimension is NOT APPLICABLE rather than false
    (`evaluator` treats a missing context field that way already), and the run
    warns `site_condition_missing` so the silence is visible.

    `jurisdiction` and `code_edition` are not decoration. The first is what *"to
    be used in Miami Dade County and other areas where allowed by the Authority
    Having Jurisdiction"* binds against. The second keeps one manufacturer's
    `ASCE 7-10` and `ASCE 7-16` wind tables from colliding on the same domain
    point: the two editions define exposure categories differently, so
    `exposure_category: "C"` is not the same condition under each.

    **Not here: the standards regime.** `us_astm` versus `cn_gb` is the frame the
    whole rule set is written in, not a dimension to select between — a condition
    key would let a GB row and an ASTM row sit in one table and be chosen
    between, which is exactly the silent wrong answer the contract's regime guard
    refuses. It rides on the snapshot.
    """

    # `Project.site`'s own comment claims a typo has to fail at the boundary.
    # Field-NAME typos did not: `{"exposure_catgeory": "C"}` validated clean,
    # stored all-None, and the run behaved as if the estimator had said nothing.
    model_config = ConfigDict(extra="forbid")

    exposure_category: Literal["B", "C", "D"] | None = None
    hvhz: bool | None = None                # high-velocity hurricane zone
    # `ge=0` because a frost line ABOVE the ground is not a thing — and the
    # browser panel was the only thing that said so, so `PUT /api/projects/{id}/
    # site` accepted -500 from anything that was not that panel. A negative depth
    # is not merely odd: it satisfies every `<=` a footing rule tests and defeats
    # every `>=`, silently, on the one dimension that decides how deep a post is
    # set. The same argument as the field-name typo above, one field lower down.
    #
    # NO upper bound, deliberately. Permafrost is metres deep and the figure a
    # jurisdiction publishes is not ours to cap; an invented ceiling would refuse
    # a real site at the boundary, which is a worse failure than the one this
    # closes. The bound is the one the arithmetic actually requires.
    frost_depth_mm: Mm | None = Field(default=None, ge=0)
    jurisdiction: str | None = None
    code_edition: str | None = None
    # Bumped by the route on every write, exactly as `Topology.revision` is, and
    # for exactly the same reason: a derived view laid over conditions the run
    # was not generated under is a document that describes a different fence.
    # See the `site_conditions_changed` 409.
    revision: int = 0

    def facts(self) -> dict:
        """The `site.*` evaluation namespace.

        Unset dimensions are OMITTED rather than sent as None — that is what
        makes a rule conditioned on one *not applicable* instead of false, and
        the difference is a rule quietly deciding a fence versus a rule standing
        aside and saying so.
        """
        return {k: v for k, v in self.model_dump().items()
                if k in SITE_DIMENSIONS and v is not None}


# Every dimension the `site.*` namespace can carry, derived from the model rather
# than listed beside it: a second list is how "what may a rule ask about the
# site" comes to have two answers, and the wrong one of the two is silent — a
# dimension in the list and not on the model reads as `MissingField` forever, so
# the rule that asks about it never fires and nothing says why.
#
# `revision` is excluded because it is not a fact about the site. It is the
# bookkeeping that lets a derived view refuse a run generated under different
# conditions, and a rule conditioned on it would be conditioned on how many
# times somebody had saved the form.
#
# Read by `fencemodel.model` to refuse a variant or a predicate naming a `site.`
# key that is not one of these. It is imported there DEFERRED and on purpose:
# `project` depends on `fencemodel`, never the reverse.
SITE_DIMENSIONS = frozenset(SiteConditions.model_fields) - {"revision"}
