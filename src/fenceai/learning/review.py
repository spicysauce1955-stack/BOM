"""Candidate review: the only path from proposal to active knowledge.

Nothing proposed is ever evaluated; approval is always a recorded human act
(knowledge-system.md learning loop; Research D anti-patterns).
"""

from __future__ import annotations

from fenceai.knowledge.model import KnowledgeVersion
from fenceai.learning.model import ReviewAction

# A promoted rule is no longer a proposal: drop the marker in every language the
# candidate carries one (a Hebrew-only reader must not see an active rule labelled
# as a candidate).
CANDIDATE_MARKERS = (" (candidate)", " (מועמד)")


def _promoted_title(text: str) -> str:
    for marker in CANDIDATE_MARKERS:
        text = text.removesuffix(marker)
    return text


def apply_review(candidate: KnowledgeVersion, action: ReviewAction) -> KnowledgeVersion:
    """Returns the resulting version record. Candidates are immutable: approval
    produces a NEW version (v+1) derived from the candidate; the candidate record
    itself only changes status."""
    if candidate.status != "proposed":
        raise ValueError(f"{candidate.ref} is not a reviewable candidate (status={candidate.status})")

    if action.action == "reject":
        candidate.status = "rejected"  # kept forever: suppresses re-proposal
        return candidate

    scope = candidate.scope
    if action.action == "scope_restrict":
        if not action.edited_scope:
            raise ValueError("scope_restrict requires edited_scope")
        # restriction may only ADD dimensions (narrow) — existing dimensions must
        # keep their values, or a "restriction" could retarget the rule entirely
        # (final architecture review, finding 2)
        if any(action.edited_scope.get(k) != v for k, v in scope.items()):
            raise ValueError("scope_restrict may only narrow the proposed scope")
        if len(action.edited_scope) <= len(scope):
            raise ValueError("scope_restrict must add at least one scope dimension")
        scope = action.edited_scope

    approved = KnowledgeVersion(
        object_id=candidate.object_id,
        version=candidate.version + 1,
        type="heuristic" if candidate.type == "candidate" else candidate.type,
        scope=scope,
        condition=candidate.condition,
        actions=candidate.actions,
        title=_promoted_title(candidate.title),
        title_i18n={
            lang: _promoted_title(text) for lang, text in candidate.title_i18n.items()
        },
        source_text=candidate.source_text,  # verbatim text travels with the promotion
        derived_from=[candidate.ref],
        attributed_to=action.reviewer,
        status="active",
        examples=candidate.examples,
    )
    candidate.status = "retired"
    return approved
