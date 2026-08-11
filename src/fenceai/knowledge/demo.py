"""Shared demo knowledge base — docs/scenarios/golden-scenarios.md."""

from __future__ import annotations

from fenceai.knowledge.ast import Cmp, FieldRef, Lit
from fenceai.knowledge.model import (
    DefaultComponent,
    KnowledgeBase,
    KnowledgeVersion,
    RuleExample,
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
                title_i18n={"he": 'מפתח מרבי 1800 מ"מ (יצרן)'},
                actions=[SetParam(param="max_span_mm", value=1800)],
                attributed_to="manufacturer",
            ),
            KnowledgeVersion(
                object_id="K-RAILS", version=1, type="fact",
                title="2 rails per span",
                title_i18n={"he": "2 מוטות לכל מפתח"},
                actions=[SetParam(param="rails_per_span", value=2)],
            ),
            KnowledgeVersion(
                object_id="K-SCREWS", version=1, type="fact",
                title="8 screws per span (2 per rail-end connection)",
                title_i18n={"he": "8 ברגים לכל מפתח (2 לכל חיבור קצה מוט)"},
                actions=[SetParam(param="screws_per_span", value=8)],
            ),
            KnowledgeVersion(
                object_id="K-MASONRY", version=1, type="hard_constraint",
                title="Masonry base requires masonry mounting",
                title_i18n={"he": "בסיס בנוי מחייב עיגון קיר"},
                actions=[RequireMounting(surface="masonry_wall", mounting="masonry", sku="POST-M")],
            ),
            KnowledgeVersion(
                object_id="K-GATE-REINF", version=1, type="company_rule",
                title="Gates get reinforced posts on both sides",
                title_i18n={"he": "עמודים מחוזקים משני צידי שער"},
                actions=[RequirePostReinforcement(context="gate", sku="POST-S-HD")],
            ),
            KnowledgeVersion(
                object_id="K-EQUAL", version=1, type="preference",
                title="Prefer equal span widths",
                title_i18n={"he": "העדפת מפתחים שווים"},
                actions=[PreferEqualSpans()],
            ),
            KnowledgeVersion(
                object_id="K-SLIVER", version=1, type="preference",
                title="Avoid spans under 500 mm",
                title_i18n={"he": 'הימנעות ממפתחים צרים מ-500 מ"מ'},
                actions=[PreferMinSpanWidth(min_mm=500)],
            ),
            KnowledgeVersion(
                object_id="K-STEP-SLOPE", version=1, type="heuristic",
                title="Steep runs look better stepped (slope > 15%)",
                title_i18n={"he": "קטעים תלולים נראים טוב יותר במדורג (שיפוע מעל 15%)"},
                condition=Cmp(
                    cmp=">", left=FieldRef(path="run.slope_permille"), right=Lit(value=150)
                ),
                actions=[PreferVertical(mode="stepped")],
                examples=[
                    RuleExample(
                        description="16.7% uphill run steps",
                        ctx={"scope": {}, "run": {"length_mm": 6000, "slope_permille": 167}},
                        expect_applicable=True,
                    ),
                    RuleExample(
                        description="gentle 10% run does not step",
                        ctx={"scope": {}, "run": {"length_mm": 6000, "slope_permille": 100}},
                        expect_applicable=False,
                    ),
                    RuleExample(
                        description="exactly 15.0% stays raked (strict inequality)",
                        ctx={"scope": {}, "run": {"length_mm": 6000, "slope_permille": 150}},
                        expect_applicable=False,
                    ),
                ],
            ),
            KnowledgeVersion(
                object_id="K-STEP-POST", version=1, type="company_rule",
                title="A step of 100 mm or more (base top or ground) needs a post",
                title_i18n={"he": 'מדרגה של 100 מ"מ ומעלה (בראש הבסיס או בקרקע) מחייבת עמוד'},
                actions=[SetParam(param="base_top_step_boundary_mm", value=100)],
            ),
            KnowledgeVersion(
                object_id="K-MAX-STEP", version=1, type="company_rule",
                title="Buildability: a single step may not exceed 600 mm",
                title_i18n={"he": 'כשירות ביצוע: מדרגה בודדת לא תעלה על 600 מ"מ'},
                actions=[SetParam(param="max_panel_step_mm", value=600)],
            ),
            KnowledgeVersion(
                object_id="K-POST-EMBED", version=1, type="fact",
                title="Posts are embedded 600 mm below ground (plumb)",
                title_i18n={"he": 'עמודים מוטמנים 600 מ"מ מתחת לקרקע (אנכיים לחלוטין)'},
                actions=[SetParam(param="post_embed_mm", value=600)],
            ),
            KnowledgeVersion(
                object_id="K-MAX-GAP", version=1, type="company_rule",
                title="Gap under a stepped panel may not exceed 200 mm",
                title_i18n={"he": 'מרווח מתחת לפאנל מדורג לא יעלה על 200 מ"מ'},
                actions=[SetParam(param="max_panel_gap_mm", value=200)],
            ),
            KnowledgeVersion(
                object_id="K-GATE-SLOPE", version=1, type="company_rule",
                title="Gate openings need near-level ground (max 5% across the opening)",
                title_i18n={"he": "פתח שער דורש קרקע כמעט מפולסת (עד 5% לרוחב הפתח)"},
                actions=[SetParam(param="gate_max_slope_permille", value=50)],
            ),
            KnowledgeVersion(
                object_id="K-POST-DEFAULT", version=1, type="fact",
                title="Default ground post product",
                title_i18n={"he": "מוצר ברירת מחדל לעמוד קרקע"},
                actions=[DefaultComponent(role="post_ground", sku="POST-S")],
            ),
        ]
    )
