"""Bilingual display names (UI v2 §4): optional name_i18n/title_i18n maps with
fallback to the canonical name/title. SKUs and object ids stay Latin.
"""

from __future__ import annotations

from fenceai.catalog.demo import demo_catalog
from fenceai.catalog.model import Product
from fenceai.knowledge.demo import demo_knowledge
from fenceai.knowledge.model import KnowledgeVersion


def test_demo_catalog_hebrew_names_with_fallback():
    catalog = demo_catalog()
    rail = catalog.product("RAIL-3000")
    assert rail.display_name("he") == 'מוט מסילה 3000 מ"מ'
    assert rail.display_name("en") == "Rail stock 3000 mm"
    assert rail.display_name("fr") == "Rail stock 3000 mm"  # fallback to name
    assert catalog.product("POST-S").display_name("he") == "עמוד קרקע"
    assert catalog.product("GATE-KIT-1000").display_name("he") == 'ערכת שער 1000 מ"מ'


def test_every_demo_product_has_a_hebrew_name():
    for sku, product in demo_catalog().products.items():
        assert product.name_i18n.get("he"), f"{sku} missing Hebrew name"


def test_demo_knowledge_hebrew_titles_with_fallback():
    kb = demo_knowledge()
    maxspan = next(v for v in kb.versions if v.object_id == "K-MAXSPAN")
    assert maxspan.display_title("he") == 'מפתח מרבי 1800 מ"מ (יצרן)'
    assert maxspan.display_title("fr") == "Manufacturer max span 1800 mm"  # fallback
    equal = next(v for v in kb.versions if v.object_id == "K-EQUAL")
    assert equal.display_title("he") == "העדפת מפתחים שווים"
    for v in kb.versions:
        assert v.title_i18n.get("he"), f"{v.object_id} missing Hebrew title"


def test_i18n_fields_are_optional_and_additive():
    p = Product(sku="X", name="Plain", consumption={"kind": "indivisible_discrete"})
    assert p.name_i18n == {}
    assert p.display_name("he") == "Plain"
    v = KnowledgeVersion(object_id="K-X", version=1, type="fact", title="Plain title")
    assert v.title_i18n == {}
    assert v.display_title("he") == "Plain title"


def test_empty_string_translation_falls_back():
    from fenceai.catalog.model import IndivisibleDiscrete, Product

    p = Product(sku="X", name="Plain", consumption=IndivisibleDiscrete(),
                name_i18n={"he": ""})
    assert p.display_name("he") == "Plain"  # empty string is not a translation
