# ADR-0013: Identity is Google's; a row here holds the capacity

Status: accepted · 2026-09-17

## Decision

Until this slice, the app kept its own password store (`identity/session.py`, a
`sessions` table, three seeded strangers) in front of an API where 70 of 74 routes
answered anybody who knew the URL — a login screen makes "is this protected?" look
like a convincing yes, and it was not one. That was survivable on a laptop; on a
public address holding a company's real customer sites it is the blocker.

**Identity moves behind a port.** `identity/ports.py` declares `IdentityProvider`
(one method, `principal(headers, cookies) -> Principal | None`) and `Principal`
(`email`, `subject`). Two adapters implement it: `IapIdentity` verifies Google's
signed `X-Goog-IAP-JWT-Assertion` against Google's public keys — issuer, audience,
signature and the six required claims all checked, because the plaintext header
alongside it is spoofable by anything that reaches the service directly — and
`DevIdentity` is a credential-less, cookie-first stand-in for a laptop with no
Google, named as an impersonation switch rather than disguised as one.
`identity/provider.py::build_provider()` reads `FENCEAI_IDENTITY` once at
startup, with **no default**: `iap` or `dev`, or the app refuses to boot naming
both, because a silently-narrow default locks someone out and a silently-wide one
lets everyone in and both failures are quiet.

**`users` becomes a capacity assignment table, not an account table.** A row
answers *what may this person do* (`capacity`: `sales`/`backoffice`/`admin`,
`active`), never *who may log in* — Google already answered that. Rows are
created **by email**, before that person has ever signed in: an admin grants Dana
a capacity on Monday and Dana arrives Tuesday. `subject` (Google's `sub`) is
**verification, not a key** — it binds on first arrival (`identity/binding.py`)
and is never used to find a row. An arrival on an address already bound to a
different subject is `subject_mismatch`, refused and audited rather than handed
to whoever holds the address today, because reconciling that is an admin's job.

**Default-deny at the app, not route by route.** `api/auth.py::make_gate` is one
`fastapi.Depends` on `app.router`, resolving every caller to an active capacity
row before any route body runs and refusing with `no_identity` (401, the
provider found nobody) or `no_capacity` / `account_deactivated` /
`subject_mismatch` (403, the provider found somebody with no admissible row).
`EXEMPT_PATHS` is a three-path allow-list — `/api/health` (an uptime check holds
no Google account), `/api/session` (the one route that must answer WITHOUT a
capacity row: the screen that tells somebody to ask an admin has to name them to
the admin), and `/api/dev/identity` (registered only under `FENCEAI_IDENTITY=dev`,
so it does not exist under `iap`) — each with a sentence in `api/auth.py` saying
why, and pinned by `tests/architecture/test_fitness.py` so a fourth exemption is
a deliberate, reviewed edit rather than a drift. `POST /api/users` and
`PATCH /api/users/{id}` are the first genuine per-capacity checks in the repo
(`require_admin`), and every write audits.

`FENCEAI_BOOTSTRAP_ADMIN` replaces the three seeded strangers: the only address
admitted uninvited, and only while no admin row is **active** — counting only
active admins, symmetric with the app's own "would this strand every admin"
guard, is what lets a deployment whose sole admin was later deactivated still be
recovered by redeploying with the variable set, rather than being locked out for
ever. It is consulted for an email with no existing row at all, so it can never
resurrect the deactivated admin's OWN row — that address still hits
`account_deactivated` exactly as before.

## Rationale

**Delegating rather than mirroring.** The alternative considered was mirroring
Google Workspace accounts locally — syncing a directory, storing a shadow
account per Google identity. Rejected: it recreates the thing being deleted, a
local store of who exists, and now has to be kept in sync with an external
system on top of everything ADR-0002/0004's determinism already demands of the
rest of this app. Google already knows who exists; the only fact worth a row
here is what they may do, and that fact is ours to keep regardless of who
answers "who is this".

**Refusing rather than auto-granting.** Auto-creating every IAP-authenticated
arrival as `sales` was offered and rejected. It is friendlier on day one and
wrong on every day after: silently handing every Workspace member a capacity is
exactly the quiet grant `identity/model.py` already argues against for
`User.capacity`'s own default. IAP decided who may reach the door; it did not
decide what they may do inside, and the two questions get two different
answers with two different owners.

**One gate rather than seventy.** Gating each route individually was rejected
because that is exactly how this repository arrived at 70 of 74 routes silently
unprotected: retrofitting a cross-cutting concern one call site at a time is how
a feature outruns its own enforcement, and the next route added after this ADR
would need the same discipline reapplied by memory. One `Depends` on the app is
what makes a route gated *by construction* — but keeping that true structurally,
rather than by habit, took two separate fitness tests, not one, and the reason
it took two is itself worth recording: an app-level assertion
(`app.router.dependencies` is non-empty) is a property of the app object, true
regardless of how any particular route got registered, so it cannot by itself
catch a route that bypassed the normal path. This slice shipped exactly that
gap once — `/openapi.json`, `/docs` and `/redoc` answered anonymously for
several commits, because FastAPI registers them with `Starlette.add_route`
rather than `add_api_route`, so they are plain `Route`s the app-level dependency
never reaches. `tests/architecture/test_fitness.py` now closes this with two
tests that inspect what got registered rather than what the app was configured
with: `test_every_api_route_actually_carries_the_gate` checks that every `/api`
`APIRoute` carries the gate on its OWN dependant, and
`test_nothing_under_api_escapes_being_a_gated_api_route` checks that nothing
under `/api` is anything OTHER than a gated `APIRoute` — no `Mount` shadows an
`/api` path, no plain `Route` sits under one — with the static UI mount at `/`
named as the sole, reasoned exception. Together with the exempt-list tests,
this is what keeps "a route is gated by construction" true structurally.

## Consequences

**Signing out stops being ours.** `identity/session.py` argued, correctly, that
opaque server-side tokens exist so that signing out actually signs out. IAP
keeps that promise better than this app ever could: revoking access is removing
the grant, centrally, for every device at once. The app cannot do that, so
"sign out" is a redirect to IAP's own logout. `active=False` is the local half
that survives the handoff — it still refuses a request whose identity resolves
to a deactivated row, which is the one revocation the app can enforce itself
between an admin's click and IAP catching up.

**A dev provider keeps the offline property.** `DevIdentity` requires no Google,
no network and no secret — a cookie or an environment default is the whole
mechanism — so `uv sync && uv run pytest -q` and a bare `uvicorn` both still work
with nothing installed, the same property `ai/stub.py` protects for the AI ports.
It is documented as an impersonation switch specifically so it is never mistaken
for authentication and never grows a credential of its own.

**Per-capacity authorization is still a separate slice.** This ADR closes *who
gets in the door at all*; it does not yet mean every route checks the right
capacity for what it does beyond `POST`/`PATCH /api/users` (admin-only) and the
command door's own per-kind check (`fenceai/commands/`, backoffice design §10).
Retrofitting fine-grained capacity checks onto the other routes is the smaller
slice this ADR was written to make possible, not the slice it performs.

**Leaving `FENCEAI_BOOTSTRAP_ADMIN` set is a standing second door, not
hygiene.** Because it only checks for an *active* admin, an address matching it
remains a live re-entry path for as long as it is set and no admin is currently
active — including the moment a deployment's only admin is deactivated by
mistake. Unsetting it after the first deploy is load-bearing for that
recovery path as well as for the ordinary demotion guard in `api/app.py`, not
merely deployment cleanliness.

**A database booted in `dev` mode refuses to serve under `iap`, and the
refusal was found by running the code, not by reading it.** `dev` mode seeds
three fixed-id, `@example.com` rows; nothing stopped that same database from
later being pointed at by an `iap` boot, where those addresses can never be
reached by a real Google account and `FENCEAI_BOOTSTRAP_ADMIN` stays disabled
while a seeded admin row is active — so the deployment is locked out forever
with no path back in, discovered only when someone actually tries to sign in.
`identity/dev.py:dev_seed_lockout` closes it: booting under `iap` against a
database carrying any dev-seeded row refuses to start at all (exit 3), naming
the offending rows and the remedy, rather than letting the app come up and
refuse every request one at a time. Its strictness is deliberate — it refuses
on ANY seeded row present, not only an admin one, because a seeded non-admin
row is just as much evidence the database was never meant for `iap` as a
seeded admin row is, and checking only the admin row would let the same trap
reopen through a seeded `sales` or `backoffice` account instead.

This ADR does not otherwise expand what it covers. `docs/reviews/2026-09-23-slice-2-carried-findings.md`
records the eleven other findings this identity work surfaced by running,
rather than reading, the code — including three (findings 1, 6, 7) that
belong to the per-capacity authorization slice above and two (findings 2, 4)
that live in `identity/iap.py`, the same adapter this ADR's Decision section
names for IAP verification, though not the same file as
`identity/dev.py:dev_seed_lockout` above — and their dispositions; none of
the eleven are addressed by this ADR.

Spec: `docs/superpowers/specs/2026-09-17-identity-is-googles-design.md`.
Plan: `docs/superpowers/plans/2026-09-17-identity-is-googles.md`.
