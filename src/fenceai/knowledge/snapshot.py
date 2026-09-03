"""`Snapshot` — the whole of what Planning receives, and the door it comes in by.

Integration contract §1.2. The type is theirs; what we do with it is ours.

**Nothing has ever been published through this door.** The Knowledge Platform is
still designing, so every field below is the contract's shape rather than
something observed, and `docs/integration-contract/fixtures/` holds a fixture
that is deliberately obviously a fixture. Building against a design before it is
implemented is not speculation — it is the fastest way to tell the designer
whether the design works, which is the argument `docs/superpowers/specs/
2026-08-23-frontend-design.md` §8 already makes for its own step 1. What WOULD be
speculation is treating what we learn here as settled: this file's shapes are a
hypothesis with good tests behind it, and the first real snapshot is what turns
any of it into a fact.

**Only the parts this engine can act on are modelled.** `parameters` becomes
knowledge through `parameters.expand`; `gaps` are carried through as the
contract's own `Gap`; `warnings` are the contract's own `DocumentWarning`, placed
by `report/annexe.py` (obligation 10 and §3.3.5); `parts` and `part_types` are
judged and joined by `knowledge/parts.py` (item 7). The rest — `models`,
`procedures`, `combinations`, `rules` — are accepted, counted and NOT parsed into
private types. A field parsed into a shape we invented is a shape nobody agreed to, and
this repo has already made that mistake once, under the contract's own type name.
They arrive as opaque payloads and are reported as unconsumed, which is an honest
statement of what this engine does with them today.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel

from pydantic import ValidationError

from fenceai.core.dates import Date
from fenceai.core.gaps import Because, Gap, GapSubject
from fenceai.core.warnings import DocumentWarning, warning_errors
from fenceai.knowledge.model import KnowledgeBase, KnowledgeVersion
from fenceai.knowledge.parameters import ParameterTable, expand
from fenceai.knowledge.parts import (
    Part, PartType, PublishedSpec, consume,
)
from fenceai.knowledge.source_docs import SourceDoc
from fenceai.knowledge.source_policy import (
    SHIPPED_DEFAULT, AdmittedBy, SourcePolicyRow,
)

# §1.2 BINDING: a snapshot serves exactly ONE standards regime and declares it.
Regime = Literal["us_astm", "cn_gb"]

# §3.2 obligation 3 — OUR promise, not theirs: "Publish the spine and contract
# versions supported, and refuse a snapshot built against an unknown major —
# loudly, at load, not silently at generate." It was never kept: `contract_version`
# was parsed and read nowhere, so a payload declaring `9.9.9` loaded without a
# word. The cost is not abstract — a pre-v1.2 snapshot carries bare-string dates
# where §1.1 now requires a `Date`, and without this gate that arrives as a heap
# of unlabelled pydantic errors about a field nobody was asking about.
SUPPORTED_CONTRACT_MAJOR = 1

# A minor floor as well as a major one, and the reason is specific rather than
# cautious. The contract's registry rule — additions are never breaking — is why
# a minor difference is normally fine. Amendment 002 was not an addition: it
# changed `valid_from`/`valid_until`/`issue_date`/`expiration_date` from strings
# to `Date`, so a payload cut before v1.2 carries a shape §1.1 now forbids. It
# arrives as a heap of unlabelled type errors about a field nobody was asking
# about, when the actual answer is one sentence: this snapshot predates the type
# and needs a re-cut.
MINIMUM_CONTRACT_MINOR = 2

# What this engine consumes today. Everything else in the payload is carried,
# counted and left alone — see the module docstring.
#
# `source_docs` moved out of CARRIED, and the word it was filed under was wrong
# in a way worth naming: it is not an unimplemented feature. It is the only
# carrier of `version_status`, `source_class`, `issue_date` and `superseded_by` —
# every field a §1.4 candidate needs — and the resolution target of §1.2.1's
# closure rule. Reporting 75 of them as "unconsumed" told the other team we had
# no use for the join their whole provenance model hangs off.
# `part_types` and `parts` left CARRIED when item 7 gave them somewhere to go,
# which is the only honest way for an entry to leave that list. A spec field's
# value is judged against §1.4 and joined to the documents behind it, and
# `part_types` is what `Part.type` resolves against — so a part filed under an
# extension nobody published is now a reported defect rather than an unread
# field. What this engine still cannot do with an admitted value is said out
# loud, per value, as `published_spec_unapplied`.
CONSUMED = ("parameters", "gaps", "warnings", "source_docs",
            "part_types", "parts")
CARRIED = ("models", "procedures", "combinations", "rules")


# §1.2's "sha256 over the canonical member list", with the canonicalisation the
# Knowledge team specified in `conversation.md` T38 — asked in T30 §6, answered in
# full, and this is the first time either side can check a snapshot against its
# own declared id.
#
# The rules, all of them theirs:
#   * these fifteen members, and `retain_until`/`snapshot_id` are NOT among them
#     (the id is computed from the member dict and attached afterwards, so it is
#     never self-referential);
#   * `policy_version` IS inside, as §1.4 requires;
#   * an unpublished member is `[]`, never absent — "declared and empty" reads as
#     a decision where a missing key reads as an oversight;
#   * keys sorted at every depth, so field order in the assembled dict is not
#     part of the identity.
CANONICAL_MEMBERS = (
    "tenant", "regime", "spine_version", "contract_version", "policy_version",
    "source_docs", "warnings", "gaps", "part_types", "parts", "models",
    "procedures", "parameters", "combinations", "rules",
)

# A declared id we will actually check: 64 hex characters. A fixture states
# something like `FIXTURE-not-a-real-snapshot` ON PURPOSE, so that it cannot be
# mistaken for published data — verifying it would be checking a hash nobody
# claimed to have computed.
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_snapshot_id(raw: dict[str, Any]) -> str:
    """The `snapshot_id` a payload's own members imply (§1.2).

    Computed from the RAW document rather than from a parsed `Snapshot`: the hash
    is over the bytes the publisher assembled, and a round trip through our types
    could differ in ways that say nothing about whether the document is intact.
    """
    members = {k: raw.get(k, []) for k in CANONICAL_MEMBERS}
    return hashlib.sha256(json.dumps(
        members, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def snapshot_id_matches(raw: dict[str, Any]) -> bool | None:
    """Whether a payload's declared id matches its members.

    `None` where the declared id is not hash-shaped, which is a fixture saying so
    about itself rather than a failure — see `_SHA256`.
    """
    declared = str(raw.get("snapshot_id") or "")
    if not _SHA256.match(declared):
        return None
    return canonical_snapshot_id(raw) == declared


class SnapshotRefused(ValueError):
    """A snapshot this engine will not load, with a code a caller can branch on.

    Refusing at the door is the whole point (§3.2.3): a snapshot that cannot be
    trusted must not reach `generate()`, where the failure would be a wrong
    number rather than a stopped load.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Snapshot(BaseModel):
    """§1.2, field for field."""

    snapshot_id: str
    # §1.1 `TenantId  str | null` — `null` is tenant-agnostic (Knowledge-global),
    # which is a real and different fact from "a tenant named empty string". As
    # `str` this rejected a conforming Knowledge-global snapshot outright.
    tenant: str | None = None
    spine_version: str = ""
    contract_version: str = ""
    policy_version: str = ""
    retain_until: str = ""
    regime: Regime = "us_astm"

    parameters: list[ParameterTable] = []
    gaps: list[Gap] = []
    # Verbatim, with what each attaches to. Typed rather than carried because
    # placing them is a surface obligation this side owns (§3.3.5): a
    # document-scoped warning goes once into the plan's annexe and never onto a
    # line. A missing `text_raw`, `lang` or `attaches_to` fails to parse HERE,
    # loudly at the door — obligation 3's discipline one type down: a warning
    # accepted without its text is a warning nothing can render, discovered by
    # the reader it was written for.
    warnings: list[DocumentWarning] = []

    # Accepted and NOT parsed. `Any` is the honest type for a payload this engine
    # does not act on: a private model here would be a shape nobody agreed to,
    # and it would look like support.
    # §1.1, typed: the join target of every `SourceRef.belongs_to` in the payload,
    # and the only place a candidate's `issue_date` and `version_status` live.
    source_docs: list[SourceDoc] = []

    # §2.1/§3.1, typed since item 7. `Part.spec` is the second place a number
    # read off a page crosses this boundary, and §2.4 says it has the identical
    # admissibility problem a `ParameterTable` row has — so it is judged by the
    # same policy, through the same `resolve()`, and joined to the same
    # `source_docs`. `part_types` is `Part.type`'s resolution target: without it
    # the parent chain §2.1 makes BINDING cannot be walked.
    part_types: list[PartType] = []
    parts: list[Part] = []

    models: list[Any] = []
    procedures: list[Any] = []
    combinations: list[Any] = []
    rules: list[Any] = []

    def doc_hashes(self) -> set[str]:
        """Every `content_hash` this snapshot brought with it."""
        return {d.content_hash for d in self.source_docs if d.content_hash}

    def dangling_refs(self) -> list[str]:
        """Cited `belongs_to` hashes that resolve to no `SourceDoc` here (§1.2.1).

        > **BINDING.** Every `SourceRef.belongs_to` cited anywhere inside a
        > snapshot resolves to a `SourceDoc` in that snapshot's `source_docs`.

        This is the closure rule that makes `belongs_to` worth anything: §3.2.2
        forbids Planning from calling Discovery during a run, so a dangling ref
        reproduces the defect the field was added to close, with extra fields.
        It is machine-checkable in ten lines and was never checked. The first real
        snapshot passes it — 543 cited refs, 75 distinct hashes, 0 dangling —
        which is the correct outcome for a check on a promise being kept, and no
        reason not to have it.
        """
        known = self.doc_hashes()
        cited: set[str] = set()
        for warning in self.warnings:
            cited |= {c.belongs_to for c in warning.cites if c.belongs_to}
        for gap in self.gaps:
            cited |= {c.belongs_to for c in gap.cites if c.belongs_to}
        for table in self.parameters:
            for row in table.rows:
                cited |= {c.belongs_to for c in row.provenance.cites if c.belongs_to}
        # Parts, both levels. While `parts` arrived as `Any` this check could not
        # see into them, so a published part could cite a document the payload
        # never carried and every closure test still passed. `Part.cites` is the
        # definition's own evidence and a `SpecField`'s is the individual value's;
        # both join to the same `source_docs`, so both are inside the rule.
        for part in self.parts:
            cited |= {c.belongs_to for c in part.cites if c.belongs_to}
            for field in part.spec:
                cited |= {c.belongs_to for c in field.provenance.cites
                          if c.belongs_to}
        return sorted(cited - known)

    def unconsumed(self) -> dict[str, int]:
        """What arrived that this engine does nothing with, by count.

        Reported rather than hidden. A snapshot carrying 40 parts into an engine
        with no part consumer is a fact the operator should be able to see — and,
        while the other team is designing, it is the most useful thing we can
        tell them about their own payload.

        `warnings` left this list when `report/annexe.py` gave them somewhere to
        go, which is the only honest way for an entry to leave it.
        """
        return {name: len(getattr(self, name))
                for name in CARRIED if getattr(self, name)}


class Ingested(BaseModel):
    """What a snapshot became, and everything it could not become.

    `gaps` merges two sources deliberately: the ones the platform PUBLISHED
    (§3.1.8 — "gaps that cannot be expressed are published as gaps, with
    evidence, rather than approximated into a type that nearly fits") and the
    ones expansion DISCOVERED (a row that does not conform to its table's own
    `value_type`, a point no row covers, an authority that lapsed before this
    run's `as_of`). They are the same type by contract, so they are one list —
    but `discovered` counts the second kind, because "your table declares a hole"
    and "your table contradicts itself" are different messages to send back.
    """

    knowledge: KnowledgeBase
    gaps: list[Gap] = []
    # Verbatim, in the order they were published, for `report/annexe.py` to
    # place. NOT merged into `knowledge`: a warning is not a rule — nothing
    # selects between two of them, nothing defeats one, and giving them a
    # `KnowledgeVersion` would put them in front of the evaluator, which is the
    # one place they have no business being.
    warnings: list[DocumentWarning] = []
    # Published warnings this side can carry but not vouch for: params with no
    # code, a document-scoped warning that names a line. English strings, exactly
    # as `validate_model` returns for a curated document, and deliberately NOT
    # gaps — a gap is a hole in what we were told and closes by somebody adding
    # knowledge, while this is a payload that contradicts its own schema and
    # closes by an edit at the sender. Different remedy, different audience.
    warning_defects: list[str] = []
    # Published gaps that could not be parsed as gaps. Same category as
    # `warning_defects` and for the same reason: a payload contradicting its own
    # schema closes by an edit at the sender, not by a curator adding knowledge.
    #
    # They are QUARANTINED rather than dropped and rather than fatal, which is a
    # deliberate third option. Failing the load loses 4 valid tables and 289
    # warnings over gap-shape drift; dropping them silently puts a hole in the
    # one list whose completeness is the entire promise (§3.2.4 — every
    # never-block promise terminates in a gap). Carrying the count keeps "we were
    # told 81 things and could parse none of them" a visible fact.
    gap_defects: list[str] = []
    # Derived gaps suppressed because the publisher already declared the same
    # hole. Counted, because "your table declares a hole" and "we found the same
    # hole ourselves" are one work item, not two.
    deduped: int = 0
    discovered: int = 0
    # Published spec values, judged and joined (item 7). NOT merged into
    # `knowledge` and the reason is the same one that keeps warnings out of it: a
    # parameter row is a rule about a fence and belongs in front of the
    # evaluator, while a spec field is a fact about an ITEM. Giving it a
    # `KnowledgeVersion` would put two kinds of thing on one precedence ladder
    # where nothing selects between them.
    part_specs: list[PublishedSpec] = []
    # Parts whose shapes contradict their own schema, and parts this engine
    # cannot file. Authoring text, same audience and same convention as
    # `warning_defects` and `gap_defects`: an edit at the sender, not a curator's
    # queue.
    part_defects: list[str] = []
    # Published parts not consumed because their `status` is not `active`.
    inactive_parts: list[str] = []
    unconsumed: dict[str, int] = {}
    snapshot_id: str = ""
    regime: Regime = "us_astm"


def load(raw: dict[str, Any]) -> tuple[Snapshot, list[str]]:
    """A published payload, at the door — version-gated, gaps quarantined.

    Two things happen here that `Snapshot.model_validate` cannot do alone.

    **The version gate (§3.2 obligation 3).** Refuse an unknown MAJOR loudly,
    here, rather than silently at generate. A minor difference is admissible by
    design — the contract's own registry rule is that additions are never
    breaking — so a v1.1 payload loads, and if its rows carry a shape v1.2
    retired it fails on that, with the version already named.

    **Gap quarantine.** One malformed gap must not cost the whole snapshot. The
    first real snapshot is exactly this case: 81 gaps carrying a bare-string
    `subject`, against 4 valid parameter tables and 289 valid warnings. Each gap
    is validated on its own and the failures come back as authoring text for the
    sender — never dropped, never fatal.
    """
    payload = dict(raw)
    declared = str(payload.get("contract_version") or "")
    if declared:
        parts = declared.split(".")
        major = parts[0]
        if not major.isdigit() or int(major) != SUPPORTED_CONTRACT_MAJOR:
            # `code=` rather than positional, so the literal is in the form
            # `tests/web/test_locale_bundles.py` can find. It scans for
            # `code="..."` at the raise site, and a code it cannot read is a code
            # that reaches a person with no sentence in either bundle.
            raise SnapshotRefused(
                code="contract_major_unsupported",
                message=f"snapshot declares contract_version {declared!r}; this engine "
                f"speaks {SUPPORTED_CONTRACT_MAJOR}.x. Refused at load rather "
                f"than at generate (§3.2 obligation 3)",
            )
        minor = parts[1] if len(parts) > 1 and parts[1].isdigit() else "0"
        if int(minor) < MINIMUM_CONTRACT_MINOR:
            raise SnapshotRefused(
                code="contract_minor_predates_typed_date",
                message=f"snapshot declares contract_version {declared!r}. §1.1's typed "
                f"`Date` has been BINDING since v1.2 (amendment 002), and this "
                f"payload predates it — its `issue_date`, `expiration_date`, "
                f"`valid_from` and `valid_until` are bare strings. It needs a "
                f"re-cut, not a parser on this side: normalising "
                f"'05/04/2023' here would manufacture a fact the source does "
                f"not state",
            )

    # §1.2.1: a snapshot fetched by hash resolves to the same bytes. Now that the
    # canonicalisation is agreed (T38), a mismatch is checkable rather than a
    # thing we hoped about — and it means the document changed between the
    # publisher hashing it and us reading it, which no downstream check would
    # notice because every field would still be individually well-formed.
    if snapshot_id_matches(payload) is False:
        raise SnapshotRefused(
            code="snapshot_id_mismatch",
            message=(
                f"this payload's members hash to "
                f"{canonical_snapshot_id(payload)} but it declares "
                f"{payload.get('snapshot_id')!r}. The document is not the one "
                f"that id names."
            ),
        )

    gaps, defects = [], []
    for index, item in enumerate(payload.get("gaps") or []):
        try:
            gaps.append(item if isinstance(item, Gap) else Gap.model_validate(item))
        except ValidationError as exc:
            # English, uncoded, addressed to the person holding the payload —
            # `validate_model`'s convention for authoring text, and the same
            # audience `warning_defects` has.
            reasons = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()[:3])
            defects.append(f"published gap {index}: {reasons}")
    payload["gaps"] = gaps
    return Snapshot.model_validate(payload), defects


def ingest(
    snapshot: Snapshot, *, as_of: str = "", gap_defects: list[str] | None = None,
    policy: list[SourcePolicyRow] | None = SHIPPED_DEFAULT,
) -> Ingested:
    """A published snapshot, as knowledge this engine already knows how to use.

    Every parameter table expands into ordinary `KnowledgeVersion`s through the
    existing loader, so published rows resolve beside authored ones in the one
    evaluator, at their own authority, with the same precedence and the same
    conflict reporting. That is the whole design: there is no second selection
    path, and a published table needs no privileged channel into the generator.

    `as_of` is the run's pinned date (obligation 16). Passed in, never read from
    a clock: generation is a pure function, and a clock here would make the same
    project against the same snapshot warn differently on different days.
    """
    versions: list[KnowledgeVersion] = []
    discovered: list[Gap] = []
    admitted: dict[str, AdmittedBy] = {}
    colliding: set[str] = set()
    # §1.4's third criterion needs a document's own `issue_date`, and that lives
    # only on `SourceDoc`. Indexed once here rather than resolved per row: the
    # join is snapshot-level (§1.2.1's closure rule), and `expand()` needs exactly
    # this one field from it — everything else a candidate is built from is on the
    # row's own `Provenance`.
    issue_dates = {d.content_hash: d.issue_date
                   for d in snapshot.source_docs
                   if d.content_hash and d.issue_date is not None}
    # The same join, kept WHOLE for parts rather than shredded to one field:
    # `parts.consume` resolves a spec field's citations to the documents
    # themselves, because the question it answers for a reviewer is *"which
    # documents is this value leaning on"* and a date alone cannot answer it.
    docs = {d.content_hash: d for d in snapshot.source_docs if d.content_hash}
    for table in snapshot.parameters:
        expanded, gaps, table_admitted = expand(
            table, as_of=as_of, tenant=snapshot.tenant,
            policy=policy, issue_dates=issue_dates,
        )
        versions.extend(expanded)
        discovered.extend(gaps)
        # A ref appearing from TWO tables cannot be attributed. `_object_id` is
        # parameter + scope + row index, which is unique within a table and not
        # across them: two unscoped tables for one parameter produce the same ref
        # for their row 0. A blind `update()` then let the second table's verdict
        # describe the first table's number — printing "backed by a spec sheet"
        # about a value that came from a sealed approval, which is a false
        # provenance claim rendered as fact.
        #
        # So a collision drops BOTH verdicts and reports it. Claiming neither is
        # the only honest option: we cannot tell which document backed which
        # number, and picking one would be inventing the answer.
        for ref, verdict in table_admitted.items():
            if ref in admitted and admitted[ref] != verdict:
                admitted.pop(ref)
                colliding.add(ref)
            elif ref not in colliding:
                admitted[ref] = verdict

    # A hole the publisher already declared is not a second hole. The first real
    # snapshot publishes all 16 of its `condition_point_uncovered` gaps AND
    # `table.uncovered` carries the same 16 points, so `expand()` independently
    # derives every one of them — 32 gaps for 16 holes, each appearing twice in a
    # curator's queue. `GapSubject.key()` is what makes them recognisable as the
    # same hole: parameter, scope and point together. That identity is exactly
    # what v1.2's `ParamRef` added, which is the argument for having implemented
    # it rather than widening `id` to a longer string.
    # What this run declined to trust, gathered from the refusals themselves so
    # there is no second channel and no chance of the two disagreeing.
    declined: dict[str, list[int]] = {}
    # Item 7. The parts path is deliberately NOT a second selection mechanism:
    # it judges each published spec value's own citations and stops there, the
    # way `_judge` scopes strictly into a parameter row. Its gaps join
    # `discovered` so they get the same dedup against what the publisher already
    # declared, and so "our findings about their data" stays one list.
    parts = consume(snapshot.parts, snapshot.part_types,
                    docs=docs, policy=policy)
    discovered.extend(parts.gaps)

    for gap in discovered:
        value = gap.because.params.get("declined_mm")
        name = gap.because.params.get("parameter")
        if isinstance(value, int) and not isinstance(value, bool) and isinstance(name, str):
            declined.setdefault(name, []).append(value)

    for ref in sorted(colliding):
        discovered.append(Gap(
            id=f"gap:ambiguous_version_ref:{ref}",
            kind="unmodellable_entity",
            subject=GapSubject(kind="param", id=ref.rsplit("@v", 1)[0],
                                tenant=snapshot.tenant),
            because=Because(code="ambiguous_version_ref",
                             params={"knowledge_ref": ref}),
            would_close=(f"an identity that distinguishes the two published rows "
                         f"resolving to {ref}, so each number can name the "
                         f"document behind it"),
            closes_by="planning", severity="warns_line",
        ))

    published_keys = {g.subject.key() for g in snapshot.gaps}
    kept = [g for g in discovered if g.subject.key() not in published_keys]

    return Ingested(
        knowledge=KnowledgeBase(versions=versions, admitted=admitted,
                                declined=declined),
        warnings=list(snapshot.warnings),
        # The closure rule gives `warning_errors` the one thing it needs to judge
        # an annexe-scoped ref: the documents that actually came with the payload.
        warning_defects=warning_errors(snapshot.warnings, where="published",
                                        known_docs=snapshot.doc_hashes()),
        # published first: they are what the other side chose to tell us, and a
        # reader scanning the list should meet those before our findings about
        # their data
        gaps=[*snapshot.gaps, *kept],
        gap_defects=list(gap_defects or []),
        deduped=len(discovered) - len(kept),
        discovered=len(kept),
        part_specs=parts.specs,
        part_defects=parts.defects,
        inactive_parts=parts.inactive,
        unconsumed=snapshot.unconsumed(),
        snapshot_id=snapshot.snapshot_id,
        regime=snapshot.regime,
    )


def fixture_digest(snapshot: Snapshot) -> str:
    """A self-consistency digest over this snapshot's `parameters`.

    **This is NOT the contract's `snapshot_id` and cannot verify one.** It was
    named `snapshot_id_for` and its docstring called it "the one property of a
    snapshot this side can verify without trusting the sender" — which was wrong
    in a way that would have been read as drift the first time anyone gated on
    it. §1.2 says `snapshot_id` is a sha256 over the canonical member list, and
    §1.4 adds that `policy_version` is part of it; this hashes `parameters`
    alone, and against the first real snapshot returns `0bd95701…` where the
    payload declares `3ae88642…`. It never agreed with a real publisher and never
    could.

    What it is good for is what the tests actually use it for: catching a fixture
    that changed underneath a test.

    **It is not made redundant by `canonical_snapshot_id`**, which does verify a
    real snapshot against its declared id. That one deliberately exempts an id
    that is not hash-shaped, and our fixture declares `FIXTURE-…` on purpose so
    it cannot be mistaken for published data — so the fixture is exactly the case
    real verification cannot cover. Two functions, two jobs; do not collapse them. The real question — how the publisher
    canonicalises — is a registry-level conversation to have with them, not an
    amendment, and is recorded in `docs/reviews/`.
    """
    members = json.dumps(
        [t.model_dump(mode="json") for t in snapshot.parameters],
        sort_keys=True, default=str,
    )
    return hashlib.sha256(members.encode()).hexdigest()
