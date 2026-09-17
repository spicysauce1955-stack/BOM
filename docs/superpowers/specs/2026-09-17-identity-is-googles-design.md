# Identity is Google's — and the doors actually lock

**Status:** DESIGN. Nothing built. This is slice 2 of
`2026-09-17-gcp-deployment-design.md` §8, expanded into its own document because
it turned out to be bigger than the deployment spec's §5 described, and because
it is a **product change wearing deployment clothes**: it alters how every person
signs in, deletes a mechanism that works today, and closes an API that is
currently open. It would be worth doing if the app never left the laptop.

Approved with the product owner on 2026-09-17. Three decisions were put to them
as choices and are marked where they occur; the alternatives are recorded,
because a reader who cannot see what was not chosen cannot judge what was.

`2026-09-17-gcp-deployment-design.md` §5 remains the deployment-level summary and
now points here. Where the two disagree, this document is newer and wins — and
the disagreement should be fixed rather than tolerated.

---

## 1. What happens to a person

Before any mechanism, the thing itself.

**Today** the app keeps its own account list with passwords. There are three
accounts and they share the password `demo`. Since PR #6 there is a login screen
in front of the app.

The login screen is a picture of a lock. Of 74 routes, **70 answer anybody who
knows the URL**, signed in or not; `_require_user` guards four. On a laptop that
was a sensible stage. On a public address holding a company's real customer sites
it is the blocker — and a login screen in front of an open API is worse than no
login screen, because it answers *is this protected?* with a convincing yes.

**After this slice,** Google does the signing in and we stop having passwords.
Our list of people stops being *who may log in* and becomes *what each person may
do*. Google says who you are; we say what you may do; nothing is stored twice.

1. The owner opens the company URL. Google asks for their account, and IAP only
   lets company accounts as far as the door.
2. The app looks their address up in our list. The list is empty and their
   address is `FENCEAI_BOOTSTRAP_ADMIN` → they become the admin. That is the only
   way anybody is admitted uninvited, and it switches itself off the moment an
   admin is ACTIVE — not the moment one exists. [Corrected — see A3 in
   `.superpowers/sdd/2026-09-17-identity-is-googles/task-10-brief.md`:
   `_bootstrap` counts only active admins, so that a deployment whose only
   admin was later deactivated can still be recovered. While
   `FENCEAI_BOOTSTRAP_ADMIN` stays set, the address it names is a live
   re-entry path whenever no admin is active — unsetting it after the first
   deploy is load-bearing for that recovery path, not merely hygiene.]
3. The owner opens the people screen and adds `dana@company.com` as *sales*.
4. Dana opens the URL, signs in with Google, lands on the sales view.
5. Somebody else at the company signs in. Google lets them to the door; our list
   has no row for them; they get a screen saying *ask an admin for access*. Not a
   blank app, and not a quietly granted account.

Net, the system gets **smaller**: a deletion, a port, one dependency, and one new
screen.

## 2. The port

`fenceai/identity/ports.py`, mirroring `ai/ports.py` exactly — a `Protocol`, a
record type, and no framework in the signature:

```python
class Principal(BaseModel):
    email: str          # normalised as User._normalised does it
    subject: str        # Google's `sub`; "" from DevIdentity


class IdentityProvider(Protocol):
    provider_id: str
    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None: ...
```

Mappings rather than a `Request`, so both providers are testable without
FastAPI — the split `base-top.js` and `session.js`'s `applyMe` already make on
the frontend, applied here.

`FENCEAI_IDENTITY` has **no default** and must read `iap` or `dev`, or the app
refuses to boot naming both. The precedent is `User.capacity`, which refuses a
default because *"there is no safe one: the narrowest silently locks somebody
out, the widest silently lets them in, and both failures are quiet."* Same
argument, one level up, failing at startup rather than per request. The app logs
one line at boot naming the active provider, because a machine running `dev` by
accident should say so loudly rather than behave strangely.

### 2.1 `IapIdentity` lands in this slice, not slice 4

**Decided against the deployment spec's slicing.** §8 put real JWT verification in
slice 4, with GCP. It moves here.

Three reasons. A port with one implementation proves nothing — the seam is only a
seam once something else has been through it. Slice 4 becomes *configure GCP*
rather than *write and debug signature verification against a live proxy, through
a load balancer, at the moment nothing else works either*. And §5.4's argument —
that `X-Goog-Authenticated-User-Email` is spoofable by anything reaching the
service directly, so the signed assertion must be verified *and* ingress locked —
is an argument you want in code before there is a header to trust.

It verifies `X-Goog-IAP-JWT-Assertion` against Google's public keys and checks
`aud`, and is unit-tested offline against a locally generated key pair: real
signature verification, fabricated issuer. Cost is one dependency
(`pyjwt[crypto]`), imported lazily, so `FENCEAI_IDENTITY=dev` never touches it and
§1's offline property survives intact.

## 3. What leaves

All of the deployment spec's §5.2 list, and it is all net deletion — the
hardening this block would otherwise have needed stops being necessary rather
than getting done:

`password_hash`, `set_password`, `verify_password`, `identity/session.py`, the
`sessions` table, the store's `save_session` / `session` / `delete_session` /
`delete_sessions_for`, `SESSION_COOKIE`, `POST /api/session`,
`DELETE /api/session`, and the password field on the sign-in form.

Two things §5.2 does not say:

- **`_seed_demo_accounts` stays, passwordless.** The objection was the shared
  `demo` password, not the rows. Three capacity rows carrying no credential are
  inert under IAP, because `example.com` is IANA-reserved and nobody can ever
  authenticate as one of them. They are what keeps a fresh laptop and the browser
  smoke suite in personas.
- **The `sessions` table is left in place on existing databases.** Dropping
  `CREATE TABLE sessions` from the baseline DDL does not remove it from a SQLite
  file that already has it. Nothing reads it; per the deployment spec §4
  (baseline-only migrations) it is not worth a migration, and that is better said
  here than rediscovered by somebody reading a schema dump.

**Stays untouched:** `capacity`, `active`, `actor_ref`, `is_agent`,
`default_view`, `may_choose_view`. The view/capacity doctrine survives whole,
because it was never about passwords.

## 4. Default-deny

**Decided against the smaller alternative.** The option was to swap the mechanism
and leave route gating to its own slice, as the deployment spec §9 proposed. It
was rejected: after this slice an identity is *always* present — IAP guarantees
one, `DevIdentity` fabricates one — so default-deny costs one dependency instead
of seventy route edits, and shipping the identity slice without it would leave
PR #6's false appearance standing in the very change that was supposed to fix
identity.

One dependency on the app:

```python
app = FastAPI(..., dependencies=[Depends(_gate)])
```

This covers every declared route and **does not cover the static mount** at `/`
(verified: a mounted `StaticFiles` app is a `Mount`, not a route, and router
dependencies are not applied to it). That is exactly the behaviour wanted — the
UI still loads, so it can render *ask an admin for access*, while every API route
behind it is shut.

`_gate` resolves a principal, looks the row up **by email**, and refuses with a
code:

| code | status | when |
|---|---|---|
| `no_identity` | 401 | the provider returned nothing. Under IAP this is a misconfiguration, not a user |
| `no_capacity` | 403 | authenticated, no row (§5.3 of the deployment spec) |
| `account_deactivated` | 403 | `active=False` — the local half of §5.4 |
| `subject_mismatch` | 403 | §7 below |
| `capacity_insufficient` | 403 | an admin-only route, a non-admin caller |

Every code is a PLATFORM code per CLAUDE.md's split registry: `code` + params,
English `message` as fallback only, and an entry in **both** locale bundles.
Nothing here is quoted from a document, so none of it goes near `DocumentWarning`.

**Exempt**, as an explicit frozen set that reads as a list of exceptions rather
than as a default:

- `GET /api/health` — an uptime check cannot hold a Google account
- the locale bundle route — the refusal screen has to be able to render itself in
  Hebrew
- `GET /api/session` — see below
- `POST /api/dev/identity` — registered only under `FENCEAI_IDENTITY=dev`

**`GET /api/session` is the one route that answers without a row.** It returns the
verified email plus `status: ok | no_capacity | deactivated`, because the screen
that says *ask an admin* has to be able to name who you are to the admin you are
about to ask. It replaces `GET /api/me`, which asked the same question under the
name §5.2 chose to retire.

An **architecture fitness test** asserts every registered route is either gated or
named in the exempt set. A new route cannot be born ungated by omission — which is
the way all seventy of the current ones were born.

## 5. Who you are on a laptop

**Decided against two alternatives.** A process-wide `FENCEAI_DEV_USER` cannot
switch persona without restarting the server, and the smoke suite switches
persona mid-run (`ui_smoke.py:2673` signs in as Dana by `fetch`, then fills the
form as the backoffice). A request header serves pytest and raw `fetch` but not a
real page, because the app's own modules fetch without it — the persona would
apply to some requests on a page and not others, which is worse than not having
it.

So: `DevIdentity` reads the `fenceai_dev_user` cookie, falling back to
`FENCEAI_DEV_USER` when there is none, so a bare `uvicorn` still opens as
somebody. `POST /api/dev/identity` takes an address and no credential and sets
the cookie. It is **registered only when `FENCEAI_IDENTITY=dev`**, so under `iap`
the route does not exist to be found.

This is honestly an impersonation switch and is named as one: no secret, no
session row, no expiry, nothing that could be mistaken for authentication. It is
the same move `ai/stub.py` makes — a deliberately capped stand-in that keeps the
system working offline, which must not grow into a second implementation of the
real thing.

**Frontend.** The sign-in form loses its password field and becomes a picker.
`signIn(email, password)` becomes `become(email)`. `signOut()` becomes a redirect
to IAP's logout under `iap` and a cookie clear under `dev` — §5.4 of the
deployment spec is right that signing out stops being ours, and right that
`active=False` remains the local half that must still refuse. `applyMe` and
`signedOutState` survive unchanged; they were always about presentation.
`pickProject` and `lastProjectKey` are untouched.

## 6. Granting

**Decided against deferring.** Without this, `_seed_demo_accounts`'s inert rows
aside, the bootstrap admin is the only human who could ever use the system: there
is no route today that creates a user or changes a capacity — `GET /api/users` is
the only users route there is. The deployment spec's slice 4 checkpoint ("the
owner signs in and grants someone else a capacity") is unreachable as written.

- `POST /api/users` — email, name, capacity; `subject` empty. A row is created
  **by email** before that person has ever signed in, which is the whole point:
  an admin grants Dana her capacity on Monday and Dana arrives on Tuesday.
- `PATCH /api/users/{id}` — capacity, active.

Both admin-only, both writing an audit row. These are the **first genuine capacity
checks in the repo**, and they are what makes the deployment spec §9's "gate the
other 68 routes" a smaller slice rather than a bigger one.

A people panel in the office view: the list, each capacity, add, deactivate. The
frontend is already open in this slice — login screen to picker, both locale
bundles — so the screen is marginal work here and awkward anywhere else. Building
it later would mean granting a capacity by hand-aiming a request through IAP at a
Cloud Run URL, during the slice where nothing else works yet either.

**`FENCEAI_BOOTSTRAP_ADMIN`** is consulted inside `_gate`, and requires all three
of: no admin row is ACTIVE anywhere, the principal's address matches, and no row
exists for that address. So it cannot promote an existing `sales` row, and it
self-disables the moment any admin is active — not the moment one exists.
[Corrected — see A3 in
`.superpowers/sdd/2026-09-17-identity-is-googles/task-10-brief.md`.] Counting
only ACTIVE admins is deliberate: a deployment whose only admin row was later
deactivated would otherwise be locked out for ever, with no cure even after
redeploying with this variable set, because `_bootstrap` would see the
deactivated row and refuse to fire. This cannot resurrect the deactivated
admin's OWN address — `resolve()` only calls `_bootstrap` for an email with no
existing row at all, so that address still hits its inactive row and is still
refused with `account_deactivated`. The only address this can ever seat is a
*different*, row-less one matching `FENCEAI_BOOTSTRAP_ADMIN` while zero admins
are active — which is exactly why leaving the variable set after the first
deploy is a standing second door, not merely hygiene: **while it is set, any
address it names is a live re-entry path whenever no admin is active.** It is
set for the first deploy and removed after, and that removal is load-bearing
for the deactivation recovery path as well as the demotion guard, not just
best practice.

## 7. Binding `subject`

Rows are found by email, and `subject` is **verification, not a key** — which is
why it needs no column and no index in a `users(id, email UNIQUE, doc TEXT)`
table. `User.subject` is a field in the JSON document, empty until first arrival.

- The row's `subject` is empty → bind the incoming `sub`, audit `identity_bound`.
- It matches → proceed, silently.
- It differs → **refuse with `subject_mismatch`**, and audit that. The address
  belonged to one Google account and now presents another. That is either a
  deleted-and-recreated Workspace account or something worth a person looking at,
  and §5.2 is right that an admin reconciles it and the app never does.

Binding is audited; ordinary requests are not. Under IAP every request is signed
in, so a row per request would drown the log it exists to serve.

## 8. The consequence nobody asked for

`_actor`'s docstring already names the problem: *"an actor a client can NAME is
not an audit trail."* The eleven `?author=` parameters survive today only as the
fallback for the unsigned-in case — and default-deny deletes that case. They
become dead parameters.

They go in this slice. A parameter that does nothing is worse than one that does
the wrong thing, because the next reader assumes it works. This is the piece most
likely to bloat the diff; if it does, it splits out cleanly as an immediate
follow-up rather than being quietly left in.

## 9. Testing

- A conftest fixture sets `FENCEAI_IDENTITY=dev`, seeds an admin row and puts the
  dev cookie on the `TestClient`. That is what carries the 689 existing call
  sites across default-deny.
- **Every refusal code gets a test that asks for it deliberately.** The anonymous
  case stops happening by accident the moment it stops being allowed, and a
  refusal nobody has ever seen fire is a refusal nobody has tested.
- `IapIdentity` gets offline signature tests: valid, wrong signature, wrong `aud`,
  expired, missing header.
- `DevIdentity` gets cookie-over-env precedence tests, and one asserting
  `POST /api/dev/identity` **does not exist** under `FENCEAI_IDENTITY=iap`.
- The architecture fitness test of §4.
- Node tests for the picker's pure half, as `session.js` already has for
  `applyMe`, `signedOutState` and `pickProject`.
- The smoke suite's persona switching moves from the password form to the picker.
- Both locale bundles gain every new key, and `tests/web/test_locale_bundles.py`
  keeps the key sets identical.

## 10. What this does not do

- **No per-capacity authorization** beyond admin-only on the two new routes. A
  salesperson can still call everything the backoffice can. That remains the
  deployment spec §9's slice, and it is now a smaller one: the dependency, the
  codes and the fitness test all exist, so it becomes a matter of saying which
  capacity each route wants.
- **No machine-to-machine caller.** Nothing calls `POST /api/knowledge/snapshot`
  except the UI. If one ever appears, IAP service-account tokens are the path,
  and that is a named seam rather than a surprise.
- **No multi-tenancy.** Unchanged from the deployment spec §9.

## 11. The contract is untouched

`docs/integration-contract/contract.md` line 502 states outright that
*"transport, framework, authentication mechanism, pagination style, and whether
these are one service or several are **not specified**. The shapes are the
contract; the plumbing is not."*

So gating the knowledge routes touches no binding item, needs no amendment, and
the freeze at v1.3 stands. Verify rather than trust this sentence:
`(cd docs/integration-contract && sha256sum -c contract.sha256)`.
