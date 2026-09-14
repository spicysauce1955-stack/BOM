"""A signed-in browser, for as long as it stays signed in.

Opaque random tokens looked up server-side, not a self-describing token the
server merely validates. The whole reason: signing out has to actually sign out.
A token that carries its own claims stays valid in somebody's pocket until it
expires, so "deactivate this account" and "log this person out" become promises
the server cannot keep. A row you can delete keeps both.

Nothing here is a scheme of our own: `secrets.token_urlsafe` and a row.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

#: How long a session lasts without being used again. Long enough that an office
#: person is not signing in twice a day, short enough that a laptop left at a
#: customer's site stops being a way in. A named constant because the number is
#: a judgement and the next person should see it as one.
SESSION_DAYS = 30

_TOKEN_BYTES = 32


def new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Session(BaseModel):
    """One browser, signed in as one account."""

    token: str
    user_id: str
    created_at: str
    expires_at: str


def start(user_id: str, *, now: datetime | None = None) -> Session:
    """Mint a session for this account.

    `now` is injectable because a test that has to wait thirty days to check an
    expiry is a test nobody runs.
    """
    at = now or _utc_now()
    return Session(
        token=new_token(),
        user_id=user_id,
        created_at=at.isoformat(),
        expires_at=(at + timedelta(days=SESSION_DAYS)).isoformat(),
    )


def is_live(session: Session, *, now: datetime | None = None) -> bool:
    """Is this session still good?

    An unparseable or naive `expires_at` answers **no**. A stored row that
    cannot be read is not a reason to let somebody in — and treating it as one
    is exactly the silent-degrade this repo keeps finding and closing.
    """
    try:
        expires = datetime.fromisoformat(session.expires_at)
    except (TypeError, ValueError):
        return False
    if expires.tzinfo is None:
        return False
    return (now or _utc_now()) < expires
