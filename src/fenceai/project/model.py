"""Project aggregate: topology + annotations + overrides + policy."""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.ai.records import InterpretationRecord
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
