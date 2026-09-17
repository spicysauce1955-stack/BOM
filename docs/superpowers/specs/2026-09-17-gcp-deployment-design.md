# Deploying to GCP — a pilot for one company

**Status:** DESIGN. Nothing built. No infrastructure exists in this repo today —
no Dockerfile, no Terraform, no CI — which is the good news: there is nothing to
unwind.

Approved section by section with the product owner on 2026-09-17. Two decisions
were made **against** the recommendation in this document and are marked where
they occur, because a reader who cannot see the alternative cannot judge the
choice. Two claims in the first draft were **wrong** and are corrected in place;
the wrong version is recorded because it is the one a reader would otherwise
reinvent.

## Why this document exists

The engine runs on a laptop. It has 74 routes, 3114 tests, a golden-scenario
gate and a frozen integration contract — and no way for a fencing company to
open it. This says how it gets to GCP, what has to change in the code before it
can go, and what each of those changes costs.

It is scoped to **one company, in pilot**: the three personas of
`2026-09-15-backoffice-design.md` — salesperson, backoffice, super user — doing
real quotes on real data, somewhere between three and twenty people. Not a
demo, not multi-tenant. That scope is load-bearing: almost every decision below
would go the other way for a hundred companies, and §9 says which.

---

## 1. What is being deployed

One FastAPI process. It serves the API and, from the same origin, 1.5 MB of
static ES modules, fonts and locale bundles. State is a single SQLite file —
140 KB today — holding projects, generation runs, knowledge snapshots, the audit
log, accounts and sessions. The only outbound dependency is the Anthropic API,
and only when `FENCEAI_AI=claude`; the stub keeps the whole system working
offline, which is a property CLAUDE.md states and this design must not quietly
spend.

There are no file uploads. Published snapshots arrive as a JSON body on
`POST /api/knowledge/snapshot`, not as a file on disk, so nothing here needs
object storage. The only filesystem reads in `api/app.py` are packaged static
assets (`WEB_DIR`, and the locale bundles at line 1829).

**The fact that shapes everything else:** `store/db.py` wraps a *single* SQLite
connection behind a process-wide `RLock`, and the comment at line 158 explains
the 500 it fixed — two overlapping fetches interleaving statements on one cursor,
invisible to pytest because `TestClient` serialises requests, caught only by the
browser smoke suite. This is a **single-process design**, deliberately. It is a
good design for twenty users. Any deployment that pretends otherwise is
introducing a class of bug the repo has already paid for once.

## 2. The shape

```
  Israel users ──HTTPS──▶  External ALB  ──▶  IAP  ──▶  Cloud Run  fenceai
                            managed cert        Google      me-west1
                            custom domain       identity    ingress: internal + LB
                                                             max-instances 1
                                                             1 vCPU / 512 MiB
                                                  │
                                       ┌──────────┴──────────┐
                                       │                     │
                            Cloud SQL connector       Secret Manager
                            private IP, IAM auth      ANTHROPIC_API_KEY
                                       │
                                       ▼
                            Cloud SQL Postgres 16
                            db-g1-small, me-west1
                            daily backup + 7-day PITR
```

**Region `me-west1` (Tel Aviv).** The users are Hebrew-first and in Israel; the
UI opens in Hebrew. Nothing about this app should cross the Mediterranean per
keystroke. Cloud Run and Cloud SQL availability in `me-west1` must be confirmed
before slice 4 begins — it is the first thing that would invalidate this diagram.

**One service, no CDN, no static bucket.** 1.5 MB served by the app itself is
simpler, and splitting the frontend out would mean a build step — which the
frontend is explicitly designed not to have.

**Durability chosen above requirement, deliberately.** Asked how much work was
acceptable to lose, the product owner answered *up to a day* — which SQLite on a
persistent disk with a nightly snapshot would satisfy at roughly a third of the
cost. Cloud SQL was chosen anyway, for automated backups, point-in-time recovery
and a growth path. This document recommended the cheaper VM shape; that
recommendation was heard and declined. It is recorded here so that if the bill
is ever questioned, the trade is visible rather than rediscovered.

## 3. Pinned to one instance

`max-instances=1` on day one.

The `RLock` in §1 makes a set of read-modify-write sequences atomic. The sharpest
is `api/app.py:672` and `:681`:

```python
topology.revision = project.topology.revision + 1
```

Read the project, add one, save. The revision is computed server-side rather than
trusted from the client, which is correct. But under two instances, both read
revision 7, both write revision 8, and one salesperson's topology is gone —
silently, with no 409 and no error, because the newer write simply wins.

`save_project` is called from 16 places in `api/app.py`. Fourteen are
read-modify-write — load the project, mutate it, save it — and two of those
fourteen recompute a revision counter from the value they just read, which is
the variant that corrupts a number other code checks itself against rather than
merely losing an edit.

Pinning to one instance preserves exactly the guarantee the code already relies
on, so the store port of §4 becomes a pure dialect change with no correctness
movement. **Unpinning is a later slice with a prerequisite**: turn those sites
into conditional `UPDATE … WHERE revision = ?` statements that affect zero rows
on a stale write and raise the 409 the frontend already understands. That work
is named here and deliberately not scheduled — see §9.

The cost of the pin is honest and small: a deploy or a restart is a few seconds
with no second instance to absorb it, for an office of twenty.

## 4. The store port

`store/db.py` is 1012 lines, 54 public methods, 63 SQL statements. Most of it is
already Postgres-compatible: 9 statements use `ON CONFLICT … DO UPDATE SET
x=excluded.x`, which is Postgres syntax SQLite adopted, and is byte-identical in
both.

The real divergence is five things, and they live behind a `_Dialect` object
rather than forking `Store` into two classes:

| | SQLite | Postgres |
|---|---|---|
| placeholders | `?` | `%s` |
| ignore-duplicate | `INSERT OR IGNORE` (2 sites) | `ON CONFLICT DO NOTHING` |
| JSON field | `json_extract(doc,'$.created_at')` | `doc::jsonb ->> 'created_at'` |
| audit sequence | `INTEGER PRIMARY KEY AUTOINCREMENT` | `GENERATED ALWAYS AS IDENTITY` |
| journal | `PRAGMA journal_mode=WAL` | — |

`FENCEAI_DB` gains a URL form: a value beginning `postgres://` selects the
Postgres dialect and a connection pool; a bare path stays SQLite and keeps the
single connection and its lock. Local and deployed then differ by one variable.

**Both backends stay.** Deleting SQLite would mean that running the app, or the
suite, requires a database daemon — spending the offline property for nothing.
The numbers make keeping it cheap: of 3114 test functions, only 28 files spin the
app through `TestClient` (~340 tests) and 10 files touch `Store` directly. About
390 tests — 12% — ever open a database. The other ~2700 are pure domain tests
that will not notice a port at all.

So: those ~350 are parameterized over both backends. SQLite in-memory always;
Postgres whenever one is reachable, which in CI is always, via a service
container. `uv run pytest -q` keeps working with zero setup, and CI proves the
two dialects agree — so the shim cannot drift silently, which is the one failure
mode a production-only dialect guarantees.

**Schema and migrations.** Keep `CREATE TABLE IF NOT EXISTS` at startup for the
pilot: it is idempotent, and with one instance there is no race. But name the
seam now — a `store/migrations/` directory with a `schema_version` row, empty
except for the baseline — so that the first column addition is not an
architecture decision taken under pressure.

## 5. Identity is Google's

> **Correction.** The first draft of this design stated that sign-in is "behind
> a `__Host`-prefixed cookie" and that "all 71 routes answer anyone who knows the
> URL." Both are wrong. The cookie is named `fenceai_session` — a plain name
> prefix, not the browser's `__Host-` prefix — and is set without `secure=True`.
> And `_require_user` gates **4** of 74 routes, not none. The substance survives
> both errors: every project, topology, run and quote route is among the other
> 70, and `api/app.py:2173` says so outright — *"Most routes are still open —
> accounts RECORD here, they do not yet gate."* On a laptop that is a sensible
> stage. On a public URL holding a company's real customer sites it is the
> blocker, and no test would catch it, because every test is already "signed in"
> in the only sense the app has.
>
> **Re-measured on 2026-09-17** against a main that was 18 commits newer than
> the one the first draft read. The counts above are the current ones. The
> finding got sharper, not weaker: PR #6 ("login-first and street") shipped a
> front door, so the app now *shows* a sign-in screen. That screen is a page,
> not a guard — still no middleware, no `Depends`, four `_require_user` call
> sites. A login screen in front of an open API is worse than none, because it
> answers "is this protected?" with a convincing yes.

The perimeter answer is **Identity-Aware Proxy**: nobody reaches the app without
a Google account the company has allowed. That alone would have been enough to
deploy safely. The product owner asked for more, and was right to:

> *"lets not have duplicated account, if we are using google accounts - lets use
> it to log on and assign a role to it."*

So the local password store goes. **The `users` table stops being an account
store and becomes a capacity assignment table.** Google holds the identity; we
hold what that identity may do. Nothing is mirrored, and there is no second
password for anyone to forget, leak or reuse.

### 5.1 The word is `capacity`

`identity/model.py` opens by insisting that three words mean three things and
must never overlap:

```
view      what is SHOWN            sales | backoffice | all
capacity  what an account may DO   sales | backoffice | admin
role      what a part is FOR       rail | screw | post | …
```

What gets assigned to a Google account is therefore a **capacity**. "Role" is
spoken for, and this document does not borrow it.

### 5.2 What leaves, what stays, what arrives

**Leaves:** `password_hash`, `set_password`, `verify_password`, the `sessions`
table, `identity/session.py`, the `fenceai_session` cookie, `POST /api/session`,
`DELETE /api/session`, the sign-in form in `web/static/js/session.js`, and
`_seed_demo_accounts` with its shared `demo` password. This is a net deletion:
the hardening that block would otherwise have needed stops being necessary
rather than getting done.

**Stays, untouched:** `capacity`, `active`, `actor_ref`, `is_agent`,
`default_view`, `may_choose_view`. The whole view/capacity doctrine survives,
because it was never about passwords.

**Arrives:**

- **`User.subject`** — Google's stable `sub` claim, empty until first sign-in.
  Rows are still created *by email*, because an admin grants Dana her capacity
  before Dana has ever logged in; the subject binds on her first arrival. Email
  stays the `UNIQUE` key it already is, and `User._normalised` keeps doing its
  job. A subject that arrives bearing a new email is a reconciliation an admin
  performs, never something the app does silently.

- **An `IdentityProvider` port**, mirroring the port-and-stub shape `fenceai/ai/`
  already uses. `IapIdentity` verifies the `X-Goog-IAP-JWT-Assertion` JWT against
  Google's public keys and checks the `aud` claim. `DevIdentity` reads
  `FENCEAI_DEV_USER`. The second is what keeps §1's offline property alive
  without a Google round-trip on a laptop.

- **`FENCEAI_IDENTITY`, with no default.** Must be `iap` or `dev`, or the app
  refuses to boot, naming both. The precedent is in the file already —
  `User.capacity` refuses a default because *"There is no safe one: the narrowest
  silently locks somebody out, the widest silently lets them in, and both
  failures are quiet."* Same argument, same answer, failing at startup rather
  than per request.

- **`FENCEAI_BOOTSTRAP_ADMIN=owner@company.com`** — if there is no admin yet and
  that address signs in, it becomes one. Self-disabling the moment an admin
  exists. This is what replaces three seeded strangers.

- **`GET /api/session`** answering *who am I* from the verified identity, since
  the frontend can no longer learn it by POSTing credentials.

### 5.3 Someone with no capacity row is refused

They reach a screen that says to ask an admin for access. IAP decided they may
reach the door; it did not decide what they may do inside, and silently handing
every Workspace member the `sales` capacity is exactly the quiet grant
`identity/model.py` argues against.

The alternative — auto-create every IAP-authenticated arrival as `sales` — is
friendlier on day one and was offered. Refusal was kept.

### 5.4 Two consequences, stated rather than discovered

**Signing out stops being ours.** `identity/session.py` argues, correctly, that
opaque server-side tokens exist so that signing out actually signs out. IAP keeps
that promise better — revoking access is removing the grant, centrally, for every
device at once — but the *app* cannot do it. The button becomes a redirect to
IAP's logout. `active=False` remains the local half and must still refuse a
request whose identity resolves to a deactivated row.

**Trusting the header is not enough.** `X-Goog-Authenticated-User-Email` is
spoofable by anything that reaches the service directly, and Cloud Run publishes
a `*.run.app` URL that bypasses the load balancer. Therefore **both**: verify the
signed JWT assertion, *and* set Cloud Run ingress to internal-and-load-balancer
only. Either one alone is a hole.

## 6. Container, config, release

**Container.** Two stages: `uv sync --frozen` into a venv, then a slim runtime
layer carrying `src/fenceai` and its static assets. `CMD` must honour Cloud Run's
injected `$PORT` rather than hardcoding 8000 — the most common first-deploy
failure there is. `core/env.py`'s `load_dotenv()` already prefers real
environment variables, so it becomes a harmless no-op in the container; no `.env`
ever ships.

**Config.** `FENCEAI_DB` as a `postgres://` URL. `FENCEAI_AI=claude`.
`FENCEAI_IDENTITY=iap`. `FENCEAI_BOOTSTRAP_ADMIN` set for the first deploy and
removed after. `ANTHROPIC_API_KEY` mounted as a Secret Manager reference, never
an env literal in the service YAML. `.env.example` gains `FENCEAI_IDENTITY=dev`
and `FENCEAI_DEV_USER=`.

**Release.** GitHub Actions on merge to `main`: `uv run pytest -q` — all 3114,
with the ~350 dual-run against a Postgres service container — then build, push to
Artifact Registry, `gcloud run deploy`. The scenario suite is the gate it already
is; deploying is simply what happens after green. Cloud Run retains the previous
revision, so rollback is one command and no rebuild.

**Observability.** Structured logs to stdout reach Cloud Logging with no
library. An uptime check on the health endpoint, and a budget alert — the alert
because §2 chose the shape whose cost never sleeps.

## 7. What it costs

Rough, and to be verified against current pricing before slice 4 commits to it:

| | est. /month |
|---|---|
| Cloud SQL `db-g1-small`, me-west1, 10 GB | $25–35 |
| External ALB — IAP requires one; also provides the domain and managed cert | $18–25 |
| Cloud Run, twenty users, scale-to-zero | $0–5 |
| Artifact Registry + Secret Manager | <$1 |
| **total** | **~$50–70** |

The ALB line is the one to check first. If IAP can attach directly to the Cloud
Run service in `me-west1` without a load balancer, it disappears and the total
lands nearer $30–40.

## 8. Slices

Each ends somewhere a person can watch it work. Green tests are not the
checkpoint.

1. **Dialect shim and dual-run tests.** No GCP at all. `Store` gains
   `_Dialect`, `FENCEAI_DB` accepts a URL, the ~350 persistence tests run against
   both backends. *Checkpoint:* suite green both ways; the app still boots on
   SQLite with zero setup.

2. **Identity becomes Google's.** The port, `DevIdentity`, every deletion in
   §5.2, `User.subject`, the bootstrap admin, `GET /api/session`, the frontend
   sign-in screen becoming an identity banner, and both locale bundles.
   *Checkpoint:* locally, `FENCEAI_DEV_USER=dana@…` opens on the sales view; an
   unknown address is refused; no password exists anywhere in the codebase.

3. **Container and local Postgres.** Dockerfile, `$PORT`, run against a real
   Postgres on the machine. *Checkpoint:* build a fence and generate a run, on
   Postgres.

4. **GCP up, with IAP.** Project, Artifact Registry, Cloud SQL, Secret Manager,
   Cloud Run with locked ingress, load balancer, IAP, and `IapIdentity` doing
   real JWT verification. *Checkpoint:* the product owner opens the URL, signs in
   with Google, arrives as admin via bootstrap, and grants someone else a
   capacity.

5. **CI/CD, and a restore actually performed.** The Actions pipeline, uptime
   check, budget alert, and a backup restored into a scratch instance. A backup
   nobody has restored is a hope, not a backup.

**Slice 2 is a product change, not a deployment change.** It alters how people
sign in, deletes a working mechanism, and touches `tests/identity/`,
`tests/api/test_session_routes.py`, `tests/web/test_locale_bundles.py` and the
two route tests that sign in. It is the right change and it makes the system
smaller — but it would be worth doing even if the app never left the laptop, and
it should be reviewed on those terms rather than waved through as infrastructure.

Slices 1–3 need no GCP account.

## 9. Named and not scheduled

Seams left deliberately open, so that the next chapter does not rediscover them
as surprises:

- **Unpinning `max-instances`.** Prerequisite: the fourteen read-modify-write
  sites of §3 become conditional updates that 409 on a stale write. Until that exists, the
  pin is load-bearing and must not be raised "to see if it helps".
- **Gating the other 68 routes.** IAP is a perimeter, not authorization. The app
  is not safe on its own, and `capacity` is read by 4 routes out of 74. This is
  what makes a second company possible, and it is a slice of its own.
- **Multi-tenancy.** There is no tenant concept in the data model. A second
  company is a product change before it is a deployment change, and every
  decision in §2 would be reconsidered.
- **`store/migrations/`.** Baseline only, per §4.
- **Staging.** One environment. A second is the obvious next thing and roughly
  doubles §7.

## 10. What must not change

This is a deployment. It touches no binding item of
`docs/integration-contract/contract.md`, and the freeze at v1.3 stands. The
golden scenarios are the gate, unchanged. `generate()` stays pure and
deterministic — nothing here goes near it. Integer millimetres and cents at rest
survive the port to Postgres unchanged: every `doc` column is JSON text today and
stays JSON text, so no numeric type conversion is introduced anywhere.
