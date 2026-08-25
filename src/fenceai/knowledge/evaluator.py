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
    defeated_by: list[str] = field(default_factory=list)  # refs of winners


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


def resolve(firings: list[Firing], key: str, *, values_agree: bool = False) -> Resolution:
    """Pick a winner among firings that all target the same param/action slot.

    Ties are surfaced as Conflicts (never silent); a tie between hard-authority
    contenders with disagreeing outputs raises GenerationFailure (knowledge-system.md)
    — but only when both contenders are `authored`. See `KnowledgeVersion.origin`.
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
        elif values_agree:
            other.defeated_by.append(winner.version.ref)  # DMN ANY: agreement, no conflict
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


def resolve_param(kb: KnowledgeBase, ctx: dict, param: str) -> Resolution:
    """Resolve a SetParam value with full precedence + conflict surfacing."""
    relevant: list[Firing] = []
    for f in applicable_firings(kb, ctx):
        acts = [a for a in f.actions if a.kind == "set_param" and a.param == param]
        if acts:
            relevant.append(Firing(version=f.version, actions=acts))
    same_value = len({a.value for f in relevant for a in f.actions}) <= 1
    return resolve(relevant, param, values_agree=same_value)


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
