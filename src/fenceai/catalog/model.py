"""Product catalog: products are consumption behavior, not SKU rows (foundation §5)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

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


class FlatPrice(BaseModel):
    """One price per purchase unit — a post, a box of screws, a whole bar."""

    kind: Literal["flat"] = "flat"


class LinearPrice(BaseModel):
    """Priced by the running metre (₪/מטר רץ), which is how bar stock is quoted.

    This is a way of AUTHORING the purchase price, not a second pricing basis for
    the BOM to carry: a divisible-linear purchase unit is a whole bar of known
    length, so one bar's price falls out of the rate. Per-m² and per-band pricing
    do NOT fall out this way — `fulfill()` emits one line per SKU with a single
    `unit_price_cents`, and two bays of one panel SKU at different heights priced
    per m² collapse into a line no single unit price can total. They need
    `fulfill()` grouping per (sku, price_basis, size) first, and the spec says so
    rather than pretending.
    """

    kind: Literal["linear"] = "linear"
    cents_per_m: Cents


Pricing = Annotated[Union[FlatPrice, LinearPrice], Field(discriminator="kind")]


class Product(BaseModel):
    sku: str
    name: str
    name_i18n: dict[str, str] = {}  # optional localized names; empty = fallback to name
    consumption: Consumption
    price_cents: Cents = 0  # per purchase unit; the FLAT basis authors it here
    pricing: Pricing = FlatPrice()
    attrs: dict[str, str | int | bool] = {}

    def display_name(self, lang: str) -> str:
        return self.name_i18n.get(lang) or self.name

    @model_validator(mode="after")
    def _one_price(self) -> "Product":
        """Two fields that can each claim to be the price is a lie waiting to
        happen — the same reason an eligibility member declares no consumption
        semantics of its own. A rate-priced product carries no flat price, and a
        rate needs a purchase length to be a price of anything."""
        if self.pricing.kind == "flat":
            return self
        if self.price_cents:
            raise ValueError(
                f"{self.sku}: priced by the metre, so price_cents must be 0 — "
                "two prices cannot both be the price"
            )
        if not isinstance(self.consumption, DivisibleLinear):
            raise ValueError(
                f"{self.sku}: priced by the metre, but it is not bought by the "
                f"length ({self.consumption.kind}), so a rate prices nothing"
            )
        return self


def purchase_price_cents(product: Product) -> Cents:
    """What ONE purchase unit costs. The single place a price is read.

    THE rounding point for rate pricing (ADR-0002): integer arithmetic, rounded
    half-up once, here. Nothing upstream rounds and nothing downstream re-rounds,
    or two call sites differ by a cent and the same BOM totals two ways.
    """
    if product.pricing.kind == "flat":
        return product.price_cents
    length_mm = product.consumption.purchase_length_mm  # type: ignore[union-attr]
    return (product.pricing.cents_per_m * length_mm + 500) // 1000


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
