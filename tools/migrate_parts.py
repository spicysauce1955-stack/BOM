"""Turning inline requirements into library parts.

Mechanical, with two refusals that are not: a SKU drawn at two widths, and a
`suggest_only` member. Both are real facts about existing data that this migration
is the first thing to look at, and neither has a safe automatic answer.

The four demo models are migrated in `parts/demo.py` and `fencemodel/demo.py`, in
source, once. This module is for a DATABASE somebody already has — the same
transformation, applied to `fence_model_library()` — and its three pure functions
are what the migration tests exercise, because a refusal nothing calls is a comment.

    uv run python tools/migrate_parts.py fence.db          # report only
    uv run python tools/migrate_parts.py fence.db --write   # write parts and models
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from fenceai.parts.model import Part, SpecField

# The three fields the dedup key is built from, beyond the type: the SKU list a slot
# named, and the two dimensions a slot could draw. Anything else on a
# `PartRequirement` — qty, length_rule, joint, engagement — is about WHERE the piece
# goes, and two slots differing only there share one part. That is the dedup's whole
# payoff and the reason the key is this short.


def width_conflicts(models) -> dict[str, dict[int, list[str]]]:
    """{sku: {width: [model refs]}} for any SKU drawn at more than one width.

    Not a migration failure — a contradiction in the models, surfaced for the first
    time. Migration reports and stops rather than picking one.
    """
    seen: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for model in models:
        for _key, req, width, _thickness in _requirements_with_width(model):
            if width is None:
                continue
            for sku in _skus(req):
                seen[sku][width].append(model.ref)
    return {sku: {w: refs for w, refs in widths.items()}
            for sku, widths in seen.items() if len(widths) > 1}


def thickness_conflicts(models) -> dict[str, dict[int, list[str]]]:
    """The same question about the other drawn dimension.

    A frame slot's `thickness_mm` is a face height, and one SKU cannot be 40 mm tall
    in one panel and 60 in another — the comment `channel_slat_model` already carries
    about why the channel is its own product. An UNDECLARED thickness is not a
    conflicting one: it is a slot that said nothing, so it is skipped here and the
    part it migrates to simply carries no thickness row.
    """
    seen: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for model in models:
        for _key, req, _width, thickness in _requirements_with_width(model):
            if not thickness:
                continue
            for sku in _skus(req):
                seen[sku][thickness].append(model.ref)
    return {sku: {t: refs for t, refs in ts.items()}
            for sku, ts in seen.items() if len(ts) > 1}


def approval_losses(models) -> list[tuple[str, str, str]]:
    """(model ref, slot key, sku) for every `suggest_only` member.

    Derived members are emitted `auto`. Promoting one would let the system substitute
    a product a human said needs sign-off, so migration refuses rather than
    converting.
    """
    out = []
    for model in models:
        for key, req, _width, _thickness in _requirements_with_width(model):
            for member in req.eligibility.members:
                if member.approval == "suggest_only":
                    out.append((model.ref, key, member.sku))
    return out


def parts_for(models) -> dict[tuple, Part]:
    """One part per distinct `(type, sku list, width, thickness)`, keyed by it.

    The dedup is the payoff landing on day one: a SKU backing the same kind of slot
    in three models becomes one part, edited once. Slots that named no SKU at all
    (a predicate slot, or one whose eligibility knowledge seeds at generation) are
    skipped — there is nothing to migrate and inventing a part would freeze a SKU in
    front of the rule that supplies it.
    """
    keys: list[tuple] = []
    for model in _migratable(models):
        for _key, req, width, thickness in _requirements_with_width(model):
            skus = _skus(req)
            if not skus:
                continue
            key = (req.role, tuple(skus), width, thickness)
            if key not in keys:
                keys.append(key)
    return {key: _part(key, _id_for(key, keys)) for key in keys}


def _id_for(key: tuple, keys: list[tuple]) -> str:
    """`{type}-{sku}`, with the drawn dimension appended only when it has to be.

    Two slots naming one SKU while declaring different faces are two parts —
    RAIL-3000 with a 40 mm face is not the same declaration as RAIL-3000 with none —
    so their ids have to differ. Appending the number unconditionally would name
    every part twice over (`infill-slat-100-100`), so it is appended only to the
    members of a colliding group, and the declaration that draws NOTHING keeps the
    bare id: it is the general one, and the dimension is what the others add.
    """
    role, skus, width, thickness = key
    base = f"{role}-{skus[0].lower()}"
    if not (width or thickness):
        return base
    if sum(1 for k in keys if f"{k[0]}-{k[1][0].lower()}" == base) == 1:
        return base
    return f"{base}-{width or thickness}"


def rewrite(models, parts: dict[tuple, Part]):
    """The models as they are AFTER migration: every migrated slot names its part
    and carries no SKU list, no width and no thickness of its own.

    Returns new documents. Rewriting in place would leave a half-migrated library
    behind if the write failed partway.
    """
    from fenceai.fencemodel.model import Member

    rewritten = []
    for model in _migratable(models):
        copy = model.model_copy(deep=True)
        for _key, req, width, thickness in _requirements_with_width(copy):
            skus = _skus(req)
            if not skus:
                continue
            part = parts[(req.role, tuple(skus), width, thickness)]
            req.part_id = part.id
            req.role = ""
            req.eligibility = req.eligibility.model_copy(update={"members": []})
        for holder in _dimension_holders(copy):
            if not holder.requirement.part_id:
                continue
            if isinstance(holder, Member):
                holder.width_mm = 0
            holder.thickness_mm = 0
        rewritten.append(copy)
    return rewritten


def _migratable(models):
    """Every model except M-LEGACY.

    M-LEGACY's eligibility is not authored: `generator._pick_model` REBUILDS it from
    the run's resolved `demand_skus` on every generation, so a knowledge
    `DefaultComponent` still reaches the BOM. A part would freeze one SKU in front of
    that rule. The stored document is only what the model picker lists, so migrating
    it would change nothing a fence is built from and break the one seam it holds
    open.
    """
    from fenceai.strategy.generator import LEGACY_MODEL_ID
    return [m for m in models if m.id != LEGACY_MODEL_ID]


# --- the walk ----------------------------------------------------------------

def _requirements_with_width(model):
    """(key, requirement, width_mm | None, thickness_mm | None) for every slot.

    Walks `parts.resolve.part_requirements`, which is the one definition of "every
    requirement in a model" — frame, infill, fixings, every variant, post and cap. A
    second copy of that walk is the drift hazard that function's own docstring warns
    about, and a variant missed HERE would migrate a model into a document with an
    unmigrated slot in it.
    """
    from fenceai.parts.resolve import part_requirements

    drawn = {id(h.requirement): h for h in _dimension_holders(model)}
    for key, req in part_requirements(model):
        holder = drawn.get(id(req))
        width = (getattr(holder, "width_mm", 0) or None) if holder else None
        thickness = (getattr(holder, "thickness_mm", 0) or None) if holder else None
        yield key, req, width, thickness


def _dimension_holders(model):
    from fenceai.parts.resolve import _dimension_holders as holders
    return holders(model)


def _skus(req) -> list[str]:
    return [m.sku for m in req.eligibility.members]


def _part(key: tuple, part_id: str) -> Part:
    role, skus, width, thickness = key
    spec = [SpecField(key="sku", value=list(skus), agree="among")]
    if width:
        spec.append(SpecField(key="width_mm", value=width, agree="==", unit="mm"))
    if thickness:
        spec.append(SpecField(key="thickness_mm", value=thickness, agree="==",
                              unit="mm"))
    return Part(id=part_id, version=1, type=role, spec=spec)


# --- the CLI -----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="path to a fence .db")
    parser.add_argument("--write", action="store_true",
                        help="write the parts and the rewritten models")
    args = parser.parse_args(argv)

    from fenceai.store.db import Store

    store = Store(args.db)
    models = store.fence_model_library().models

    conflicts = width_conflicts(models)
    conflicts.update(thickness_conflicts(models))
    losses = approval_losses(models)
    if conflicts or losses:
        for sku, drawn in sorted(conflicts.items()):
            print(f"REFUSED {sku}: drawn at {sorted(drawn)} by "
                  f"{sorted({r for refs in drawn.values() for r in refs})}",
                  file=sys.stderr)
        for ref, key, sku in losses:
            print(f"REFUSED {ref} slot {key!r}: {sku} is suggest_only — promoting it "
                  "to auto would let the system substitute a product a human said "
                  "needs sign-off", file=sys.stderr)
        print("nothing written", file=sys.stderr)
        return 1

    parts = parts_for(models)
    rewritten = rewrite(models, parts)
    print(f"{len(models)} models -> {len(parts)} parts")
    for key, part in sorted(parts.items(), key=lambda kv: kv[1].id):
        print(f"  {part.id:<24} {[f.value for f in part.spec if f.key == 'sku']}")
    if not args.write:
        print("dry run — pass --write to apply")
        return 0
    written = 0
    for part in parts.values():
        # A published version is frozen, and this database may already hold the part
        # — the built-ins are SEEDED. An id whose spec already says what migration
        # would write is left alone; one that says something else gets a NEW version
        # rather than an overwrite, because a run stamped the old one.
        existing = store.part_library().latest_active(part.id)
        if existing is not None and existing.spec == part.spec:
            print(f"  {part.id}: already {existing.ref}, unchanged")
            continue
        version = store.next_part_version(part.id)
        # Saved as a DRAFT and then activated, never saved active. A part id with
        # an existing active version would otherwise end with two, and `save_part`
        # refuses that: activation is the act that retires the predecessor, and it
        # is the only one that does. Unconditional rather than branched on
        # `version > 1` — the branch is what left the second-version path untested
        # on every fresh database, and it aborted AFTER committing the second active
        # row on every database that was not.
        store.save_part(
            part.model_copy(update={"version": version, "status": "draft"}),
            actor="migrate_parts")
        store.set_part_status(part.id, version, "active", actor="migrate_parts")
        written += 1
    for model in rewritten:
        store._conn.execute(
            "UPDATE fence_models SET doc=? WHERE model_id=? AND version=?",
            (model.model_dump_json(), model.id, model.version),
        )
        store.log("migrate_parts", "migrate_fence_model", model.ref)
    store._conn.commit()
    print(f"wrote {written} parts and rewrote {len(rewritten)} models")
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
