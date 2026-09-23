# Task 3 report: the stack — the app and a Postgres of its own

## Summary

Wrote `compose.yaml` verbatim from the brief (Step 3) and appended the three
compose tests to `tests/deploy/test_dockerfile.py` (Step 1), with the one
correction the brief pre-authorized applied to
`test_the_app_service_sets_no_dev_user`. Brought the stack up with
`docker compose up -d --build --wait`, confirmed both services `healthy`,
confirmed the app answers its health endpoint, and confirmed via `psql` that
the app is running against a real Postgres with the store's tables and the
three seeded demo accounts. Committed as `a6dc98b`. Stack is left running.

## What was done, in brief order

### Step 1–2: failing tests first

Appended `COMPOSE = ROOT / "compose.yaml"` and the three tests to
`tests/deploy/test_dockerfile.py`, using the corrected version of
`test_the_app_service_sets_no_dev_user` (checks the variable is not set as a
compose environment **key**, via a `re.match(r"^\s*FENCEAI_DEV_USER\s*:", ln)`
scan, rather than asserting the string is absent from the file — the file's
own comment names the variable to explain its absence, so the literal-absence
version of the test would fail against the brief's own fixture). `re` was
already imported in the file from Task 1, so no new import was needed.

Ran `uv run pytest tests/deploy/test_dockerfile.py -q` before creating
`compose.yaml`:

```
FAILED tests/deploy/test_dockerfile.py::test_the_database_publishes_no_host_port
FAILED tests/deploy/test_dockerfile.py::test_the_app_waits_for_a_healthy_database_rather_than_a_sleep
FAILED tests/deploy/test_dockerfile.py::test_the_app_service_sets_no_dev_user
3 failed, 6 passed in 0.06s
```
All three failed with `FileNotFoundError: .../compose.yaml`, as expected.

### Step 3: compose.yaml

Created `compose.yaml` at the repo root, byte-identical to the brief's Step 3
content (db service with no published port, `pg_isready -U fenceai -d
fenceai` healthcheck with `start_period: 5s`; app service built via `build:
.`, `FENCEAI_DB` pointed at `db:5432`, `FENCEAI_AI=stub`,
`FENCEAI_IDENTITY=dev`, host port `${FENCEAI_COMPOSE_PORT:-8080}`, `python -c
...urlopen(...)` healthcheck since the runtime image has no curl,
`depends_on: db: condition: service_healthy`). The comment block explaining
the three deliberate choices, and the inline comment naming
`FENCEAI_DEV_USER`'s absence, are both intact.

### Step 4: tests pass

```
$ uv run pytest tests/deploy/test_dockerfile.py -q
.........
9 passed in 0.01s

$ uv run pytest tests/deploy -q
ssss.........
4 skipped, 9 passed in 0.02s
```
Matches the brief's expectation exactly (9 passed, 4 skipped — the 4 skips
are `test_container.py`'s Docker-gated tests, unaffected by this task).

### Step 5: bring the stack up

```
$ docker compose up -d --build --wait
 ...
 Container slice3-container-postgres-db-1  Healthy
 Container slice3-container-postgres-app-1  Healthy

$ docker compose ps
NAME                              IMAGE                           COMMAND                  SERVICE   STATUS                    PORTS
slice3-container-postgres-app-1   slice3-container-postgres-app   "sh -c 'exec uvicorn…"   app       Up 7 seconds (healthy)    0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp
slice3-container-postgres-db-1    postgres:16                     "docker-entrypoint.s…"   db        Up 13 seconds (healthy)   5432/tcp

$ curl -s localhost:8080/api/health
{"ok":true,"interpreter":"stub"}
```
Note `db`'s `PORTS` column shows only `5432/tcp` (container-internal), not a
host mapping — confirming no host port was published, and no collision with
the pre-existing `fenceai-test-pg` container that already owns host 5432.

### Step 6: prove it's really on Postgres

```
$ docker compose exec db psql -U fenceai fenceai -c '\dt'
               List of relations
 Schema |        Name         | Type  |  Owner  
--------+---------------------+-------+---------
 public | active_snapshot     | table | fenceai
 public | audit_log           | table | fenceai
 public | catalogs            | table | fenceai
 public | corrections         | table | fenceai
 public | fence_models        | table | fenceai
 public | generation_runs     | table | fenceai
 public | inventories         | table | fenceai
 public | knowledge_snapshots | table | fenceai
 public | knowledge_versions  | table | fenceai
 public | parts               | table | fenceai
 public | projects            | table | fenceai
 public | quotes              | table | fenceai
 public | supply_runs         | table | fenceai
 public | users               | table | fenceai
(14 rows)
```

The brief's literal second query (`select id, email, capacity from users
order by id`) does **not** run as written — see Deviations below. The
equivalent query against the actual schema:

```
$ docker compose exec db psql -U fenceai fenceai \
    -c "select id, email, doc::jsonb->>'capacity' as capacity from users order by id"
   id    |       email       |  capacity  
---------+-------------------+------------
 u_admin | admin@example.com | admin
 u_dana  | dana@example.com  | sales
 u_yossi | yossi@example.com | backoffice
(3 rows)
```

All three demo accounts (`u_admin`, `u_dana`, `u_yossi`) are present with the
expected capacities, confirming the app seeded its demo data into this
Postgres on first boot.

Additional sanity check — no SQLite fallback occurred:

```
$ docker compose exec app env | grep FENCEAI
FENCEAI_IDENTITY=dev
FENCEAI_DB=postgresql://fenceai:fenceai@db:5432/fenceai
FENCEAI_AI=stub

$ docker compose exec app sh -c 'ls -la /app/*.db 2>&1 || echo "no .db file (expected)"'
ls: cannot access '/app/*.db': No such file or directory
no .db file (expected)
```

### Step 7: commit

```
$ git add compose.yaml tests/deploy/test_dockerfile.py
$ git commit -F <scratchpad>/commit-msg.txt
[worktree-slice3-container-postgres a6dc98b] feat(deploy): compose the app with a Postgres of its own
 2 files changed, 101 insertions(+)
 create mode 100644 compose.yaml
```

## Deviations from the brief, with reasons

1. **`test_the_app_service_sets_no_dev_user`** written per the pre-authorized
   correction in the task instructions (checks "not set as a compose
   environment key" via regex, rather than "the literal string
   `FENCEAI_DEV_USER` is absent from the file"). This was specified by the
   dispatching instructions as a correction to a self-contradicting brief, not
   something I discovered independently — flagging it here for completeness
   since it changes the test's assertion from the brief's literal Step 1 code
   block.

2. **Step 6's exact `psql` query does not run as written.** The brief's
   `select id, email, capacity from users order by id` assumes `capacity` is
   a top-level column of `users`. The actual schema (revealed by `\d users`)
   is `id text`, `email text`, `doc text` — a JSON-blob-per-row store, where
   `capacity` lives inside the `doc` column (itself stored as `text`, not
   `jsonb`, so reading it needs an explicit `doc::jsonb->>'capacity'` cast).
   I ran the brief's literal query first, saw
   `ERROR: column "capacity" does not exist`, and reran with the corrected
   query above to fulfil the step's actual intent (prove the seeded demo
   accounts and their capacities are visible in Postgres). No files were
   changed for this — it's purely a difference between the brief's
   illustrative SQL and the real schema, which the brief's authors couldn't
   have known when writing Task 3's text (the schema comes from application
   code, not this task). The unqualified `\dt` output and the seeded rows are
   the evidence Task 7 needs regardless of the exact SQL used to see them.

No other deviations. `compose.yaml` is byte-identical to the brief's Step 3
content including all comments (the "three deliberate choices" block and the
`FENCEAI_DEV_USER` inline comment). Ports, healthchecks, `depends_on`
condition, and volume all match the brief.

## State left behind

- Stack is **up and healthy**: `slice3-container-postgres-app-1` on host
  `8080`, `slice3-container-postgres-db-1` with no published host port, both
  named per the `slice3-container-postgres` compose project (derived from the
  worktree directory name).
- `fenceai-test-pg` (host 5432) was never touched.
- Host port 8000 (another session's uvicorn) was never touched.
- Working tree is clean; `compose.yaml` and the three tests are committed at
  `a6dc98b`.
- `uv run pytest tests/deploy -q` → 9 passed, 4 skipped.
- Did not run the full suite (`uv run pytest -q`), per instructions.

## Fix round 1: two weak substring assertions

The coordinator's review found that `test_the_database_publishes_no_host_port`
and `test_the_app_waits_for_a_healthy_database_rather_than_a_sleep` both
searched the raw file text for literals, which `compose.yaml`'s own comments
can legitimately satisfy (the comment block explains why the file does *not*
say `5432:5432` and does *not* use a `sleep`, so those exact strings appear in
the prose). A regression using compose's long-form `ports:`, a different host
port like `15432:5432`, a `condition: service_healthy` present but on the
wrong service, or a `sleep` sitting alongside an otherwise-correct
`condition:` would have passed both tests unnoticed.

### Fix

Added `_service_block(name)` — strips comments and blank lines, then isolates
one service's indented block by tracking a top-level (`services:`) reset and
a service-name line at 2-space indent — and rewrote both tests against
service-scoped, structural checks rather than whole-file substrings:

- `test_the_database_publishes_no_host_port` now rejects any line in `db`'s
  block matching `^\s*(ports|published)\s*:`, so both the short-form list
  syntax and the long-form `target:`/`published:` mapping are caught, and any
  host port (not just `5432:5432`/`5433:5432`) fails it.
- `test_the_app_waits_for_a_healthy_database_rather_than_a_sleep` now asserts
  three things independently: the app's block contains
  `condition: service_healthy`, the db's block contains `pg_isready`, and
  neither block contains the word "sleep" anywhere — so a healthy-looking
  `condition:` cannot coexist with a `sleep` smuggled into the app's
  `command:`.

`compose.yaml`'s comments were not touched.

### 1. Regression check

```
$ uv run pytest tests/deploy -q
ssss.........
9 passed, 4 skipped in 0.02s
```
Unchanged from before the fix.

### 2. Proving the new assertions discriminate

Backed up `compose.yaml` to the scratchpad first. Made each edit, ran
`uv run pytest tests/deploy/test_dockerfile.py -q`, confirmed RED, then
restored the backup and confirmed `git diff compose.yaml` was empty before
the next edit.

**(i) Publish db on `15432:5432`** — added `ports: ["15432:5432"]` under `db`:
```
FAILED tests/deploy/test_dockerfile.py::test_the_database_publishes_no_host_port
AssertionError: the db service publishes a host port: ['    ports:']
1 failed, 8 passed in 0.02s
```
Reverted; `git diff compose.yaml` → empty.

**(ii) Add a fixed sleep to the app** — set the app's `command:` to
`sh -c "sleep 10 && exec uvicorn ..."` (health/`depends_on` left intact):
```
FAILED tests/deploy/test_dockerfile.py::test_the_app_waits_for_a_healthy_database_rather_than_a_sleep
AssertionError: a fixed sleep stands in for a readiness check:
['    command: sh -c "sleep 10 && exec uvicorn fenceai.api.app:app --host 0.0.0.0 --port 8080"']
1 failed, 8 passed in 0.02s
```
Reverted; `git diff compose.yaml` → empty.

**(iii) Remove `condition: service_healthy`** — replaced the app's
`depends_on: db: condition: service_healthy` with the bare-list form
`depends_on: [db]`:
```
FAILED tests/deploy/test_dockerfile.py::test_the_app_waits_for_a_healthy_database_rather_than_a_sleep
AssertionError: the app does not wait on any service's health
1 failed, 8 passed in 0.02s
```
Reverted; `git diff compose.yaml` → empty. Final `uv run pytest tests/deploy -q`
confirmed back to 9 passed, 4 skipped.

### 3. Commit

Committed the test file only:

```
$ git add tests/deploy/test_dockerfile.py
$ git commit -F <scratchpad>/fix1-commit-msg.txt
[worktree-slice3-container-postgres 0e4fb3c] test(deploy): stop substring assertions from reading the comments they explain
 1 file changed, 50 insertions(+), 9 deletions(-)
```

`compose.yaml` is byte-identical to what was committed in `a6dc98b` — no
diff, nothing staged for it. Compose stack was left running throughout
(`docker compose ps` after the fix still shows both services `healthy`,
unchanged uptime lineage). Full test suite was not run, per instructions.
