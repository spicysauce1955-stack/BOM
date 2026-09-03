"""A published `Part`, its `SpecField`s, and the verdict a run reaches on each.

Build-order item 7 — obligation 6's other half. The `ParameterTable` side of
this has been live since `parameters.py` learned §1.4; a `SpecField` is the
other place a number read off a page crosses the boundary, and
`knowledge-datamodel.md` §2.4 is explicit that it has the identical problem:

> a Chesterfield rail length is `derived`, marketing-grade OCR, or PE-sealed
> depending on which of the eleven documents it came from — exactly the same
> admissibility problem as a parameter row.

Three things happen here and nothing else does.

**The join (§1.2.1).** Every `SourceRef.belongs_to` on a spec field's
provenance is resolved to the `SourceDoc` that came with the same snapshot. That
is not decoration: §1.4's third criterion is the document's `issue_date`, which
lives nowhere else, and §3.2.2 forbids calling Discovery during a run — so
without the join an opaque citation carries no admissibility bits at all.

**The judgement (§1.4).** Each field's own citations compete through
`source_policy.resolve()`, exactly as a parameter row's do, scoped strictly
INSIDE the field: this answers *"which of this value's citations admits it, and
at what rank"*, never *"which value wins"*. Two mechanisms selecting between
facts is the failure the knowledge design exists to avoid.

**The honest report of what we still cannot do.** A judged value with a
resolvable citation reaches no bill of materials, because nothing in this engine
can say which catalog product a published `Part` is. That gap is emitted rather
than implied — `published_spec_unapplied`, the same call
`parameter_hit_policy_unsupported` makes: the publisher is correct, the missing
mechanism is ours, and the `would_close` names the work. (The analogy used to
name `parameter_paired_unsupported`, which is retired: amendment 006 gave
`paired` rows a shape and `parameters.py` now binds both columns. That is the
outcome this code is waiting for, and a retired sibling makes a poor landmark.)

**What is deliberately absent.** No spec value becomes a `KnowledgeVersion`. A
parameter row is a rule about a fence and belongs in front of the evaluator; a
spec field is a fact about an ITEM, and giving it a version would put two kinds
of thing on one precedence ladder where nothing selects between them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator

from fenceai.core.dates import Date
from fenceai.core.gaps import Because, Gap, GapSubject, SourceRef
from fenceai.knowledge.parameters import (
    KNOWN_SOURCE_CLASSES, Provenance, Quantity, Token,
)
from fenceai.knowledge.source_docs import SourceDoc
from fenceai.knowledge.source_policy import (
    AdmittedBy, Candidate, SourcePolicyRow, TaskCode, explain_rejection, resolve,
)

# §2.1's spine, verbatim: *"The ten to start: `post`, `post_cap`, `rail`, `bar`,
# `infill`, `reinforcement`, `bracket`, `fastener`, `anchor`, `gate_hardware`."*
#
# Held HERE rather than delegated, because §2.1 says the `shared` namespace is
# Planning's to extend and the contract's registry table says the same: *"Roles
# | Spine: Planning. Extensions: Knowledge."* A published extension's parent
# chain has to terminate in this set, so this set is the one thing in the filing
# vocabulary that cannot be data.
SPINE: frozenset[str] = frozenset({
    "post", "post_cap", "rail", "bar", "infill", "reinforcement",
    "bracket", "fastener", "anchor", "gate_hardware",
})

# §2.1: *"Plus `site_material`, reserved and unimplemented — concrete and gravel
# are out of scope for now, and the id is held so it cannot be reused."*
#
# Reserved is not the same as absent, and both readings would be wrong: treating
# it as a spine key admits parts this engine cannot place, and treating it as
# unknown would let somebody re-use the id for something else. It resolves, and
# it resolves to "not implemented".
RESERVED_SPINE: frozenset[str] = frozenset({"site_material"})

# §2.2's own agreement vocabulary. `supplies` is the one that carries no value.
Agreement = Literal["==", "!=", "<=", ">=", "in", "supplies"]


class PartTypeRef(BaseModel):
    """§2.1 — a part type named by `(namespace, key)`.

    `namespace` defaults to `shared` because a bare spine key is what a `Part`
    in the negotiated vocabulary carries, and defaulting to anything else would
    silently file a spine part under an extension.
    """

    key: str
    namespace: str = "shared"

    def ref(self) -> str:
        return f"{self.namespace}/{self.key}"


class PartType(BaseModel):
    """§2.1, field for field. `parent` is `null` only for a spine key itself."""

    key: str
    namespace: str
    parent: PartTypeRef | None = None
    label_i18n: dict[str, str] = {}

    def ref(self) -> str:
        return f"{self.namespace}/{self.key}"


class SpecField(BaseModel):
    """§2.2 — one cell of what a part IS, with the provenance of that claim.

    `value: Quantity | Token` is C15 as settled (`conversation.md` T41/T42/T43,
    no amendment: the type is not in `contract.md` and §1.2 delegates it). The
    union is discriminable by shape — `amount_milli` against `key` — so unlike a
    `ParameterTable` a single cell needs no `value_type` declaration beside it.

    `None` is admissible because §2.2 says `agree = supplies` carries no value;
    a valued agreement arriving without one is a payload defect, reported by
    `consume` rather than refused here, so one malformed field cannot cost a
    whole snapshot.
    """

    key: str
    agree: Agreement = "=="
    value: Quantity | Token | None = None
    provenance: Provenance = Provenance()


class Part(BaseModel):
    """§3.1. A part says what the piece IS — never where it goes."""

    id: str
    version: int = 1
    status: Literal["draft", "active", "retired"] = "active"
    type: PartTypeRef
    name_i18n: dict[str, str] = {}
    spec: list[SpecField] = []
    # An open vocabulary on their side (`third_party_authored` is what the real
    # payload carries) and nothing this engine acts on. `str`, therefore, rather
    # than a Literal that would turn their next value into our load failure.
    authorship: str = ""
    cites: list[SourceRef] = []
    # §1.2.1 calls this a ROLL-UP — *"for the reviewer's benefit; the join
    # itself is snapshot-level"*. Only the join key is kept: `source_docs` is the
    # authority, and a second copy of a document's fields here would be a second
    # authority over the same facts.
    contributing_sources: list[str] = []

    @field_validator("contributing_sources", mode="before")
    @classmethod
    def _accept_a_hash_or_a_document(cls, value: Any) -> Any:
        """`knowledge-datamodel.md` §3.1 writes `[SourceDoc]`; the real payload
        sends content hashes. Both are accepted, and the reason is T42 §5: three
        shapes the contract permits have now been rejected by a narrower type of
        ours, each time with the symptom pointing at the sender.
        """
        if not isinstance(value, list):
            return value
        return [item.get("content_hash", "") if isinstance(item, dict)
                else getattr(item, "content_hash", item)
                for item in value]


class PublishedSpec(BaseModel):
    """One published spec value, judged and joined.

    `admitted_by` is a RUN's answer and never read off published data (§1.4),
    which is why `Provenance` has no field for it. `sources` is the join — the
    documents this value actually leans on, in the order the payload cited them,
    so a reviewer sees what backs it rather than an opaque id.
    """

    part_id: str
    part_type: str
    key: str
    agree: Agreement
    task: TaskCode
    value: Quantity | Token
    admitted_by: AdmittedBy
    sources: list[SourceDoc] = []


class Consumed(BaseModel):
    """What a snapshot's parts became, and everything they could not become.

    `defects` is authoring text in the convention `warning_defects` and
    `gap_defects` already follow: English, uncoded, addressed to whoever holds
    the payload. A payload contradicting its own schema closes by an edit at the
    sender, not by a curator adding knowledge — different remedy, different
    audience, so it must not be a `Gap`.

    `inactive` names the parts whose `status` is not `active`. Counted rather
    than dropped for the reason every other count here exists: "we were sent
    eleven definitions and used nine" is a fact somebody may need to see.
    """

    specs: list[PublishedSpec] = []
    gaps: list[Gap] = []
    defects: list[str] = []
    inactive: list[str] = []


def task_for(field: SpecField) -> TaskCode:
    """Which §1.4 task a spec field's value is being used FOR.

    §1.4 is BINDING that Planning applies the source policy *"because
    admissibility depends on the task a value is being used for, and only the
    planner knows the task"*. A `SpecField` carries no task — so this is the
    named seam where that judgement is made, and it is deliberately a function
    of the value's SHAPE rather than a lookup table of field keys.

    A `Quantity` is a measurement of a component: `component_dimension`, which
    is the row the shipped default table already has for exactly this. Anything
    else is a `Token` — a colour, a finish, a texture — which is a
    `product_description`, and judging a brochure's word for a colour against
    the bar for a measurement would refuse a fact that was never a measurement.

    A key-based table was the alternative and is worse: it would need an entry
    per registry addition on their side, so a new spec key would arrive
    unjudgeable rather than judged by what it carries.
    """
    return "component_dimension" if isinstance(field.value, Quantity) \
        else "product_description"


def _subject(part: Part, field: SpecField) -> GapSubject:
    """The gap's subject: the PART, as the contract's own `EntityRef`.

    An entity rather than a `ParamRef`, and the distinction is not cosmetic — a
    `param` subject is a cell in a parameter table, and a curator sent to one
    for a rail's published length would go looking for a table that does not
    exist. `ref_kind` carries the open registry value (`part`); the field is
    named in `because.params`, where a renderer can put it in a sentence.
    """
    return GapSubject(kind="entity", ref_kind="part", id=part.id)


def _candidates(field: SpecField, docs: dict[str, SourceDoc]) -> list[Candidate]:
    """One field's citations, as competing candidates — `_candidates_for`'s twin.

    The axes come from the field's own `Provenance` (one class, one level, one
    status, per §2.4) and the DATE comes from the document, which is the half
    only the join can supply.

    A field with no citations still yields one candidate, from what it does
    carry. Obligation 3 makes an uncited value a payload defect, but refusing to
    judge it would make it MORE admissible than a cited one, which is backwards.
    """
    prov = field.provenance
    hashes = [c.belongs_to for c in prov.cites if c.belongs_to] or [""]
    return [
        Candidate(
            source_class=prov.source_class,          # type: ignore[arg-type]
            version_status=prov.version_status,
            curation_level=prov.curation_level,
            content_hash=content_hash,
            label=content_hash,
            issue_date=_issue_date(docs.get(content_hash)),
        )
        for content_hash in hashes
    ]


def _issue_date(doc: SourceDoc | None) -> Date | None:
    return doc.issue_date if doc is not None else None


def _rejected_gap(part: Part, field: SpecField, code: str) -> Gap:
    """A spec value the policy refused, and what would let it be used.

    The two codes are `parameters.py`'s, reused deliberately: the fact is the
    same fact — a value this run declined to lean on, and why — and a second
    pair of codes would mean two sentences to keep in step for one distinction
    that is already drawn. `parameter` carries the spec key, which is what the
    shipped sentence interpolates, and `part` is added beside it so a reader
    knows which definition the field belongs to.
    """
    prov = field.provenance
    params: dict[str, str | int] = {
        "part": part.id, "parameter": field.key, "task": task_for(field),
        "source_class": prov.source_class, "curation_level": prov.curation_level,
    }
    if isinstance(field.value, Quantity) and field.value.value_raw:
        params["declined_raw"] = field.value.value_raw[0]
    # Literals, not the variable `code` — `tests/web/test_locale_bundles.py`
    # finds an emitted code by scanning for `code="..."` at the emitting site,
    # and a code arriving as a variable is invisible to it.
    if code == "source_below_min_curation":
        because = Because(code="source_below_min_curation", params=params)
        would_close = (
            f"a reviewer confirming {part.id}'s {field.key} against the source "
            f"image, raising it to the curation level the policy asks for"
        )
    else:
        because = Because(code="source_inadmissible", params=params)
        would_close = (
            f"a {field.key} for {part.id} from a source class the policy admits "
            f"for {task_for(field)} — {prov.source_class or 'this field’s class'} "
            f"is not one"
        )
    return Gap(
        id=f"gap:{code}:{part.id}#{field.key}",
        kind="missing_value",
        subject=_subject(part, field),
        because=because,
        cites=list(prov.cites),
        would_close=would_close,
        closes_by="knowledge", severity="warns_line",
    )


def _unrecognised_class_gap(part: Part, field: SpecField) -> Gap:
    """A class our own registry has no row for — so nothing judged this value.

    Not a refusal: §2 makes a registry addition a non-breaking change, so an
    unregistered class may not fail a load. But a value nobody judged has to say
    so, or it is indistinguishable from one that passed.
    """
    return Gap(
        id=f"gap:source_class_unrecognised:{part.id}#{field.key}",
        kind="missing_value",
        subject=_subject(part, field),
        because=Because(code="source_class_unrecognised",
                         params={"part": part.id, "parameter": field.key,
                                 "source_class": field.provenance.source_class}),
        cites=list(field.provenance.cites),
        would_close=(f"a source-policy row in the Planning repo for "
                     f"{field.provenance.source_class or 'this class'}, so "
                     f"{part.id}'s {field.key} can be judged rather than carried"),
        closes_by="planning", severity="warns_line",
    )


def _unapplied_gap(spec: PublishedSpec) -> Gap:
    """An admitted value this engine holds and cannot yet use.

    Emitted for every admitted value, and that is the point rather than an
    oversight: there is no mechanism at all — no product in this catalog can
    claim to be a published `Part` — so an operator told "2 values admitted"
    would otherwise reasonably believe the plan had changed.

    Same kind and `closes_by` as `parameter_hit_policy_unsupported`, for the same
    reason: the publisher is correct, the missing piece is ours, and refusing to
    say so is how a hypothesis becomes a fact nobody checked. (Was
    `parameter_paired_unsupported`, retired once amendment 006 gave paired rows
    a shape this engine binds.)
    """
    return Gap(
        id=f"gap:published_spec_unapplied:{spec.part_id}#{spec.key}",
        kind="unmodellable_entity",
        subject=GapSubject(kind="entity", ref_kind="part", id=spec.part_id),
        because=Because(code="published_spec_unapplied",
                         params={"part": spec.part_id, "parameter": spec.key,
                                 "part_type": spec.part_type}),
        would_close=(f"a catalog product in the Planning repo declaring which "
                     f"published Part it is, so {spec.part_id}'s {spec.key} "
                     f"reaches the cut plan instead of stopping here"),
        closes_by="planning", severity="informational",
    )


def _file_type(
    ref: PartTypeRef, published: dict[str, PartType],
) -> str | None:
    """Walk a part type's parent chain to the spine — or say why it does not end
    there (§2.1 BINDING).

    Returns authoring text on failure, `None` when the chain terminates in the
    spine. Three distinct failures, because they send different work to
    different people: a chain ending nowhere (they publish the missing
    `PartType`), a chain ending in the reserved id (a scope decision nobody has
    made), and a cycle (a payload that cannot be walked at all).

    The cycle guard is not defensive dressing: without it a payload — theirs to
    build, not ours to trust — hangs the load instead of reporting a defect.
    """
    seen: set[str] = set()
    at: PartTypeRef | None = ref
    while at is not None:
        key = at.ref()
        if key in seen:
            return (f"part type {key} is in a parent-chain cycle, so §2.1's "
                    f"\"terminates in the shared spine\" cannot be checked")
        seen.add(key)
        if at.namespace == "shared" and at.key in SPINE:
            return None
        if at.namespace == "shared" and at.key in RESERVED_SPINE:
            return (f"part type {key} is RESERVED and unimplemented (§2.1): the "
                    f"id is held so it cannot be re-used, and nothing here can "
                    f"place a part filed under it")
        published_type = published.get(key)
        if published_type is None:
            return (f"part type {key} is neither a shared spine key nor a "
                    f"PartType published in this snapshot, so §2.1's parent "
                    f"chain cannot be followed to the spine")
        at = published_type.parent
    return (f"part type {ref.ref()}'s parent chain ends at a type with no "
            f"parent that is not a spine key")


def _class_disagreement(
    part: Part, field: SpecField, sources: list[SourceDoc],
) -> list[str]:
    """A field claiming one `source_class` while its cited document states
    another — the check only the join makes possible.

    Reported, not refused, and the value is judged on the field's own claim.
    `knowledge-datamodel.md` §2.5 records the honest reason a mismatch may be
    legitimate rather than false: one SHA-256 filed four times under four
    manufacturers has four `source_class` values, and `belongs_to` names one of
    them. Resolving those groups is on their list (§8, N-obs-1). Ours is to make
    the disagreement visible, because the alternative — silence — lets a payload
    upgrade its own admissibility by claiming a class its document does not have.
    """
    claimed = field.provenance.source_class
    if not claimed:
        return []
    return [
        f"{part.id} spec {field.key}: provenance claims source_class "
        f"{claimed!r} but cited document {doc.content_hash[:12]}… states "
        f"{doc.source_class!r}"
        for doc in sources
        if doc.source_class and doc.source_class != claimed
    ]


def consume(
    parts: list[Part], part_types: list[PartType], *,
    docs: dict[str, SourceDoc],
    policy: list[SourcePolicyRow] | None,
) -> Consumed:
    """Every published spec value, judged against the documents behind it.

    `docs` is the snapshot's `source_docs` keyed by `content_hash` — §1.2.1's
    closure rule is what makes that a complete index, and a citation resolving
    to nothing here is reported once, snapshot-wide, by
    `Snapshot.dangling_refs()` rather than a second time per field.

    `policy=None` means no judgement was asked for, matching `expand()`: the
    parts are still filed and their shapes still checked, and no verdict is
    invented.
    """
    published = {t.ref(): t for t in part_types}
    out = Consumed()

    for part in parts:
        defect = _file_type(part.type, published)
        if defect is not None:
            out.defects.append(f"{part.id}: {defect}")

        if part.status != "active":
            # Judging a draft would put a value nobody published behind a
            # verdict that reads exactly like a published one.
            out.inactive.append(part.id)
            continue

        for field in part.spec:
            out.defects.extend(_shape_defects(part, field))
            if field.value is None:
                continue
            if field.agree == "supplies":
                continue

            sources = [docs[c.belongs_to] for c in field.provenance.cites
                       if c.belongs_to in docs]
            out.defects.extend(_class_disagreement(part, field, sources))

            if policy is None:
                continue
            if field.provenance.source_class not in KNOWN_SOURCE_CLASSES:
                out.gaps.append(_unrecognised_class_gap(part, field))
                continue

            task = task_for(field)
            candidates = _candidates(field, docs)
            resolution = resolve(policy, task, candidates)
            if resolution.winner is None:
                # Every citation failed. They share the field's class, level and
                # status, so they fail for the same reason — the first explains
                # all of them.
                code = explain_rejection(policy, task, candidates[0])
                out.gaps.append(_rejected_gap(part, field, code or ""))
                continue

            spec = PublishedSpec(
                part_id=part.id, part_type=part.type.ref(), key=field.key,
                agree=field.agree, task=task, value=field.value,
                admitted_by=resolution.winner, sources=sources,
            )
            out.specs.append(spec)
            out.gaps.append(_unapplied_gap(spec))

    return out


def _shape_defects(part: Part, field: SpecField) -> list[str]:
    """§2.2's own two rules about a value, checked at the door.

    Authoring text rather than gaps, and non-fatal rather than refused: one
    malformed field must not cost a snapshot its nine valid parameter tables,
    and the remedy is an edit at the sender either way.
    """
    if field.agree == "supplies" and field.value is not None:
        return [f"{part.id} spec {field.key}: `agree: supplies` carries no value "
                f"(§2.2) — that rule is about a CUT length and compiles to "
                f"`item.stock_length_mm >= 0`, so a value here states something "
                f"the field cannot mean"]
    if field.agree != "supplies" and field.value is None:
        return [f"{part.id} spec {field.key}: `agree: {field.agree}` needs a "
                f"value; only `supplies` carries none (§2.2)"]
    return []
