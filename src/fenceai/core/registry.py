"""A named-function registry — the mechanism behind the first extension seam.

`docs/superpowers/specs/2026-08-25-engine-architecture.md` §3 states the rule
this exists to move things across:

> A vocabulary is **open** when a general mechanism reads it, and **closed** when
> `if kind == "…"` branches on it somewhere.

Fixing bases, length rules and objective presets were all closed: a `Literal`
naming the members, plus a branch somewhere that knew what each one meant. Adding
`per_corner` meant editing the type, editing the branch, and shipping a release —
while adding a part type, a knowledge rule or a warning code was a row in a table.
Nothing about the *concepts* makes a fixing basis harder to extend than a part
type. One was data; the other was a branch.

**The escalation test** (§4 of the same spec), which is what a registry is FOR:

> Can the new thing be written as a function with the EXISTING signature?
>
> **Yes** → register it. Configuration. No release.
> **No** → it needs a new shape, so it is a release — and until that release it
> is published as a `Gap`.

So a registry is deliberately not a plugin system. It holds one signature, and
the signature is the contract: a `per_corner` basis is `(counts) -> int` like
every other and registers; a basis that must see the neighbouring bay cannot be
written that way, and that is the signal that it needs a release rather than a
row.

**Registration refuses to overwrite.** A silent override is the failure this type
would otherwise introduce: two modules registering `per_member`, the winner
decided by import order, and a fence quietly counted by whichever one loaded
last. Re-registering the *same* function is fine — that is an idempotent import,
not a conflict.
"""

from __future__ import annotations

from typing import Callable, Generic, Iterable, TypeVar

F = TypeVar("F", bound=Callable)


class Registry(Generic[F]):
    """Named implementations of ONE signature.

    `kind` names what is being registered, and is used in error messages: an
    author who typed a basis that does not exist is told what the thing was and
    what the alternatives are, not merely that a key was missing.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._fns: dict[str, F] = {}

    def register(self, name: str) -> Callable[[F], F]:
        """Decorator form: `@REGISTRY.register("per_member")`."""

        def bind(fn: F) -> F:
            self.add(name, fn)
            return fn

        return bind

    def add(self, name: str, fn: F) -> None:
        existing = self._fns.get(name)
        if existing is not None and existing is not fn:
            raise ValueError(
                f"{self.kind} {name!r} is already registered by "
                f"{getattr(existing, '__module__', '?')}; two implementations of one "
                "name would be resolved by import order"
            )
        self._fns[name] = fn

    def get(self, name: str) -> F:
        try:
            return self._fns[name]
        except KeyError:
            raise KeyError(
                f"unknown {self.kind} {name!r}; registered: {', '.join(self.names())}"
            ) from None

    def names(self) -> list[str]:
        """Sorted, because THIS reaches an error message: it is interpolated into
        the refusal an author sees, and an order that varied with import order
        would make the same mistake read differently on two machines."""
        return sorted(self._fns)

    def declared(self) -> list[str]:
        """Registration order, because THIS reaches a select.

        The sequence a vocabulary is declared in is an editorial judgement —
        `clear_between_posts` first because it is what most rails are, `per_panel`
        last because it is the coarsest — and alphabetising a dropdown discards it
        silently. `names()` and this are not redundant: one answers *"what could
        you have meant?"* after a mistake, where a stable order is the whole
        point, and the other answers *"what may I choose?"* before one, where the
        author's ordering is information.
        """
        return list(self._fns)

    def __contains__(self, name: object) -> bool:
        return name in self._fns

    def __iter__(self) -> Iterable[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self._fns)
