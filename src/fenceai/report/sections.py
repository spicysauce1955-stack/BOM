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
that half the fence is not standing on. `base_surface_of` below is the ONE
implementation of that question and `report/structure.py` now calls it, so the
card reads the same before and after generation — which it did not when the two
models each had their own answer.

**There is no STEP LIST here, and that is the interesting omission.** The
obvious field for a card that says *the wall jumps here* is a list of steps, and
`station.py` has `ground_step_stations` and `base_top_step_stations` ready to
give one. Both take a `min_step_mm`, and the generator's comment says where that
number comes from: *"the threshold is knowledge, not code (K-STEP-POST)"*. A
read model that picked one would be hard-coding a rule the knowledge base owns,
and a read model that took one as an argument would push the same problem onto a
route that has no business resolving rules — `readiness.py` keeps no knowledge
base in its signature for exactly this reason.

So *this step is a step* is not a fact about the drawing here. The JUDGEMENT
that a particular step is too big arrives after generation, as the
`excessive_step` warning, through `flags.py`. That split is the honest one:
before the rules have run, nobody knows whether a 1120 mm step is a problem.

**The SHAPE, though, is reportable without resolving anything** — and the
omission was over-applied once. `ground_samples` already carries a vertical
ground step losslessly and threshold-free, as TWO SAMPLES AT ONE STATION with
different z; asking *are these two the same station?* needs no `min_step_mm`,
only `==`. `base_top` below does exactly that for the built base, so a card can
draw the wall standing on the ground before Generate — which is the whole point
of a section whose fence stops where its wall starts. What it must never do is
compare the two z values against a number.
"""

from __future__ import annotations

from pydantic import BaseModel

from fenceai.core.units import Mm
from fenceai.report.handover import uncovered_mm
from fenceai.topology.model import Run, Topology
from fenceai.topology.station import (
    anchor_station,
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
#: attached to the value, and USED — by `_one_surface`, for a run with no
#: stretches at all. A constant nothing reads drifts from the literal it is
#: supposed to stand for.
DEFAULT_SURFACE = "soil"

#: A, B, … Z, AA, AB … Sections are NAMED, not numbered, so a bay tag (B3) never
#: reads like a section tag.
#:
#: It lives here rather than in `structure.py` — where it was first written —
#: because this is the more primitive of the two models: it answers from the
#: topology alone, while the structure report needs a generated strategy. The
#: dependency has to run that way round or the two import each other.
_SECTION_TAGS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def section_tag(index: int) -> str:
    """The letter for the n-th stretch of a drawing.

    **One implementation, because two read models letter sections.** This one
    answers before anything is generated; `structure.py` answers after. Two
    private copies would agree on every job anybody has drawn and disagree on
    the twenty-seventh run.
    """
    tag = ""
    n = index
    while True:
        tag = _SECTION_TAGS[n % 26] + tag
        n = n // 26 - 1
        if n < 0:
            return tag


#: What `base_surface` says when a stretch genuinely has more than one. The same
#: word `structure.py` uses, so a card reads the same before and after a run.
MIXED = "mixed"


class GroundPoint(BaseModel):
    """One sample of the ground along a stretch.

    `z_mm` is ABSOLUTE ground elevation — the node/sample elevation itself. Two
    of these at one station are a vertical ground step.
    """

    station_mm: Mm
    z_mm: Mm


class BaseTopPoint(BaseModel):
    """One point of the built base's top line along a stretch.

    It shares its name with `model.BaseTopPoint` deliberately: it IS that
    point, re-expressed for a reader. `pos_permille` along the event's own
    interval becomes a station along the stretch; `z_mm` is carried through
    unchanged; the authoring `lock` is dropped. Anything else here would be a
    second geometry, which is what this module exists not to be.

    `z_mm` is the base top's height ABOVE LOCAL GROUND at that station — the
    number `station.base_top_at` answers and the number the event itself
    stores. **It is not an elevation.** `GroundPoint.z_mm` is; a reader draws
    the wall by ADDING the two, and a reader that plots this against the ground
    axis draws a wall underground.

    It is reported in the event's own convention rather than converted, because
    converting is not free: a base top that is linear above sloping ground is
    NOT a straight line in absolute terms, so an absolute polyline would have to
    be resampled at every ground breakpoint. That is a recomputation, and this
    model does not recompute — `station.ground_z` is the one place that
    combines the two, and a consumer that needs absolute z calls it.

    Two points at ONE station with different z are a vertical step in the base
    top, carried losslessly and with no threshold — the same representation
    `ground_samples` uses, which is what makes reporting the shape admissible
    here at all (see the module docstring). The event's `lock` is deliberately
    not carried: it is authoring intent, and the geometry already says whether
    a segment is a step.
    """

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

    `tag` comes from `section_tag` above, which `report/structure.py` also
    calls — so the letters here are the letters the setting-out sheet will use.
    """

    run_id: str
    tag: str
    length_mm: Mm
    surfaces: list[SurfaceRun]
    #: The one surface, or `MIXED`. Never a guess — see the module docstring.
    base_surface: str
    ground: list[GroundPoint]
    #: The built base's top line along the stretch, as a threshold-free polyline
    #: of heights ABOVE LOCAL GROUND (see `BaseTopPoint`) — a step is two points
    #: at one station, never a flagged station.
    #:
    #: EMPTY where nothing is built: a run standing on soil has no base top, and
    #: an empty list is the honest answer. A synthesised flat line at zero would
    #: draw a wall that does not exist, which is the `soil`-is-reported rule
    #: above read backwards.
    base_top: list[BaseTopPoint]
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


def _base_top(topo: Topology, run: Run) -> list[BaseTopPoint]:
    """The built base's top line, inverted out of the interval events.

    **`wall_profile` belongs here, and `base_top` does not win over it by
    accident.** The two are one question authored two ways:
    `model.BaseTopPoint.z_mm` documents itself as "wall_profile semantics", and
    `station.base_top_at`
    answers from a `base_top` profile *falling back to* `wall_profile`. So a
    wall authored as a two-point `wall_profile` IS a built base top, and leaving
    it out would answer "nothing is built" for a wall that is — the exact lie
    the empty-list rule exists to avoid. It is reported as the two points it
    is, which is the same polyline shape with no special case.

    Precedence mirrors `base_top_at` rather than inventing its own: a
    `wall_profile` overlapping a stretch a `base_top` profile already answers
    for is not drawn, so the card and the generator read the same wall. An
    event with no points claims nothing, exactly as `base_top_at` skips it.
    """
    # (start, end, points) per contributing event — the range is kept so a later
    # event can be tested for overlap before it is allowed to draw.
    drawn: list[tuple[Mm, Mm, list[BaseTopPoint]]] = []

    def free(s0: Mm, s1: Mm) -> bool:
        return not any(s0 < b and a < s1 for a, b, _ in drawn)

    def span(ev) -> tuple[Mm, Mm]:
        return (anchor_station(topo, run, ev.start_anchor),
                anchor_station(topo, run, ev.end_anchor))

    for ev in run.interval_events:
        if ev.payload.kind != "base_top" or not ev.payload.points:
            continue
        s0, s1 = span(ev)
        if s1 <= s0 or not free(s0, s1):
            continue
        # Sorted by (position, authoring order) exactly as `base_top_at` sorts
        # them, so the two sides of a step stay in the order they were drawn in.
        points = [pt for _, pt in sorted(
            enumerate(ev.payload.points), key=lambda ip: (ip[1].pos_permille, ip[0]))]
        drawn.append((s0, s1, [
            # Proportional, and rounded the way `base_top_step_stations` rounds
            # it, so a step reported here lands on the station the generator
            # will put a post at. Integer mm throughout (ADR-0002).
            BaseTopPoint(station_mm=s0 + round((s1 - s0) * pt.pos_permille / 1000),
                         z_mm=pt.z_mm)
            for pt in points
        ]))

    for ev in run.interval_events:
        if ev.payload.kind != "wall_profile":
            continue
        s0, s1 = span(ev)
        if s1 <= s0 or not free(s0, s1):
            continue
        drawn.append((s0, s1, [
            BaseTopPoint(station_mm=s0, z_mm=ev.payload.top_z_start_mm),
            BaseTopPoint(station_mm=s1, z_mm=ev.payload.top_z_end_mm),
        ]))

    drawn.sort(key=lambda d: d[0])
    return [pt for _, _, points in drawn for pt in points]


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
            base_top=_base_top(topology, run),
            max_slope_permille=max_slope_permille(topology, run),
            corner_stations=list(corner_stations(topology, run)),
            height_intent_mm=height_mm,
            height_covered_mm=covered,
            models=_models(topology, run, length),
        ))
    return out


def _one_surface(surfaces: list[SurfaceRun]) -> str:
    """The stretch's surface, or `MIXED`.

    An EMPTY list answers the default, not `MIXED`. A run with no stretches has
    no length to stand on anything with, and calling that "mixed" would put a
    word meaning *more than one* on a stretch that has none.
    """
    distinct = {s.surface for s in surfaces}
    if not distinct:
        return DEFAULT_SURFACE
    return distinct.pop() if len(distinct) == 1 else MIXED


def base_surface_of(topo: Topology, run: Run) -> str:
    """What this stretch stands on: one surface, or `MIXED`.

    **The one implementation, shared with `report/structure.py`.** The structure
    report used to answer this by folding over the run's base EVENTS, which is
    the existence-is-not-coverage mistake audit finding B02 is about: one event
    covering half an 8 m run answered `masonry_wall` for the whole of it, while
    this model — folding over derived stretches, including the uncovered
    remainder that stands on `soil` — answered `MIXED`. Same drawing, same
    question, two answers, and a card that changed its mind the moment somebody
    pressed Generate.

    Derived from coverage, so the remainder is visible. That is the honest half
    of the disagreement and the one both surfaces now use.
    """
    return _one_surface(_surfaces(topo, run, run_length(topo, run)))


__all__ = ["DEFAULT_SURFACE", "MIXED", "BaseTopPoint", "GroundPoint", "ModelRun",
           "SectionFacts", "SurfaceRun", "base_surface_of", "section_facts",
           "section_tag"]
