"""Project aggregate: topology + annotations + overrides + policy."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from typing import Literal

from fenceai.ai.records import InterpretationRecord
from fenceai.core.units import Mm
from fenceai.fencemodel.selection import FenceModelChoice
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology


class Annotation(BaseModel):
    id: str
    target_ref: str  # "project" | "run:<id>" | "node:<id>" | "event:<id>"
    text: str  # verbatim, immutable
    author: str = "user"
    created_at: str = ""
    interpretations: list[InterpretationRecord] = []


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
    frost_depth_mm: Mm | None = None
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
                if k != "revision" and v is not None}


class Project(BaseModel):
    id: str
    name: str
    created_at: str = ""
    topology: Topology = Topology()
    annotations: list[Annotation] = []
    overrides: list[Override] = []
    policy: dict = {}
    # The model a stretch of this project's fence is built to unless a fence_model
    # interval event says otherwise. A typed field rather than another key in the
    # bare `policy` dict: it is resolved against the model library and stamped on
    # the run, so a typo has to fail at the boundary, not at generation.
    # None keeps the compatibility path (M-LEGACY, seeded from demand skus).
    fence_model: FenceModelChoice | None = None
    # What kind of site this is. A typed field rather than another key in the
    # bare `policy` dict, for `fence_model`'s reason: it is stamped on the run
    # and guards every derived view, so a typo has to fail at the boundary.
    site: SiteConditions = SiteConditions()
