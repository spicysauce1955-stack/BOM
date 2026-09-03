"""User overrides: first-class, anchored to topology coordinates (ADR-0004).

Never reference generated element ids — anchors are (run_id, station/interval, kind).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.core.units import Mm
from fenceai.topology.model import Anchor, Run, Topology
from fenceai.topology.station import anchor_station

# `station_mm` is the reading the browser has always sent and every stored
# override still carries; `anchor` is the one that survives a geometry edit. Both
# are optional so a directive can carry either, and `override_station` decides
# which answers — never a caller reading a field directly.


class PinPost(BaseModel):
    kind: Literal["pin_post"] = "pin_post"
    # defaulted so `anchor` can be the only field a new pin carries. A bare
    # PinPost then resolves to None and is reported as `orphaned_override`,
    # rather than quietly pinning a post at station 0.
    station_mm: Mm = 0
    anchor: Anchor | None = None


class SuppressPost(BaseModel):
    kind: Literal["suppress_post"] = "suppress_post"
    station_mm: Mm = 0
    anchor: Anchor | None = None


class ForcePostSku(BaseModel):
    kind: Literal["force_post_sku"] = "force_post_sku"
    station_mm: Mm
    sku: str


class ForceMounting(BaseModel):
    kind: Literal["force_mounting"] = "force_mounting"
    station_mm: Mm
    mounting: Literal["ground", "masonry"]


class ForceVertical(BaseModel):
    kind: Literal["force_vertical"] = "force_vertical"
    start_station_mm: Mm
    end_station_mm: Mm
    mode: Literal["level", "stepped", "raked"]


class LockBay(BaseModel):
    """Build the bay starting at this anchor, exactly this wide.

    One anchor and a width, not two anchors. Two anchors can resolve to a
    half-orphaned interval, can grow to contain a corner (which is structurally
    unsuppressable), and can silently relabel which bay a person signed off on.

    This is the one directive this work adds, and the reason hand placement
    means what it says: without it `layout_segment` honours `max_span_mm` inside
    a hand-placed gap and puts a post back that nobody asked for.
    """

    kind: Literal["lock_bay"] = "lock_bay"
    at: Anchor
    width_mm: Mm


Directive = Annotated[
    Union[PinPost, SuppressPost, ForcePostSku, ForceMounting, ForceVertical, LockBay],
    Field(discriminator="kind"),
]


def override_station(topo: Topology, run: Run, directive: Directive) -> Mm | None:
    """Where this directive applies, or None when it applies nowhere.

    A thin wrapper over `anchor_station` — deliberately NOT a second
    implementation. Rev 1 reimplemented the resolution here and the two answers
    diverged on the one input its tests never built (a segment that changed
    length with the anchor still inside it), which drew the same pinned post
    800 mm apart in the plan canvas and the generator.

    `None` means orphaned, which the generator already reports as
    `orphaned_override`. It is returned only when the directive carries neither
    an anchor nor a usable station — never as a re-anchoring decision, because
    `anchor_station` always resolves to somewhere.

    The anchor wins where a directive carries both: `station_mm` is the reading
    from the geometry as it was, so preferring it would freeze a pin at the
    number it had when the run was a different length.
    """
    anchor = getattr(directive, "anchor", None) or getattr(directive, "at", None)
    if anchor is not None:
        return anchor_station(topo, run, anchor)
    station = getattr(directive, "station_mm", 0)
    return station or None


class Override(BaseModel):
    id: str
    run_id: str  # topology run anchor
    directive: Directive
    status: Literal["active", "orphaned"] = "active"
    origin: Literal["user", "correction"] = "user"
    origin_ref: str | None = None  # correction id when origin == correction
    author: str = "user"
    created_at: str = ""
    note: str | None = None
