"""Shared demo catalog — the one defined in docs/scenarios/golden-scenarios.md.

`material` and `finish` are drawn from a small closed vocabulary — material:
aluminium | steel | galvanised_steel | composite | cedar | concrete; finish:
powder_coated | anodised | mill | stained | raw — closed because every value has
to have a word in both locale bundles before a Hebrew reader can be shown it
(`tests/web/test_locale_bundles.py` derives the check from THIS catalog, so a
product with a new material fails the suite rather than shipping an English word
into a Hebrew UI). Nothing in code enumerates them: the vocabulary is data, and a
company that stocks bamboo adds a product and two locale words.

LATCH deliberately declares none of the three. A product with no material is
ordinary, and the drawer must show no material row rather than guess one — a demo
catalog where every product happened to have one would leave that path untested
by the thing people actually click.
"""

from __future__ import annotations

from fenceai.catalog.model import (
    AssemblyKit,
    Capabilities,
    Catalog,
    CoverageBased,
    DivisibleLinear,
    IndivisibleDiscrete,
    KitComponent,
    PackagedDiscrete,
    Product,
    Ratio,
    SubstitutionRule,
)


def demo_catalog() -> Catalog:
    return Catalog.of(
        Product(sku="POST-S", name="Ground post (soil)", name_i18n={"he": "עמוד קרקע"},
                consumption=IndivisibleDiscrete(), price_cents=2500,
                # face_width_mm is the post as SEEN in elevation, which is not
                # its length and not derivable from anything else here: the macro
                # drawing needs it to draw a post at its real width instead of a
                # nominal band. A product without it still draws (nominal, and
                # said so), which is why it is an attr and not a required field.
                attrs={"material": "galvanised_steel", "finish": "mill",
                       "colour": "#9ca3af"}, capabilities=Capabilities(length_mm=2600, face_width_mm=80)),
        Product(sku="POST-S-HD", name="Heavy-duty ground post", name_i18n={"he": "עמוד מחוזק"},
                consumption=IndivisibleDiscrete(), price_cents=4200,
                attrs={"material": "galvanised_steel", "finish": "powder_coated",
                       "colour": "#374151"}, capabilities=Capabilities(length_mm=2600, face_width_mm=100)),
        Product(sku="POST-M", name="Masonry post/bracket", name_i18n={"he": "עמוד קיר"},
                consumption=IndivisibleDiscrete(), price_cents=3100,
                attrs={"material": "steel",
                       "finish": "powder_coated", "colour": "#374151"}, capabilities=Capabilities(face_width_mm=60)),
        Product(sku="POST-CAP", name="Post cap", name_i18n={"he": "כיפת עמוד"},
                consumption=IndivisibleDiscrete(), price_cents=300,
                attrs={"material": "aluminium", "finish": "powder_coated",
                       "colour": "#374151"}),
        Product(
            sku="RAIL-3000",
            name="Rail stock 3000 mm",
            name_i18n={"he": 'מוט מסילה 3000 מ"מ'},
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3, min_reusable_remnant_mm=300),
            price_cents=1800,
            attrs={"material": "aluminium", "finish": "mill", "colour": "#cbd5e1"},
        ),
        Product(
            # A different PROFILE, not a different length of the same one: the
            # bottom member of M-SLAT@v2 is a U-channel the slats seat into, and
            # its face height (60 mm) and 20 mm housing are properties of the
            # section. Giving the rail a second face height on the slot that
            # happened to need one would have made a single SKU 40 mm tall in
            # one panel and 60 mm in another, and the cut length depends on it.
            sku="CHANNEL-3000",
            name="U-channel 3000 mm",
            name_i18n={"he": 'תעלת U 3000 מ"מ'},
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3,
                                        min_reusable_remnant_mm=300),
            price_cents=2400,
        ),
        Product(
            sku="SLAT-100",
            name="Slat 100 mm (6000 mm stock)",
            name_i18n={"he": 'שלב 100 מ"מ (מוט 6000)'},
            # 6 m is the stock length the profile actually arrives in, and it is
            # chosen against the piece M-SLAT cuts from it rather than against a
            # round number: `plan_cuts` charges every piece its kerf against
            # (stock + kerf), so an 1800 mm slat costs 1803 and three of them
            # (5409) fit 6003 where four (7212) do not. The 591 mm tail then
            # clears min_reusable_remnant_mm, so a 20-slat bay plans seven bars
            # with a reusable end on each rather than seven offcuts of scrap:
            # this product exercises the remnant path instead of leaving it dead.
            consumption=DivisibleLinear(purchase_length_mm=6000, kerf_mm=3,
                                        min_reusable_remnant_mm=300),
            price_cents=5400,
            attrs={"material": "cedar", "finish": "stained", "colour": "#8b5e34"},
        ),
        Product(
            sku="SCREW-S10",
            name="Screw S10 (box of 20)",
            name_i18n={"he": "בורג S10 (קופסה של 20)"},
            consumption=PackagedDiscrete(qty_per_package=20),
            price_cents=450,
            attrs={"material": "steel", "finish": "mill", "colour": "#6b7280"},
        ),
        Product(
            sku="CONC-25",
            name="Concrete bag 25 kg",
            name_i18n={"he": 'שק בטון 25 ק"ג'},
            consumption=CoverageBased(
                purchase_unit="bag",
                qty_per_application=Ratio(num=1, den=2),  # 0.5 bag per soil post footing
                application="per_post_footing",
            ),
            price_cents=800,
            attrs={"material": "concrete", "finish": "raw", "colour": "#94a3b8"},
        ),
        Product(
            sku="GATE-KIT-1000",
            name="Gate assembly 1000 mm",
            name_i18n={"he": 'ערכת שער 1000 מ"מ'},
            consumption=AssemblyKit(
                components=[
                    KitComponent(sku="GATE-LEAF-1000", qty=1),
                    KitComponent(sku="HINGE-SET", qty=1),
                    KitComponent(sku="LATCH", qty=1),
                ]
            ),
            price_cents=18500,
            # the opening this kit fits: fit is catalog DATA, never parsed from the sku
            attrs={"category": "gate", "material": "aluminium", "finish": "powder_coated",
                   "colour": "#374151"}, capabilities=Capabilities(opening_width_mm=1000),
        ),
        Product(sku="GATE-LEAF-1000", name="Gate leaf 1000 mm", name_i18n={"he": 'כנף שער 1000 מ"מ'},
                consumption=IndivisibleDiscrete(), price_cents=12000,
                attrs={"material": "aluminium", "finish": "powder_coated",
                       "colour": "#374151"}),
        Product(sku="HINGE-SET", name="Hinge set", name_i18n={"he": "סט צירים"},
                consumption=IndivisibleDiscrete(), price_cents=2200,
                attrs={"material": "aluminium", "finish": "anodised",
                       "colour": "#d1d5db"}),
        # no material, no finish, no colour: the ordinary case the drawer must
        # leave blank rather than guess at
        Product(sku="LATCH", name="Latch", name_i18n={"he": "בריח"},
                consumption=IndivisibleDiscrete(), price_cents=1400),
        substitutions=[
            SubstitutionRule(id="sub_post_hd", from_sku="POST-S", to_sku="POST-S-HD", policy="suggest_only"),
        ],
    )
