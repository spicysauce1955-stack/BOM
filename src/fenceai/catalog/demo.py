"""Shared demo catalog — the one defined in docs/scenarios/golden-scenarios.md."""

from __future__ import annotations

from fenceai.catalog.model import (
    AssemblyKit,
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
                attrs={"length_mm": 2600}),
        Product(sku="POST-S-HD", name="Heavy-duty ground post", name_i18n={"he": "עמוד מחוזק"},
                consumption=IndivisibleDiscrete(), price_cents=4200,
                attrs={"length_mm": 2600}),
        Product(sku="POST-M", name="Masonry post/bracket", name_i18n={"he": "עמוד קיר"},
                consumption=IndivisibleDiscrete(), price_cents=3100),
        Product(sku="POST-CAP", name="Post cap", name_i18n={"he": "כיפת עמוד"},
                consumption=IndivisibleDiscrete(), price_cents=300),
        Product(
            sku="RAIL-3000",
            name="Rail stock 3000 mm",
            name_i18n={"he": 'מוט מסילה 3000 מ"מ'},
            consumption=DivisibleLinear(purchase_length_mm=3000, kerf_mm=3, min_reusable_remnant_mm=300),
            price_cents=1800,
        ),
        Product(
            sku="SCREW-S10",
            name="Screw S10 (box of 20)",
            name_i18n={"he": "בורג S10 (קופסה של 20)"},
            consumption=PackagedDiscrete(qty_per_package=20),
            price_cents=450,
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
            attrs={"category": "gate", "opening_width_mm": 1000},
        ),
        Product(sku="GATE-LEAF-1000", name="Gate leaf 1000 mm", name_i18n={"he": 'כנף שער 1000 מ"מ'},
                consumption=IndivisibleDiscrete(), price_cents=12000),
        Product(sku="HINGE-SET", name="Hinge set", name_i18n={"he": "סט צירים"},
                consumption=IndivisibleDiscrete(), price_cents=2200),
        Product(sku="LATCH", name="Latch", name_i18n={"he": "בריח"},
                consumption=IndivisibleDiscrete(), price_cents=1400),
        substitutions=[
            SubstitutionRule(id="sub_post_hd", from_sku="POST-S", to_sku="POST-S-HD", policy="suggest_only"),
        ],
    )
