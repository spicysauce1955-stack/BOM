"""Turning a model's part references into the predicate the matcher already reads.

Strictly UPSTREAM of `match_spec`, which is the point: the existing
`height -> rail positions -> post -> clear width -> infill` DAG does not move, and
neither does `generator.py`'s ordering. Compilation happens, then everything
downstream is what it was.
"""

from __future__ import annotations

import hashlib

from fenceai.fencemodel.model import FenceModel, PanelSpec, PartRequirement
from fenceai.parts.compile import compile_spec
from fenceai.parts.model import Part, PartLibrary
from fenceai.strategy.model import PartUse


def _spec_requirements(spec: PanelSpec) -> list[tuple[str, PartRequirement]]:
    out = [(s.key, s.requirement) for s in spec.frame]
    if spec.infill:
        out += [(m.key, m.requirement) for m in spec.infill.pattern]
    out += [(f.key, f.requirement) for f in spec.fixings]
    return out


def part_requirements(model: FenceModel) -> list[tuple[str, PartRequirement]]:
    """Every requirement in a model — default spec, every variant, post and cap.

    A variant missed here would leave a slot with no predicate and the bay would
    report `no_eligible_item` only at the heights that hit that variant, which is
    the worst shape a bug of this kind can take.
    """
    out = _spec_requirements(model.default_spec)
    for index, variant in enumerate(model.variants):
        out += [(f"variant{index}.{key}", req)
                for key, req in _spec_requirements(variant.spec)]
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
        part = library.latest_active(requirement.part_id)
        if part is None:
            raise ValueError(
                f"{model.ref} slot {key!r} names part {requirement.part_id!r}, which "
                "has no active version — nothing would be eligible for it"
            )
        requirement.eligibility = requirement.eligibility.model_copy(
            update={"predicate": compile_spec(part), "members": []})
        uses[part.id] = PartUse(part_id=part.id, version=part.version,
                                content_hash=content_hash(part))
    _apply_dimensions(resolved, library)
    return resolved, sorted(uses.values(), key=lambda u: (u.part_id, u.version))


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
        part = library.latest_active(holder.requirement.part_id)
        if part is None:
            continue
        if hasattr(holder, "width_mm"):
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
