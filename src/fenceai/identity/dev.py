"""Who you are on a laptop.

**This is an impersonation switch and is named as one.** No secret, no session
row, no expiry, nothing that could be mistaken for authentication — it exists
so the app keeps working with no Google, which is the same offline property
`ai/stub.py` protects. Like the stub, it must stay capped: if it ever grows a
credential it has become a second, worse implementation of the thing it stands
in for.

`provider.py` registers it only when `FENCEAI_IDENTITY=dev`, and `api/app.py`
registers `POST /api/dev/identity` on the same condition, so under `iap` the
route does not exist to be found.

This file also holds `dev_seed_lockout`, which is a PRODUCTION-boot refusal,
not a dev-mode capability — it lives here because it is about residue from a
dev-mode boot (the seeded ids and IANA-reserved addresses this module already
names), and it does not widen what `DevIdentity` itself may do: the cap above
still holds.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Mapping, Sequence

from fenceai.identity.ports import Principal

if TYPE_CHECKING:
    from fenceai.identity.model import User

#: Named for what it is. Not `session`, which would suggest it were one.
DEV_COOKIE = "fenceai_dev_user"


class DevIdentity:
    """Cookie first, environment second.

    The env var is what a bare `uvicorn` opens as, so a developer who has set
    nothing still lands somewhere. The cookie is how ONE browser becomes
    somebody else without restarting the server — which the browser smoke needs,
    because it switches persona mid-run.
    """

    provider_id = "dev"

    def __init__(self, default_email: str = "") -> None:
        self._default = default_email

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        email = (cookies.get(DEV_COOKIE) or self._default or "").strip()
        if not email:
            return None
        # No subject. There is no Google here, and inventing one would BIND a
        # fabricated `sub` to a row — after which the real person's first
        # arrival is refused with `subject_mismatch` by a database nobody can
        # explain.
        return Principal(email=email, subject="")


def dev_identity_from_env() -> DevIdentity:
    return DevIdentity(default_email=os.environ.get("FENCEAI_DEV_USER", ""))


#: The accounts a DEV boot seeds into an empty table, so that a developer who
#: has granted nobody anything still lands somewhere. Here rather than in
#: `api/app.py` because they are dev-identity data, and because
#: `dev_seed_lockout` below has to name the same ids — once.
DEMO_ACCOUNTS: tuple[tuple[str, str, str, str], ...] = (
    ("u_dana", "Dana", "dana@example.com", "sales"),
    ("u_yossi", "Yossi", "yossi@example.com", "backoffice"),
    ("u_admin", "Admin", "admin@example.com", "admin"),
)

#: Both halves of the fingerprint, because each catches what the other cannot.
#: The ID is the precise half: `POST /api/users` mints `u_{uuid4().hex[:8]}`,
#: which is hex, and `admin`/`dana`/`yossi` are not — so a real grant can never
#: collide with one of these. The ADDRESS is the belt: `example.com` is
#: IANA-reserved for documentation, so no Google account can ever hold one,
#: whatever id the row was given.
_DEMO_IDS = frozenset(uid for uid, _, _, _ in DEMO_ACCOUNTS)
_DEMO_EMAILS = frozenset(email for _, _, email, _ in DEMO_ACCOUNTS)


def dev_seed_lockout(provider_id: str, users: Sequence["User"]) -> str | None:
    """Why this database may not be served under this provider, or None.

    Returns the operator's SENTENCE rather than a bool, for the same reason
    `provider.py` raises with one: the person who has to act on this is reading
    a crash log, and a caller that had to re-derive which rows were found would
    write a worse message than the check that found them.

    The failure it prevents is unrecoverable, which is why it is a refusal and
    not a warning. A dev boot seeds `admin@example.com` as an ACTIVE admin;
    `api/auth.py:_bootstrap` fires only while no active admin exists anywhere
    (deliberately — see `would_strand_the_admins`, which counts the same way);
    and no Google account can authenticate as an IANA-reserved address. So under
    `iap` nobody can ever sign in, `FENCEAI_BOOTSTRAP_ADMIN` cannot rescue it,
    and the cure is database surgery.

    `provider.py`'s docstring is the argument for doing this at boot: "failing
    at boot is strictly better than failing per request". The counter-argument in
    `lifespan` — that refusing to boot turns a legitimate configuration into a
    restart loop — does not reach here, and the difference is the point. An
    unset `FENCEAI_BOOTSTRAP_ADMIN` is recoverable by setting a variable; this
    state refuses every caller for ever. A crash loop naming the remedy beats a
    server that passes its own health check and answers nobody.

    Deliberately strict: it refuses on ANY seeded row, including a lone `sales`
    one that would not actually disable the bootstrap. Over-refusing a database
    nobody should be promoting from dev to production costs a fresh
    `FENCEAI_DB`; under-refusing the one arrangement that locks a company out of
    its own deployment costs database surgery.

    The message names the matched ROW, not a guessed address: the id half can
    catch a row already sitting at a company's own domain (an operator who
    typed `u_admin` for a real grant), and a message hard-coded to talk about
    `example.com` would then name an address that is not the one on the row.
    It also names both remedies — a fresh `FENCEAI_DB`, or removing the rows —
    and the reason is NOT that a route could still create such a row. The
    creation path is closed at the write: `POST /api/users` applies this very
    function to the row it is about to insert and refuses with 409
    `reserved_address`, so under `iap` no route can produce a lockout-triggering
    row at all. (It has to be closed there and not only at boot, because on
    Cloud Run `lifespan` runs per INSTANCE: a row admitted by a running instance
    leaves that instance healthy and makes every subsequent one refuse to start.)

    The reason that still holds is the DATABASE THIS FUNCTION IS LOOKING AT. A
    company reaches this refusal by pointing `FENCEAI_DB` at a database that was
    once booted in dev mode — after a trial run, a copied volume, a restore from
    a developer's snapshot — and by then that database may well hold a week of
    real jobs, quotes and audit rows beside the seeded ones. There is no route
    that deletes a user and no `PATCH` that can change an email, so removing the
    seeded rows is hand-written SQL; but "point FENCEAI_DB elsewhere" as the
    ONLY remedy would be telling that company to discard its own data to escape
    three demo rows. Both remedies, because only the operator can know which of
    the two their database is.
    """
    if provider_id == "dev":
        return None
    found = sorted(f"{u.id} ({u.email})" for u in users
                   if u.id in _DEMO_IDS or u.email.strip().lower() in _DEMO_EMAILS)
    if not found:
        return None
    return (
        f"refusing to serve this database under FENCEAI_IDENTITY={provider_id}: "
        f"it holds the row(s) {', '.join(found)} — the accounts a dev-mode boot "
        "seeds, recognised by the ids it mints and by the IANA-reserved "
        "addresses it gives them. While any seeded admin row is active, "
        "FENCEAI_BOOTSTRAP_ADMIN stays disabled, so no real first admin can be "
        "seated; and no Google account can ever hold an example.com address. "
        "Either way every request is refused for ever. Point FENCEAI_DB at a "
        "database that has never been booted in dev mode, or remove these rows."
    )
