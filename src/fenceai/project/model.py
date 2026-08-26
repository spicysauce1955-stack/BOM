"""Project aggregate: topology + annotations + overrides + policy."""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.ai.records import InterpretationRecord
from fenceai.fencemodel.selection import FenceModelChoice
# Re-exported, not redefined: `SiteConditions` moved to its own leaf module so
# `fencemodel.model` can read the dimension vocabulary without importing this
# aggregate. Every caller that already said `from fenceai.project.model import
# SiteConditions` still resolves, and there is still exactly one definition.
from fenceai.project.site import SITE_DIMENSIONS, SiteConditions
from fenceai.strategy.overrides import Override
from fenceai.topology.model import Topology


class Annotation(BaseModel):
    id: str
    target_ref: str  # "project" | "run:<id>" | "node:<id>" | "event:<id>"
    text: str  # verbatim, immutable
    author: str = "user"
    created_at: str = ""
    interpretations: list[InterpretationRecord] = []


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
