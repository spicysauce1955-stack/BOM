"""Construction topology: user-authored physical reality (ADR-0003).

Nodes + run-edges of int-mm vertex polylines; varying properties live in
station-addressed events, never baked into geometry. Stationing is derived.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from fenceai.core.units import Mm
from fenceai.fencemodel.selection import FenceModelChoice


class Node(BaseModel):
    id: str
    x_mm: Mm
    y_mm: Mm
    # ground elevation at this node — a corner shared by two runs has ONE height,
    # and the whole-fence ground profile is continuous by construction
    z_mm: Mm = 0
    kind: Literal["terminal", "junction"] = "terminal"


class Anchor(BaseModel):
    """Station anchor stored as (segment, offset) so events re-anchor proportionally
    within their originating segment when geometry is edited (ADR-0003)."""

    segment_index: int
    offset_mm: Mm
    seg_len_at_authoring_mm: Mm
    # How this anchor follows a change in its segment's length. PROPORTIONAL is
    # ADR-0003's rule and stays the default, so nothing stored changes meaning:
    # an elevation sample a third of the way along a wall stays a third of the
    # way along when the wall is stretched.
    #
    # RIGID is for an anchor whose OFFSET is the fact — a post a person placed
    # 800 mm from a corner. Stretch an earlier leg and it is still 800 mm from
    # that corner, which is what they measured.
    #
    # The policy lives here rather than in a second resolver because rev 1's
    # second resolver put the same pin 800 mm apart in the canvas and the
    # generator (spec §10).
    reanchor: Literal["proportional", "rigid"] = "proportional"


# --- point event payloads -------------------------------------------------

# How a gate opens. This lives on the TOPOLOGY, not on anything the knowledge
# platform publishes: contract obligation 18 has `PanelSpec` model no gate — no
# handedness, no swing direction — so the only place the fact can live is the
# drawing the salesperson authored it on.
GateLeaf = Literal["single", "double", "sliding"]
# Which side of the run LINE, in the run's own direction (start node -> end node).
GateSide = Literal["left", "right"]
# An edge of the OPENING, named in station order along the run.
GateEdge = Literal["start", "end"]


def check_swing_coherence(
    leaf: GateLeaf,
    opens_to: GateSide | None,
    hinge: GateEdge | None,
    slides_to: GateEdge | None,
) -> None:
    """Refuse the contradictions rather than clearing them quietly.

    A contradiction here is somebody's UI writing nonsense; clearing it would
    hide that bug and hand a crew a confident wrong drawing.

    A FUNCTION, and not a method on either model, because there are now two
    places a gate's swing can be authored — inside a run (`GatePayload`) and
    beside one (`GateSpan`) — and they are the same four facts about the same
    physical object. Two copies of this would drift, and the day they did, one
    of the two ways of drawing a gate would start accepting the nonsense the
    other refuses.
    """
    if leaf == "sliding":
        for field, value in (("opens_to", opens_to), ("hinge", hinge)):
            if value is not None:
                raise ValueError(
                    "a sliding gate swings toward no side and hangs from no "
                    f"edge: leaf='sliding' with {field}={value!r}"
                )
    elif slides_to is not None:
        raise ValueError(
            "a swing gate slides nowhere: "
            f"leaf={leaf!r} with slides_to={slides_to!r}"
        )
    if leaf == "double" and hinge is not None:
        raise ValueError(
            "a double gate hangs from both edges of the opening: "
            f"leaf='double' with hinge={hinge!r}"
        )


class GatePayload(BaseModel):
    kind: Literal["gate"] = "gate"
    width_mm: Mm
    kit_sku: str | None = None

    # How it opens. "Gate at station 2000, opening 1000" tells an installer
    # there is a hole and not which way the leaf goes, and a plan that cannot
    # answer that is not a plan anybody can build from.
    leaf: GateLeaf = "single"
    # `None` everywhere means NOBODY HAS SAID, and it must stay valid: every
    # gate authored before these fields existed carries none of them. A side
    # nobody stated is drawn as a question rather than as a default, because a
    # swing drawn from a default is a confident wrong drawing.
    #
    # Run-relative (`left`/`right`) on purpose. "Opens toward the house" is a
    # SENTENCE, rendered by the frontend from the landmarks actually on that
    # side; storing the sentence would leave a gate claiming to open toward a
    # house that has since been moved.
    opens_to: GateSide | None = None
    # Which edge carries the hinge — meaningful only for a single leaf, and
    # read out on the setting-out sheet as the POST TAG the crew can walk up to.
    hinge: GateEdge | None = None
    # Which way a sliding leaf retracts.
    slides_to: GateEdge | None = None

    @model_validator(mode="after")
    def _swing_is_coherent(self) -> "GatePayload":
        check_swing_coherence(self.leaf, self.opens_to, self.hinge, self.slides_to)
        return self


class ObstaclePayload(BaseModel):
    kind: Literal["obstacle"] = "obstacle"
    description: str = ""


class ExistingFoundationPayload(BaseModel):
    kind: Literal["existing_foundation"] = "existing_foundation"


class ElevationSamplePayload(BaseModel):
    kind: Literal["elevation_sample"] = "elevation_sample"
    z_mm: Mm


class CornerOverridePayload(BaseModel):
    kind: Literal["corner_override"] = "corner_override"
    is_corner: bool


PointPayload = Annotated[
    Union[
        GatePayload,
        ObstaclePayload,
        ExistingFoundationPayload,
        ElevationSamplePayload,
        CornerOverridePayload,
    ],
    Field(discriminator="kind"),
]


class PointEvent(BaseModel):
    id: str
    anchor: Anchor
    payload: PointPayload


# --- interval event payloads ----------------------------------------------

BaseSurface = Literal["soil", "concrete", "masonry_wall"]


class BasePayload(BaseModel):
    kind: Literal["base"] = "base"
    surface: BaseSurface


class HeightIntentPayload(BaseModel):
    kind: Literal["height_intent"] = "height_intent"
    height_mm: Mm
    source: str = "user"  # "user" | interpretation record id


class TopLinePayload(BaseModel):
    kind: Literal["top_line"] = "top_line"
    mode: Literal["follow", "level", "stepped"]
    z_mm: Mm | None = None
    source: str = "user"


class WallProfilePayload(BaseModel):
    kind: Literal["wall_profile"] = "wall_profile"
    top_z_start_mm: Mm
    top_z_end_mm: Mm


class PostTiltPayload(BaseModel):
    """Per-section post orientation. Plumb (vertical to earth) is the default and
    the construction norm; 'perpendicular' follows the local ground slope
    (agricultural/slope-following fences); 'custom' is an explicit lean.
    tilt_deg: degrees from vertical, positive leans toward increasing station."""

    kind: Literal["post_tilt"] = "post_tilt"
    mode: Literal["plumb", "perpendicular", "custom"] = "plumb"
    tilt_deg: int = Field(default=0, ge=-45, le=45)


class BaseTopPoint(BaseModel):
    """A point of a built base's top line, positioned proportionally along its
    interval (permille, so points re-anchor with the interval on geometry edits).
    Two consecutive points at the same position = a vertical STEP."""

    pos_permille: int  # 0..1000 along the interval
    z_mm: Mm  # height of the base top ABOVE local ground (wall_profile semantics)
    # AUTHORING constraint on the segment that STARTS at this point, kept so the
    # user's intent survives later edits: "level" holds that segment at one
    # absolute elevation (z compensates the ground), "step" holds it vertical
    # (both ends at one position). None = free, the segment just follows its
    # end points. The generator reads geometry, never this field.
    lock: Literal["level", "step"] | None = None


class FenceModelPayload(FenceModelChoice):
    """Which fence model this stretch is built to — an interval event, because a
    fence changes model partway along exactly as it changes base or height.

    A model change is a STRUCTURAL boundary: the generator adds these stations to
    the fixed set, so no bay ever straddles the place where the fence visibly
    changes (spans sample their properties at the mid-point, which would otherwise
    hand one model's panel to a bay that is half another's)."""

    kind: Literal["fence_model"] = "fence_model"


class BaseTopPayload(BaseModel):
    """General top profile for wall/concrete bases: slopes, steps, or both, as a
    point sequence (sections-model addendum). wall_profile remains the 2-point
    linear special case and keeps working."""

    kind: Literal["base_top"] = "base_top"
    points: list[BaseTopPoint] = []


IntervalPayload = Annotated[
    Union[BasePayload, HeightIntentPayload, TopLinePayload, WallProfilePayload, BaseTopPayload, PostTiltPayload, FenceModelPayload],
    Field(discriminator="kind"),
]


class IntervalEvent(BaseModel):
    id: str
    start_anchor: Anchor
    end_anchor: Anchor
    payload: IntervalPayload


class Run(BaseModel):
    id: str
    start_node_id: str
    end_node_id: str
    interior_vertices: list[tuple[Mm, Mm]] = []
    point_events: list[PointEvent] = []
    interval_events: list[IntervalEvent] = []



class GateSpan(BaseModel):
    """A gate that is its OWN element, standing beside the runs rather than
    inside one.

        o------------o  [====gate====]  o------------o
            run rA      this element        run rB
                        n2          n3

    The other way to author a gate — `GatePayload`, a point event that punches a
    hole in a run — stays exactly as it is, and every stored project keeps
    working. This is the second kind, and it exists because the first one models
    something a salesperson does not do: a gate is not a stretch of fence that
    happens to be missing, it is a thing placed NEXT to a run, joining two runs
    that were drawn unconnected. Placing one must change the layout of neither.

    **There is no `width_mm`, and its absence is the point.** The opening is the
    distance between `start_node_id` and `end_node_id`, exactly as a run's length
    is the distance between its own two nodes — one fact, one place. A stored
    width would disagree with the geometry the instant somebody drags a node,
    and from then on the drawing and the price would be about different gates.
    `topology.station.gate_opening_mm` reads it from the nodes, which is the
    only place it is ever true — the same module that answers a run's length
    from the same geometry.
    """

    id: str
    start_node_id: str
    end_node_id: str
    kit_sku: str | None = None
    # The same four facts a `GatePayload` carries, validated by the same
    # function, and carrying the same meaning: `None` is NOBODY HAS SAID and
    # stays valid, because a swing drawn from a default is a confident wrong
    # drawing.
    #
    # `opens_to` is relative to THIS element's own direction
    # (`start_node_id -> end_node_id`) — the same convention `GatePayload`
    # documents against its run. A gate beside the fence has a direction of its
    # own; borrowing a neighbouring run's would leave the side meaning something
    # different depending on which way that run happened to be drawn.
    leaf: GateLeaf = "single"
    opens_to: GateSide | None = None
    hinge: GateEdge | None = None
    slides_to: GateEdge | None = None

    @model_validator(mode="after")
    def _swing_is_coherent(self) -> "GateSpan":
        check_swing_coherence(self.leaf, self.opens_to, self.hinge, self.slides_to)
        return self


class Topology(BaseModel):
    revision: int = 0
    nodes: list[Node] = []
    runs: list[Run] = []
    # Gates that stand BESIDE the runs (see `GateSpan`). A topology with no
    # `gates` key is every project stored before this existed, and it must keep
    # loading and round-tripping unchanged — which is what the default says.
    gates: list[GateSpan] = []

    @model_validator(mode="after")
    def _integrity(self) -> "Topology":
        """Duplicate ids silently merge distinct objects downstream — reject at the
        model boundary so a bad PUT becomes a 422, never corrupted geometry
        (final architecture review, finding 1)."""
        node_ids = [n.id for n in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate node ids in topology")
        run_ids = [r.id for r in self.runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("duplicate run ids in topology")
        event_ids = [
            e.id for r in self.runs for e in [*r.point_events, *r.interval_events]
        ]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("duplicate event ids in topology")
        known = set(node_ids)
        for r in self.runs:
            if r.start_node_id not in known or r.end_node_id not in known:
                raise ValueError(f"run {r.id} references a missing node")
        # A gate span and a run are both ELEMENTS downstream — the strategy pegs
        # to `gate@<id>` and `<run id>`, the decision graph scopes to them, and
        # the reports group by them. Two of them sharing an id would silently
        # merge, so the ids are checked together and not merely within their own
        # list.
        gate_ids = [g.id for g in self.gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("duplicate gate ids in topology")
        collisions = sorted(set(gate_ids) & set(run_ids))
        if collisions:
            raise ValueError(
                f"gate id {collisions[0]} collides with a run id in topology"
            )
        for g in self.gates:
            if g.start_node_id not in known or g.end_node_id not in known:
                raise ValueError(f"gate {g.id} references a missing node")
            # The opening IS the distance between the two nodes, so a gate
            # between one node and itself has no opening at all — there is
            # nothing for a leaf to close.
            if g.start_node_id == g.end_node_id:
                raise ValueError(f"gate {g.id} starts and ends at the same node")
        return self

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def run(self, run_id: str) -> Run:
        for r in self.runs:
            if r.id == run_id:
                return r
        raise KeyError(run_id)

    def gate(self, gate_id: str) -> GateSpan:
        for g in self.gates:
            if g.id == gate_id:
                return g
        raise KeyError(gate_id)
