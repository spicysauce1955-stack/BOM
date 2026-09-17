"""Who is asking, and whether they may ask at all.

**Default-deny.** One dependency on the app covers every declared route; the
static mount at `/` is a `Mount` rather than a route, so router dependencies do
not reach it and the UI still loads — which is exactly what is wanted, because
the page has to render "ask an admin for access" to somebody the API refuses.

Until this slice, 70 of 74 routes answered anybody who knew the URL while a
login screen stood in front of them — which answers "is this protected?" with a
convincing yes.

The refusal codes are PLATFORM codes (CLAUDE.md's split registry): `code` +
params, English `message` as fallback only, an `error.<code>` entry in both
locale bundles. Nothing here is quoted from a document, so `DocumentWarning` is
not involved.
"""

from __future__ import annotations

import os
import uuid

from fastapi import HTTPException, Request

from fenceai.identity.binding import bind
from fenceai.identity.model import User, actor_ref
from fenceai.identity.ports import IdentityProvider, Principal

#: Routes that answer without a capacity row. An explicit list of exceptions
#: rather than a default, so adding one is a deliberate edit.
EXEMPT_PATHS = frozenset({
    "/api/health",        # an uptime check cannot hold a Google account
    "/api/session",       # names you so you can tell an admin who to grant
    "/api/dev/identity",  # registered only under FENCEAI_IDENTITY=dev
})
# NOT here, and worth saying so: the locale bundles are NOT an API route.
# `_locale_bundle` is an internal helper, and the browser loads
# `i18n/<lang>.json` off the static mount — which is a `Mount`, not a route, so
# the gate never reached it. The refusal screen renders itself in Hebrew
# because the mount was never gated, not because of an exemption here.


#: The gate's refusal code for each non-`ok` status `resolve` can return.
#:
#: `deactivated` and `account_deactivated` are the same fact in two registers,
#: and the difference is deliberate: `GET /api/session` reports a STATE to a
#: screen, while a 403 body carries a PLATFORM refusal code that a person may
#: read in a log — where `deactivated` alone would not say deactivated *what*.
#: The design's refusal table names them, so the mapping is written out rather
#: than assumed.
_REFUSAL_CODE = {
    "no_capacity": "no_capacity",
    "deactivated": "account_deactivated",
    "subject_mismatch": "subject_mismatch",
}


def _bootstrap_address() -> str:
    return os.environ.get("FENCEAI_BOOTSTRAP_ADMIN", "").strip().lower()


def resolve(store, principal: Principal) -> tuple[User | None, str]:
    """The row this principal is, and what to do about it.

    Returns `(user, status)` with status one of `ok` · `no_capacity` ·
    `deactivated` · `subject_mismatch`. Persists a first binding and a
    bootstrap promotion; writes nothing otherwise.
    """
    user = store.user_by_email(principal.email)
    if user is None:
        user = _bootstrap(store, principal)
        if user is None:
            return None, "no_capacity"
    outcome = bind(user, principal)
    # `bind` MUTATES the row it is handed, and only on `"bound"`. Persisting on
    # any other answer would write a row nothing changed; not persisting on
    # `"bound"` would re-bind the same subject on every request for ever, and
    # the mismatch that is supposed to catch a swapped Google account would
    # never have a stored subject to catch it against.
    if outcome == "mismatch":
        store.log(actor_ref(user), "subject_mismatch", user.id)
        return user, "subject_mismatch"
    if outcome == "bound":
        store.save_user(user, actor=actor_ref(user))
        store.log(actor_ref(user), "identity_bound", user.id)
    if not user.active:
        return user, "deactivated"
    return user, "ok"


def _bootstrap(store, principal: Principal) -> User | None:
    """The first admin, and only the first.

    Three conditions, all of them: no admin row exists anywhere, the address
    matches `FENCEAI_BOOTSTRAP_ADMIN`, and no row exists for that address. So it
    cannot promote an existing `sales` row, and it self-disables the moment any
    admin exists. This is what replaces three seeded strangers with a password.
    """
    wanted = _bootstrap_address()
    if not wanted or principal.email != wanted:
        return None
    if any(u.capacity == "admin" for u in store.list_users()):
        return None
    user = User(id=f"u_{uuid.uuid4().hex[:8]}", name=principal.email.split("@")[0],
                email=principal.email, capacity="admin",
                subject=principal.subject)
    store.save_user(user, actor="bootstrap")
    store.log("bootstrap", "bootstrap_admin", user.id)
    return user


def make_gate(provider_of, store_of):
    """Built as a closure over two callables so the app can supply its live
    `state` without this module importing `api.app` — which would be a cycle,
    and which `test_fitness.py` would rightly object to."""

    def gate(request: Request) -> None:
        if request.url.path in EXEMPT_PATHS:
            return
        provider: IdentityProvider = provider_of()
        principal = provider.principal(dict(request.headers), dict(request.cookies))
        if principal is None:
            # `no_identity` rather than `no_capacity`: under IAP this is a
            # misconfiguration — the proxy should never have let it through —
            # and the two want different people to look at them.
            raise HTTPException(401, {"code": "no_identity"})
        user, status = resolve(store_of(), principal)
        if status != "ok":
            # 403 unconditionally: the only caller that reaches here is one the
            # provider already identified, so every refusal `resolve` can give
            # is "we know who you are and the answer is still no". A 401 would
            # invite a browser to re-authenticate against an answer that will
            # not change until an admin changes it.
            raise HTTPException(403, {"code": _REFUSAL_CODE.get(status, status)})
        request.state.user = user

    return gate


def current_user(request: Request) -> User:
    """The caller, guaranteed by the gate. A route that reaches this on an
    exempt path is a bug in the exempt list, not a case to handle."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, {"code": "no_identity"})
    return user


def require_admin(request: Request) -> User:
    user = current_user(request)
    if user.capacity != "admin":
        raise HTTPException(403, {"code": "capacity_insufficient"})
    return user
