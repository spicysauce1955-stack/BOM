"""Product catalog: products are consumption behavior, not SKU rows (foundation §5)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from fenceai.core.units import Cents, Mm

_SWATCH = re.compile(r"^#[0-9a-fA-F]{6}$")

# The SHAPE of a Product, as part of what a run's `catalog_hash` means.
#
# The hash is computed over `model_dump()`, so adding a field changes it for
# every product and every previously generated run refuses. That refusal is
# correct — those runs cannot be re-read against a catalog they were not
# resolved against — but `catalog_changed` is the wrong SENTENCE for it: nothing
# was repriced and no product moved, the schema did, and a reader told the
# catalog changed goes looking for a price edit that never happened.
#
# Bump this when Product's shape changes. It buys the honest message; it does
# not avoid the migration, which is deliberate.
CATALOG_SCHEMA_VERSION = "capabilities-v1"


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


class Capabilities(BaseModel):
    """What DETERMINISTIC CODE may read about a product.

    The rule: data consumed by deterministic logic is typed and versioned; data
    used for display, annotation or forward-compatible metadata may stay in the
    open `attrs` bag. A magic string key in Python is the defect —
    `attrs.get("length_mm")` compiles whether or not anything ever sets it, a
    typo is a silent `None`, and by the time it matters the number is on a cut
    list.

    Every field is optional because every one is a fact only SOME products have:
    a rail declares no opening width, a gate kit no face width. `None` means "not
    declared", which each reader answers in its own honest way — the elevation
    draws a flagged nominal, `clear_opening_mm` narrows by nothing, the length
    check measures against no stock.

    Deliberately a flat record rather than a union of capability KINDS. Three
    facts is not a taxonomy, and a union whose variants each hold one integer
    would be machinery around nothing. It becomes one when a capability arrives
    that genuinely carries a different shape.
    """

    # the piece a post is cut from — what `_check_post_lengths` measures against
    length_mm: Mm | None = None
    # the post's extent along the run, as SEEN. The clear opening between two
    # posts is measured to these faces.
    face_width_mm: Mm | None = None
    # the gate opening a kit fits. Catalog DATA, never parsed from a sku.
    opening_width_mm: Mm | None = None


class Product(BaseModel):
    sku: str
    name: str
    name_i18n: dict[str, str] = {}  # optional localized names; empty = fallback to name
    consumption: Consumption
    price_cents: Cents = 0  # per purchase unit; the FLAT basis authors it here
    pricing: Pricing = FlatPrice()
    # Open bag of catalog facts. Three of them are the material drawer's
    # vocabulary — `material`, `finish` and `colour` — and they live HERE rather
    # than in a Python enum because what a product is made of is the catalog's
    # answer, not the code's: a company that stocks bamboo adds a product and a
    # locale word, it does not ship a release. All three are optional, and a
    # product without `material` shows no material row rather than a guessed one.
    # Lists are allowed because some specs genuinely are one: a routed post's
    # hole heights are `[150, 1650]` and no scalar can hold that. Kept in the
    # open bag rather than promoted to a typed field for the same reason the bag
    # exists — an eligibility PREDICATE names the keys it reads, so a company
    # that stocks a new kind of thing adds a product and a rule, not a release.
    #
    # The rule that bounds this: data read by CODE should be typed (a magic
    # string key in Python is the defect); data read by a predicate is data
    # reading data, and belongs here.
    attrs: dict[str, str | int | bool | list[int] | list[str]] = {}
    capabilities: Capabilities = Capabilities()

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

    @model_validator(mode="after")
    def _colour_is_a_swatch(self) -> "Product":
        """`attrs.colour` is not text, it is paint.

        It reaches the client as a CSS `fill` / `background`, and `esc()` does
        nothing for that: escaping makes a string safe to put in an element, not
        safe to hand to the painter, where an arbitrary value is a style the
        catalog author gets to write into the page. `#rrggbb` is the entire
        vocabulary a swatch needs, so it is checked at load — the same rule, for
        the same reason, that `OptionValue.swatch` is checked by
        `validate_model`."""
        colour = self.attrs.get("colour")
        if colour is None:
            return self
        if not isinstance(colour, str) or not _SWATCH.match(colour):
            raise ValueError(
                f"{self.sku}: attrs.colour must be #rrggbb, got {colour!r}"
            )
        return self


def catalog_hash(catalog: "Catalog", skus: list[str] | None = None) -> str:
    """A content hash of the products a run actually depends on.

    `skus=None` hashes the whole catalog, which is what a run stamped before this
    existed did — and which is far too broad: it cannot tell "the product this run
    bought got cheaper" from "somebody added an unrelated gate kit", so ONE price
    edit made every previously generated run's working views refuse.

    Narrowing is safe precisely because eligibility is FROZEN into the run: the
    members a stored run may choose among were recorded when it was generated, so
    a product that did not exist then can never change what it means. What a run
    does depend on is the content of the products it named — a price, a purchase
    length, a kerf, a kit's component list — and those are exactly what this
    covers. Assembly kits are expanded transitively, because a kit's components
    are products a BOM line's notes read.
    """
    wanted = sorted(_expand_kits(catalog, set(skus))) if skus is not None \
        else sorted(catalog.products)
    payload = json.dumps(
        [catalog.products[s].model_dump() for s in wanted if s in catalog.products],
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _expand_kits(catalog: "Catalog", skus: set[str]) -> set[str]:
    out = set(skus)
    stack = list(skus)
    while stack:
        product = catalog.products.get(stack.pop())
        if product is None or not isinstance(product.consumption, AssemblyKit):
            continue
        for component in product.consumption.components:
            if component.sku not in out:
                out.add(component.sku)
                stack.append(component.sku)
    return out


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
