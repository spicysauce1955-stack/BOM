# Task 1 report — the image, and the three lines a deploy depends on

Worktree: `/home/user/.superset/projects/BOM/.claude/worktrees/slice3-container-postgres`
Commit: `b7c8a7c` (`feat(deploy): a two-stage image that honours $PORT and ships no .env`)

## What was done

Followed the brief's steps 1–8 exactly, with the one correction to `_sync_lines()`
specified in the task instructions (filter on lines that start with `RUN` and contain
`uv sync`, not on every line that mentions the phrase — the Dockerfile's two explanatory
comments about `uv sync` would otherwise be misread as sync instructions with no
`--extra` flags, and the brief's own tests would fail against the brief's own Dockerfile).
Both explanatory comments were kept in the Dockerfile as written in the brief; nothing was
stripped to shorten it.

Files created:
- `Dockerfile` — two-stage build (`builder` / `runtime`), verbatim from the brief.
- `.dockerignore` — verbatim from the brief.
- `tests/deploy/__init__.py` — empty.
- `tests/deploy/test_dockerfile.py` — verbatim from the brief except `_sync_lines()`,
  which uses the corrected version given in the task instructions.

No other files were touched.

## Commands run and their output

### Step 1–2: write the test, confirm it fails without a Dockerfile

```
$ uv run pytest tests/deploy/test_dockerfile.py -q
```
All 6 tests failed with `FileNotFoundError: [Errno 2] No such file or directory:
'.../Dockerfile'` (the first test to run tried `.dockerignore` and failed the same way).
This is the expected pre-Dockerfile failure mode, not a logic failure in the tests
themselves.

### Step 3–4: write Dockerfile and .dockerignore

Written verbatim from the brief (Dockerfile with the two `uv sync` explanatory comments
intact).

### Step 5: confirm the tests pass

```
$ uv run pytest tests/deploy/test_dockerfile.py -q
......                                                                   [100%]
6 passed in 0.01s
```

### Step 6: build the image by hand

```
$ docker build -t fenceai:slice3 .
```

Build succeeded in one pass, no README/build-backend error. Key excerpts:

```
Step 6/17 : RUN uv sync --frozen --no-install-project --extra postgres --extra iap
 ---> Running in 451156ae3d10
Using CPython 3.12.13 interpreter at: /usr/local/bin/python3
Creating virtual environment at: .venv
...
Installed 33 packages in 91ms
Bytecode compiled 2184 files in 390ms
 + ... anthropic, fastapi, psycopg, psycopg-binary, pydantic, pyjwt, uvicorn, ...

Step 7/17 : COPY src ./src
Step 8/17 : RUN uv sync --frozen --extra postgres --extra iap
 ---> Running in eebff838b556
   Building fenceai @ file:///app
      Built fenceai @ file:///app
Installed 1 package in 1ms
 + fenceai==0.1.0 (from file:///app)

...
Step 17/17 : CMD ["sh", "-c", "exec uvicorn fenceai.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
Successfully built 2b55a5d9e943
Successfully tagged fenceai:slice3
```

`docker images fenceai:slice3` reports 295 MB disk usage / 67.5 MB content size —
reasonable for a `python:3.12-slim` base plus psycopg/cryptography/fastapi/uvicorn.

`psycopg`, `pyjwt`, `fastapi`, `uvicorn`, `anthropic` all appear in the first sync's
install list, confirming both extras (`postgres`, `iap`) landed and the second sync only
adds the project itself (`fenceai==0.1.0`), not a re-resolve.

No README or build-backend error occurred — `pyproject.toml` declares no `readme`, as the
task context said, so nothing extra was needed.

### Step 7: confirm the suite is unmoved

Pre-existing Postgres 16 container `fenceai-test-pg` was already running on
`localhost:5432` (confirmed via `docker ps`, `Up 5 days`); it was reused, not restarted.

```
$ export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres
$ time uv run pytest -q
...
SKIPPED [1] tests/store/test_dialect.py:244: only meaningful in CI
3998 passed, 1 skipped, 9 warnings in 88.29s (0:01:28)

real    1m29.189s
```

**3998 passed, 1 skipped** — matches the brief's expected count exactly
(3992 baseline + 6 new `tests/deploy/test_dockerfile.py` tests). No disagreement to flag;
the predicted number and the measured number are the same.

### Step 8: commit

```
$ git add Dockerfile .dockerignore tests/deploy/__init__.py tests/deploy/test_dockerfile.py
$ git commit -F <scratchpad>/commit-msg.txt
[worktree-slice3-container-postgres b7c8a7c] feat(deploy): a two-stage image that honours $PORT and ships no .env
 4 files changed, 172 insertions(+)
 create mode 100644 .dockerignore
 create mode 100644 Dockerfile
 create mode 100644 tests/deploy/__init__.py
 create mode 100644 tests/deploy/test_dockerfile.py
```

Commit message body kept the brief's rationale text; attribution line changed to
`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` per this session's attribution
instructions (overriding the brief's literal `Claude Opus 5 (1M context)` line, since the
attribution instruction for this session takes precedence over a plan artifact written
before it).

`git status` afterward: clean.

## What changed relative to the brief, and why

1. **`_sync_lines()` filter** — changed from `"uv sync" in ln` to
   `ln.startswith("RUN") and "uv sync" in ln`, per the task's Correction 1. Verified this
   was necessary: the Dockerfile as written contains two comment lines that say
   `uv sync` (`# Both extras again — uv sync without them would...` and the `uv sync
   installs the project as an editable pointer` comment) with no `--extra` flags. Without
   the `RUN`-prefix filter, `test_every_sync_installs_both_extras` and
   `test_every_sync_is_frozen` would have matched those comment lines and failed. With the
   filter, both tests pass as part of the 6/6 in Step 5.
2. **Commit attribution line** — `Claude Sonnet 5` instead of the brief's `Claude Opus 5
   (1M context)`, per this session's active attribution instructions.

Nothing else deviates from the brief. Dockerfile and .dockerignore are verbatim.

## Surprises / notes

- Nothing surprising in the build or test run. Both extras' packages (psycopg-binary,
  pyjwt, cryptography, fastapi, uvicorn) showed up correctly in the first `uv sync`'s
  install list, and the second sync only added the `fenceai` project itself (1 package,
  1ms), confirming the two-layer cache structure works as intended (dependency layer
  survives `COPY src ./src` + code-only changes).
- Full-suite runtime (88.29s) is comfortably inside the ~96s baseline figure given in the
  task context, despite 6 additional (near-instant) tests.
- Image size: 295 MB disk / 67.5 MB content on top of `python:3.12-slim` — not asked for
  by the brief's acceptance criteria but recorded here for future reference.
