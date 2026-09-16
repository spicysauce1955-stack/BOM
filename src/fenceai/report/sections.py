"""What each stretch of fence IS — the half of a job that exists before it is generated.

The office opens a job somebody else drew. `report/structure.py` answers what
that job BECAME — posts, bays, parts — and it cannot answer anything until
`generate()` has run. This model answers the other half: how long each stretch
is, what it stands on, what the ground does along it, and whether anybody
actually stated a height. All of it is a pure function of the topology, so it
is there the moment the drawing is.

**A derived read model** (foundation §15): nothing here is stored and nothing
here is recomputed. Every field is a call into `topology/station.py`, which is
the one implementation of each of these questions; this module arranges the
answers per stretch and stops.

**A silent default is REPORTED, never hidden.** A run with no base event stands
on `soil` because that is what `base_surface_at` answers, and this model says
`soil` rather than leaving the field blank. `handover.py` exists because a
silent default reaching the office looks exactly like a measured one, and this
screen is the office's first look — so the same discipline applies one surface
further on.

**"Mixed" is an answer; a guess is not.** A stretch standing on two surfaces has
no single surface, and choosing the longer one would put a material on a card
that half the fence is not standing on. `structure.py: _base_surface` already
makes that move for a generated section and this mirrors it exactly, so the
card reads the same before and after generation.

**There are no STEPS here, and that is the interesting omission.** The obvious
field for a card that says *the wall jumps here* is a list of steps, and
`station.py` has `ground_step_stations` and `base_top_step_stations` ready to
give one. Both take a `min_step_mm`, and the generator's comment says where that
number comes from: *"the threshold is knowledge, not code (K-STEP-POST)"*. A
read model that picked one would be hard-coding a rule the knowledge base owns,
and a read model that took one as an argument would push the same problem onto a
route that has no business resolving rules — `readiness.py` keeps no knowledge
base in its signature for exactly this reason.

So a step is not a fact about the drawing here. The SHAPE is (`ground`, and the
surfaces it stands on), and the JUDGEMENT that a particular step is too big
arrives after generation, as the `excessive_step` warning, through `flags.py`.
That split is also the honest one: before the rules have run, nobody knows
whether a 1120 mm step is a problem.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.report.handover import uncovered_mm
from fenceai.report.structure import section_tag
from fenceai.topology.model import Run, Topology
from fenceai.topology.station import (
    base_surface_at,
    base_transition_stations,
    corner_stations,
    fence_model_at,
    fence_model_transition_stations,
    ground_samples,
    max_slope_permille,
    run_length,
)

#: What `base_surface_at` answers where no interval covers the station. Named
#: here so the reason this model reports it rather than blanking it stays
#: attached to the value.
DEFAULT_SURFACE = "soil"

#: What `base_surface` says when a stretch genuinely has more than one. The same
#: word `structure.py` uses, so a card reads the same before and after a run.
MIXED = "mixed"


class GroundPoint(BaseModel):
    """One sample of the ground along a stretch."""

    station_mm: Mm
    z_mm: Mm


class SurfaceRun(BaseModel):
    """One stretch of one base surface, half-open `[start_mm, end_mm)`.

    Half-open because that is how `base_surface_at` reads its intervals, and two
    models disagreeing about which side a boundary belongs to is how a station
    lands on the wrong material.
    """

    start_mm: Mm
    end_mm: Mm
    surface: str


class ModelRun(BaseModel):
    """One stretch built to one fence model, half-open like `SurfaceRun`."""

    start_mm: Mm
    end_mm: Mm
    model_id: str


class SectionFacts(BaseModel):
    """One stretch of fence, as it was drawn.

    `tag` comes from `structure.section_tag`, so the letters here are the letters
    the setting-out sheet will use. A second lettering would be right on every
    job anybody has drawn and wrong on the twenty-seventh run.
    """

    run_id: str
    tag: str
    length_mm: Mm
    surfaces: list[SurfaceRun]
    #: The one surface, or `MIXED`. Never a guess — see the module docstring.
    base_surface: str
    ground: list[GroundPoint]
    max_slope_permille: int
    corner_stations: list[Mm]
    #: The stated height when every stated height agrees, else `None`. `None`
    #: means "no single answer" and covers both "nobody said" and "they said two
    #: different things" — `height_covered_mm` is what tells those apart.
    height_intent_mm: Mm | None
    #: How much of the stretch a stated height covers. Merged, not summed:
    #: existence is not coverage (audit finding B02).
    height_covered_mm: Mm
    #: Empty when nobody stated a model on this stretch — the PROJECT default
    #: then applies, and this model does not know what it is. An invented entry
    #: would make a card claim a per-stretch decision nobody made.
    models: list[ModelRun]


def _boundaries(length: Mm, inner: list[Mm]) -> list[tuple[Mm, Mm]]:
    """`[0, …inner…, length]` as consecutive pairs, with empties dropped.

    A transition reported at 0 or at the very end produces a zero-width stretch,
    which is not a stretch of anything — and one on a card would read as a
    material somebody used none of.
    """
    marks = sorted({0, length, *(s for s in inner if 0 < s < length)})
    return [(a, b) for a, b in zip(marks, marks[1:]) if b > a]


def _surfaces(topo: Topology, run: Run, length: Mm) -> list[SurfaceRun]:
    return [
        SurfaceRun(start_mm=a, end_mm=b, surface=base_surface_at(topo, run, a))
        for a, b in _boundaries(length, base_transition_stations(topo, run))
    ]


def _models(topo: Topology, run: Run, length: Mm) -> list[ModelRun]:
    """Only stretches somebody actually stated. `fence_model_at` answers `None`
    where no interval covers the station, and that absence is carried as an
    absence rather than as a row naming the project default."""
    out: list[ModelRun] = []
    for a, b in _boundaries(length, fence_model_transition_stations(topo, run)):
        choice = fence_model_at(topo, run, a)
        if choice is not None:
            out.append(ModelRun(start_mm=a, end_mm=b, model_id=choice.model_id))
    return out


def _height(topo: Topology, run: Run, length: Mm) -> tuple[Mm | None, Mm]:
    """The stated height and how much of the stretch states one.

    Two events stating the same height are one answer, not two — a salesperson
    who stated 1800 either side of a gate has not contradicted herself.
    """
    stated = {ev.payload.height_mm for ev in run.interval_events
              if ev.payload.kind == "height_intent"}
    covered = length - uncovered_mm(topo, run, "height_intent")
    return (stated.pop() if len(stated) == 1 else None), covered


def section_facts(topology: Topology) -> list[SectionFacts]:
    """Every stretch of this drawing, in the order it was drawn.

    Order is the topology's own, never sorted: the letters follow the drawing,
    so A is the stretch the reader sees first. Sorting by id would letter a job
    by the order its runs happened to be created in, which nobody can see.
    """
    out: list[SectionFacts] = []
    for index, run in enumerate(topology.runs):
        length = run_length(topology, run)
        height_mm, covered = _height(topology, run, length)
        # Computed once and used twice: the scalar is a reading of the list, not
        # a second walk of the run, so the two can never disagree.
        surfaces = _surfaces(topology, run, length)
        out.append(SectionFacts(
            run_id=run.id,
            tag=section_tag(index),
            length_mm=length,
            surfaces=surfaces,
            base_surface=_one_surface(surfaces),
            ground=[GroundPoint(station_mm=s, z_mm=z)
                    for s, z in ground_samples(topology, run)],
            max_slope_permille=max_slope_permille(topology, run),
            corner_stations=list(corner_stations(topology, run)),
            height_intent_mm=height_mm,
            height_covered_mm=covered,
            models=_models(topology, run, length),
        ))
    return out


def _one_surface(surfaces: list[SurfaceRun]) -> str:
    """The stretch's surface, or `MIXED`. Empty only for a zero-length run, which
    `segment_lengths` refuses to build in the first place."""
    distinct = {s.surface for s in surfaces}
    return distinct.pop() if len(distinct) == 1 else MIXED


__all__ = ["DEFAULT_SURFACE", "MIXED", "GroundPoint", "ModelRun", "SectionFacts",
           "SurfaceRun", "section_facts"]
