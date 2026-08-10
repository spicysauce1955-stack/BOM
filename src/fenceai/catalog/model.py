"""Product catalog: products are consumption behavior, not SKU rows (foundation §5)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from fenceai.core.units import Cents, Mm


class Ratio(BaseModel):
    """Exact integer ratio for UoM / coverage conversion (never a bare float)."""

    num: int
    den: int = 1


class IndivisibleDiscrete(BaseModel):
    kind: Literal["indivisible_discrete"] = "indivisible_discrete"


class DivisibleLinear(BaseModel):
    kind: Literal["divisible_linear"] = "divisible_linear"
    purchase_length_mm: Mm
    kerf_mm: Mm = 3
    min_reusable_remnant_mm: Mm = 300


class PackagedDiscrete(BaseModel):
    kind: Literal["packaged_discrete"] = "packaged_discrete"
    engineering_unit: str = "each"
    qty_per_package: int


class CoverageBased(BaseModel):
    kind: Literal["coverage_based"] = "coverage_based"
    engineering_unit: str = "application"
    purchase_unit: str
    qty_per_application: Ratio  # purchase units consumed per application
    application: str  # e.g. "per_post_footing"


class KitComponent(BaseModel):
    sku: str
    qty: int


class AssemblyKit(BaseModel):
    kind: Literal["assembly_kit"] = "assembly_kit"
    components: list[KitComponent] = []


Consumption = Annotated[
    Union[IndivisibleDiscrete, DivisibleLinear, PackagedDiscrete, CoverageBased, AssemblyKit],
    Field(discriminator="kind"),
]


class Product(BaseModel):
    sku: str
    name: str
    name_i18n: dict[str, str] = {}  # optional localized names; empty = fallback to name
    consumption: Consumption
    price_cents: Cents = 0  # per purchase unit
    attrs: dict[str, str | int | bool] = {}

    def display_name(self, lang: str) -> str:
        return self.name_i18n.get(lang) or self.name


class SubstitutionRule(BaseModel):
    id: str
    from_sku: str
    to_sku: str
    policy: Literal["auto", "suggest_only"] = "suggest_only"


class Catalog(BaseModel):
    products: dict[str, Product] = {}
    substitutions: list[SubstitutionRule] = []

    def product(self, sku: str) -> Product:
        return self.products[sku]

    @classmethod
    def of(cls, *products: Product, substitutions: list[SubstitutionRule] | None = None) -> "Catalog":
        return cls(products={p.sku: p for p in products}, substitutions=substitutions or [])
