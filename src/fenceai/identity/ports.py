"""What a signed-in person IS, before anything decides what they may do.

Two layers, kept apart on purpose. A provider answers *who is this* from
whatever the transport carries — a signed assertion from Google, a cookie on a
laptop. It answers nothing about permission: the `users` table does that, and
the whole point of this slice is that Google holds the identity and we hold the
capacity.

The signature takes mappings rather than a `Request` so both implementations
are testable without FastAPI — the same split `base-top.js` and `session.js`'s
`applyMe` make on the frontend.
"""

from __future__ import annotations

from typing import Mapping, Protocol

from pydantic import BaseModel, field_validator


class Principal(BaseModel):
    """A verified identity. NOT an account — there may be no row for it."""

    email: str
    #: Google's stable `sub` claim. Empty from a provider that has no Google
    #: behind it, which `binding.bind` treats as "nothing to bind" rather than
    #: as a subject of its own.
    subject: str = ""

    @field_validator("email")
    @classmethod
    def _normalised(cls, v: str) -> str:
        """Stripped and lower-cased HERE, the way `User._normalised` does it.
        The two halves of one lookup have to agree on the spelling, or a row
        written by one casing is unreachable from the other."""
        return v.strip().lower()


class IdentityProvider(Protocol):
    provider_id: str

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        """Who is this request, or None. Never raises for an absent identity —
        "nobody" is an ordinary answer that the gate turns into a refusal."""
        ...
