"""Rule evaluation with native trace emission (ADR-0005).

evaluate() returns every applicable firing; resolve_param()/resolve_actions() apply
precedence (authority tier -> scope specificity -> explicit overrides -> recency),
recording winners, defeated_by, and surfaced conflicts. Ties never resolve silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fenceai.knowledge.ast import MissingField, evaluate_expr
from fenceai.knowledge.model import Action, KnowledgeBase, KnowledgeVersion


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


def resolve(firings: list[Firing], key: str) -> Resolution:
    """Pick a winner among firings that all target the same param/action slot."""
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
        else:
            # tie: surfaced, never silent (knowledge-system.md)
            conflicts.append(
                Conflict(
                    param_or_action=key,
                    contenders=[winner.version.ref, other.version.ref],
                    message=(
                        f"'{key}': {winner.version.ref} and {other.version.ref} tie on "
                        "authority and scope; using the former — review required"
                    ),
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
    res = resolve(relevant, param)
    if same_value:
        res.conflicts = []  # agreeing outputs are not conflicts (DMN ANY semantics)
    return res


def resolve_actions(kb: KnowledgeBase, ctx: dict, kind: str) -> Resolution:
    """Resolve action-kind firings (e.g. require_mounting) for a context."""
    relevant = []
    for f in applicable_firings(kb, ctx):
        acts = [a for a in f.actions if a.kind == kind]
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
