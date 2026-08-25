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

from typing import Literal

from pydantic import BaseModel

from fenceai.core.gaps import Gap, GapSubject, SourceRef
from fenceai.knowledge.ast import And, Cmp, Expr, FieldRef, Lit
from fenceai.knowledge.model import KnowledgeVersion, SetParam, SetToken

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


class Provenance(BaseModel):
    """§1.1. `admitted_by` is deliberately NOT here — it is an output of a RUN
    (§1.4), so a field for it on published data would be a place to record an
    answer this side has not computed yet."""

    cites: list[SourceRef] = []
    source_class: str = ""
    curation_level: int = 0
    version_status: Literal["active", "superseded", "unknown"] = "unknown"


class ParameterRow(BaseModel):
    conditions: dict[str, str | int | bool] = {}
    # Obligation 15. `stated` with EMPTY conditions means the document gave none:
    # such a row is a fallback, is excluded from the `unique` overlap check, and
    # asserts nothing about the points it lands on. 66% of the structural facts
    # in the class §1.4 admits are exactly this shape, and publishing them into a
    # declared domain would assert brackets the source never stated.
    condition_basis: Literal["stated", "assumed"] = "stated"
    value: Quantity | str
    provenance: Provenance = Provenance()
    valid_from: str | None = None
    valid_until: str | None = None
    authority: str = ""

    def is_fallback(self) -> bool:
        return self.condition_basis == "stated" and not self.conditions


class ParameterTable(BaseModel):
    """§1.3, field for field."""

    parameter: str
    scope: dict[str, str] = {}          # EntityRef — which product or assembly
    task: str = ""                      # TaskCode — what this parameter decides
    hit_policy: Literal["unique", "priority", "collect_min", "collect_max"] = "unique"
    # `value_type` sits on the TABLE, not the row, so one column cannot hold both
    # `10000 deg_milli` and `not_rackable`. `not_rackable` is not an angle — it is
    # a different parameter. Without the declaration every consumer must branch on
    # the type of every cell.
    value_type: str = "quantity(mm)"
    domain: dict[str, list] = {}
    # `declared` means we may not know this table's real extent; `measured` means
    # it really does not cover that point. Different facts, rendered differently.
    domain_basis: Literal["measured", "declared"] = "declared"
    # Obligation 13: a published condition key declares its scope.
    condition_scope: dict[str, ConditionScope] = {}
    rows: list[ParameterRow] = []
    uncovered: list[dict[str, str | int | bool]] = []

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
    rather than 3, so the half-up form is written out.
    """
    if q.unit != "mm":
        raise ValueError(f"{q.unit} is not a length this engine stores; expected mm")
    whole, rem = divmod(abs(q.amount_milli), 1000)
    if rem >= 500:
        whole += 1
    return -whole if q.amount_milli < 0 else whole


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
    terms = [
        Cmp(cmp="==",
            left=FieldRef(path=_path(table, key)),
            right=Lit(value=value))
        for key, value in sorted(row.conditions.items())
    ]
    return terms[0] if len(terms) == 1 else And(items=terms)


def _path(table: ParameterTable, key: str) -> str:
    scope = table.condition_scope.get(key)
    return f"{_NAMESPACE[scope]}.{key}" if scope else key


def expand(
    table: ParameterTable, *, as_of: str = "", tenant: str = "",
) -> tuple[list[KnowledgeVersion], list[Gap]]:
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
    """
    versions: list[KnowledgeVersion] = []
    gaps: list[Gap] = []
    tokens = table.token_values()

    for index, row in enumerate(table.rows):
        action = _action_for(table, row, tokens)
        if action is None:
            gaps.append(_bad_value_gap(table, row, index))
            continue
        versions.append(KnowledgeVersion.from_published(
            object_id=f"{table.parameter}#{index}",
            version=1,
            # A published row is a fact about the world, not a company rule —
            # `fact` is the tier the demo base already gives measured inputs, and
            # the row's own `authority` field is what a policy will read later.
            type="fact",
            scope=dict(table.scope),
            condition=_condition_for(table, row),
            actions=[action],
            title=f"{table.parameter} = {_display(row.value)}",
            attributed_to="knowledge_platform",
        ))
        if row.valid_until and as_of and row.valid_until < as_of:
            gaps.append(_lapsed_gap(table, row, index, as_of))

    gaps.extend(_uncovered_gaps(table))
    return versions, gaps


def _action_for(table: ParameterTable, row: ParameterRow, tokens: set[str] | None):
    """The action a row lands as, or None when the row does not conform.

    `value_type` is declared once on the table, so a row that disagrees with it is
    the table contradicting itself — a gap, not something to coerce.
    """
    if tokens is not None:
        if not isinstance(row.value, str) or row.value not in tokens:
            return None
        return SetToken(param=table.parameter, value=row.value)
    if not isinstance(row.value, Quantity) or table.quantity_unit() != "mm":
        return None
    try:
        return SetParam(param=table.parameter, value=to_mm(row.value))
    except ValueError:
        return None


def _display(value) -> str:
    return value if isinstance(value, str) else f"{value.amount_milli / 1000:g} {value.unit}"


def _uncovered_gaps(table: ParameterTable) -> list[Gap]:
    """`uncovered` points, as gaps — never silently omitted (§1.3 BINDING).

    `domain_basis` decides what the point MEANS, which is the reason the contract
    carries the field: against a `measured` domain the table really does not cover
    it; against a `declared` one we may not know the table's real extent. The
    would_close sentence says which, because they send a curator to different work.
    """
    out = []
    for point in table.uncovered:
        where = ", ".join(f"{k}={v}" for k, v in sorted(point.items()))
        measured = table.domain_basis == "measured"
        out.append(Gap(
            id=f"gap:uncovered:{table.parameter}:{where}",
            kind="uncovered_condition",
            subject=GapSubject(kind="param", ref=table.parameter),
            code="uncovered_parameter_point",
            params={"parameter": table.parameter, "point": where,
                    "domain_basis": table.domain_basis},
            message=f"{table.parameter} has no row for {where}.",
            would_close=(
                f"a {table.parameter} row for {where}" if measured else
                f"a re-read of the source's own table extent for {table.parameter}, "
                f"then a row for {where} if the source covers it"
            ),
            closes_by="knowledge", severity="warns_line",
        ))
    return out


def _lapsed_gap(table: ParameterTable, row: ParameterRow, index: int, as_of: str) -> Gap:
    return Gap(
        id=f"gap:lapsed:{table.parameter}#{index}",
        kind="uncovered_condition",
        subject=GapSubject(kind="param", ref=table.parameter),
        code="parameter_authority_lapsed",
        params={"parameter": table.parameter, "valid_until": row.valid_until or "",
                "as_of": as_of, "authority": row.authority},
        message=(f"{table.parameter} row {index} was valid until {row.valid_until}, "
                 f"before this run's as_of {as_of}."),
        would_close=f"a reissue of {row.authority or 'the authority'} covering {as_of}",
        closes_by="knowledge", severity="warns_line",
    )


def _bad_value_gap(table: ParameterTable, row: ParameterRow, index: int) -> Gap:
    return Gap(
        id=f"gap:nonconforming:{table.parameter}#{index}",
        kind="disputed", on="value",
        subject=GapSubject(kind="param", ref=table.parameter),
        code="parameter_value_nonconforming",
        params={"parameter": table.parameter, "value_type": table.value_type,
                "row": index},
        message=(f"{table.parameter} row {index} does not conform to the table's "
                 f"declared value_type {table.value_type}."),
        would_close=(f"a {table.parameter} row {index} whose value conforms to "
                     f"{table.value_type}, or a value_type that admits it"),
        closes_by="knowledge", severity="warns_line",
    )
