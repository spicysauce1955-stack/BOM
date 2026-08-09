"""Shared demo knowledge base — docs/scenarios/golden-scenarios.md."""

from __future__ import annotations

from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.model import (
    DefaultComponent,
    KnowledgeBase,
    KnowledgeVersion,
    PreferEqualSpans,
    PreferMinSpanWidth,
    PreferVertical,
    RequireMounting,
    RequirePostReinforcement,
    SetParam,
)


def demo_knowledge() -> KnowledgeBase:
    return KnowledgeBase(
        versions=[
            KnowledgeVersion(
                object_id="K-MAXSPAN", version=1, type="hard_constraint",
                title="Manufacturer max span 1800 mm",
                actions=[SetParam(param="max_span_mm", value=1800)],
                attributed_to="manufacturer",
            ),
            KnowledgeVersion(
                object_id="K-RAILS", version=1, type="fact",
                title="2 rails per span",
                actions=[SetParam(param="rails_per_span", value=2)],
            ),
            KnowledgeVersion(
                object_id="K-SCREWS", version=1, type="fact",
                title="8 screws per span (2 per rail-end connection)",
                actions=[SetParam(param="screws_per_span", value=8)],
            ),
            KnowledgeVersion(
                object_id="K-MASONRY", version=1, type="hard_constraint",
                title="Masonry base requires masonry mounting",
                actions=[RequireMounting(surface="masonry_wall", mounting="masonry", sku="POST-M")],
            ),
            KnowledgeVersion(
                object_id="K-GATE-REINF", version=1, type="company_rule",
                title="Gates get reinforced posts on both sides",
                actions=[RequirePostReinforcement(context="gate", sku="POST-S-HD")],
            ),
            KnowledgeVersion(
                object_id="K-EQUAL", version=1, type="preference",
                title="Prefer equal span widths",
                actions=[PreferEqualSpans()],
            ),
            KnowledgeVersion(
                object_id="K-SLIVER", version=1, type="preference",
                title="Avoid spans under 500 mm",
                actions=[PreferMinSpanWidth(min_mm=500)],
            ),
            KnowledgeVersion(
                object_id="K-STEP-SLOPE", version=1, type="heuristic",
                title="Steep runs look better stepped (slope > 15%)",
                condition=Cmp(
                    cmp=">", left=FieldRef(path="run.slope_permille"), right=Lit(value=150)
                ),
                actions=[PreferVertical(mode="stepped")],
            ),
            KnowledgeVersion(
                object_id="K-POST-DEFAULT", version=1, type="fact",
                title="Default ground post product",
                actions=[DefaultComponent(role="post_ground", sku="POST-S")],
            ),
        ]
    )
