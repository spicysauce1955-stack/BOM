"""Rule evaluation with native trace emission (ADR-0005).

evaluate() returns every applicable firing; resolve_param()/resolve_actions() apply
precedence (authority tier -> scope specificity -> explicit overrides -> recency),
recording winners, defeated_by, and surfaced conflicts. Ties never resolve silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fenceai.core.errors import GenerationFailure
from fenceai.knowledge.ast import MissingField, evaluate_expr, field_paths
from fenceai.knowledge.model import Action, KnowledgeBase, KnowledgeVersion

# Authority tiers at or above company_rule are "hard": a tie between them with
# disagreeing outputs is a generation failure, not a survivable conflict.
HARD_AUTHORITY_MAX = 3


@dataclass
class Firing:
    version: KnowledgeVersion
    actions: list[Action]
    defeated_by: list[str] = field(default_factory=list)      # refs of winners
    # Distinct from `defeated_by`: this firing agreed with the winner, it was
    # never beaten. Conflating the two rendered five identical sources as
    # "4 defeated, 0 conflicts" — a contest that never happened.
    corroborated_by: list[str] = field(default_factory=list)  # refs it agrees with


@dataclass
class Conflict:
    param_or_action: str
    contenders: list[str]  # version refs
    message: str
    # This tie sat INSIDE the hard-authority band and survived only because a
    # contender is `published` — i.e. it would have been a generation failure
    # between two rules we wrote. It is not an ordinary preference tie and must
    # not be treated as one: the caller has to resolve it conservatively (it
    # knows which direction is safe for its own parameter; the evaluator does
    # not), and it has to be reported BACK, because only the publisher can fix
    # two of their own rows contradicting each other.
    hard: bool = False


@dataclass
class Resolution:
    winner: Firing | None
    firings: list[Firing]  # all applicable, losers carry defeated_by
    conflicts: list[Conflict]


def _scope_matches(version: KnowledgeVersion, ctx: dict) -> bool:
    scope_ctx = ctx.get("scope", {})
    return all(scope_ctx.get(k) == v for k, v in version.scope.items())


def applicable_firings(kb: KnowledgeBase, ctx: dict) -> list[Firing]:
    firings: list[Firing] = []
    for v in kb.active():
        if v.type == "candidate":
            continue  # candidates are never evaluated (knowledge-system.md)
        if not _scope_matches(v, ctx):
            continue
        if v.condition is not None:
            _assert_namespaces_bound(v, ctx)
            try:
                if not evaluate_expr(v.condition, ctx):
                    continue
            except MissingField:
                continue  # missing context field => not applicable
        firings.append(Firing(version=v, actions=list(v.actions)))
    # deterministic order: authority, specificity desc, version desc, object id
    firings.sort(
        key=lambda f: (
            f.version.effective_authority(),
            -f.version.specificity(),
            -f.version.version,
            f.version.object_id,
        )
    )
    return firings


# Namespaces a rule may condition on that a CALLER has to bind. `scope`, `run`,
# `post` and `panel` are built by whichever site is resolving; `site` is a
# whole-run fact threaded from `generate()`. The distinction below is between an
# unanswered dimension and an unbound namespace, and it is not pedantry — see
# `_assert_namespaces_bound`.
_CALLER_BOUND = ("site",)


def _assert_namespaces_bound(v: KnowledgeVersion, ctx: dict) -> None:
    """A context that cannot answer a question is a BUG, not a "no".

    `MissingField` means *the user did not tell us*, and the correct response is
    "not applicable" — that is the hook the whole site-conditions design leans
    on. But it cannot distinguish that from *the caller forgot to bind the
    namespace at all*, and the two need opposite treatments: the first is a fact
    about the project, the second is a fact about our code.

    `SiteConditions.facts()` returns `{}` — never absence — for a project that
    answered nothing, so `"site" in ctx` separates them cleanly. Without this
    check, a resolution path that never received `site` silently evaluates every
    site-conditioned rule as not-applicable and produces a plausible fence built
    to rules that never fired. That is exactly how the impact preview came to
    report "this rule costs nothing" for a rule that relays the whole fence.

    Raising rather than warning is deliberate: no project data can cause it, only
    a call site we wrote, so it is a build error in the same sense a disagreeing
    tie between two authored rules is.
    """
    for ns in _CALLER_BOUND:
        if ns in ctx:
            continue
        if any(p.startswith(f"{ns}.") for p in field_paths(v.condition)):
            raise GenerationFailure(
                f"{v.ref} conditions on '{ns}.*' but the evaluation context has no "
                f"'{ns}' namespace — the caller did not bind it",
                constraint_refs=[v.ref],
            )


def _beats(a: KnowledgeVersion, b: KnowledgeVersion) -> bool:
    """Strict structural win of a over b (silently resolvable, but recorded)."""
    if a.effective_authority() != b.effective_authority():
        return a.effective_authority() < b.effective_authority()
    if b.object_id in a.overrides_objects:
        return True
    if a.specificity() != b.specificity():
        return a.specificity() > b.specificity()
    if a.object_id == b.object_id and a.version != b.version:
        return a.version > b.version
    return False


# What a firing SAYS about the slot being resolved, as one comparable value.
# `resolve` is generic over params, tokens and action kinds and cannot read a
# value out of a `Firing` itself, so the caller that narrowed the firings to a
# slot supplies the reader. `None` means "this slot has no comparable value" —
# `resolve_actions` resolves shapes, not numbers — and then no pair can ever
# agree, which is exactly the pre-existing behaviour for those kinds.
Stated = Callable[[Firing], object]


def resolve(
    firings: list[Firing], key: str, *, stated: Stated | None = None
) -> Resolution:
    """Pick a winner among firings that all target the same param/action slot.

    Ties are surfaced as Conflicts (never silent); a tie between hard-authority
    contenders with disagreeing outputs raises GenerationFailure (knowledge-system.md)
    — but only when both contenders are `authored`. See `KnowledgeVersion.origin`.

    AGREEMENT IS PAIRWISE, and it has to be asked here rather than handed in.
    This used to take one `values_agree: bool` computed by the caller over the
    WHOLE set of firings, and that boolean then decided, for every pair, whether
    the loser had been beaten or had merely said the same thing. One dissenting
    row therefore turned every agreeing row into a defeat: five published rows,
    four stating 1800 and one stating 1500, produced four `defeated_by` edges and
    four `hard=True` conflicts — review tasks telling a publisher that two of
    their byte-identical rows contradict each other. That is `e291d4b`'s
    *"a contest that never happened"* reintroduced one level up, and `38a2c6b`'s
    milli tightening made it strictly easier to reach: 0.2 mm between any two
    rows now flips the flag for all of them.

    So `stated` answers the question per pair, against the CURRENT winner. The
    ladder above it is untouched: WHICH rule wins is `_beats` and only `_beats`,
    and this decides nothing but corroborate-vs-defeat for a rule that already
    tied.
    """
    if not firings:
        return Resolution(winner=None, firings=[], conflicts=[])
    contenders = list(firings)
    winner = contenders[0]
    conflicts: list[Conflict] = []
    for other in contenders[1:]:
        if _beats(winner.version, other.version):
            other.defeated_by.append(winner.version.ref)
        elif _beats(other.version, winner.version):
            winner.defeated_by.append(other.version.ref)
            winner = other
        elif stated is not None and stated(other) == stated(winner):
            # DMN ANY: agreement, no conflict — and no defeat either. `other`
            # was never beaten by `winner`; it independently said the same
            # thing, and the graph must say so rather than call it a loser.
            # Asked of THIS pair, not of the set: a third row disagreeing with
            # both of them is a fact about that row, not about these two.
            other.corroborated_by.append(winner.version.ref)
        else:
            if (
                winner.version.effective_authority() <= HARD_AUTHORITY_MAX
                and other.version.effective_authority() <= HARD_AUTHORITY_MAX
                # ...and both are OURS. A tie between two rules we wrote is a
                # build error someone here can go and fix. A tie involving a
                # PUBLISHED row is neither our bug nor fixable here, and the
                # exposure scales with adoption: our expansion puts published
                # rows at authority 1 (structural) or 3 (everything else), so
                # both branches sit inside this band. Raising there would fail a
                # run over a gap, which contract §3.2.4 forbids — it becomes the
                # Conflict below: a warned line and a review task.
                and winner.version.origin == "authored"
                and other.version.origin == "authored"
            ):
                raise GenerationFailure(
                    f"hard knowledge conflict on '{key}': {winner.version.ref} vs "
                    f"{other.version.ref} tie with disagreeing outputs",
                    constraint_refs=[winner.version.ref, other.version.ref],
                )
            hard = (winner.version.effective_authority() <= HARD_AUTHORITY_MAX
                    and other.version.effective_authority() <= HARD_AUTHORITY_MAX)
            conflicts.append(
                Conflict(
                    param_or_action=key,
                    contenders=[winner.version.ref, other.version.ref],
                    message=(
                        f"'{key}': {winner.version.ref} and {other.version.ref} tie on "
                        "authority and scope; using the former — review required"
                    ),
                    hard=hard,
                )
            )
            other.defeated_by.append(winner.version.ref)
    return Resolution(winner=winner, firings=contenders, conflicts=conflicts)


def _param_statement(f: Firing) -> tuple[int, ...]:
    """What this rule states about the slot, in the publisher's thousandths.

    A TUPLE, in the rule's own action order, rather than one number — because a
    firing may carry more than one `set_param` for the same parameter and the
    set-based predicate this replaced silently flattened that. It pooled every
    action of every firing into one set, so a single rule stating both 1800 and
    1500 was indistinguishable from two rules stating one each.

    Ordered, and compared whole, for the reason that decides it: the consumer
    reads the FIRST matching action (`next(a for a in res.winner.actions ...)` in
    `strategy/generator.py`). A rule stating `(1800, 1500)` and one stating
    `(1500, 1800)` therefore build different fences, and a rule stating
    `(1800, 1500)` says something the rule stating `(1800,)` never said. Neither
    pair corroborates: corroboration is the claim that a second source
    independently said the SAME thing, and a source that also said something else
    did not. Falling to `defeated_by` there is the conservative direction — it
    surfaces a conflict for review rather than manufacturing agreement — and it
    is unreachable for every rule in `demo.py`, which state one action per slot.

    `effective_milli()` and not `value`, for `resolve_param`'s own reason: two
    published rows at 2463.8 and 2464.2 both round to 2464 mm and did not agree.
    """
    return tuple(a.effective_milli() for a in f.actions)


def _token_statement(f: Firing) -> tuple[str, ...]:
    """The word form of `_param_statement` — a token has no precision to lose."""
    return tuple(a.value for a in f.actions)


def resolve_param(kb: KnowledgeBase, ctx: dict, param: str) -> Resolution:
    """Resolve a SetParam value with full precedence + conflict surfacing.

    WHICH rule wins is unchanged — `resolve`'s precedence ladder decides that and
    nothing here touches it. What changed is what counts as AGREEMENT, and the
    two are different questions: precedence picks a winner, agreement decides
    whether the losers were beaten (`defeated_by`, a Conflict, possibly a
    `GenerationFailure`) or merely said the same thing (`corroborated_by`, DMN
    ANY, no conflict at all).

    Agreement is measured at `effective_milli()`, not at `value`, because the
    millimetre is no longer the finest thing a consumer reads. Two published rows
    stating `2463.8 mm` and `2464.2 mm` both round to `2464`, so at `value` they
    were judged to agree: no conflict was surfaced, no defeat edge was drawn, one
    of them was recorded as CORROBORATING the other — and `equal_layout_milli`
    then divides by whichever one the precedence ladder happened to return, whose
    last tie-break is `object_id`. That is the alphabet deciding a safety limit,
    which is the very thing the generator's hard-tie handling exists to refuse
    (*"renaming a row would otherwise flip a 1200 mm maximum to 2400 mm and quote
    it"*). Two sources that sent different numbers did not corroborate each other,
    and a graph saying they did is a claim about the sources that is false.

    Tightening this costs nothing today and cannot cost anything for authored
    knowledge: `effective_milli()` is `value * 1000` when nothing published a
    finer number, so mm-agreement and milli-agreement are the same predicate for
    every rule in `demo.py`, for every model `layout_policy` contribution, and
    for any mixture of those with a published row. It can only diverge where two
    contenders actually disagree BELOW the millimetre — which used to be silent
    and is now a Conflict, a warned line and a review task, exactly as §3.2.4
    asks for a disagreement nobody here can fix.

    `resolve_token` keeps `value`: a token is a word from a closed set and has no
    precision to lose.

    And agreement is asked PAIRWISE — `resolve` calls `_param_statement` on the
    two rules that actually tied. Measuring it over the whole set made one
    dissenter erase the agreement between every other pair; see `resolve`.
    """
    relevant: list[Firing] = []
    for f in applicable_firings(kb, ctx):
        acts = [a for a in f.actions if a.kind == "set_param" and a.param == param]
        if acts:
            relevant.append(Firing(version=f.version, actions=acts))
    return resolve(relevant, param, stated=_param_statement)


def resolve_token(kb: KnowledgeBase, ctx: dict, param: str) -> Resolution:
    """Resolve a `SetToken` value — the word form of `resolve_param`.

    Separate from `resolve_param` on purpose. A resolver asking for a length must
    not receive a word, and the two can never compete for one parameter anyway:
    a `ParameterTable` declares `value_type` ONCE, so a parameter is a quantity
    or a token for the whole table. Sharing one function would mean every caller
    branching on the type of the value it got back, which is exactly the cost
    §1.3 puts `value_type` on the table to avoid.
    """
    relevant: list[Firing] = []
    for f in applicable_firings(kb, ctx):
        acts = [a for a in f.actions if a.kind == "set_token" and a.param == param]
        if acts:
            relevant.append(Firing(version=f.version, actions=acts))
    return resolve(relevant, param, stated=_token_statement)


def resolve_actions(
    kb: KnowledgeBase,
    ctx: dict,
    kind: str,
    match: Callable[[Action], bool] | None = None,
) -> Resolution:
    """Resolve action-kind firings for a context.

    `match` narrows to the slot (e.g. only require_mounting actions for THIS surface)
    so rules governing different slots never spuriously compete (critic finding 5).
    """
    relevant = []
    for f in applicable_firings(kb, ctx):
        acts = [a for a in f.actions if a.kind == kind and (match is None or match(a))]
        if acts:
            relevant.append(Firing(version=f.version, actions=acts))
    # No `stated`, deliberately: a mounting requirement or a reinforcement is a
    # shape, not a value, and "these two said the same thing" is not a question
    # this function can answer for them. Nothing here corroborates — which is
    # exactly what the set-level flag did for these kinds too.
    return resolve(relevant, kind)


def preference_firings(kb: KnowledgeBase, ctx: dict, kinds: set[str]) -> list[Firing]:
    """All applicable preference/heuristic firings of the given action kinds.

    Preferences aggregate rather than exclude; precedence applies only when two
    preferences are contradictory for the same slot — handled by the caller per slot.
    """
    out = []
    for f in applicable_firings(kb, ctx):
        acts = [a for a in f.actions if a.kind in kinds]
        if acts:
            out.append(Firing(version=f.version, actions=acts))
    return out
