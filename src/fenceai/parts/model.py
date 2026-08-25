"""Parts: a named, versioned, SHARED declaration of what a piece is.

Immutable versions like knowledge objects and fence models (ADR-0006): a run stamps
the part versions it resolved, so editing a part cannot change what an old run meant.

A model names a part by id and NOT by version, which is the whole reason the entity
is shared rather than copied — fixing a rail spec once has to reach every model that
names it. The price is stated in the design doc §2.1 and paid by the impact preview:
an ACTIVE model version no longer means one fixed thing forever.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from fenceai.core.units import Mm

# How an ITEM's declared value must relate to the part's. Authored per part rather
# than derived from the field name (that would put the matching vocabulary in Python,
# which `match.py` refuses) and rather than declared by the type (that would make the
# type a schema and force a release for a company with an unusual dimension). The
# cost, accepted knowingly: two rails may disagree about what `width` means.
Agree = Literal["==", "!=", ">=", "<=", "supplies", "covers", "among", "between"]

# The agreements whose value is a SET the part declares, not a scalar.
_LIST_VALUED = frozenset({"among", "between"})


class SpecField(BaseModel):
    """One declared fact, and how an item must agree with it.

    Reads left to right as a sentence about the ITEM: `item.<key> <agree> <value>`.
    One direction always, because the alternative is an editor where half the rows are
    read forwards and half backwards and the author has to remember which side they
    are standing on.
    """

    key: str
    value: int | str | bool | list[int] | list[str] | None = None
    agree: Agree = "=="
    unit: Literal["mm"] | None = None

    @model_validator(mode="after")
    def _value_matches_agreement(self) -> "SpecField":
        if self.agree == "supplies":
            # A part cannot declare its length. The same rail part serves a 2400 bay
            # and an 1800 one: length is the slot's `length_rule` answering per bay,
            # not a fact about the part. The number is also unavailable when matching
            # runs, so a literal here would be evaluated against the wrong one.
            if self.value is not None:
                raise ValueError(
                    f"{self.key}: `supplies` carries no value — a part cannot declare "
                    "its length, the bay resolves it"
                )
            if self.unit != "mm":
                raise ValueError(f"{self.key}: `supplies` needs unit='mm'")
            return self
        if self.value is None:
            raise ValueError(f"{self.key}: {self.agree} needs a value")
        if self.agree in _LIST_VALUED and not isinstance(self.value, list):
            # The set-valued agreements read the value AS a set, and every python
            # scalar this field accepts is either iterable the wrong way or not
            # iterable at all. `among` with `"white"` compiles to
            # `In(options=['w','h','i','t','e'])` — a part that publishes clean and
            # then matches nothing, on every bay of every job; with an int it raises
            # `TypeError` out of compilation, which reaches the author as a 500.
            # Checked against the constant that names the invariant, so a third
            # set-valued agreement cannot be added without arriving here.
            raise ValueError(
                f"{self.key}: `{self.agree}` takes a LIST of values, got "
                f"{type(self.value).__name__}"
            )
        if self.agree == "between":
            if (len(self.value) != 2 or not all(isinstance(v, int) for v in self.value)):
                raise ValueError(f"{self.key}: `between` takes exactly two ints")
        return self


def is_dimension(f: SpecField) -> bool:
    """A dimension is not a type — it is what falls out when three fields line up.

    `unit` says the value is a measurement rather than a token. `agree` says whether
    the part's number and the item's number are the SAME number: under `==` they are,
    so "the part's width" is well defined; under `>=` or `between` it is not, because
    those are floors and ranges on the item and the part has no such dimension of its
    own. `key` says which measurement, and is the only part code knows by name.
    """
    return f.unit == "mm" and f.agree == "==" and isinstance(f.value, int)


# The separator that turns a container's slot key and a contained piece's own key
# into ONE addressable identity. Declared here, beside the type that creates the
# need for it, and imported by everything that builds or reads a path.
#
# `/` and not `.`: `.` is already the separator `parts.resolve.part_requirements`
# uses for a VARIANT's validation key (`variant0.rail`), which is a different
# namespace with different rules, and one character meaning two things is how a
# reader ends up parsing the wrong tree. `/` also survives an HTML attribute, a
# `data-slot` selector and the `kind:slot_key:index` handle ids `panel-canvas-geom.js`
# builds, none of which is true of every punctuation mark.
PATH_SEP = "/"


def contained_path(container_key: str, contained_key: str) -> str:
    """The one place a path key is spelled. Both callers — the resolver that
    creates the slot and the validator that checks a credit names a real one —
    go through it, so a path can never be built two ways."""
    return f"{container_key}{PATH_SEP}{contained_key}"


class ContainedPart(BaseModel):
    """A piece that ships INSIDE another piece.

    A gate kit arrives with its hinges in the box; a post cap assembly arrives
    with its screw. Those pieces are members of the panel — a fitter places them,
    obligation 9 counts them — and they are NOT purchases, because the thing that
    was bought is the container. Containment is exactly where "what you buy" and
    "what you place" stop being the same list, which is why the contract names it
    ("every one of its members ... including parts contained inside other parts").

    Declared on the PART and not on the model's slot, for the reason
    `PartRequirement._part_or_authored` already enforces one level up: what a
    piece IS belongs to the part, and two models naming one gate kit must not be
    able to disagree about what is in the box. What a contained piece is USED FOR
    in a particular panel is a different fact and lives on the model, as
    `PartRequirement.credits`.

    `part_id` is unpinned exactly as `PartRequirement.part_id` is, and for the
    same reason: fixing a hinge spec once has to reach every kit that ships one.

    `role` is authored ONLY when no part is named. A contained piece that names a
    part takes its role from that part, because the part is the one authority on
    what a piece is — the same rule, in the same words, that a slot obeys.
    """

    key: str
    part_id: str = ""
    role: str = ""
    qty: int = Field(default=1, ge=1)
    # Nesting is real and is not decoration: a kit ships a hinge, and the hinge
    # ships its own pin. The path key composes, so depth costs the readers
    # nothing — `gate_kit/hinge/pin` is one string like every other slot key.
    contains: list["ContainedPart"] = []

    @model_validator(mode="after")
    def _key_cannot_forge_a_path(self) -> "ContainedPart":
        if not self.key:
            raise ValueError("a contained part needs a key — it is its identity")
        if PATH_SEP in self.key:
            raise ValueError(
                f"contained part key {self.key!r} contains {PATH_SEP!r}, which is "
                "the path separator — a key that spells its own path can collide "
                "with a sibling's descendant and address two different pieces"
            )
        said = [name for name, authored in (
            ("role", bool(self.role)), ("contains", bool(self.contains)),
        ) if authored]
        if self.part_id and said:
            # The same refusal `PartRequirement._part_or_authored` makes, one
            # level down and for the same reason: `parts.resolve` OVERWRITES both
            # from the named part, so a document carrying either was accepted,
            # validated clean, and then silently had the authored half deleted.
            # Assignment is deliberately unvalidated (pydantic's default), which
            # is what lets resolution write the resolved answer onto a copy.
            raise ValueError(
                f"contained part {self.key!r} names part {self.part_id!r} and also "
                f"authors {', '.join(said)} — the part is the one authority on "
                "what a piece is, and resolution would overwrite what is written here"
            )
        seen: set[str] = set()
        for child in self.contains:
            if child.key in seen:
                raise ValueError(
                    f"contained part {self.key!r} holds two pieces called "
                    f"{child.key!r}, so one path would name both"
                )
            seen.add(child.key)
        return self


def walk_contained(
    contains: list[ContainedPart], container_key: str
) -> list[tuple[str, ContainedPart]]:
    """Every piece inside a container, at every depth, under its path key.

    Depth-first in authored order, which is what makes the resolved slot list
    deterministic: `resolve_supply` groups on member signatures and the whole run
    digest rests on the same answer coming back twice.
    """
    return [(path, piece) for path, piece, _ in
            walk_contained_qty(contains, container_key, 1)]


def walk_contained_qty(
    contains: list[ContainedPart], container_key: str, factor: int
) -> list[tuple[str, ContainedPart, int]]:
    """The same walk, carrying the running MULTIPLICATION.

    Two kits each holding two hinges are four hinges, and a hinge holding two
    washers makes eight — the count of a piece is its own quantity times every
    container above it. `factor` is the container's resolved quantity at the
    root of the walk.

    This is the one place that arithmetic lives. `resolve._flatten` builds the
    panel's members from it and `resolve._plan_credits` sizes a credit from it,
    and those two numbers MUST be the same number: a credit sized from a second
    copy of this multiplication could hand back more pieces than the box holds,
    which is the phantom saving the whole feature exists to refuse.
    """
    out: list[tuple[str, ContainedPart, int]] = []
    for child in contains:
        path = contained_path(container_key, child.key)
        qty = factor * child.qty
        out.append((path, child, qty))
        out += walk_contained_qty(child.contains, path, qty)
    return out


class PartType(BaseModel):
    """The filing vocabulary, shared by parts and products.

    An entity rather than a bare string because "rails" needs a Hebrew label and a
    free string has nowhere to put one; data rather than a Python enum because a
    company that stocks a new kind of thing adds a row, not a release.
    """

    key: str
    label_i18n: dict[str, str] = {}

    def label(self, lang: str) -> str:
        return self.label_i18n.get(lang) or self.label_i18n.get("en") or self.key


class Part(BaseModel):
    id: str
    version: int
    status: Literal["draft", "active", "retired"] = "active"
    type: str
    name_i18n: dict[str, str] = {}
    spec: list[SpecField] = []
    # What ships inside one of these. Empty is the ordinary case and means "this
    # piece is just itself" — not "unknown", which is why nothing infers
    # containment from a product's `AssemblyKit.components`: a kit's component
    # list is what the BOM note prints, and reading it as a panel's members would
    # credit the panel for hinges no model ever asked it to place.
    contains: list[ContainedPart] = []

    @model_validator(mode="after")
    def _contained_keys_are_unique(self) -> "Part":
        seen: set[str] = set()
        for child in self.contains:
            if child.key in seen:
                raise ValueError(
                    f"{self.id}: holds two pieces called {child.key!r}, so one "
                    "path would name both"
                )
            seen.add(child.key)
        return self

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"

    def display_name(self, lang: str) -> str:
        return self.name_i18n.get(lang) or self.name_i18n.get("en") or self.id

    @property
    def dimensions(self) -> dict[str, Mm]:
        """Derived, never stored (CLAUDE.md: read models are derived).

        A stored dimension beside the spec field producing it would be two
        authorities over one number and eventually two answers — the exact defect
        having the width on the slot AND a sku on the slot used to be.
        """
        return {f.key: f.value for f in self.spec if is_dimension(f)}

    @property
    def width_mm(self) -> Mm | None:
        return self.dimensions.get("width_mm")

    @property
    def thickness_mm(self) -> Mm | None:
        return self.dimensions.get("thickness_mm")


class PartLibrary(BaseModel):
    parts: list[Part] = []

    def latest_active(self, part_id: str) -> Part | None:
        found = [p for p in self.parts if p.id == part_id and p.status == "active"]
        return max(found, key=lambda p: p.version) if found else None

    def by_ref(self, part_id: str, version: int) -> Part | None:
        for p in self.parts:
            if p.id == part_id and p.version == version:
                return p
        return None
