"""`Gap` — what is missing, said addressably (integration contract §1.2.1).

One type whether the Knowledge Platform publishes it or a planning run produces
it. That is the contract's wording and it is the reason this lives in `core/`
rather than under `knowledge/` or `strategy/`: a gap arriving in a snapshot and a
gap discovered while laying out a fence are the same fact seen from two sides,
and a curator's queue has to be able to hold both without a translation step.

**A gap is not a failure and not a warning.** A failure means the run stops; a
warning is a note on an answer. A gap is a hole in what we were told, carried
alongside an answer that was produced anyway — contract §3.2.4: *never fail a run
over a gap; warned, named, unfulfilled lines instead.* Every gap here is paired
with a `StrategyWarning` so the hole is visible on the drawing, and with a `gap`
node in the decision graph so it is traceable to the line it affected.

The fields are the contract's, unrenamed. Two are BINDING and are the reason the
type is worth having at all:

* `would_close` — one sentence naming what would resolve it. *"a footing row for
  exposure C, non-HVHZ, at 6 ft"* is a work item; *"footing depth is missing"*
  sends a curator hunting.
* `closes_by` — WHO can close it. Two kinds (`unmodellable_entity`,
  `unmapped_part_kind`) close by a schema change in THIS repo and by nothing a
  curator can do, and a review queue that shows a curator work only an engineer
  can perform is a queue whose items are not actionable.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, model_validator

GapKind = Literal[
    "unmodellable_entity",       # the corpus describes something no type fits
    "uncovered_condition",       # a domain point no row covers
    "unsatisfiable_requirement", # nothing can fill a slot
    "unquantified",              # stated in prose, never given a number
    "missing_value",             # a field that should exist and does not
    "unmapped_part_kind",        # a part-kind no counting rule can produce
    "disputed",                  # two admissible readings disagree — carries `on`
    "illegible_source",          # the source states it; we cannot read it
]

# The two kinds a curator cannot close: they need a schema change here.
PLANNING_CLOSES: frozenset[str] = frozenset({"unmodellable_entity", "unmapped_part_kind"})


class EntityRef(BaseModel):
    """§1.1: `EntityRef { kind, id, tenant }` — a thing in the world.

    `kind` is a **str, not a Literal**, and that is v1.2 being obeyed rather than
    laxity: *"`EntityRef.kind` is a closed vocabulary in the registries, on the
    same terms as `TaskCode`, `SourceClass` and `RoleCode`: adding an entry is
    never a breaking change and never an amendment."* A Literal here would make
    every registry addition a code change on this side and a release the other
    team has to wait for — which is the property registry delegation exists to
    prevent.

    It is therefore NOT the same vocabulary as `GapSubject.kind`, and the two must
    not share a field. `GapSubject.kind` is a closed, locale-keyed discriminator
    over the contract's ref union; this is an open registry of entity kinds. They
    were one field until v1.2 gave us the language to separate them.
    """

    kind: str = ""
    id: str
    # §1.1: `TenantId  str | null    null = tenant-agnostic, i.e. Knowledge-global`.
    # `None` and `""` are different facts and both occur, so the type carries both.
    tenant: str | None = None


class GapSubject(BaseModel):
    """WHAT is missing, addressably — the contract's `EntityRef | SlotRef | ParamRef`.

    A discriminated envelope rather than a bare union, because every consumer wants
    the same two things first (which kind, which name) and a three-arm union buys a
    curator queue nothing but three code paths. The structure the union carries is
    kept in full underneath.

    **`slot` is gone, and its absence is the type doing its job.** v1.2 §1.1 marks
    `SlotRef` RESERVED — *"No producer may emit a slot-shaped `Gap.subject` until
    an amendment defines it"* — so the reservation is enforced here rather than
    trusted to every call site. This repo emitted one (`strategy/generator.py`,
    `gap:post_ground`) at the moment of ratification, which is the argument for
    enforcing it in the type: the contract's own survey said we did not.

    **`scope` and `point` are v1.2's `ParamRef`.** A `param` subject naming only
    `max_span_mm` is not addressable: the first real snapshot publishes the SAME
    parameter twice under different `scope.id`s, so a subject without its scope
    names two different holes at once. `point` is structured for the same reason it
    is structured in the contract — a pre-rendered `"exposure_category=D, hvhz=True"`
    cannot be localised, and Hebrew is not a language this system renders English
    fragments into.
    """

    # The closed, locale-keyed discriminator over the contract's ref union. Every
    # value here needs `gaps.subject.<value>` in BOTH bundles
    # (`tests/web/test_locale_bundles.py` derives the key set from this Literal).
    kind: Literal["entity", "param"]
    id: str
    tenant: str | None = None
    # `EntityRef.kind` when this subject IS an entity — the open registry value,
    # carried as data and never used to build a locale key.
    ref_kind: str = ""
    # `ParamRef.scope` — which product or assembly the parameter belongs to.
    scope: EntityRef | None = None
    # `ParamRef.point` — the cell inside the table, or None for the whole table.
    # A dimension's value is a token, a bool, a number — or, on a `range()`
    # dimension, an `Interval` (§1.3, amendment 007). The interval's own shape
    # belongs to the knowledge layer, so it is accepted here as a mapping rather
    # than imported: `core/` describing a `ParameterTable` type would invert the
    # dependency, and a gap only needs to carry the point, not interpret it.
    point: dict[str, str | bool | int | dict] | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_the_contracts_own_union(cls, data):
        """Parse the contract's `EntityRef | ParamRef`, not only our envelope.

        §1.2.1 writes `subject` as a bare UNION — `{kind, id, tenant}` for an
        `EntityRef`, `{parameter, scope, point}` for a `ParamRef`. The envelope
        below, with its `entity | param` discriminator, is OURS: a deliberate
        internal choice so a curator queue gets one shape instead of three code
        paths. It is not what crosses.

        That deviation had a cost we did not see until real data arrived. The
        publisher implemented amendment 004 exactly as ratified and every one of
        their 65 gaps still failed to parse here, because their `kind` carries the
        REGISTRY value (`element`, `source_document`) where ours expects the
        discriminator. Our envelope was reading their open vocabulary as our
        closed one — and the symptom looked like their defect.

        So the mapping happens at the door, once. Structural detection rather
        than a `kind` lookup: `parameter` identifies a `ParamRef` and `ref_kind`
        identifies our own shape round-tripping, so neither depends on a registry
        value happening not to collide with a discriminator word.

        A shape matching neither is left to fail. `snapshot.load()` quarantines a
        gap that will not parse, so an unrecognised subject is reported to the
        sender rather than guessed at — and `SlotRef` is still RESERVED, so there
        is no third arm to add.
        """
        if not isinstance(data, dict):
            return data
        if "parameter" in data:                     # ParamRef (§1.1)
            return {
                "kind": "param",
                "id": data["parameter"],
                "tenant": data.get("tenant"),
                "scope": data.get("scope"),
                "point": data.get("point"),
            }
        if "ref_kind" in data or data.get("kind") in ("entity", "param"):
            return data                             # already our envelope
        if data.get("kind") == "slot":
            # §1.1: `SlotRef` is RESERVED — *"No producer may emit a slot-shaped
            # `Gap.subject` until an amendment defines it."*
            #
            # This branch is here because the mapper above nearly destroyed that.
            # Reading an unrecognised `kind` as a registry value turned
            # `{kind: "slot"}` into an entity with `ref_kind: "slot"` — silently
            # admitting the one shape the contract forbids, through the very
            # function written to accept the contract's shapes. The reservation
            # has to be refused explicitly, not left to fall through a default.
            raise ValueError(
                "SlotRef is RESERVED (§1.1): no producer may emit a slot-shaped "
                "Gap.subject until an amendment defines it"
            )
        if "kind" in data and "id" in data:          # EntityRef (§1.1)
            return {
                "kind": "entity",
                "ref_kind": data["kind"],
                "id": data["id"],
                "tenant": data.get("tenant"),
            }
        return data

    def key(self) -> str:
        """A stable identity for this subject, scope and point included.

        This is what makes two gaps about the same hole recognisable as the same
        hole — which is not a nicety: the first real snapshot publishes 16
        `uncovered_condition` gaps and `expand()` independently derives the same
        16 from `table.uncovered`, so without an identity the ingest reports 32
        holes where there are 16. It is also what a derived gap id is built from,
        after the scope-less version collided 16 rows into 8 ids.
        """
        tenant = self.tenant if self.tenant is not None else "~null"
        if self.kind == "entity":
            return f"entity:{self.ref_kind}/{self.id}@{tenant}"
        scope = f"{self.scope.kind}/{self.scope.id}" if self.scope else "~unscoped"
        # `json.dumps(sort_keys=True)` for a mapping value rather than `repr`:
        # a dict's repr follows insertion order, so two identical intervals
        # parsed from differently-ordered JSON would key differently and the
        # same hole would count twice.
        point = (";".join(
            f"{k}=" + (json.dumps(v, sort_keys=True) if isinstance(v, dict) else repr(v))
            for k, v in ((k, self.point[k]) for k in sorted(self.point)))
                 if self.point else "~whole-table")
        return f"param:{self.id}@{scope}#{point}@{tenant}"


class SourceRef(BaseModel):
    """Evidence, where there is any — contract §1.1, verbatim.

    ```text
    SourceRef    { id, belongs_to }        belongs_to = content_hash -> SourceDoc
    ```

    > **BINDING.** `SourceRef` is opaque to Planning in every respect except
    > `belongs_to`. That one field exists because a source ref resolves only on
    > the Discovery surface, which §3.2.2 forbids Planning from calling during a
    > run — so without it an opaque id carries **zero admissibility bits into a
    > pinned snapshot**, and a run cannot tell that three of a definition's five
    > citations are superseded approvals.

    So `belongs_to` is the whole point of the type and the one field this side is
    allowed to read. `id` is opaque and stays opaque: do not parse it, do not
    build one, do not infer a page number from it.

    A run-produced gap usually cites nothing — the evidence for *"no row covers
    this"* is the absence itself — so `cites` is empty far more often on this
    side than on a published gap. That is exactly why this type has to be right
    anyway: the direction it is NOT exercised in is the direction it will first
    be handed real data.
    """

    id: str
    belongs_to: str = ""  # content_hash -> SourceDoc; "" only where none was given


# A `because` param value. `bool` is listed BEFORE `int` deliberately: a domain
# point's `hvhz: true` is a boolean, and under a `str | int` annotation pydantic
# admits it through the `int` arm and stores `1` — after which the sentence renders
# "hvhz=1" in both languages and the type has silently lost a fact it was handed.
#
# The nested value is `PointValue`, which is itself allowed to be a mapping: since
# amendment 007 a condition on a `range()` dimension is an `Interval`, whose own
# `min`/`max` are `Quantity` objects — so a point is two levels deep, not one. A
# one-level annotation admitted the outer dict and rejected the interval inside it.
PointValue = str | bool | int | dict
ParamValue = str | bool | int | dict[str, PointValue]


class Because(BaseModel):
    """§1.2.1: `because { code, params }` — the ONLY rendering mechanism a `Gap`
    has. A `Gap` carries no `text_raw` the way a quoted `DocumentWarning` does, so
    a free-text `message` beside `because` would compete with it and, per the
    contract's own argument for warnings turned the other way round, become what
    implementations actually display while the locale path rots.

    §1.2.1 places no ceiling on what a param VALUE is, and the first real snapshot
    proves why: a condition point is structurally a mapping, and flattening it to a
    string at the boundary is the same loss `Quantity.value_raw` exists to prevent
    one type over. A renderer that meets a mapping formats it from its parts; it
    must never be handed a pre-joined English fragment to interpolate.
    """

    code: str
    params: dict[str, ParamValue] = {}


class Gap(BaseModel):
    id: str
    kind: GapKind
    # WHICH half of a `disputed` subject is in dispute — required by that kind and
    # meaningless on the other seven, so it is optional here and enforced below.
    #
    # Not a detail to flatten away: the contract records that **33.3% of the
    # platform's human-gated facts** carry a note that readers did not agree on
    # the applicability bracket — *the value is certain and the conditions are
    # not*. Dropping `on` turns that into an undifferentiated "somebody
    # disagreed" and discards the half that says where to look.
    on: Literal["value", "conditions"] | None = None
    subject: GapSubject
    because: Because
    cites: list[SourceRef] = []
    would_close: str
    closes_by: Literal["knowledge", "planning"] = "knowledge"
    severity: Literal["warns_line", "informational"] = "warns_line"

    def model_post_init(self, _ctx) -> None:
        # The one invariant worth enforcing in the type: the two schema-change
        # kinds cannot claim a curator can close them. Getting this wrong is not
        # a rendering bug, it is a work item nobody can action.
        if self.kind in PLANNING_CLOSES and self.closes_by != "planning":
            raise ValueError(
                f"a {self.kind} gap closes by a schema change in Planning, "
                f"not by {self.closes_by}"
            )
        # `disputed{ on: value | conditions }` is how the contract writes it: the
        # discriminator is part of the kind, not an optional embellishment.
        if self.kind == "disputed" and self.on is None:
            raise ValueError("a disputed gap must say what is disputed: value | conditions")
        if self.kind != "disputed" and self.on is not None:
            raise ValueError(f"`on` is meaningless on a {self.kind} gap")
