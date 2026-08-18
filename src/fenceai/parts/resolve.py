"""Turning a model's part references into the predicate the matcher already reads.

Strictly UPSTREAM of `match_spec`, which is the point: the existing
`height -> rail positions -> post -> clear width -> infill` DAG does not move, and
neither does `generator.py`'s ordering. Compilation happens, then everything
downstream is what it was.
"""

from __future__ import annotations

import hashlib

from fenceai.fencemodel.model import FenceModel, Member, PartRequirement, spec_requirements
from fenceai.parts.compile import compile_spec
from fenceai.parts.model import Part, PartLibrary
from fenceai.strategy.model import PartUse


def part_requirements(model: FenceModel) -> list[tuple[str, PartRequirement]]:
    """Every requirement in a model — default spec, every variant, post and cap.

    A variant missed here would leave a slot with no predicate and the bay would
    report `no_eligible_item` only at the heights that hit that variant, which is
    the worst shape a bug of this kind can take. Walks each spec via the SAME
    `spec_requirements` `validate_model` uses — a second copy of that walk is
    exactly this kind of drift hazard, applied to itself.
    """
    out = spec_requirements(model.default_spec)
    for index, variant in enumerate(model.variants):
        out += [(f"variant{index}.{key}", req)
                for key, req in spec_requirements(variant.spec)]
    if model.post is not None:
        out.append(("post", model.post.requirement))
        if model.post.cap is not None:
            out.append(("post.cap", model.post.cap))
    return out


def content_hash(part: Part) -> str:
    """Why a version number is not enough: a DRAFT is mutable. Versions are immutable
    only once active, so a run that drew on a draft needs the content. Not a new
    precaution — `ModelUse.content_hash` already takes it one level up."""
    return hashlib.sha256(part.model_dump_json().encode()).hexdigest()[:16]


def resolve_model_parts(
    model: FenceModel, library: PartLibrary
) -> tuple[FenceModel, list[PartUse]]:
    """Fill every requirement's predicate from its part; report what was resolved.

    Returns a NEW document. `generate()` is pure (ADR-0004), and mutating the stored
    model here would make a second generation from the same library mean something
    different from the first.
    """
    resolved = model.model_copy(deep=True)
    uses: dict[str, PartUse] = {}
    for key, requirement in part_requirements(resolved):
        if not requirement.part_id:
            # A slot that names no part keeps the eligibility it was authored with.
            # The one production case is `routed_vinyl_model`'s post and cap, whose
            # predicates compare against a fact about the BAY — a `SpecField` is
            # `item.<key> <agree> <literal>` and a part cannot declare where this
            # panel puts its rails. Overwriting it here with the conjunction of
            # nothing would admit every vinyl post at every station.
            continue
        part = library.latest_active(requirement.part_id)
        if part is None:
            raise ValueError(
                f"{model.ref} slot {key!r} names part {requirement.part_id!r}, which "
                "has no active version — nothing would be eligible for it"
            )
        requirement.eligibility = requirement.eligibility.model_copy(
            update={"predicate": compile_spec(part), "members": []})
        # Filled, never authored — the part is the one authority on what a piece is,
        # and `ResolvedSlot.role` / `demand.derive` read it downstream.
        requirement.role = part.type
        uses[part.id] = PartUse(part_id=part.id, version=part.version,
                                content_hash=content_hash(part))
    _apply_dimensions(resolved, library)
    return resolved, sorted(uses.values(), key=lambda u: u.sort_key())


def library_at(library: PartLibrary, snapshot: list[PartUse]) -> PartLibrary:
    """The library as one run saw it — exactly the versions it stamped.

    Resolving against a RUN's parts is `resolve_model_parts(model, library_at(...))`
    — two calls rather than one wrapper, because the caller that needs this also
    needs the pinned library ITSELF: `preview_panel` validates the document against
    the same versions it draws, and validating against today's parts while drawing
    the run's would be the same two-authorities defect one level up. A wrapper
    returning only the document would be an entry point no production path could
    use, standing in front of the one they do.

    This is what closes the trap `bay_preview_plan` half-closed: it reloads a model
    by the version the run STAMPED, explicitly never `latest_active`, because the
    drawer once marked one product chosen while the run had bought another — and an
    unpinned `part_id` inside that stamped document reopens the identical bug by a
    new door.

    An empty snapshot returns the library UNCHANGED, which is the fallback to
    `latest_active` — a run generated before parts existed. Pinning to nothing would
    hand back an empty library and refuse the document for naming parts, which is
    the opposite of what having no snapshot means.

    COPIES each part rather than re-labelling it in place: `library` belongs to the
    caller, and flipping a retired version back to active on the shared object would
    make a preview of an old run change what every later reader of that library sees
    — a read that writes, through the one door nobody would think to look at.

    A version this run resolved may since have been retired, and it is still what the
    run resolved, so the copy is `active` — the only status `latest_active` looks at.
    A part in the snapshot that has since been DELETED is absent here, and
    `resolve_model_parts` refuses by name rather than quietly resolving today's.
    """
    if not snapshot:
        return library
    return PartLibrary(parts=[
        part.model_copy(deep=True, update={"status": "active"})
        for use in snapshot
        if (part := library.by_ref(use.part_id, use.version)) is not None
    ])


def _apply_dimensions(model: FenceModel, library: PartLibrary) -> None:
    """Write the part's dimensions onto the holders that draw them.

    `Member.width_mm`, `Member.thickness_mm` and `FrameSlot.thickness_mm` keep their
    place on the schema because `resolve.py`, `preview.py` and `report/elevation.py`
    read them — but they stop being AUTHORED and take the same lifetime `eligibility`
    has: filled here, from the one authority. Keeping them authored is what let a
    model draw 38 while buying 45.

    A part declaring no dimension leaves the field at 0, which is what the elevation
    already renders as `declared=False` — a flag, not a nominal band that reads as
    measured.
    """
    for holder in _dimension_holders(model):
        if not holder.requirement.part_id:
            # Names no part, so nothing here is the authority on its dimensions and
            # whatever the document already carries stands. Zeroing it would erase a
            # number this function never supplied a replacement for.
            continue
        # No `if part is None` guard: every requirement here already passed
        # through the loop in `resolve_model_parts`, which raises for any
        # part_id with no active version before this function is ever called.
        part = library.latest_active(holder.requirement.part_id)
        if isinstance(holder, Member):
            holder.width_mm = part.width_mm or 0
        holder.thickness_mm = part.thickness_mm or 0


def _dimension_holders(model: FenceModel) -> list:
    """Frame slots and infill members — the two that carry a drawn dimension.

    Fixings and posts do not: a screw has no elevation band, and a post's face width
    is a CAPABILITY read off the chosen product (`PanelContext.post_face_width_*`),
    not a dimension the panel draws.
    """
    out = []
    for spec in [model.default_spec, *(v.spec for v in model.variants)]:
        out += list(spec.frame)
        if spec.infill:
            out += list(spec.infill.pattern)
    return out
