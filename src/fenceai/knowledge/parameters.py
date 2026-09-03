"""`ParameterTable` — how conditional knowledge crosses the boundary, and lands.

Integration contract §1.3, and the shapes in §1.1. **These are the contract's
types, so they are not ours to redesign**: the last time this repo defined a
boundary type from memory it invented a `SourceRef` with the wrong fields under
the contract's own name, which is precisely the defect its BINDING clause exists
to close.

A value such as maximum post spacing is not one number — it depends on conditions
known only when a site is planned. The platform publishes the whole small table
and Planning evaluates it at run time against that project's conditions.

**The expansion is the design.** A table becomes ordinary `KnowledgeVersion`s,
one per row, whose `condition` reads the namespace that row's keys are scoped to.
The existing evaluator then resolves them beside everything else, at their own
authority, with the same precedence and the same conflict reporting. There is no
second selection path and no second rule engine — which is the property the whole
knowledge design is built on, and the reason a published table needs no privileged
channel into the generator.

That also satisfies obligation 13 without a scheduler: *keys that are all `site`
or `param` resolve at snapshot expansion; narrower keys expand up front and bind
at their own scope*. A row conditioned on `post.role` becomes a rule conditioned
on `post.role`, expanded now and selected when a post exists.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel

from fenceai.core.dates import Date, is_iso_date, precedes
from fenceai.core.gaps import Because, EntityRef, Gap, GapSubject, SourceRef
from fenceai.knowledge.ast import And, Cmp, Expr, FieldRef, Lit
from fenceai.knowledge.model import KnowledgeVersion, SetParam, SetToken
from fenceai.knowledge.source_policy import (
    AdmittedBy, Candidate, SourceClass, SourcePolicyRow, TaskCode,
    explain_rejection, resolve,
)
# `strategy.choices` is a pure leaf over `core.units` and imports nothing from
# here, so this is a one-way edge rather than a cycle. `DesignPoint` is not
# duplicated for the knowledge layer's convenience: a paired row's alternatives
# and a gap's alternative bay widths are the same concept measured on different
# axes, and two types for it is how one of them silently stops carrying a lexeme.
from fenceai.strategy.choices import DesignPoint

# The two §1.4 vocabularies this engine's policy is written against. A published
# table may name a value in either that we have not registered yet, and BOTH are
# registries the contract guarantees can grow without an amendment (§2):
#
#   "Registry additions are not amendments — new part types, warning codes,
#    condition dimensions and source classes need no ratification."
#
# So an unregistered value must never fail a load. `Candidate.source_class` and
# `task` are closed `Literal`s in the policy module — correctly, since the policy
# is a table over known axes — and handing them an unregistered value raises a
# raw `ValidationError` that takes down the whole snapshot. §1.4 itself records
# that two source classes were ADDED in its last revision, so this is the
# expected case, not a hypothetical.
#
# `_judge` therefore checks both and declines to judge, and `expand()` raises a
# gap saying so. Used-and-flagged, not refused: a hole in our registry is not a
# defect in their data.
KNOWN_TASKS: frozenset[str] = frozenset(get_args(TaskCode))
KNOWN_SOURCE_CLASSES: frozenset[str] = frozenset(get_args(SourceClass))

# The hit policies this engine can actually honour. `unique` is a CLAIM about the
# condition space ("these rows are disjoint") which `_overlap_gaps` checks and the
# evaluator reports as a `Conflict` when it is false — so consuming it changes no
# arithmetic. The other three change WHICH number comes out: `collect_min` over
# rows of 1000 and 2000 must yield 1000, and expanding them into ordinary rules
# yields whichever fires first. A table whose policy we cannot honour is refused
# with a gap, on exactly the argument `_scope_for` already makes about a scope we
# cannot aim: producing a confident wrong number is worse than producing none.
SUPPORTED_HIT_POLICIES = frozenset({"unique"})

# §1.1. `mm` is the only unit this engine stores at rest, so it is the only one
# the loader can land today — the rest are accepted, declared, and refused with a
# gap rather than silently converted through a factor nobody wrote down.
UnitCode = Literal[
    "mm", "mm2", "mm3", "each", "gram_milli", "cent",
    "deg_milli", "mph_milli", "pa_milli", "second_milli",
]

# §1.2 obligation 13: what a condition key is answered by, and therefore WHEN.
ConditionScope = Literal["site", "param", "run", "post", "bay", "panel"]

# The namespace each scope reads in the evaluation context. `param` has no
# namespace of its own: a table conditioned on another table's value reads the
# parameter the other table set, which lands in the same place every other
# resolved parameter does.
_NAMESPACE: dict[str, str] = {
    "site": "site", "run": "run", "post": "post", "bay": "bay", "panel": "panel",
    "param": "param",
}


class Quantity(BaseModel):
    """§1.1. Thousandths, so the boundary never carries a float.

    `value_raw` is the source's own lexeme — `88"` beside `2235` — kept because a
    disagreement between the two is a bug somebody can see, and because §1.1 says
    the display keeps the source form.
    """

    amount_milli: int
    unit: UnitCode
    value_raw: list[str] = []


class Token(BaseModel):
    """§1.3. A token carries its lexeme too — it is not a bare string.

    Publishing `"stepped_only"` alone loses the sentence the document actually
    used (*"They should be only installed using the slope method"*), which is
    what a curator needs beside the code. Leaving it bare would have
    reintroduced, through this loader, the exact loss the contract's `value_raw`
    was accepted to prevent for `Quantity` — the Knowledge team's review of the
    conforming fixture is what caught this side publishing it bare.
    """

    key: str
    value_raw: list[str] = []


class Interval(BaseModel):
    """§1.3 `Interval` — a condition on a `range(<UnitCode>)` dimension (007).

    A condition dimension can be a QUANTITY. Real footing schedules condition on
    fence height, and a height is a length — but a listed domain can only hold
    labels, so `"Up to 48\""` used to cross as an English phrase that no rule
    could evaluate and no `uncovered` entry could report a hole in.

    `min`/`max` are `null` for **unbounded on that side**, which is a statement
    rather than an absence — do not confuse it with §1.1's `Date` null. And the
    inclusivity flags carry no default: the real brackets leave a 25.4 mm band
    between them, and whether that band is a dead zone in the source or an
    artefact of whole-inch rounding is a fact only the publisher holds.

    `value_raw` is the publisher's own phrase, for the reason it exists
    everywhere else: a disagreement between the label and the bounds is a bug
    somebody can see.
    """

    min: Quantity | None = None
    max: Quantity | None = None
    min_inclusive: bool = True
    max_inclusive: bool = True
    value_raw: list[str] = []

    def label(self) -> str:
        """What the source said, falling back to the bounds we would compare."""
        if self.value_raw:
            return self.value_raw[0]
        lo = f"{to_mm(self.min)}mm" if self.min else "-"
        hi = f"{to_mm(self.max)}mm" if self.max else "-"
        return f"{lo}..{hi}"


class Provenance(BaseModel):
    """§1.1. `admitted_by` is deliberately NOT here — it is an output of a RUN
    (§1.4), so a field for it on published data would be a place to record an
    answer this side has not computed yet."""

    cites: list[SourceRef] = []
    source_class: str = ""
    curation_level: int = 0
    version_status: Literal["active", "superseded", "unknown"] = "unknown"


class ParameterRow(BaseModel):
    # A condition value is a token OR, since 007, an `Interval` on a
    # `range(<UnitCode>)` dimension. `bool` precedes `int` for the reason
    # `Because.params` needs it: `hvhz: true` admitted through an int arm
    # becomes 1 and renders as one.
    conditions: dict[str, str | bool | int | Interval] = {}
    # Obligation 15. `stated` with EMPTY conditions means the document gave none:
    # such a row is a fallback, is excluded from the `unique` overlap check, and
    # asserts nothing about the points it lands on. 66% of the structural facts
    # in the class §1.4 admits are exactly this shape, and publishing them into a
    # declared domain would assert brackets the source never stated.
    condition_basis: Literal["stated", "assumed"] = "stated"
    # `[[Quantity, Quantity], …]` is 006's `paired` shape: one row holding
    # several independently-valid design points at the same conditions, so a
    # deeper footing buying a wider span is not lost by picking one.
    value: Quantity | Token | list[list[Quantity]]
    provenance: Provenance = Provenance()
    # §1.1 `Date`, BINDING since v1.2 (amendment 002). These were `str | None`,
    # which is how a `MM/DD/YYYY` lexeme came to be compared against an ISO
    # `as_of` and reported a row valid until 2028 as lapsed in 2026. The type now
    # separates the two facts the string conflated: `iso` is a date this side may
    # order, `value_raw` is what the document actually said. A source date that
    # cannot be normalised without guessing arrives as `iso: null` beside its own
    # lexeme — and is then never ordered, rather than being ordered wrongly.
    valid_from: Date | None = None
    valid_until: Date | None = None
    authority: str = ""

    def is_fallback(self) -> bool:
        return self.condition_basis == "stated" and not self.conditions


class ParameterTable(BaseModel):
    """§1.3, field for field."""

    parameter: str
    # `str | None` because a published `EntityRef` states `tenant: null` for "no
    # tenant" rather than omitting the key or sending `""` — only `kind`/`id` are
    # ever read here (`tenant` has nowhere to go until obligation 7 lands on this
    # side), so a `None` value is accepted and simply unused rather than refused.
    scope: dict[str, str | None] = {}   # EntityRef — which product or assembly
    task: str = ""                      # TaskCode — what this parameter decides
    hit_policy: Literal["unique", "priority", "collect_min", "collect_max"] = "unique"
    # `value_type` sits on the TABLE, not the row, so one column cannot hold both
    # `10000 deg_milli` and `not_rackable`. `not_rackable` is not an angle — it is
    # a different parameter. Without the declaration every consumer must branch on
    # the type of every cell.
    value_type: str = "quantity(mm)"
    # A listed dimension enumerates its values; `range(<UnitCode>)` declares a
    # CONTINUOUS one instead (007), so the value is a string rather than a list.
    domain: dict[str, list | str] = {}
    # `declared` means we may not know this table's real extent; `measured` means
    # it really does not cover that point. Different facts, rendered differently.
    domain_basis: Literal["measured", "declared"] = "declared"
    # Obligation 13: a published condition key declares its scope.
    condition_scope: dict[str, ConditionScope] = {}
    rows: list[ParameterRow] = []
    # §1.3 BINDING, as amended by 007: where a dimension is `range(<UnitCode>)`,
    # an `uncovered` entry for it is an `Interval` rather than a value — which is
    # what makes a BAND no row covers reportable at all. The 25.4 mm gap between
    # `Up to 48"` and `49" to 76"` was previously invisible: `uncovered`
    # enumerated domain points, and a height in that band was not a point.
    uncovered: list[dict[str, str | bool | int | Interval]] = []

    def token_values(self) -> set[str] | None:
        """The closed set for `token(a|b|c)`, or None for a quantity table."""
        if not self.value_type.startswith("token("):
            return None
        return {v.strip() for v in self.value_type[6:-1].split("|") if v.strip()}

    def quantity_unit(self) -> str | None:
        if not self.value_type.startswith("quantity("):
            return None
        return self.value_type[9:-1].strip()


def to_mm(q: Quantity) -> int:
    """THE one named point where thousandths become millimetres, and it ROUNDS.

    Contract §1.1, BINDING, with the arithmetic spelled out because a floor here
    is not harmless: a span limit passes through `n = ceil(run_length / max_span)`,
    so `2463.8` floored to 2463 rather than rounded to 2464 buys an extra post, an
    extra footing and an extra pour on a 9.8 m run.

    `round()` is banker's rounding in Python and would send 2500 thousandths to 2
    rather than 3, so the rounding is written out. It is half-away-from-ZERO, not
    half-up: `-2500` gives `-3`, where half-up gives `-2`. That is the right
    behaviour — the magnitude rounds the same in both directions and neither
    direction ever floors — and the word is corrected here because the two differ
    only on negatives, which is precisely where nobody looks.
    """
    if q.unit != "mm":
        raise ValueError(f"{q.unit} is not a length this engine stores; expected mm")
    whole, rem = divmod(abs(q.amount_milli), 1000)
    if rem >= 500:
        whole += 1
    return -whole if q.amount_milli < 0 else whole


def paired_columns(value_type: str) -> list[str]:
    """The parameter each column of a `paired(...)` row binds, in DECLARED order.

    `paired(footing_depth_mm:mm, max_span_mm:mm)` -> `["footing_depth_mm",
    "max_span_mm"]`. Amendment 006's named-member form exists precisely so this
    is never positional: a publisher who lists the span first is not wrong, and a
    reader that assumed depth-then-span would silently sink a 1676 mm hole under
    a 610 mm span and report it as a sealed engineering answer.

    A member declared in a unit this engine does not store at rest is not
    reinterpreted — `[]` comes back and the row lands as nonconforming, which is
    the same call `_action_for` already makes about `quantity(in)`.
    """
    if not (value_type.startswith("paired(") and value_type.endswith(")")):
        return []
    names: list[str] = []
    for member in value_type[7:-1].split(","):
        name, sep, unit = member.partition(":")
        if not sep or not name.strip() or unit.strip() != "mm":
            return []
        names.append(name.strip())
    # "paired" with one column is not a pair. Refused rather than read as an
    # ordinary quantity: a table declaring itself paired and holding one member
    # is a table disagreeing with itself, and coercing it invents the agreement.
    return names if len(names) > 1 else []


def paired_points(table: ParameterTable, row: ParameterRow) -> list[DesignPoint]:
    """One `DesignPoint` per alternative in a `paired` row (amendment 006).

    A paired row is not one fact with several fields: it is several *jointly*
    valid design points at the same conditions — 24" holes at 66" centres **or**
    30" holes at 97" — and a builder picks. Splitting the pair into independent
    per-parameter rules would let the evaluator resolve the shallow hole beside
    the wide span, which is a fence the document never approved.

    Order is the publisher's, because that is data; which one we BUILD is
    `default_point`'s answer and is deliberately not the first.

    `lexemes` carry `value_raw[0]` per binding — obligation 5: convert once at
    the boundary and keep the source's own words for display, so the panel can
    show `24" (610 mm)` and a reader can check it against the page.

    A row that does not conform to its table's own declaration yields `[]`; the
    caller raises `parameter_value_nonconforming`, the same as any other
    disagreement between a row and its `value_type`.
    """
    columns = paired_columns(table.value_type)
    if not columns or not isinstance(row.value, list):
        return []
    points: list[DesignPoint] = []
    for pair in row.value:
        if not isinstance(pair, list) or len(pair) != len(columns):
            # Not "drop the extra": which members of a wider tuple were meant is
            # a fact only the publisher holds, and guessing it is the failure
            # 006 was ratified to prevent.
            return []
        try:
            bindings = {name: to_mm(q) for name, q in zip(columns, pair)}
        except ValueError:
            return []
        lexemes = {name: q.value_raw[0] for name, q in zip(columns, pair)
                   if q.value_raw}
        points.append(DesignPoint(
            # Identity is the VALUES, not the position: a re-cut that reorders a
            # row's alternatives must not turn a stored selection into a
            # different fence, and `choice_unavailable` exists for a point that
            # genuinely went away rather than for one that moved.
            id=f"{table.parameter}:" + "x".join(str(bindings[c]) for c in columns),
            label=" · ".join(lexemes.get(c) or str(bindings[c]) for c in columns),
            bindings=bindings, lexemes=lexemes,
        ))
    built = default_point(points)
    if built is not None:
        built.is_default = True
    return points


def default_point(points: list[DesignPoint]) -> DesignPoint | None:
    """Which alternative the engine builds when nobody has chosen: the SHORTEST
    `max_span_mm`.

    Most posts, stiffest fence, and the deeper-hole option one click away. The
    engine does not spend the customer's money on its own initiative — the
    cheaper point is offered with what it saves, and a person decides (spec §6,
    *"never money"*).

    `min` is stable, so two alternatives stating the same span resolve to the
    first the publisher listed rather than to whichever the sort felt like.

    A paired row that binds no span has no such rule, and inventing one from
    another column would be this function guessing which parameter buys
    tolerance: the first alternative as published is the honest fallback, and it
    is the one case where publication order decides anything here.
    """
    if not points:
        return None
    if not all("max_span_mm" in p.bindings for p in points):
        return points[0]
    return min(points, key=lambda p: p.bindings["max_span_mm"])


# A table's `scope` is an **EntityRef** — `{kind, id, tenant}`, naming which
# product or assembly it applies to. The evaluator's `scope` is a set of bound
# DIMENSIONS — `{"series": "M-VINYL"}`. They share a word and are not the same
# thing, and copying one into the other produces a rule that can never fire:
# `_scope_matches` requires every key to be present in the context, and nothing
# ever binds `kind` or `id`. It cost nothing in unit tests, where tables are
# built without a scope, and showed up the first time a whole document was
# ingested — which is what the fixture is for.
_ENTITY_DIMENSION = {
    "product_line": "series",
    "model": "series",
    # The kind their real first publish actually uses (`3ae88642…`, 2026-08-30) —
    # `product_line`/`model` were guesses made before either side had a real
    # table to check them against. A registry addition, not a rename: kept
    # alongside the other two rather than replacing them, since nothing says a
    # future publisher will not use one of those instead.
    "fence_model": "series",
}


def _scope_ref(table: ParameterTable) -> EntityRef | None:
    """The table's `scope` as the contract's own `EntityRef`, unmapped.

    Distinct from `_scope_for` below, which converts it into evaluator DIMENSIONS.
    This one keeps it as published, because it is the half a `ParamRef` needs: a
    gap must say which product's table has the hole, and the dimension mapping
    (`fence_model` -> `series`) is a fact about our evaluator, not about the hole.
    """
    if not table.scope:
        return None
    return EntityRef(
        kind=str(table.scope.get("kind") or ""),
        id=str(table.scope.get("id") or ""),
        tenant=table.scope.get("tenant"),
    )


def _plain(point: dict | None) -> dict | None:
    """A point as plain data, so a `Gap` carries it without knowing our types.

    `Interval` is a `ParameterTable` type and `core/gaps.py` deliberately does not
    import it — a gap needs to CARRY a point, not interpret one, and `core/`
    describing a knowledge type would invert the dependency. So the model is
    dumped here, at the one boundary that knows both sides.

    `mode="json"` and not `dict()`: the point ends up in a `because.params` that a
    renderer reads and an API returns, so nested `Quantity` models have to be
    plain too, not one level of dict wrapping more models.
    """
    if point is None:
        return None
    return {
        k: (v.model_dump(mode="json") if isinstance(v, BaseModel) else v)
        for k, v in point.items()
    }


def _param_subject(
    table: ParameterTable, tenant: str | None,
    point: dict[str, str | int | bool] | None = None,
) -> GapSubject:
    """A `ParamRef` subject (§1.1, v1.2): the parameter, its scope, and the cell.

    The scope is not decoration. The first real snapshot publishes
    `footing_depth_mm` TWICE — once scoped to Barrette, once to CertainTeed, each
    citing a different approval and one superseded by the other. A subject naming
    only `footing_depth_mm` names both holes at once, which is how 16 derived gaps
    collapsed into 8 ids and half a curator's queue disappeared.
    """
    return GapSubject(kind="param", id=table.parameter, tenant=tenant,
                      scope=_scope_ref(table), point=_plain(point))


def _object_id(table: ParameterTable, index: int) -> str:
    """A row's stable identity — parameter, SCOPE, and row index.

    The scope was missing, and it is load-bearing in a way a gap id is not: the
    decision graph cites `version.ref`, `KnowledgeBase.snapshot_set()` stamps a
    run's knowledge identity from it, and `overrides_objects` targets it. Two rows
    sharing `footing_depth_mm#0@v1` mean an explanation that cannot say which
    manufacturer's approval it used, a snapshot hash that cannot tell "Barrette
    and CertainTeed" from "Barrette twice", and one override defeating both.
    """
    ref = _scope_ref(table)
    scope = f"@{ref.kind}/{ref.id}" if ref and ref.id else ""
    return f"{table.parameter}{scope}#{index}"


def _scope_for(table: ParameterTable) -> tuple[dict[str, str], str | None]:
    """The table's EntityRef as bound dimensions, or the kind we cannot map.

    An unmappable kind is NOT dropped. Dropping the scope would leave the table
    applying to EVERY product, which is the silent wrong answer: a rule scoped to
    something we do not understand must not become a rule scoped to nothing.
    """
    if not table.scope:
        return {}, None
    kind = str(table.scope.get("kind", ""))
    dimension = _ENTITY_DIMENSION.get(kind)
    if dimension is None:
        return {}, kind or "(unnamed)"
    return {dimension: str(table.scope.get("id", ""))}, None


def _candidates_for(
    row: ParameterRow, issue_dates: dict[str, Date] | None,
) -> list[Candidate]:
    """One row's citations, as competing candidates.

    **This is the scope of the whole mechanism and it is deliberately small.** A
    row carries ONE `Provenance` — one `source_class`, one `curation_level`, one
    `version_status` (§1.3) — and one or more `cites`. So the candidates differ
    only in WHICH document is being leant on: its `content_hash`, and its
    `issue_date`. That is not a technicality: 8 of the 16 rows in the first real
    snapshot cite two documents, so "which citation admits this row" is a real
    question with a real answer, not a degenerate one-element case.

    A row with no citations still yields one candidate, from the row's own
    provenance. Obligation 3 says every value carries at least one resolvable
    `SourceRef`, so an uncited row is a payload defect — but refusing to judge it
    would make an uncited row MORE admissible than a cited one, which is exactly
    backwards. It is judged on what it does carry.
    """
    dates = issue_dates or {}
    hashes = [c.belongs_to for c in row.provenance.cites if c.belongs_to] or [""]
    return [
        Candidate(
            source_class=row.provenance.source_class,      # type: ignore[arg-type]
            version_status=row.provenance.version_status,
            curation_level=row.provenance.curation_level,
            content_hash=content_hash,
            label=content_hash,
            issue_date=dates.get(content_hash),
        )
        for content_hash in hashes
    ]


def _judge(
    table: ParameterTable, row: ParameterRow,
    policy: list[SourcePolicyRow] | None, issue_dates: dict[str, Date] | None,
) -> tuple[AdmittedBy | None, str | None]:
    """Is this row's source good enough for this table's task? (§1.4)

    Returns `(admitted_by, rejection_code)` — exactly one of which is set, or
    both None when no policy was supplied and no judgement was asked for.

    **`resolve()` is used, and it scopes strictly INTO this row.** It answers
    "which of this row's own citations admits it, and at what rank". It is never
    used to choose BETWEEN rows: that is the evaluator's question, answered once,
    for authored and published knowledge alike. Two mechanisms selecting between
    facts is the failure the whole knowledge design is built to avoid — they
    would eventually disagree, and neither could explain the other.

    An unrecognised `task` is NOT a rejection. Task codes are a registry we own
    (§1.4), so a table naming one we have not added would otherwise have every
    row refused for a hole in OUR list rather than any defect in their data. The
    row is used and the caller raises a gap saying we could not judge it.
    """
    if policy is None:
        return None, None
    # Neither axis may be judged against a vocabulary that does not contain it,
    # and neither may take the load down for growing (§2). Both decline.
    if table.task not in KNOWN_TASKS:
        return None, None
    if row.provenance.source_class not in KNOWN_SOURCE_CLASSES:
        return None, None
    candidates = _candidates_for(row, issue_dates)
    resolution = resolve(policy, table.task, candidates)   # type: ignore[arg-type]
    if resolution.winner is not None:
        return resolution.winner, None
    # Every citation failed. They share the row's class, level and status, so
    # they fail for the same reason — the first one explains all of them.
    return None, explain_rejection(policy, table.task, candidates[0])   # type: ignore[arg-type]


def _condition_for(table: ParameterTable, row: ParameterRow) -> Expr | None:
    """A row's conditions as an evaluator expression, each key in the namespace
    its declared scope names.

    A key with no declared scope is left UNPREFIXED rather than guessed into
    `site.*`: an unprefixed path simply will not resolve, so the rule is
    not-applicable and reported, where a guess would make it fire on the wrong
    thing quietly.
    """
    if not row.conditions:
        return None
    terms: list[Expr] = []
    for key, value in sorted(row.conditions.items()):
        path = _path(table, key)
        if isinstance(value, Interval):
            # An `Interval` compiles to REAL COMPARISONS, which is the whole
            # point of 007. Before it, `fence_height` arrived as `"Up to 48\""`
            # and became `bay.fence_height == 'Up to 48"'` — false for every
            # project that will ever run, because a bay's height is an integer in
            # millimetres. It reported as not-applicable rather than as broken,
            # which is why nobody noticed 16 inert rows.
            #
            # The inclusivity flags pick the operator rather than being assumed:
            # the publisher states them precisely because the band between two
            # brackets is theirs to define, not ours to round away.
            if value.min is not None:
                terms.append(Cmp(cmp=">=" if value.min_inclusive else ">",
                                 left=FieldRef(path=path),
                                 right=Lit(value=to_mm(value.min))))
            if value.max is not None:
                terms.append(Cmp(cmp="<=" if value.max_inclusive else "<",
                                 left=FieldRef(path=path),
                                 right=Lit(value=to_mm(value.max))))
            # An interval unbounded on BOTH sides constrains nothing, and
            # contributing no term is the honest reading — not a term that is
            # always true, which would look like a condition in the explanation.
            continue
        terms.append(Cmp(cmp="==", left=FieldRef(path=path), right=Lit(value=value)))
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else And(items=terms)


def _path(table: ParameterTable, key: str) -> str:
    scope = table.condition_scope.get(key)
    return f"{_NAMESPACE[scope]}.{key}" if scope else key


def expand(
    table: ParameterTable, *, as_of: str = "", tenant: str | None = None,
    policy: list[SourcePolicyRow] | None = None,
    issue_dates: dict[str, Date] | None = None,
) -> tuple[list[KnowledgeVersion], list[Gap], dict[str, AdmittedBy]]:
    """One published table -> ordinary knowledge, plus the gaps it declares.

    Every version is built through `KnowledgeVersion.from_published`, never the
    constructor: `origin` defaults to `authored`, so a loader that forgot it would
    make published rows look home-grown, and two of them that tie and disagree
    would RAISE — the exact defect `origin` was added to close, reinstated with
    nothing failing, because `demo_knowledge()` holds no published rows to notice.

    `as_of` is the run's pinned date (obligation 16). A row whose `valid_until`
    precedes it is EXPANDED anyway and marked — never dropped: dropping it would
    turn a lapsed authority into a coverage hole, and those are different facts
    with different fixes.

    `tenant` names every `GapSubject` this table's gaps carry — the field the
    Knowledge team's review of the conforming fixture added, matching `EntityRef`.
    It was accepted here and threaded to `snapshot.py`'s call site with nothing
    ever reading it from `snapshot.tenant` down to the gaps themselves; a
    test-review of that same change is what caught the wiring stopping short.
    """
    versions: list[KnowledgeVersion] = []
    gaps: list[Gap] = []
    admitted: dict[str, AdmittedBy] = {}
    tokens = table.token_values()

    # An `as_of` this side cannot read is OUR bug, not a publisher's, so it is
    # refused rather than quietly downgraded to "no judgement" — a typo'd pin
    # would otherwise silence every expiry check in the run without a sound.
    if as_of and not is_iso_date(as_of):
        raise ValueError(
            f"as_of={as_of!r} is not an ISO-8601 YYYY-MM-DD date. It is this "
            f"engine's own pinned run date, not published data"
        )
    as_of_date = Date(iso=as_of) if as_of else None

    scope, unmappable = _scope_for(table)
    if unmappable is not None:
        # Nothing is expanded. A table we cannot aim is not a table we may apply
        # everywhere, and this closes by a schema change HERE, not by a curator.
        return [], [_unmappable_scope_gap(table, unmappable, tenant)], {}

    if table.hit_policy not in SUPPORTED_HIT_POLICIES:
        # Same argument, one field over: expanding these rows would produce a
        # number, and the number would be wrong.
        return [], [_unsupported_hit_policy_gap(table, tenant)], {}

    if policy is not None and table.task not in KNOWN_TASKS:
        # Once per table, not once per row: the hole is our registry, and one
        # note about it is a work item where sixteen identical ones are noise.
        # The rows are still expanded — see `_judge`.
        gaps.append(_task_unrecognised_gap(table, tenant))

    for index, row in enumerate(table.rows):
        actions = _actions_for(table, row, tokens)
        if not actions:
            gaps.append(_bad_value_gap(table, row, index, tenant))
            continue
        object_id = _object_id(table, index)
        if (policy is not None and table.task in KNOWN_TASKS
                and row.provenance.source_class not in KNOWN_SOURCE_CLASSES):
            # Per ROW, unlike the task gap: a table may mix classes, and which
            # row carries the unregistered one is what a reader needs.
            gaps.append(_source_class_unrecognised_gap(table, row, index, tenant))
        # Validity is judged BEFORE admissibility and independently of it. The
        # two are different questions about the same row — "is this authority in
        # force?" and "is this source good enough?" — and one can invalidate the
        # work the other implies. A row that is both unchecked and expired must
        # report both: `source_below_min_curation` alone sends a reviewer to open
        # a crop for a document that lapsed two years ago, which is precisely the
        # wasted bounded work the review queue exists to avoid.
        #
        # `precedes` returns None when either side carries no `iso`, and None is
        # NOT "no" — it means the question has no answer, so no gap is reported
        # rather than a wrong one. That is §1.1's null rule doing its job: an
        # undated authority is never treated as earliest or latest, so it is
        # never silently declared lapsed and never silently declared current.
        if precedes(row.valid_until, as_of_date) is True:
            gaps.append(_lapsed_gap(table, row, index, as_of, tenant))
        # The lapsed check's twin, and it was never written. A row whose
        # authority does not take effect until after this run's pinned date was
        # expanded silently and applied with no marker — the same defect as a
        # lapsed row, failing in the more dangerous direction: a lapsed row at
        # least produces a warned line, while a not-yet-in-force row produces a
        # confident wrong answer. Marked, never dropped, for the same reason.
        if precedes(as_of_date, row.valid_from) is True:
            gaps.append(_not_yet_in_force_gap(table, row, index, as_of, tenant))

        if policy is not None and not row.provenance.cites:
            # Obligation 3: *"Every value carries at least one resolvable
            # SourceRef."* Judged anyway — the axes the policy reads are all on
            # the row, so refusing to judge would make an UNCITED row more
            # admissible than a cited one, which is backwards — but reported,
            # because the verdict is about to be shown beside the number and
            # "backed by a sealed approval, checked by a person" with nothing to
            # click through to is a provenance claim with no document behind it.
            gaps.append(_source_ref_missing_gap(table, row, index, tenant))
        admitted_by, rejected = _judge(table, row, policy, issue_dates)
        if rejected is not None:
            # NOT expanded. A value the policy refuses must not reach the
            # evaluator at all — the whole point of §1.4 is that the decision
            # graph can say "a spec sheet was inadmissible for a structural
            # parameter" instead of the value silently never existing. The
            # generator's existing "no rule covered this" path then produces a
            # conservative fallback, a gap node and a warned line, which is the
            # shape that path was built for.
            gaps.append(_rejected_source_gap(table, row, index, rejected, tenant))
            continue
        version = KnowledgeVersion.from_published(
            object_id=object_id,
            version=1,
            # A published row is a fact about the world, not a company rule —
            # `fact` is the tier the demo base already gives measured inputs, and
            # the row's own `authority` field is what a policy will read later.
            type="fact",
            scope=scope,
            condition=_condition_for(table, row),
            actions=actions,
            title=f"{table.parameter} = {_row_label(table, row)}",
            attributed_to="knowledge_platform",
        )
        versions.append(version)
        if admitted_by is not None:
            # Keyed by `ref`, the same `"OBJ@vN"` the decision graph's
            # `governed_by` edges carry — so the verdict joins onto an edge that
            # already exists rather than needing a second identity scheme.
            admitted[version.ref] = admitted_by

    gaps.extend(_overlap_gaps(table, tenant))
    gaps.extend(_uncovered_gaps(table, tenant))
    return versions, gaps, admitted


def _actions_for(table: ParameterTable, row: ParameterRow, tokens: set[str] | None):
    """The actions a row lands as, or `[]` when the row does not conform.

    `value_type` is declared once on the table, so a row that disagrees with it is
    the table contradicting itself — a gap, not something to coerce.

    A list, not one action, because of `paired` (006): the alternative this
    engine builds binds SEVERAL parameters at once, and they land on one version
    so that the evaluator can never resolve half of a pair. Everything else
    returns a single-element list and reads exactly as it did.
    """
    if table.value_type.startswith("paired("):
        # A paired row states several design points, and the one that lands as
        # knowledge is the DEFAULT — the shortest span (spec §6). The others are
        # not discarded: they are the choice set a person is offered, measured
        # against this baseline and resolved back through `resolve_param` as a
        # synthesized version, so precedence and defeat edges keep working.
        #
        # This is why the pair may not be split into two independent rules. Both
        # numbers are one statement of the source's — 24" holes are approved at
        # 66" centres and at nothing wider — and two rules would let the
        # evaluator pick the shallow hole from one and the wide span from the
        # other, producing a fence the sealed approval does not cover.
        built = default_point(paired_points(table, row))
        if built is None:
            return []
        return [SetParam(param=name, value=value)
                for name, value in built.bindings.items()]
    if tokens is not None:
        if not isinstance(row.value, Token) or row.value.key not in tokens:
            return []
        return [SetToken(param=table.parameter, value=row.value.key)]
    if not isinstance(row.value, Quantity) or table.quantity_unit() != "mm":
        return []
    try:
        return [SetParam(param=table.parameter, value=to_mm(row.value))]
    except ValueError:
        return []


def _row_label(table: ParameterTable, row: ParameterRow) -> str:
    """A row's value as a title — for a `paired` row, the alternative we built.

    A title naming the whole row would state two spans the run does not honour;
    naming the point that landed is what makes `governed_by` legible.
    """
    if table.value_type.startswith("paired("):
        built = default_point(paired_points(table, row))
        return built.label if built is not None else ""
    return _display(row.value)


def _display(value) -> str:
    """A row's value as a title.

    `value_raw` first, because §1.1 says the source's own lexeme exists to be
    shown beside the number — a title reading `34"` is what a curator matches
    against the page, where `863.6 mm` is this engine's arithmetic.

    The fallback no longer goes through `%g`, which is six SIGNIFICANT digits and
    therefore misstates exactly the values worth checking: `1234567` thousandths
    rendered as `1234.57 mm` (wrong by 0.43 mm) and `1000000000` as `1e+06 mm`.
    Integer division by the unit's own scale keeps the number the publisher sent.
    """
    if isinstance(value, Token):
        return value.value_raw[0] if value.value_raw else value.key
    if value.value_raw:
        return value.value_raw[0]
    whole, rem = divmod(abs(value.amount_milli), 1000)
    sign = "-" if value.amount_milli < 0 else ""
    fraction = f".{rem:03d}".rstrip("0") if rem else ""
    return f"{sign}{whole}{fraction} {value.unit}"


def _uncovered_gaps(table: ParameterTable, tenant: str) -> list[Gap]:
    """`uncovered` points, as gaps — never silently omitted (§1.3 BINDING).

    `domain_basis` decides what the point MEANS, which is the reason the contract
    carries the field: against a `measured` domain the table really does not cover
    it; against a `declared` one we may not know the table's real extent. The
    would_close sentence says which, because they send a curator to different work.
    """
    out = []
    for point in table.uncovered:
        where = _point_label(point)
        measured = table.domain_basis == "measured"
        subject = _param_subject(table, tenant, point=point)
        out.append(Gap(
            # Derived from the SUBJECT, so the id carries everything that
            # distinguishes one hole from another — scope included. Built from
            # `{parameter}:{point}` alone, the two published `footing_depth_mm`
            # tables produced byte-identical ids for different manufacturers'
            # holes, and 16 gaps arrived as 8.
            id=f"gap:uncovered:{subject.key()}",
            kind="uncovered_condition",
            subject=subject,
            # `point` is the contract's own mapping, carried structured. It used
            # to be pre-joined into `"exposure_category=D, hvhz=True"` and
            # interpolated into a Hebrew sentence, which is English leaking
            # through a locale template with Python's `True` inside it.
            because=Because(code="uncovered_parameter_point",
                             params={"parameter": table.parameter, "point": _plain(point),
                                     "domain_basis": table.domain_basis}),
            would_close=(
                f"a {table.parameter} row for {where}" if measured else
                f"a re-read of the source's own table extent for {table.parameter}, "
                f"then a row for {where} if the source covers it"
            ),
            closes_by="knowledge", severity="warns_line",
        ))
    return out


def _point_label(point: dict[str, str | int | bool]) -> str:
    """A point rendered for a `would_close` SENTENCE — and nowhere else.

    §1.2.1 makes `would_close` a str ("one sentence: what would resolve this"), so
    a rendered form is what belongs there. It must not be reused as a `because`
    param: those render through a locale template in two languages, and this is
    English.
    """
    return ", ".join(f"{k}={v}" for k, v in sorted(point.items()))


def _lapsed_gap(
    table: ParameterTable, row: ParameterRow, index: int, as_of: str,
    tenant: str | None,
) -> Gap:
    return Gap(
        id=f"gap:lapsed:{_object_id(table, index)}",
        kind="uncovered_condition",
        subject=_param_subject(table, tenant),
        because=Because(code="parameter_authority_lapsed",
                         params={"parameter": table.parameter,
                                 # The lexeme, not the ISO form: this sentence is
                                 # read beside the document, and the document says
                                 # what it says.
                                 "valid_until": _date_label(row.valid_until),
                                 "as_of": as_of, "authority": row.authority}),
        would_close=f"a reissue of {row.authority or 'the authority'} covering {as_of}",
        closes_by="knowledge", severity="warns_line",
    )


def _not_yet_in_force_gap(
    table: ParameterTable, row: ParameterRow, index: int, as_of: str,
    tenant: str | None,
) -> Gap:
    return Gap(
        id=f"gap:not_yet_in_force:{_object_id(table, index)}",
        kind="uncovered_condition",
        subject=_param_subject(table, tenant),
        because=Because(code="parameter_not_yet_in_force",
                         params={"parameter": table.parameter,
                                 "valid_from": _date_label(row.valid_from),
                                 "as_of": as_of, "authority": row.authority}),
        would_close=(f"an authority for {table.parameter} already in force at "
                     f"{as_of}, or a run pinned on or after "
                     f"{_date_label(row.valid_from)}"),
        closes_by="knowledge", severity="warns_line",
    )


def _date_label(d: Date | None) -> str:
    """What the document said, falling back to the normalised form.

    `value_raw` first is the same order of preference §1.1 gives `Quantity`: the
    source's own stamp is what a curator matches against the page in front of
    them, and `iso` is what this engine ordered by.
    """
    if d is None:
        return ""
    return d.raw() or (d.iso or "")


def _unsupported_hit_policy_gap(table: ParameterTable, tenant: str | None) -> Gap:
    """A `hit_policy` this engine cannot honour — refused, never approximated.

    `hit_policy` was accepted and then dropped on the floor: every row became an
    ordinary rule and evaluator precedence picked a winner, so a `collect_min`
    table of 1000 and 2000 resolved to whichever fired first. Three of the
    contract's four policies silently produced a different number from the one
    the publisher declared. Closing by a schema change HERE is what it is.
    """
    return Gap(
        id=f"gap:hit_policy:{table.parameter}:{table.hit_policy}",
        kind="unmodellable_entity",
        subject=_param_subject(table, tenant),
        because=Because(code="parameter_hit_policy_unsupported",
                         params={"parameter": table.parameter,
                                 "hit_policy": table.hit_policy}),
        would_close=(f"a {table.hit_policy} resolver in the Planning repo, so a "
                     f"table declaring it returns the value it declares"),
        closes_by="planning", severity="warns_line",
    )


def _overlap_gaps(table: ParameterTable, tenant: str | None) -> list[Gap]:
    """§1.3 BINDING: under `unique`, no two rows may match the same domain point.

    *"`unique` means 'I claim these conditions are disjoint,' and the check will
    tell you when that is false."* That check is the one mechanical property
    `hit_policy` was added to buy, and it did not exist — the contradiction
    surfaced only at run time, as a `Conflict` on a warned line, attributed to
    this engine rather than to the table that declared something untrue.

    A FALLBACK row (`stated` with no conditions) is excluded, which is what
    `is_fallback()` was written for and never called for: such a row asserts
    nothing about the points it lands on, so it cannot contradict one that does.
    """
    if table.hit_policy != "unique":
        return []
    out: list[Gap] = []
    rows = [(i, r) for i, r in enumerate(table.rows) if not r.is_fallback()]
    for a, (i, left) in enumerate(rows):
        for j, right in rows[a + 1:]:
            shared = set(left.conditions) & set(right.conditions)
            # Two rows overlap when they agree everywhere they both speak: any
            # point satisfying the union of their conditions matches both. Rows
            # that share NO key overlap too — each is silent where the other
            # speaks — which is why an empty `shared` is not an early exit.
            if any(left.conditions[k] != right.conditions[k] for k in shared):
                continue
            point = {**left.conditions, **right.conditions}
            subject = _param_subject(table, tenant, point=point)
            out.append(Gap(
                id=f"gap:overlap:{_object_id(table, i)}:{j}",
                kind="disputed", on="conditions",
                subject=subject,
                because=Because(code="parameter_rows_overlap",
                                 params={"parameter": table.parameter,
                                         "row": i, "other_row": j,
                                         "point": _plain(point)}),
                would_close=(f"disjoint conditions on rows {i} and {j} of "
                             f"{table.parameter}, or a hit_policy that admits "
                             f"more than one match"),
                closes_by="knowledge", severity="warns_line",
            ))
    return out


def _rejected_source_gap(
    table: ParameterTable, row: ParameterRow, index: int, code: str,
    tenant: str | None,
) -> Gap:
    """A row the source policy refused (§1.4), and what would let it be used.

    `missing_value` is the kind, and it is the honest one: after the policy has
    spoken there IS no admissible value for this point. It is not `disputed` —
    nobody disagrees about the number — and it is not `uncovered_condition`,
    because the table does cover the point; what is missing is a source good
    enough to rely on there.

    `would_close` differs by code because the two need different people. Below
    the curation bar, the work is bounded and already queued: a reviewer opens
    the crop for a document we hold. Inadmissible, no amount of reviewing helps —
    somebody must find a different document.
    """
    prov = row.provenance
    params: dict[str, str | int] = {
        "parameter": table.parameter, "task": table.task,
        "source_class": prov.source_class,
        "curation_level": prov.curation_level,
    }
    # The DECLINED number and the source's own lexeme travel with the refusal.
    #
    # Two things needed this and neither is cosmetic. A reader has to be able to
    # see WHAT we declined — "we did not use the manufacturer's 36 inches" is the
    # sentence that makes a refusal reviewable, and without the value the gap can
    # only say that something was refused. And a refused value is still evidence
    # about RISK: a source we have not verified saying "no wider than 858 mm" does
    # not become permission to build 1500 mm bays. `min_bound_mm` is what lets a
    # consumer that knows its parameter's safe direction refuse to be laxer than
    # a number it declined to trust. Carrying it here rather than in a second
    # channel keeps one object describing one refusal.
    if isinstance(row.value, Quantity) and row.value.unit == "mm":
        params["declined_mm"] = to_mm(row.value)
        if row.value.value_raw:
            params["declined_raw"] = row.value.value_raw[0]
    # Both codes are written as LITERALS here rather than passed through from
    # `explain_rejection`, and that is not redundancy. `tests/web/
    # test_locale_bundles.py` finds every emitted code by scanning for
    # `code="..."` at the site that emits it — a code arriving as a variable is
    # invisible to it, and an unseen code reaches a screen as its own key in both
    # languages. The guard can only guard what it can read.
    if code == "source_below_min_curation":
        because = Because(code="source_below_min_curation", params=params)
        would_close = (
            f"a reviewer confirming {table.parameter} row {index} against the "
            f"source image, raising it to curation level 2"
        )
    else:
        because = Because(code="source_inadmissible", params=params)
        would_close = (
            f"a {table.parameter} value for these conditions from a source class "
            f"the policy admits for {table.task or 'this task'} — "
            f"{prov.source_class or 'this row’s class'} is not one"
        )
    return Gap(
        id=f"gap:{code}:{_object_id(table, index)}",
        kind="missing_value",
        subject=_param_subject(table, tenant, point=dict(row.conditions) or None),
        because=because,
        cites=list(prov.cites),
        would_close=would_close,
        closes_by="knowledge", severity="warns_line",
    )


def _source_ref_missing_gap(
    table: ParameterTable, row: ParameterRow, index: int, tenant: str | None,
) -> Gap:
    """A row carrying no citation at all (obligation 3).

    `dangling_refs` catches a ref that resolves to no document; this catches the
    other half, which nothing checked: no ref at all. The row is still used and
    still judged — see the call site — so this is a report about what a reader
    will not be able to check, not a refusal.
    """
    return Gap(
        id=f"gap:source_ref_missing:{_object_id(table, index)}",
        kind="missing_value",
        subject=_param_subject(table, tenant, point=dict(row.conditions) or None),
        because=Because(code="source_ref_missing",
                         params={"parameter": table.parameter,
                                 "source_class": row.provenance.source_class}),
        would_close=(f"a resolvable SourceRef on {table.parameter} row {index}, so "
                     f"a reader can see the document behind the number"),
        closes_by="knowledge", severity="warns_line",
    )


def _source_class_unrecognised_gap(
    table: ParameterTable, row: ParameterRow, index: int, tenant: str | None,
) -> Gap:
    """A row naming a source class this engine's policy has no row for.

    `SourceClass` is a registry the contract guarantees can grow without an
    amendment, and §1.4 records that two classes were added in its own last
    revision — so this is the expected case. Before it was handled, an
    unregistered class raised a raw `ValidationError` from inside `Candidate`
    and took the entire snapshot down: 4 tables, 289 warnings and 81 gaps lost
    because the other team registered a word. That is the opposite of what a
    registry is for, and it violated §3.2.4 into the bargain.

    So the row is used UNJUDGED and this says so. `closes_by: planning` — the
    fix is a policy row here, not anything a curator can do to their document.
    """
    return Gap(
        id=f"gap:source_class_unrecognised:{_object_id(table, index)}",
        kind="unmodellable_entity",
        subject=_param_subject(table, tenant, point=dict(row.conditions) or None),
        because=Because(code="source_class_unrecognised",
                         params={"parameter": table.parameter,
                                 "source_class": row.provenance.source_class,
                                 "task": table.task}),
        cites=list(row.provenance.cites),
        would_close=(f"a source-policy row for {row.provenance.source_class!r} on "
                     f"{table.task or 'this task'}, so this row can be judged "
                     f"rather than used unjudged"),
        closes_by="planning", severity="warns_line",
    )


def _task_unrecognised_gap(table: ParameterTable, tenant: str | None) -> Gap:
    """A table declaring a task this engine's policy vocabulary has no row for.

    `TaskCode` is a registry we own (§1.4), so this is a hole in OUR list, not a
    defect in their data — hence `closes_by: planning`, and hence the rows are
    expanded anyway. Refusing them would mean a published fact going unused
    because we had not added a word, which is a failure mode that looks exactly
    like the data being wrong.

    The cost of using them is stated rather than hidden: they are used
    **unjudged**, so no `admitted_by` is recorded for them and nothing claims
    their source was checked.
    """
    return Gap(
        id=f"gap:task_unrecognised:{table.parameter}:{table.task}",
        kind="unmodellable_entity",
        subject=_param_subject(table, tenant),
        because=Because(code="parameter_task_unrecognised",
                         params={"parameter": table.parameter,
                                 "task": table.task}),
        would_close=(f"a {table.task!r} entry in this engine's TaskCode registry "
                     f"and a source-policy row for it, so its rows can be judged "
                     f"rather than used unjudged"),
        closes_by="planning", severity="warns_line",
    )


def _unmappable_scope_gap(
    table: ParameterTable, kind: str, tenant: str | None,
) -> Gap:
    return Gap(
        id=f"gap:unmappable_scope:{table.parameter}:{kind}",
        kind="unmodellable_entity",
        subject=GapSubject(kind="entity", ref_kind=kind,
                            id=str(table.scope.get("id") or ""), tenant=tenant),
        because=Because(code="parameter_scope_unmappable",
                         params={"parameter": table.parameter, "entity_kind": kind}),
        would_close=(f"an evaluator dimension for a {kind} in the Planning repo, so a "
                     f"table scoped to one can be aimed at it"),
        # BINDING (§1.2.1): `unmodellable_entity` closes by a schema change HERE.
        # Showing a curator this row would be showing them work they cannot do.
        closes_by="planning", severity="warns_line",
    )


def _bad_value_gap(
    table: ParameterTable, row: ParameterRow, index: int, tenant: str | None,
) -> Gap:
    return Gap(
        id=f"gap:nonconforming:{_object_id(table, index)}",
        kind="disputed", on="value",
        subject=_param_subject(table, tenant),
        because=Because(code="parameter_value_nonconforming",
                         params={"parameter": table.parameter,
                                 "value_type": table.value_type, "row": index}),
        would_close=(f"a {table.parameter} row {index} whose value conforms to "
                     f"{table.value_type}, or a value_type that admits it"),
        closes_by="knowledge", severity="warns_line",
    )
