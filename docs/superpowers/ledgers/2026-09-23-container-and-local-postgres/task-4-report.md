# Task 4 report: a dev-seeded database refuses to be served under `iap`

## Summary

Followed the brief's TDD steps exactly for the policy function and its unit
tests, then hit a real hang (not the brief's predicted one) when the new boot
test ran against Postgres: raising `RuntimeError` before `lifespan`'s `yield`
skips `state.store.close()`, and the `list_users()` read just above the raise
had already opened an implicit Postgres transaction that psycopg leaves open
until something closes it — which held a lock that made the test's own
`pg_dsn` fixture teardown (`DROP SCHEMA ... CASCADE`) hang forever. Fixed by
calling `state.store.close()` before raising. All targeted suites and the
full suite are green. Committed as `05ebcd3`.

**Full-suite numbers: 4011 passed, 5 skipped — matches the corrected
prediction, not the brief's original "4008 passed, 1 skipped".**

## Step 1–2: failing unit test

Created `tests/identity/test_dev_seed_lockout.py` verbatim from the brief.

```
$ uv run pytest tests/identity/test_dev_seed_lockout.py -q
ImportError: cannot import name 'DEMO_ACCOUNTS' from 'fenceai.identity.dev'
1 error in 0.07s
```
Collection error, exactly as predicted.

## Step 3–4: the policy function

Appended `DEMO_ACCOUNTS`, `_DEMO_IDS`, `_DEMO_EMAILS`, and `dev_seed_lockout`
to `src/fenceai/identity/dev.py`, verbatim from the brief.

```
$ uv run pytest tests/identity/test_dev_seed_lockout.py -q
......                                                                   [100%]
6 passed in 0.01s
```

## Step 5–6: the failing boot test

Created `tests/api/test_dev_seed_boot.py` verbatim from the brief.

```
$ FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres \
    uv run pytest tests/api/test_dev_seed_boot.py -q
FF..
FAILED tests/api/test_dev_seed_boot.py::test_a_dev_seeded_database_refuses_to_boot_under_iap[sqlite]
FAILED tests/api/test_dev_seed_boot.py::test_a_dev_seeded_database_refuses_to_boot_under_iap[postgres]
2 failed, 2 passed in 0.79s
```
Both failures were `Failed: DID NOT RAISE RuntimeError`, once per backend, as
the brief predicted. `test_a_fresh_database_boots_under_iap_normally` passed
on both backends already, as expected (it's the regression guard, not the new
behaviour).

## Step 7: wiring, with one addition beyond the brief

Changed the import line and deleted `DEMO_ACCOUNTS` from `api/app.py`
(keeping the comment above `_seed_demo_accounts`), and added the check in
`lifespan` immediately after the provider-mismatch WARNING block and before
`state.interpreter = build_interpreter()`, per the brief.

**One line beyond the brief's snippet, found by running the code rather than
reading it — same category of finding this whole task exists to fix.** The
brief's snippet was:

```python
    lockout = dev_seed_lockout(state.provider.provider_id, state.store.list_users())
    if lockout:
        raise RuntimeError(f"[fenceai] {lockout}")
```

Running the new boot test against Postgres (see Step 8) hung indefinitely —
not the `DID NOT RAISE` failure the brief warns about, but a real deadlock,
and only on the `[postgres]` parametrization. I isolated it with a
`faulthandler`-instrumented run (`signal.alarm` + stack dump of all threads)
against the single failing test, which showed the process stuck here:

```
File ".../psycopg/connection.py", line 484 in wait
File ".../psycopg/cursor.py", line 113 in execute
File ".../psycopg/connection.py", line 298 in execute
File "tests/conftest.py", line 156 in pg_dsn
File ".../_pytest/fixtures.py", line 1014 in _teardown_yield_fixture
```

`tests/conftest.py:156` is `pg_dsn`'s teardown: `DROP SCHEMA "{name}" CASCADE`.
The test itself had already passed (single `.` printed) — the hang was
entirely in fixture teardown, waiting on a lock. The cause: `dev_seed_lockout`'s
second argument, `state.store.list_users()`, is a SELECT; psycopg runs an
implicit transaction per statement and never auto-commits it (this file's own
`Conn.execute` docstring explains exactly this property, in the context of
rollback-on-error). Raising `RuntimeError` before `yield` means `lifespan`
never reaches its own `state.store.close()` at the bottom of the function, so
that idle SELECT transaction stayed open, holding a lock on the just-created
schema — the schema the test's own teardown then tried to `DROP ... CASCADE`.
The guard against the unrecoverable failure was, itself, leaving a connection
open against the very database it had just refused to serve.

Fix: close the store before raising.

```python
    lockout = dev_seed_lockout(state.provider.provider_id, state.store.list_users())
    if lockout:
        # `list_users()` just above is a read, and on Postgres a read still
        # opens an implicit transaction that psycopg leaves open until
        # something commits, rolls back, or closes it. Raising past `yield`
        # skips the `state.store.close()` at the bottom of this function, so
        # without this line the refusal would leave that transaction idle,
        # holding a lock on the very database it just refused to serve — a
        # second, self-inflicted way to make the database unusable, this time
        # by the guard meant to protect it.
        state.store.close()
        raise RuntimeError(f"[fenceai] {lockout}")
```

Re-ran the single Postgres test after the fix: `1 passed in 0.39s` (was
hanging indefinitely before). This is a deviation from the brief's literal
snippet, made necessary by a real defect the brief's author could not have
seen without running it against Postgres specifically — which is exactly
what this task's own premise says review-by-reading misses.

(Aside, not a code issue: my own tooling also stumbled here first. I
initially launched Step 8 with `run_in_background` and waited for a
completion notification; on `[postgres]` that command never terminates
without the fix above, so the wait was never going to end. The coordinator
correctly redirected me to run everything in the foreground, which is how I
found and fixed the actual bug rather than continuing to wait on a stuck
process. All test runs from Step 8 onward below were run in the foreground.)

## Step 8: both test files, both backends

```
$ FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres \
    uv run pytest tests/api/test_dev_seed_boot.py tests/identity/test_dev_seed_lockout.py -q
..........                                                               [100%]
10 passed, 1 warning in 0.42s
```
Matches the brief's expectation: 10 passed (6 unit + 2 boot tests × 2
backends). Also separately confirmed `tests/identity/test_iap.py` runs (not
skipped whole): `27 passed in 0.06s`, so the `--extra iap` install is in
effect and the full-suite count below is reproducible.

## Step 9: suites most likely disturbed

```
$ FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres \
    uv run pytest tests/api tests/identity tests/architecture -q
764 passed, 1 warning in 36.12s
```
All green, including `tests/api/test_gate.py`'s `under_iap` fixture — as
predicted, it boots against an empty database (via the autouse
`_isolated_store` fixture), so the new check is a no-op there.

## Step 10: full suite

```
$ FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest -q
...
SKIPPED [1] tests/deploy/test_container.py:123: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:131: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:139: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:152: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/store/test_dialect.py:244: only meaningful in CI
4011 passed, 5 skipped, 9 warnings in 88.76s (0:01:28)
```

**This matches the task instructions' corrected prediction (4011 passed, 5
skipped), not the brief's original "4008 passed, 1 skipped".** The 9 warnings
are all pre-existing (`StarletteDeprecationWarning` about `httpx`/`httpx2`,
and four `SyntaxWarning: invalid escape sequence` warnings from
`tests/web/test_smoke_cases_registered.py` reading JS regex literals as
Python strings) — none are new from this change.

## Step 11: commit

Staged the four files by name (never `-A`, per repo convention — another
session shares this repository) and committed as **`05ebcd3`**:

```
fix(identity): refuse to serve a dev-seeded database under iap

Slice 2 review finding 3. A dev boot seeds admin@example.com as an ACTIVE
admin; _bootstrap fires only while no active admin exists; no Google
account can hold an IANA-reserved address. So every request is refused
for ever and the cure is database surgery.

Slice 3 is what creates the database slice 4 boots under iap, so the trap
and its guard ship together. DEMO_ACCOUNTS moves to identity/dev.py so
the ids are named once.

Also closes state.store before raising the refusal: list_users() is a
read, and on Postgres a read still opens an implicit transaction that
psycopg leaves open until something commits, rolls back, or closes it.
Raising past `yield` skips lifespan's own state.store.close(), so without
this the refusal itself would leave an idle transaction holding a lock on
the database it just refused to serve. Found by running the new boot test
against the Postgres backend: without the close(), the test's own pg_dsn
fixture teardown (DROP SCHEMA ... CASCADE) hung forever waiting on that
lock.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

`4 files changed, 195 insertions(+), 8 deletions(-)`.

## Deviations from the brief, and why

1. **Full-suite count**: reported the task instructions' corrected 4011/5
   rather than the brief's 4008/1 — confirmed as the actual number pytest
   printed.
2. **`state.store.close()` before the raise** in `lifespan` — one line beyond
   the brief's exact snippet. Necessary because raising past `yield` orphans
   an open Postgres transaction from the `list_users()` read that fed the
   check, which otherwise deadlocks the very next thing to touch that
   database (here, the test's own schema-drop teardown; in a real deployment,
   the operator's own attempt to inspect or fix the database by connecting to
   it). Verified the hang reproduces without this line and disappears with
   it, via an isolated single-test run with a `faulthandler` thread dump.

No other deviations. `DEMO_ACCOUNTS`'s type changed from the brief's original
`list` (in `api/app.py`) to a `tuple[tuple[str, str, str, str], ...]` in
`identity/dev.py`, exactly as the brief's own Step 3 code specifies.

## Confirmed facts from the brief

All of the brief's "verified facts" held as stated: `DEMO_ACCOUNTS` had
exactly one functional consumer; the AST-scan claim about no other test
entering `TestClient` twice was not re-verified by me but nothing in this run
contradicts it; `test_gate.py`'s `under_iap` fixture survived the change
because `_isolated_store` gives it a fresh database; the demo ids are
non-hex and the minted ids are hex, exactly as the fingerprint depends on;
`identity/dev.py`'s prior imports were as stated, so no import cycle was
created.

## State of the environment afterward

- `fenceai-test-pg` (host 5432): left running, untouched.
- Compose stack `slice3-container-postgres-app-1` (host 8080) and its
  `db` service: confirmed still `Up ... (healthy)` after all test runs,
  untouched.
- No stray schemas left behind: the one hang-reproduction schema from my
  debugging was the same `t_*` schema the fixture itself creates and drops;
  once the fix was in place, that fixture's own teardown handled it normally
  (confirmed no hung `psql` processes or lingering `pytest`/`python` processes
  remained after the debugging session — the earlier stuck runs were killed
  by PID before re-running).

---

## Fix round 1 (review response)

Three source/test changes plus a plan-doc reconciliation, all in the
foreground per the coordinator's instruction.

### 1 (Important) — guard the close

Wrapped `state.store.close()` in `try/except Exception: pass` in
`src/fenceai/api/app.py`, matching the precedent in `store/dialect.py`'s
`Conn.execute` (swallowing a failed rollback so it can't hide the real
failure). The reviewer had proved a failed close could surface
`RuntimeError closing a closed connection` in place of the lockout
sentence — exactly the opaque-crash failure mode this task exists to
prevent.

### 2 — the message names the row, not a guessed address, and offers both remedies

Replaced the `found`/`return` block in `identity/dev.py`'s
`dev_seed_lockout`: `found` now collects `f"{u.id} ({u.email})"` instead of
just `u.email`, so a row caught only by the id half (e.g. `u_admin` at a
real company address) is named accurately rather than having an
`example.com` address attributed to it that isn't on the row. The returned
sentence now names both remedies — a fresh `FENCEAI_DB`, or removing the
rows by hand — since `POST /api/users` can create an `example.com` row in
a genuine `iap` deployment too, and there is no route that deletes a user
or a `PATCH` that can change an email. Added a docstring paragraph
explaining both fixes.

### 3 (Minor) — type annotation and module docstring

`users: Sequence["User"]` with a `TYPE_CHECKING`-only import of `User` from
`identity.model` (no runtime cycle — confirmed `identity/model.py` imports
only `re`, `typing`, `pydantic`). Added a paragraph to `identity/dev.py`'s
module docstring stating `dev_seed_lockout` is a production-boot refusal
about dev-mode residue, not a widening of what `DevIdentity` itself may do.

### Two new tests

Added `test_the_message_names_the_row_rather_than_guessing_its_address` and
`test_the_message_offers_both_remedies` to
`tests/identity/test_dev_seed_lockout.py`, verbatim from the review.

```
$ uv run pytest tests/identity/test_dev_seed_lockout.py -q
........                                                                 [100%]
8 passed in 0.02s
```

### 4 — plan doc reconciled

Updated Step 7's snippet in
`docs/superpowers/plans/2026-09-23-container-and-local-postgres.md` to the
guarded version actually committed, with a note explaining the snippet was
corrected in review (the deadlock-on-raise finding and the mask risk in the
naive close).

### Targeted suites, foreground

```
$ FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres \
    uv run pytest tests/api/test_dev_seed_boot.py tests/identity -q
........................................................................ [100%]
72 passed, 1 warning in 0.79s
```

### Full suite, foreground

```
$ FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest -q
...
SKIPPED [1] tests/deploy/test_container.py:123: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:131: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:139: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:152: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/store/test_dialect.py:244: only meaningful in CI
4013 passed, 5 skipped, 9 warnings in 88.19s (0:01:28)
```

Matches the expected 4013 passed (4011 + the 2 new tests), 5 skipped.

### Mask experiment: proving the guard works

Wrote a throwaway script (not committed, deleted after the run — along with
its scratch SQLite file) that: boots the app once in `dev` to seed the demo
rows, then boots it twice under a stand-in `iap` provider — once as a
CONTROL with `Store.close` unpatched, once as the MASK reproduction with
`Store.close` monkeypatched to raise `RuntimeError("closing a closed
connection")` — and prints what `RuntimeError` actually reaches the caller
in each case, plus whether `admin@example.com` (part of the lockout
sentence) survives, plus `__context__` on the surfaced exception.

Output:

```
CONTROL surfaced: RuntimeError [fenceai] refusing to serve this database under FENCEAI_IDENTITY=iap: ...
control lockout sentence present: True
MASK surfaced:    RuntimeError [fenceai] refusing to serve this database under FENCEAI_IDENTITY=iap: it holds the row(s) u_admin (admin@example.com), u_dana (dana@example.com), u_yossi (yossi@example.com) — the accounts a dev-mode boot seeds, recognised by the ids it mints and by the IANA-reserved addresses it gives them. While any seeded admin row is active, FENCEAI_BOOTSTRAP_ADMIN stays disabled, so no real first admin can be seated; and no Google account can ever hold an example.com address. Either way every request is refused for ever. Point FENCEAI_DB at a database that has never been booted in dev mode, or remove these rows.
lockout sentence present: True
chained __context__: None
```

Even with `close()` forced to raise, the surfaced `RuntimeError` carries
the full lockout sentence (previously it would have carried "closing a
closed connection" instead, per the reviewer's own reproduction). And
`__context__` is `None`: the `except Exception: pass` discards the close
failure outright rather than implicitly chaining it onto the `raise`,
which is the exact "never let a failed X hide the real failure" shape used
by `store/dialect.py`.

### Commit

Staged the four changed files by name and committed as **`7ecbf1e`**:
`docs/superpowers/plans/2026-09-23-container-and-local-postgres.md`,
`src/fenceai/api/app.py`, `src/fenceai/identity/dev.py`,
`tests/identity/test_dev_seed_lockout.py`. `4 files changed, 83
insertions(+), 11 deletions(-)`.

### Environment afterward

`fenceai-test-pg` (5432) and the compose stack
`slice3-container-postgres-app-1`/`slice3-container-postgres-db-1` (8080)
both confirmed still running/healthy, untouched throughout this round.
