# PR #14 — the six review findings, closed

Worktree `slice3-container-postgres`, branch `worktree-slice3-container-postgres`.
Every finding was reproduced before it was changed and re-measured after.

## Status

All six done. No finding deferred, nothing partially applied.

## Finding 1 (MEDIUM, security) — the IAP grace window served retired keys indefinitely

`src/fenceai/identity/iap.py`. The grace check sat inside the retry-backoff
branch; every failed refresh reset `_last_attempt_at`, so for the next 59 s the
whole `elif` body was skipped and control fell through to
`return self._keys.get(kid)`.

Reviewer's table, reproduced with a fake clock (throwaway script, not committed):

| t | before | after |
|---|---|---|
| `0` | `'PEM'` | `'PEM'` |
| `TTL+GRACE+1` (25201) | raised `blip` | raised — past the grace window |
| `TTL+GRACE+2` (25202) | **`'PEM'`** — served past grace | raised — past the grace window |
| `TTL+GRACE+10002` (35202) | raised `blip` | raised — past the grace window |

The middle row is the bug, and it repeats for the whole outage: 59 of every
60 seconds, for ever, not "up to 60s at a time".

The two decisions are now separate. `attempted` gates only the FETCH; the grace
boundary is evaluated on every call that reaches the stale branch, and raises a
fresh `RuntimeError` chained from the stored `self._last_error` (a fresh
exception rather than re-raising the stored one, which would grow one
traceback per request for the length of the outage). The within-grace WARNING
is still gated on `attempted`, so log volume is unchanged at one line per
failed refresh rather than one per request.

Regression test:
`tests/identity/test_iap.py::test_the_retry_backoff_does_not_reopen_the_expired_grace_window`
— verified failing against `HEAD` (`assert Principal(...) is None` → served the
stale key) and passing after.

`docs/reviews/2026-09-23-slice-2-carried-findings.md` finding 4 gained a
**Correction** block saying the "up to 60s" characterisation was false and that
the deferral rested on it; the carried-findings table in
`docs/superpowers/plans/2026-09-23-container-and-local-postgres.md` now points
at that correction instead of scheduling the work for slice 4.

## Finding 2 (MEDIUM) — `grant_capacity` 500 on a duplicate address

Reproduced at store level (both requests read `None`, as the double-click does):

| step | before | after |
|---|---|---|
| first read of `dana@example.org` | `None` | `None` |
| second read (the other click) | `None` | `None` |
| first write | ok | `(User(...), 'ok')` |
| second write | **`sqlite3.IntegrityError: UNIQUE constraint failed: users.email`** → unhandled 500 | `(None, 'user_exists')` → 409 |

At route level, against `HEAD`, both new tests died inside
`src/fenceai/store/dialect.py:182` with `sqlite3.IntegrityError`; after the fix
both pass on SQLite and Postgres.

**Server.** `Store.create_user_guarded(user, actor)` — `amend_user_guarded`'s
shape and register — does the existence check and a plain INSERT (not the
upsert) inside one `@_serialized` call and returns `(user, "ok")` or
`(None, "user_exists")`. No driver exception is caught and no driver is
imported into `api/`; `store/dialect.py`'s standing note that `sqlite3` and
`psycopg` share no base beyond `Exception` is why. The route's `user_by_email`
pre-read is kept and commented as NOT the guard: it preserves the refusal
ORDER (`user_exists` before `reserved_address`), which the guarded call cannot,
since the `dev_seed_lockout` check sits between them. Both audit rows
(`save_user`, `grant_capacity`) moved inside the guarded call, so a refusal
writes none.

**Frontend.** `js/people.js`'s submit handler disables
`form.querySelector('button[type="submit"]')` for the request and re-enables it
in `finally` — `notes.js`'s pattern, and `finally` because `apiSend` re-throws
every refusal after alerting, so a plain re-enable would be skipped on exactly
the outcome where the admin needs the control back. No new user-visible string,
so no locale key added.

**Tests.** Store level, dual backend, in `tests/identity/test_store.py`:
conflict instead of `IntegrityError`, no audit row on a refusal, and casing
parity (the guard reads `users.email` directly, so it needs its own proof).
Route level in `tests/api/test_user_admin_routes.py`: the second POST is 409
`user_exists`, and the refused grant leaves one row and one `grant_capacity`
audit line. The interleaving is forced by stubbing `user_by_email` for ONE
address — stubbed wholesale it also blinds the `dev` provider to the caller and
the route answers 403 `no_capacity`, proving nothing.

The disabled control IS covered in node
(`tests/web/test_people_module.py`), using the hand-rolled `document`/`fetch`
double that file already uses for the capacity `<select>`. `disabled` is read
from INSIDE the `fetch` stub, because reading it after the `await` passes
against the broken code too. Verified failing against `HEAD`
(`duringPost is False`).

## Finding 3 (LOW) — `executescript` had no rollback

`src/fenceai/store/dialect.py`. Routed through the same `try/except → rollback
→ raise` as `Conn.execute`, with a comment saying the reason is `execute`'s own
and naming what is worse here: this runs from `Store.__init__`, so the
exception leaves before `state.store` is assigned and nothing closes a
connection now idle-in-failed-transaction.

Parity tests `test_a_refused_script_does_not_brick_a_{sqlite,postgres}_conn`
mirror the existing `execute` pair. The Postgres half fails against `HEAD`.

## Finding 4 (LOW) — the documented SQLite floor was false

`ON CONFLICT DO NOTHING` without a target needs **3.35.0 (2021-03-12)**, not
3.24 — 3.24 added UPSERT but required a target. Both statements now read
`ON CONFLICT(id) DO NOTHING`; `id` is verified as the PRIMARY KEY and the only
unique constraint on `generation_runs` and on `supply_runs`, so the target is
the actual conflict in each.

Corrected in both places the claim lived: `store/dialect.py`'s module docstring,
and `docs/superpowers/specs/2026-09-17-gcp-deployment-design.md` §4 as a new
`> **Amendment (slice 3 PR review, implemented 2026-09-23).**` block in that
file's own convention — the original Task 5 amendment is left standing and
named as the thing being corrected.

Guarded by `tests/store/test_dialect.py::test_no_upsert_omits_its_conflict_target`,
a text assertion because no database this suite can reach would fail on the
targetless form. It fails against `HEAD` naming all three occurrences.

While in that docstring: the opening line fixed `store/db.py`'s statement count
at 63. It was already 64 at `HEAD` and is 66 with `create_user_guarded`, so the
number was decaying while the invariant it stood for had not moved. Replaced
with the invariant (one statement per thing done, never a second spelling of an
existing one), which is what the line was for.

## Finding 5 (LOW) — attached-mode preflight crashed on its own diagnosis

`tools/ui_smoke.py`. Exercised directly against three `/api/health` replies on
a throwaway server (no browser run).

Against `HEAD`, the older-build case:

```
  File ".../tools/ui_smoke.py", line 4878, in main
    interpreter = json.loads(resp.read())["interpreter"]
KeyError: 'interpreter'
```

After, all three diagnose and return 2:

```
--- older build: /api/health with no interpreter key ---
FATAL: http://localhost:8099/api/health has no 'interpreter' key, so which AI
interpreter that server runs cannot be established. The key predates this
suite's attached mode, so this is almost certainly an OLDER build of the app
than the one under test — which is the one thing attaching to an image is
supposed to prove it is not. Answered: ['db', 'status']
exit=2

--- a live interpreter (the pre-existing check still works) ---
FATAL: http://localhost:8099 is running interpreter 'claude', not 'stub' — set
FENCEAI_AI=stub on that server before attaching this suite to it
exit=2

--- not this app at all: a JSON array ---
FATAL: http://localhost:8099/api/health answered something this suite cannot
read (ValueError('not a JSON object: list')) — that is not this app, or not a
version of it this suite can drive
exit=2
```

The parse is guarded too: a non-JSON or non-object body is exactly as
disqualifying as a live interpreter, and would have tracebacked the same way.

## Finding 6 (LOW) — a rationale invalidated by its own commit's guard

`src/fenceai/identity/dev.py`. `dev_seed_lockout`'s docstring justified naming
two remedies by claiming `POST /api/users` could still create an `example.com`
row under `iap`. It cannot — `grant_capacity` applies this same function to the
row it is about to insert and refuses 409 `reserved_address`.

Rewritten to the reason that holds: the database this function is looking at.
A company reaches the refusal by pointing `FENCEAI_DB` at a database once booted
in dev mode, which by then may hold a week of real jobs beside three seeded
rows — so "point `FENCEAI_DB` elsewhere" as the only remedy would tell a real
company to discard its own data. The note also says the creation path is now
closed at the write, and why it had to be closed there rather than only at boot
(Cloud Run runs `lifespan` per instance).

## Verification

All foreground.

- Scoped: `tests/identity tests/api tests/store tests/web tests/deploy tests/architecture`
  → **1763 passed, 5 skipped**.
- Full suite, dual-run:
  `FENCEAI_TEST_POSTGRES=... uv run pytest -q` → **4038 passed, 5 skipped**
  (was 4022 / 5). **+16**, accounted for exactly:

  | file | tests added | runs | total |
  |---|---|---|---|
  | `tests/identity/test_iap.py` | 1 | not parametrised | +1 |
  | `tests/identity/test_store.py` | 3 | ×2 backends | +6 |
  | `tests/api/test_user_admin_routes.py` | 2 | ×2 backends | +4 |
  | `tests/web/test_people_module.py` | 2 | node, once | +2 |
  | `tests/store/test_dialect.py` | 3 | once each (1 sqlite, 1 pg, 1 text) | +3 |
  | | | | **+16** |

  The 5 skips are unchanged: 4 `tests/deploy/test_container.py` (needs
  `FENCEAI_TEST_DOCKER=1`) and 1 `tests/store/test_dialect.py` (CI-only).
- Release gate: `uv run pytest tests/scenarios -q` → **310 passed**.
- Browser smoke suite NOT run, as instructed; finding 5 exercised directly.
- The compose stack on :8080 was never touched and still answers
  `/api/health` 200. `fenceai-test-pg` used read-only through the documented
  DSN. No `tools/smoke-out/*.png` is dirty.

## Not done

Nothing. One judgement call worth flagging: `create_user_guarded` closes the
window within one process (the `@_serialized` lock), which is what the
double-click and the FastAPI threadpool can reach. Two PROCESSES racing one
Postgres would still hit the UNIQUE constraint; that needs a caught driver
exception per backend, which `store/dialect.py` explicitly declines, and it is
unreachable while the deployment pins `max-instances=1` — the same condition
finding 3 is filed under.
