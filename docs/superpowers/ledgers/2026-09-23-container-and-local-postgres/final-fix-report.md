# Slice 3 fix wave — final report

Applied all nine findings from the whole-branch review. All verification
foreground, all green.

## Status

Complete — all nine items closed, nothing skipped.

## Commit(s)

`c1a753a` — "fix: close slice 3's nine post-merge review findings" (single
commit, all fourteen changed files staged by name; branch
`worktree-slice3-container-postgres`).

## Full-suite numbers

- Before (baseline, per the review): **4017 passed / 5 skipped**
- After (this run, `FENCEAI_TEST_POSTGRES=... uv run pytest -q`): **4022 passed / 5 skipped**
- Difference: **+5 passed, 0 change to skipped**, accounted for exactly:
  - `tests/api/test_user_admin_routes.py::test_granting_admin_at_example_com_is_refused`
    — new (item 1). Runs once per backend (autouse `dsn` fixture in
    `tests/api/conftest.py`): **+2**.
  - `tests/api/test_dev_seed_boot.py::test_the_refusal_survives_a_failing_close`
    — new (item 2). Same autouse parametrization: **+2**.
  - `tests/deploy/test_dockerfile.py::test_every_sync_skips_dev_dependencies`
    — new (item 4). Not parametrized over `dsn`: **+1**.
  - Total: +5, matching 4022 − 4017.

`tests/deploy -q`: 10 passed, 4 skipped (Docker-gated).
`FENCEAI_TEST_DOCKER=1 tests/deploy -q`: 14 passed (the 4 previously-skipped
container tests now run, plus the new `--no-dev` test) — count rose by 1
relative to the prior 13, as expected.
`tests/api tests/identity tests/web/test_locale_bundles.py tests/architecture tests/tools -q`:
917 passed.

## Item 4 — image check

`docker build -t fenceai-test:slice3 .` succeeded with both `uv sync` lines
carrying `--no-dev`.

```
$ docker run --rm fenceai-test:slice3 python -c "import pytest"
ModuleNotFoundError: No module named 'pytest'

$ docker run --rm fenceai-test:slice3 python -c "import psycopg; import jwt; \
    print('psycopg', psycopg.__version__); print('jwt', jwt.__version__)"
psycopg 3.3.5
jwt 2.14.0

$ docker run --rm fenceai-test:slice3 sh -c \
    "ls /app/.venv/lib/python3.12/site-packages | grep -iE 'pytest|websocket_client|pluggy|iniconfig|pygments' || echo none-found"
none-found
```

`pytest` (and `httpx`'s dev-only companions `websocket-client`, `pluggy`,
`iniconfig`, `pygments`) are gone from the runtime image; `psycopg` and `jwt`
still import.

## Item by item

1. **Write-time guard on `POST /api/users`.** `grant_capacity`
   (`src/fenceai/api/app.py`) now calls
   `dev_seed_lockout(state.provider.provider_id, [user])` after building the
   candidate `User` and before saving, raising `HTTPException(409,
   {"code": "reserved_address"})` if it returns a sentence. Comment names
   the Cloud Run per-instance `lifespan` failure mode this closes.
   `reserved_address` added to `REFUSAL_CODES` in
   `tests/web/test_locale_bundles.py` (hand-maintained list, per the file's
   own pattern for admin-route refusals like `user_exists`/`last_admin`) and
   `error.reserved_address` added to both `src/fenceai/web/static/i18n/en.json`
   and `he.json`. New test
   `tests/api/test_user_admin_routes.py::test_granting_admin_at_example_com_is_refused`
   (iap-shaped provider stand-in, mirroring `test_dev_seed_boot.py`'s `_Iap`)
   asserts the 409 and that an ordinary company address still succeeds.

2. **Committed regression test for the close guard.** New
   `tests/api/test_dev_seed_boot.py::test_the_refusal_survives_a_failing_close`:
   dev-boots (seeding), monkeypatches `Store.close` to actually close the
   connection and then raise `RuntimeError("close failed")`, boots again
   under the iap-shaped provider, and asserts the raised `RuntimeError`
   still carries `admin@example.com` and `FENCEAI_DB` — the lockout
   sentence, not the close failure. (First attempt patched `close` to raise
   without actually closing the connection, which left the read's implicit
   transaction open and hung the Postgres teardown at DROP SCHEMA — exactly
   the failure mode the docstring warns about. Fixed by calling the real
   `close()` before raising.)

3. **Provider before store.** `lifespan` in `src/fenceai/api/app.py` now
   calls `build_provider()` before `Store(...)`, with a comment explaining
   why: a configuration error surfaces before any I/O instead of orphaning
   an opened read.

4. **`--no-dev` in the Dockerfile.** Added to both `uv sync` lines. New test
   `tests/deploy/test_dockerfile.py::test_every_sync_skips_dev_dependencies`.
   Spec §6 (`docs/superpowers/specs/2026-09-17-gcp-deployment-design.md`)
   amended in place, following the file's existing `> **Amendment (...)**`
   convention, recording that the spec (not the Dockerfile) was wrong.

5. **Three-document disagreement on where per-capacity authorization goes.**
   `docs/reviews/2026-09-23-slice-2-carried-findings.md`'s summary table
   split into "Per-capacity authorization slice (next)" (findings 1, 6, 7)
   and "Slice 4 (IAP adapter / ADR-0013)" (findings 2, 4, 5), matching the
   per-finding dispositions and ADR-0013. `plan/current-status.md`'s
   sentence corrected: findings 2 and 4 live in `identity/iap.py`; finding 5
   is documentation, not code, carried forward as a stated assumption for
   ADR-0013. ADR-0013 itself left unchanged (already correct, confirmed the
   reference).

6. **Runbook symptom wording.** `docs/v1-runbook.md`'s boot-failure entry
   now says "empty stdout" rather than "no output," and states plainly that
   stderr carries the full traceback, visible via `docker logs`. Verified
   directly: booted the built image with `FENCEAI_IDENTITY=dev` and no
   `FENCEAI_DB` — exit code 3, empty stdout, full
   `sqlite3.OperationalError: unable to open database file` traceback on
   stderr.

7. **`down -v` reasoning strengthened.** Runbook now states plainly that an
   attached run without `down -v` **fails** — not merely accumulates rows —
   naming both `ui_smoke.py:2805`'s `wait_for(... .queue-take ... < 2)` (a
   second run leaves one takeable job behind and the wait never resolves)
   and `ui_smoke.py:8929`'s retirement of `K-MAXSPAN/1` (unretireable twice).

8. **Attached mode's `FENCEAI_AI` check.** `tools/ui_smoke.py`'s attached
   preflight now parses the `/api/health` body it already fetches and
   aborts with a clear FATAL naming `FENCEAI_AI=stub` if
   `interpreter != "stub"`. Verified two ways: (a) fetched
   `http://localhost:8080/api/health` from the live compose stack directly
   and ran the exact check logic against the real response body — passes,
   `interpreter` is `"stub"`; (b) ran the same logic against a synthetic
   `{"interpreter": "claude"}` body — aborts with the FATAL message. Did
   **not** run the browser smoke suite itself, per instructions.

9. **compose.yaml port comment.** Added at `PORT: "8080"` (the first of the
   three occurrences), naming the other two (the `ports:` mapping's
   container-side half, and the healthcheck URL). Comment only;
   `docker compose config -q` still validates.

## Verification, all foreground

- `uv run pytest tests/deploy -q` — 10 passed, 4 skipped
- `FENCEAI_TEST_DOCKER=1 uv run pytest tests/deploy -q` — 14 passed (rebuilds
  the image; count rose by 1 for the new `--no-dev` test)
- `FENCEAI_TEST_POSTGRES=... uv run pytest tests/api tests/identity tests/web/test_locale_bundles.py tests/architecture tests/tools -q` — 917 passed
- `FENCEAI_TEST_POSTGRES=... uv run pytest -q` — 4022 passed, 5 skipped (see
  difference accounting above)
- Compose stack left running and healthy on :8080 throughout
  (`docker compose ps` shows both services healthy at report time;
  `curl localhost:8080/api/health` → `{"ok":true,"interpreter":"stub"}`)
- `fenceai-test-pg` on :5432 untouched
- `git status --short` clean of `tools/smoke-out/*.png` before commit; only
  the fourteen intended files modified

## Items not completed

None — all nine items closed.

---

## Post-review documentation-truth pass (2026-09-23)

**Status:** complete. All four items fixed and verified; no code changes.

**Commit:** `78c51a0` — "docs: correct four drifted claims before slice 3 merges"

**Item 1 — the `httpx` claim (Dockerfile comment, spec §6 amendment,
`test_every_sync_skips_dev_dependencies` docstring).** Verified first: the
`fenceai:slice3` tag predated the Dockerfile commit and was stale. Rebuilt
fresh (`docker build --target runtime .`) and checked directly:

```
$ docker run --rm fenceai:verify python -c "import httpx; print('httpx OK', httpx.__version__)"
httpx OK 0.28.1

$ docker run --rm fenceai:verify python -c "import pytest; print(pytest.__version__)"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'pytest'
```

`uv.lock` confirms `httpx` is a direct dependency of `anthropic` (a runtime
dependency), independent of the `dev` group. Corrected all three locations
to name only `pytest`, `websocket-client`, `pluggy`, `iniconfig`,
`pygments`; the spec amendment now states explicitly that `httpx` stays
because `anthropic` needs it.

**Item 2 — plan document, `docs/superpowers/plans/2026-09-23-container-and-local-postgres.md`
step 4 (~line 1428).** Corrected the false "findings 2, 4 and 5 all live in
the IAP adapter and ADR-0013" to match the accurate statement already in
`plan/current-status.md` (finding 5 is the absence of a CSRF/Origin/CORS
layer, not code in `identity/iap.py`). Kept as an executed step with an
appended correction note rather than deleted, per instructions.

**Item 3 — stale line citation in `docs/v1-runbook.md` (~line 67).** Found
current line numbers by content, not by trusting the old numbers:
- `.queue-take` wait: still exactly `tools/ui_smoke.py:2805` — confirmed correct, unchanged.
- `K-MAXSPAN/1` retire call: moved to `tools/ui_smoke.py:8944` (was cited as `:8929`). Corrected.

**Item 4 — `plan/current-status.md`.** Added a new top-of-file checkpoint
section ("post-merge review closes nine findings, one fix wave") recording:
final suite numbers 4022 passed / 5 skipped (dual-run) at commit `c1a753a`;
the most important finding (write-time `POST /api/users` race against the
boot-time dev-seed refusal, hazardous specifically because Cloud Run runs
`lifespan` per instance) and its fix (write-time 409 `reserved_address`,
same predicate as the boot check — confirmed present at `src/fenceai/api/app.py:2420`);
that the production image no longer ships the dev dependency group; and the
two deliberate residues slice 4 inherits (pre-fix reserved rows need manual
SQL; the write-time guard is a no-op under `FENCEAI_IDENTITY=dev` by
construction, which `dev_seed_lockout` catches at boot instead).

### Verification, all foreground

- `uv run pytest tests/deploy tests/web/test_locale_bundles.py tests/architecture -q` → **77 passed, 4 skipped**
- `FENCEAI_TEST_DOCKER=1 uv run pytest tests/deploy -q` → **14 passed**
- Image check (fresh build): `httpx` imports (`0.28.1`), `pytest` raises `ModuleNotFoundError` — see transcript above.
- Compose stack left up and healthy on :8080 throughout; `fenceai-test-pg` on :5432 untouched.
- `git status --short` clean of `tools/smoke-out/*.png` before commit; only the six intended files staged (by name) and committed.
- No subagents dispatched; all work done directly in this session.
