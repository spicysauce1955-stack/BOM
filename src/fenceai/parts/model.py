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

from pydantic import BaseModel, model_validator

from fenceai.core.units import Mm

# How an ITEM's declared value must relate to the part's. Authored per part rather
# than derived from the field name (that would put the matching vocabulary in Python,
# which `match.py` refuses) and rather than declared by the type (that would make the
# type a schema and force a release for a company with an unusual dimension). The
# cost, accepted knowingly: two rails may disagree about what `width` means.
Agree = Literal["==", "!=", ">=", "<=", "supplies", "covers", "among", "between"]

# The agreements whose value is a SET the part declares, not a scalar.
_LIST_VALUED = frozenset({"among", "between"})

# The two keys code knows by name. Everything else is matched and never drawn — the
# rule `Capabilities` already states: data read by CODE is typed and named, data read
# by a predicate stays open.
DRAWN_KEYS = ("width_mm", "thickness_mm")


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
