# Container and Local Postgres Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The app runs from a container image against a real Postgres, and a
database that was created in dev mode can never be served under `iap`.

**Architecture:** A two-stage Dockerfile whose runtime layer carries the venv and
`src/fenceai`; a `compose.yaml` pairing it with its own Postgres; a boot-time
refusal for the dev-seed lockout, written as a pure function beside the
lockout policy that already exists; and one environment seam in
`tools/ui_smoke.py` so the existing 646 browser checks can be pointed at a
running container instead of a server they started themselves.

**Tech Stack:** Docker 29.1 + Compose 2.40, `python:3.12-slim`, uv 0.11.8,
Postgres 16, FastAPI/uvicorn, pytest.

**Spec:** `docs/superpowers/specs/2026-09-17-gcp-deployment-design.md` — §6
(container, config, release), §8 slice 3, §9 (what stays unscheduled), §10 (what
must not change). §6 is this slice's design document; the design was reviewed and
approved in conversation on 2026-09-23 and no separate design file was written.

**Slice 2's ledger** (rulings, deferred findings, seven review passes) is at
`docs/superpowers/ledgers/2026-09-17-identity-is-googles/`. It was gitignored in
a worktree and has been copied here; that was the last piece of slice 2's
housekeeping.

## Global Constraints

- **Both extras are mandatory in the image**: `uv sync --frozen --extra postgres
  --extra iap`. A bare sync produces a server that passes its own health check
  and 500s on every route, including `/api/session` (§6).
- **`--frozen` everywhere.** A drifted lockfile must fail the build, not resolve
  something nobody tested. `uv lock --check` passes at 2f4efb0 — verified.
- **`CMD` honours `$PORT` and binds `0.0.0.0`.** Cloud Run injects `$PORT` and
  does not promise 8080; a container bound to `127.0.0.1` answers its own health
  check and nobody else.
- **No `.env` ever ships** (§6).
- **No fixed host port anywhere.** Every port in this slice is either
  Docker-assigned or overridable by environment variable. A hard-coded port in
  this repository has twice produced 22 errors that read like a bug in whatever
  was just written (`tests/tools/conftest.py` records both).
- **Never a fixed sleep as a readiness wait.** Condition-based, always. A
  `time.sleep(4)` racing Chrome's startup kept this repository's CI red from the
  day CI was added until 088db4f.
- **Integer millimetres and cents at rest survive unchanged** (§10). Nothing in
  this slice goes near `generate()`, the scenarios, or any `doc` column.
- **The boundary contract is frozen at v1.3.** This slice touches no binding
  item. Do not edit `docs/integration-contract/`.
- **Baseline at 2f4efb0, measured in this worktree:** `uv run pytest -q` with
  `FENCEAI_TEST_POSTGRES` set = **3992 passed, 1 skipped** in 96s. Any other
  number after a task means that task did it.
- Install with `uv sync --extra postgres --extra iap`. Without `--extra iap`,
  `tests/identity/test_iap.py` skips whole behind its `importorskip` and the
  suite count is not reproducible.
- Never pass `--ignore=tests/tools`. It hid a real regression for two review
  cycles in slice 2.

## File Structure

| File | Responsibility |
|---|---|
| `Dockerfile` (create) | Two stages. Builder resolves deps then installs the project; runtime carries `/app/.venv` + `/app/src` and the `$PORT`-honouring CMD. |
| `.dockerignore` (create) | Keeps `.env`, `*.db`, `.git`, `.venv` out of the build context. A security control, not hygiene. |
| `compose.yaml` (create) | `app` + `db`, the db publishing no port, the app waiting on a real healthcheck. |
| `tests/deploy/test_dockerfile.py` (create) | Unconditional. Parses the Dockerfile and `.dockerignore` for the invariants above. Runs in every suite, needs no daemon. |
| `tests/deploy/test_container.py` (create) | Docker-gated. Builds the image and runs it: both extras importable, `$PORT` honoured, boots under `iap`, non-root. |
| `src/fenceai/identity/dev.py` (modify) | Gains `DEMO_ACCOUNTS` (moved here from `api/app.py`) and the pure `dev_seed_lockout` policy. |
| `src/fenceai/api/app.py` (modify) | Imports `DEMO_ACCOUNTS` instead of defining it; `lifespan` raises on a lockout before writing anything. |
| `tests/identity/test_dev_seed_lockout.py` (create) | The pure policy, both directions. |
| `tests/api/test_dev_seed_boot.py` (create) | The scenario itself: boot dev, reboot iap, refused. Dual-run over both backends. |
| `tools/ui_smoke.py` (modify) | `target_base_url()` / `attached()`, read at call time; five URL sites and the launch/teardown branch. |
| `tests/tools/test_ui_smoke_target.py` (create) | The two seam functions, behaviourally. |
| `.github/workflows/tests.yml` (modify) | A second job that builds the image and runs `tests/deploy`. No registry, no deploy — those stay slice 5's. |
| `docs/v1-runbook.md` (modify) | How to run the container stack, and how to look inside the database. |
| `docs/adr/0013-identity-is-delegated.md` (modify) | Records the dev-seed refusal under Consequences. |
| `docs/reviews/2026-09-23-slice-2-carried-findings.md` (create) | The 11 findings this slice does not fix, each with a disposition. |
| `plan/current-status.md` (modify) | Checkpoint entry. |

**Task order rationale:** Task 1 must precede 2 (nothing to build otherwise) and
3 (compose builds it). Task 4 is independent code and comes before 7 because the
checkpoint demonstrates it live. Task 5 must precede 7. Task 6 needs 1 and 2.

---

### Task 1: The image, and the three lines a deploy depends on

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/deploy/__init__.py` (empty)
- Test: `tests/deploy/test_dockerfile.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an image buildable with `docker build -t fenceai .` from the repo
  root, listening on `$PORT` (default 8080), running as uid 10001. Task 2 builds
  it, Task 3 composes it, Task 6 builds it in CI.

- [ ] **Step 1: Write the failing test**

Create `tests/deploy/__init__.py` as an empty file, then
`tests/deploy/test_dockerfile.py`:

```python
"""The three lines in the Dockerfile that a deploy depends on.

Parsing a Dockerfile is a weak kind of test and this file knows it: the real
proof is `test_container.py`, which builds the image and runs it. But that test
needs a Docker daemon and skips without one, and these properties are exactly
the ones whose absence produces "a server that passes its own health check and
answers nobody" (spec §6). A string check that ALWAYS runs is worth having
underneath a behavioural check that sometimes does.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def _logical_lines() -> list[str]:
    """The Dockerfile with backslash continuations folded into one line each."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    return [ln.strip() for ln in re.sub(r"\\\n\s*", " ", text).splitlines()]


def _sync_lines() -> list[str]:
    return [ln for ln in _logical_lines() if "uv sync" in ln]


def _cmd_line() -> str:
    cmds = [ln for ln in _logical_lines() if ln.startswith("CMD")]
    assert len(cmds) == 1, f"{len(cmds)} CMD lines — a later one silently wins"
    return cmds[0]


def test_every_sync_installs_both_extras():
    """Built with a bare sync, the app comes up healthy, announces `identity
    provider: iap`, and raises ModuleNotFoundError out of the gate on every
    route including `/api/session` (spec §6). `postgres` is the driver Cloud SQL
    needs; `iap` is PyJWT, which `iap_identity_from_env()` imports eagerly."""
    lines = _sync_lines()
    assert lines, "no `uv sync` in the Dockerfile"
    for line in lines:
        assert "--extra postgres" in line, line
        assert "--extra iap" in line, line


def test_every_sync_is_frozen():
    """A drifted lockfile must fail the build rather than resolve something
    nobody tested."""
    for line in _sync_lines():
        assert "--frozen" in line, line


def test_the_server_binds_every_interface():
    """Cloud Run routes to the container's external interface. A server bound to
    localhost answers its own health check and nobody else."""
    cmd = _cmd_line()
    assert "0.0.0.0" in cmd, cmd
    assert "127.0.0.1" not in cmd and "--host localhost" not in cmd, cmd


def test_the_server_honours_the_injected_port():
    """"The most common first-deploy failure there is" — spec §6. Cloud Run
    injects `$PORT` and does not promise 8080."""
    assert "${PORT" in _cmd_line(), _cmd_line()


def test_the_command_execs_so_uvicorn_receives_sigterm():
    """Without `exec`, `sh` is PID 1, keeps the signal, and every deploy waits
    out the full termination grace period."""
    assert "exec uvicorn" in _cmd_line(), _cmd_line()


def test_no_env_file_can_enter_the_build_context():
    """The one line in `.dockerignore` that is a security control rather than
    hygiene: `.env` holds a live ANTHROPIC_API_KEY, and spec §6's "no `.env`
    ever ships" is currently true only because no `COPY . .` exists yet."""
    patterns = {ln.strip() for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()}
    assert ".env" in patterns
    assert ".env.*" in patterns
    assert "*.db" in patterns
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/deploy/test_dockerfile.py -q`
Expected: every test FAILS — `FileNotFoundError: .../Dockerfile`.

- [ ] **Step 3: Write the Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1

# ---- builder ----------------------------------------------------------------
FROM python:3.12-slim AS builder

# Pinned, not `:latest`: the thing that resolves the dependency tree is itself a
# dependency, and an unpinned one makes the build unreproducible in the one
# place `--frozen` was supposed to guarantee it.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies in their own layer, before any source: they change when uv.lock
# changes, which is rare, while src/ changes every commit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra postgres --extra iap

# Then the project itself. Both extras again — `uv sync` without them would
# PRUNE what the line above installed.
COPY src ./src
RUN uv sync --frozen --extra postgres --extra iap

# ---- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

# `/app` in both stages, and not a coincidence: `uv sync` installs the project
# as an editable pointer to /app/src/fenceai, so the venv copied below only
# resolves if the source sits at the same absolute path it did at build time.
WORKDIR /app

RUN useradd --create-home --uid 10001 fenceai

COPY --from=builder --chown=fenceai:fenceai /app/.venv /app/.venv
COPY --from=builder --chown=fenceai:fenceai /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER fenceai

# Documentation only — Cloud Run ignores it and injects $PORT instead.
EXPOSE 8080

# Three things, each guarding a named failure:
#   exec          — uvicorn becomes PID 1 and receives Cloud Run's SIGTERM
#   0.0.0.0       — Cloud Run routes to the container's external interface;
#                   127.0.0.1 answers the health check and nobody else
#   ${PORT:-8080} — Cloud Run injects $PORT and does not promise 8080
#
# `core/env.py`'s load_dotenv() prefers real environment variables, so it is a
# harmless no-op here and no .env is needed or wanted (spec §6).
CMD ["sh", "-c", "exec uvicorn fenceai.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

- [ ] **Step 4: Write the .dockerignore**

```
# Build-context hygiene, and one security control.
#
# `.env` is the one that matters. It is gitignored, it holds a live
# ANTHROPIC_API_KEY, and nothing but this file stops a future `COPY . .` from
# baking it into a pushed image. Spec §6 says no `.env` ever ships; this is what
# makes that true by construction instead of by everybody remembering.
.env
.env.*

# A developer's database has been 141 MB of accumulated state before now — see
# tests/api/conftest.py, which records what that cost. None of it belongs in an
# image.
*.db
*.db-wal
*.db-shm

.venv/
**/__pycache__/
**/*.pyc

.git/
.gitignore
.github/
.claude/

tests/
tools/
docs/
plan/
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/deploy/test_dockerfile.py -q`
Expected: 6 passed.

- [ ] **Step 6: Build the image by hand, once, to see it work**

Run: `docker build -t fenceai:slice3 .`
Expected: build succeeds. If it fails at the second `uv sync` complaining about
a missing README or build backend, read the error rather than adding files
speculatively — `pyproject.toml` at 2f4efb0 declares no `readme`, so none is
needed.

- [ ] **Step 7: Confirm the suite is unmoved**

Run: `FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest -q`
Expected: 3998 passed, 1 skipped (3992 + the 6 new).

- [ ] **Step 8: Commit**

```bash
git add Dockerfile .dockerignore tests/deploy/__init__.py tests/deploy/test_dockerfile.py
git commit -m "feat(deploy): a two-stage image that honours \$PORT and ships no .env

Both extras on every sync line, --frozen on every sync line, 0.0.0.0 and
\${PORT:-8080} in an exec CMD. Each is a named first-deploy failure from
spec §6, and each is asserted by a test that needs no Docker daemon.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The image, actually built and actually run

**Files:**
- Test: `tests/deploy/test_container.py`

**Interfaces:**
- Consumes: the `Dockerfile` from Task 1.
- Produces: `FENCEAI_TEST_DOCKER=1` as the gate variable Task 6's CI job sets.
  No importable symbols.

- [ ] **Step 1: Write the failing test**

Create `tests/deploy/test_container.py`:

```python
"""The image, built and run, rather than read.

Gated on `FENCEAI_TEST_DOCKER` for the same reason the Postgres half of the
suite is gated on `FENCEAI_TEST_POSTGRES` (`tests/conftest.py`): a laptop with
no daemon must stay comfortable. The gate is ASYMMETRIC on purpose — with the
variable SET and Docker unusable these tests FAIL rather than skip, because
slice 1's amendment already paid for the other arrangement: "a dual-run that
nothing runs proves nothing", and a container job that skips its own tests exits
0 having proved exactly that.

The host port is assigned by Docker (`-p 0:...`) and read back, never chosen
here. A fixed port in this repository has twice produced 22 errors that read
like a bug in whatever was just written; `tests/tools/conftest.py` records both
occasions, and nothing in this file needs a predictable port.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "fenceai-test:slice3"
_GATE = "FENCEAI_TEST_DOCKER"


def _docker(*args: str, check: bool = True,
            timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], cwd=ROOT, check=check,
                          capture_output=True, text=True, timeout=timeout)


@pytest.fixture(scope="module", autouse=True)
def _require_docker():
    if not os.environ.get(_GATE, "").strip():
        pytest.skip(f"set {_GATE}=1 to build and run the image")
    try:
        _docker("version", "--format", "{{.Server.Version}}", timeout=60)
    except Exception as exc:  # noqa: BLE001 — the reason goes in the message
        pytest.fail(f"{_GATE} is set but the Docker daemon did not answer "
                    f"({exc!r}) — a container job that skips its own tests "
                    f"passes while proving nothing")


@pytest.fixture(scope="module")
def image() -> str:
    """Built once for the module. The image is left behind deliberately: it is
    layer-cached, and rebuilding it per test would dominate the run."""
    _docker("build", "-t", IMAGE, ".")
    return IMAGE


class _Container:
    def __init__(self, cid: str, port: int) -> None:
        self.cid, self.port = cid, port

    def url(self, path: str) -> str:
        return f"http://localhost:{self.port}{path}"

    def logs(self) -> str:
        p = _docker("logs", self.cid, check=False)
        return f"--- container stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"


@pytest.fixture()
def run_container(image):
    """Start containers, and remove every one of them afterwards."""
    started: list[str] = []

    def start(env: dict[str, str], container_port: int = 8080) -> _Container:
        args = ["run", "-d", "-p", f"0:{container_port}"]
        for key, value in env.items():
            args += ["-e", f"{key}={value}"]
        cid = _docker(*args, image).stdout.strip()
        started.append(cid)
        mapped = _docker("port", cid, str(container_port)).stdout.strip().splitlines()[0]
        return _Container(cid, int(mapped.rsplit(":", 1)[1]))

    yield start
    for cid in started:
        _docker("rm", "-f", cid, check=False)


def _wait_healthy(c: _Container, timeout: float = 90.0) -> dict:
    """Condition-based, and it prints the container's OWN logs when it gives up.

    A fixed sleep here is the defect that kept this repository's CI red from the
    day CI was added (`tools/persona_lab/stack.py:_wait_for_both` tells the
    story), and a timeout that does not show the logs makes a refusal to boot
    look like a network problem.
    """
    deadline = time.monotonic() + timeout
    last = "no attempt completed"
    while time.monotonic() < deadline:
        running = _docker("inspect", "-f", "{{.State.Running}}", c.cid,
                          check=False).stdout.strip()
        if running != "true":
            raise AssertionError(f"the container exited before serving\n{c.logs()}")
        try:
            with urllib.request.urlopen(c.url("/api/health"), timeout=2) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001 — retried, and reported on timeout
            last = repr(exc)
        time.sleep(0.2)
    raise AssertionError(f"no health answer in {timeout}s (last: {last})\n{c.logs()}")


_DEV_ENV = {"FENCEAI_IDENTITY": "dev", "FENCEAI_AI": "stub",
            "FENCEAI_DB": "/tmp/fenceai.db"}


def test_the_image_carries_both_extras(image):
    """The §6 failure, asked directly. Built with a bare `uv sync` the image
    imports neither, comes up healthy anyway, and 500s on every route."""
    out = _docker("run", "--rm", image, "python", "-c",
                  "import psycopg, jwt; print('both')").stdout
    assert "both" in out


def test_the_server_answers_on_the_port_it_was_given(run_container):
    """Two properties in one request, and both are behavioural rather than
    read: an injected $PORT the CMD did not hardcode, reached through a
    published port that only works because the bind is 0.0.0.0."""
    c = run_container({**_DEV_ENV, "PORT": "9110"}, container_port=9110)
    assert _wait_healthy(c)["ok"] is True


def test_it_boots_under_iap_on_a_database_with_no_dev_seed(run_container):
    """`iap_identity_from_env()` imports `jwt` eagerly, so this is the sharpest
    available proof that the iap extra is in the image: without PyJWT the
    provider cannot be built and the process dies at startup.

    A fresh database, which is the only kind that may be served under iap —
    `identity/dev.py:dev_seed_lockout` is what makes the other kind refuse."""
    c = run_container({"FENCEAI_IDENTITY": "iap", "FENCEAI_AI": "stub",
                       "FENCEAI_DB": "/tmp/fresh.db",
                       "FENCEAI_IAP_AUDIENCE": "/projects/1/global/backendServices/2"})
    assert _wait_healthy(c)["ok"] is True


def test_the_container_does_not_run_as_root(image):
    assert _docker("run", "--rm", image, "id", "-u").stdout.strip() == "10001"
```

- [ ] **Step 2: Run it to verify it skips without the gate**

Run: `uv run pytest tests/deploy/test_container.py -q`
Expected: 4 skipped. This is the laptop case and it must stay comfortable.

- [ ] **Step 3: Run it with the gate set**

Run: `FENCEAI_TEST_DOCKER=1 uv run pytest tests/deploy/test_container.py -q`
Expected: the first run builds the image (a few minutes), then 4 passed.

If `test_it_boots_under_iap_on_a_database_with_no_dev_seed` fails before Task 4
exists, read the container logs it prints — at this point in the plan nothing
refuses a dev-seeded database, so a failure here is a real problem with the
image, not the lockout.

- [ ] **Step 4: Prove the asymmetric gate actually fires**

Run: `FENCEAI_TEST_DOCKER=1 PATH=/nonexistent uv run pytest tests/deploy/test_container.py -q`
Expected: FAILS (not skips) with "the Docker daemon did not answer". This is the
one property of this file that matters more than the rest, so see it once.

- [ ] **Step 5: Commit**

```bash
git add tests/deploy/test_container.py
git commit -m "test(deploy): build the image and run it, behind an asymmetric gate

Skips with no daemon, FAILS when FENCEAI_TEST_DOCKER is set and Docker
cannot be used — a container job that skips its own tests exits 0 having
proved nothing, which is the failure slice 1's amendment already paid for.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The stack — the app and a Postgres of its own

**Files:**
- Create: `compose.yaml`
- Modify: `tests/deploy/test_dockerfile.py` (add the compose assertions)

**Interfaces:**
- Consumes: the image from Task 1.
- Produces: `docker compose up -d --build --wait` brings up a healthy app on
  `${FENCEAI_COMPOSE_PORT:-8080}` against Postgres. Task 7 drives it.

- [ ] **Step 1: Write the failing test**

Append to `tests/deploy/test_dockerfile.py`:

```python
COMPOSE = ROOT / "compose.yaml"


def test_the_database_publishes_no_host_port():
    """5432 on a developer's machine is already the test Postgres that
    `FENCEAI_TEST_POSTGRES` names. A second publisher either collides with it or
    quietly shadows it, and nothing here needs to reach the database from the
    host — `docker compose exec db psql` does."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "5432:5432" not in text
    assert "5433:5432" not in text


def test_the_app_waits_for_a_healthy_database_rather_than_a_sleep():
    """`Store()` opens its connection during `lifespan`, so the app must not
    start before Postgres accepts one. A fixed sleep racing a daemon's startup
    is the defect that kept this repository's CI red from the day CI was
    added."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "condition: service_healthy" in text
    assert "pg_isready" in text


def test_the_app_service_sets_no_dev_user():
    """`tools/ui_smoke.py` excludes FENCEAI_DEV_USER deliberately and documents
    why at length: DevIdentity is cookie-first and env-second, so a default here
    authenticates the page's first `GET /api/session` before the login form
    runs, making the form's sign-in redundant and racing its own tab placement
    against queue.js. The checkpoint suite signs in like a person."""
    assert "FENCEAI_DEV_USER" not in COMPOSE.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/deploy/test_dockerfile.py -q`
Expected: the 3 new tests FAIL with `FileNotFoundError: .../compose.yaml`.

- [ ] **Step 3: Write compose.yaml**

```yaml
# The local half of slice 3: the app exactly as it will be deployed, against a
# real Postgres. `docker compose up -d --build --wait`, and the checkpoint is
# reachable on http://localhost:8080.
#
# Three deliberate choices, each with a failure behind it:
#
#  * `db` publishes NO host port. 5432 here is already a test Postgres that
#    `FENCEAI_TEST_POSTGRES` points at; a second publisher would collide with it
#    or silently shadow it. Look inside with
#    `docker compose exec db psql -U fenceai fenceai`.
#  * `depends_on: condition: service_healthy`, never a sleep. `Store()` opens
#    its connection during `lifespan`, and a fixed sleep racing a daemon's start
#    is the defect that kept this repo's CI red from the day CI was added.
#  * the app's host port is overridable. Every fixed port in this repository has
#    eventually collided with another checkout, an agent, or a persona lab.

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: fenceai
      POSTGRES_PASSWORD: fenceai
      POSTGRES_DB: fenceai
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      # `-U` and `-d` are not decoration: bare `pg_isready` asks about a database
      # named after the OS user, which does not exist here. `start_period`
      # covers the entrypoint's temporary server, which answers while it is
      # still running the init scripts.
      test: ["CMD-SHELL", "pg_isready -U fenceai -d fenceai"]
      interval: 2s
      timeout: 3s
      retries: 15
      start_period: 5s

  app:
    build: .
    environment:
      FENCEAI_DB: postgresql://fenceai:fenceai@db:5432/fenceai
      FENCEAI_AI: stub
      FENCEAI_IDENTITY: dev
      PORT: "8080"
      # FENCEAI_DEV_USER is absent on purpose, not merely unset — see
      # tests/deploy/test_dockerfile.py:test_the_app_service_sets_no_dev_user.
    ports:
      - "${FENCEAI_COMPOSE_PORT:-8080}:8080"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      # python, not curl: the runtime image is python:3.12-slim and has no curl.
      # This is what makes `up --wait` mean something.
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health', timeout=2)\""]
      interval: 3s
      timeout: 5s
      retries: 20
      start_period: 5s

volumes:
  pgdata:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/deploy/test_dockerfile.py -q`
Expected: 9 passed.

- [ ] **Step 5: Bring the stack up and see it healthy**

```bash
docker compose up -d --build --wait
docker compose ps
curl -s localhost:8080/api/health
```
Expected: both services `healthy`, and `{"ok":true,"interpreter":"stub"}`.

- [ ] **Step 6: Prove it is really on Postgres, not a stray SQLite file**

```bash
docker compose exec db psql -U fenceai fenceai -c '\dt'
docker compose exec db psql -U fenceai fenceai -c 'select id, email, capacity from users order by id'
```
Expected: the store's tables exist, and the three dev demo accounts
(`u_admin`, `u_dana`, `u_yossi`) are present — which is precisely the database
Task 4 will refuse to serve under `iap`.

- [ ] **Step 7: Commit**

```bash
git add compose.yaml tests/deploy/test_dockerfile.py
git commit -m "feat(deploy): compose the app with a Postgres of its own

The db publishes no host port (5432 is already the test server), the app
waits on a real pg_isready healthcheck rather than a sleep, and the host
port is overridable because every fixed port here has eventually collided.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: A dev-seeded database refuses to be served under `iap`

This is carried finding 3 from slice 2's reviews. Slice 3 is what creates the
database slice 4 must boot under `iap`, so the trap and its guard belong in the
same slice. Left alone it detonates at slice 4's checkpoint, in front of the
product owner, and the only recovery is database surgery.

**The mechanism, confirmed in the code:** a dev boot seeds `u_admin` /
`admin@example.com` as an **active admin** row. `api/auth.py:_bootstrap` fires
only when no active admin exists anywhere, so it never fires for the operator's
real Google address — and no Google account can ever hold an address at
`example.com`, which IANA reserves for documentation. Every request is refused,
for ever.

**Files:**
- Modify: `src/fenceai/identity/dev.py`
- Modify: `src/fenceai/api/app.py` (`lifespan`, and delete `DEMO_ACCOUNTS`)
- Test: `tests/identity/test_dev_seed_lockout.py`
- Test: `tests/api/test_dev_seed_boot.py`

**Interfaces:**
- Consumes: `User` rows from `Store.list_users()`.
- Produces:
  - `fenceai.identity.dev.DEMO_ACCOUNTS: tuple[tuple[str, str, str, str], ...]`
    — `(id, name, email, capacity)`, moved verbatim from `api/app.py`.
  - `fenceai.identity.dev.dev_seed_lockout(provider_id: str, users) -> str | None`
    — the operator-facing reason this database may not be served, or `None`.

- [ ] **Step 1: Write the failing unit test**

Create `tests/identity/test_dev_seed_lockout.py`:

```python
"""A database created in dev mode cannot be served under `iap`.

Slice 2's reviews found this by running the code: the dev seed writes an ACTIVE
admin row at an IANA-reserved address, `_bootstrap` fires only while no active
admin exists, and no Google account can ever authenticate as
`admin@example.com`. Every request is refused and the only cure is database
surgery.
"""

from __future__ import annotations

from fenceai.identity.dev import DEMO_ACCOUNTS, dev_seed_lockout
from fenceai.identity.model import User


def _demo_rows() -> list[User]:
    return [User(id=uid, name=name, email=email, capacity=cap)
            for uid, name, email, cap in DEMO_ACCOUNTS]


def test_dev_mode_is_never_refused_its_own_seed():
    """The whole point of the seed is that a developer lands somewhere."""
    assert dev_seed_lockout("dev", _demo_rows()) is None


def test_iap_refuses_a_database_holding_the_dev_seed():
    reason = dev_seed_lockout("iap", _demo_rows())
    assert reason is not None
    assert "admin@example.com" in reason
    assert "FENCEAI_DB" in reason, "the message must name the remedy, not just the fault"


def test_iap_is_content_with_a_database_of_real_accounts():
    """A company's own rows are what this must never refuse. Ids here are the
    shape `POST /api/users` actually mints."""
    real = [User(id="u_3f9a1c22", name="Dana", email="dana@fences.co.il",
                 capacity="sales"),
            User(id="u_b71e0d84", name="Yossi", email="yossi@fences.co.il",
                 capacity="admin")]
    assert dev_seed_lockout("iap", real) is None


def test_an_empty_database_is_the_normal_first_deploy():
    assert dev_seed_lockout("iap", []) is None


def test_a_demo_id_is_caught_even_at_a_company_address():
    """The id is the precise half of the fingerprint. `POST /api/users` mints
    `u_{uuid4().hex[:8]}` — hex — and `admin`, `dana` and `yossi` are not hex,
    so a real grant can never collide with one of these."""
    disguised = [User(id="u_admin", name="Admin", email="boss@fences.co.il",
                      capacity="admin")]
    assert dev_seed_lockout("iap", disguised) is not None


def test_a_demo_address_is_caught_even_under_a_minted_id():
    """And the address is the belt. `example.com` is IANA-reserved, so no Google
    account can hold one however the row got its id."""
    disguised = [User(id="u_3f9a1c22", name="Admin", email="ADMIN@example.com",
                      capacity="admin")]
    assert dev_seed_lockout("iap", disguised) is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/identity/test_dev_seed_lockout.py -q`
Expected: collection error — `ImportError: cannot import name 'DEMO_ACCOUNTS'`.

- [ ] **Step 3: Move `DEMO_ACCOUNTS` and add the policy**

Append to `src/fenceai/identity/dev.py`:

```python
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


def dev_seed_lockout(provider_id: str, users) -> str | None:
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
    """
    if provider_id == "dev":
        return None
    found = sorted({u.email for u in users
                    if u.id in _DEMO_IDS or u.email.strip().lower() in _DEMO_EMAILS})
    if not found:
        return None
    return (
        f"refusing to serve this database under FENCEAI_IDENTITY={provider_id}: "
        f"it was created by a dev-mode boot and still holds the seeded demo "
        f"account(s) {', '.join(found)}. Nobody can authenticate as an "
        "example.com address under IAP, and while any seeded admin row is "
        "active FENCEAI_BOOTSTRAP_ADMIN stays disabled — so no real first admin "
        "can ever be seated and every request is refused. Point FENCEAI_DB at a "
        "database that has never been booted in dev mode."
    )
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `uv run pytest tests/identity/test_dev_seed_lockout.py -q`
Expected: 6 passed.

- [ ] **Step 5: Write the failing boot test**

Create `tests/api/test_dev_seed_boot.py`:

```python
"""The scenario, staged end to end: a dev database, then an iap boot.

Two `TestClient`s in one test is a shape no other test in this suite uses, and
here it IS the subject — the lockout only exists in the transition. Runs over
both backends through the `dsn` fixture, because the database that will actually
be promoted by mistake is the Postgres one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fenceai.api.app import app
from fenceai.identity.ports import Principal


class _Iap:
    """Enough of an IdentityProvider to make `lifespan` build an iap-shaped app.
    A stand-in rather than the real adapter, which would want Google's keys."""

    provider_id = "iap"

    def principal(self, headers, cookies):
        return Principal(email="founder@fences.co.il", subject="sub-founder")


def test_a_dev_seeded_database_refuses_to_boot_under_iap(monkeypatch):
    """`tests/api/conftest.py`'s autouse `_isolated_store` has already pointed
    FENCEAI_DB at this run's backend, so both boots below share one database —
    which is the whole scenario."""
    with TestClient(app):
        pass  # a dev boot; `_seed_demo_accounts` writes the three demo rows

    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: _Iap())
    with pytest.raises(RuntimeError) as e:
        with TestClient(app):
            pass

    reason = str(e.value)
    assert "admin@example.com" in reason
    assert "FENCEAI_DB" in reason


def test_a_fresh_database_boots_under_iap_normally(monkeypatch):
    """The refusal must not fire on the arrangement every real first deploy
    has. Nothing has booted this database in dev mode."""
    monkeypatch.setattr("fenceai.api.app.build_provider", lambda: _Iap())
    with TestClient(app) as c:
        assert c.get("/api/health").json()["ok"] is True
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/api/test_dev_seed_boot.py -q`
Expected: `test_a_dev_seeded_database_refuses_to_boot_under_iap` FAILS with
`DID NOT RAISE RuntimeError` (twice — once per backend). The second test passes
already, which is correct: it is the regression guard, not the new behaviour.

- [ ] **Step 7: Wire the check into `lifespan`**

In `src/fenceai/api/app.py`, add `DEMO_ACCOUNTS` and `dev_seed_lockout` to the
existing `from fenceai.identity.dev import DEV_COOKIE` line, and **delete** the
`DEMO_ACCOUNTS` list near `_seed_demo_accounts` (keeping the comment above it
that explains why the seed is dev-only, which is still true and still earns its
place). Then, in `lifespan`, immediately after the provider-mismatch WARNING
block and **before** `state.interpreter = build_interpreter()`:

```python
    # Before anything is written and before any request can arrive. A database
    # this provider cannot serve must say so at boot, not refuse every caller
    # afterwards — `identity/provider.py` states the principle one level up:
    # "failing at boot is strictly better than failing per request".
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
        try:
            state.store.close()
        except Exception:
            # Never let a failed close hide the refusal that names the remedy —
            # `store/dialect.py`'s `Conn.execute` swallows a failed rollback for
            # the same reason. The close matters (a raise past `yield` orphans
            # the open read and deadlocks a DROP SCHEMA), but it matters less
            # than the sentence the operator is about to read.
            pass
        raise RuntimeError(f"[fenceai] {lockout}")
```

(This snippet was corrected in review after implementation: raising past
`yield` on a live Postgres connection deadlocked the test suite's own schema
teardown, and the naive fix — an unguarded `state.store.close()` — could
itself swallow the refusal's sentence if the close failed. Both the plan and
`src/fenceai/api/app.py` now show the guarded version above.)

- [ ] **Step 8: Run both test files to verify they pass**

Run: `FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest tests/api/test_dev_seed_boot.py tests/identity/test_dev_seed_lockout.py -q`
Expected: 10 passed (6 unit + 2 boot tests × 2 backends).

- [ ] **Step 9: Run the suites most likely to be disturbed**

Run: `FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest tests/api tests/identity tests/architecture -q`
Expected: all pass. `tests/api/test_gate.py`'s `under_iap` fixture boots the real
app on a provider reporting `provider_id == "iap"`, and it passes because
`tests/api/conftest.py` gives every API test a fresh database — verified before
this plan was written, and the reason this change is safe. If anything here goes
red, that assumption is what to re-check first.

- [ ] **Step 10: Run the full suite**

Run: `FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest -q`
Expected: 4008 passed, 1 skipped.

- [ ] **Step 11: Commit**

```bash
git add src/fenceai/identity/dev.py src/fenceai/api/app.py \
        tests/identity/test_dev_seed_lockout.py tests/api/test_dev_seed_boot.py
git commit -m "fix(identity): refuse to serve a dev-seeded database under iap

Slice 2 review finding 3. A dev boot seeds admin@example.com as an ACTIVE
admin; _bootstrap fires only while no active admin exists; no Google
account can hold an IANA-reserved address. So every request is refused
for ever and the cure is database surgery.

Slice 3 is what creates the database slice 4 boots under iap, so the trap
and its guard ship together. DEMO_ACCOUNTS moves to identity/dev.py so
the ids are named once.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Point the browser suite at a server it did not start

**Files:**
- Modify: `tools/ui_smoke.py`
- Test: `tests/tools/test_ui_smoke_target.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ui_smoke.target_base_url() -> str` — no trailing slash.
  - `ui_smoke.attached() -> bool` — True when we must not stop the server.
  - `FENCEAI_SMOKE_BASE_URL` as the environment seam Task 7 uses.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_ui_smoke_target.py`:

```python
"""Where the browser suite points, and who owns the server it talks to.

Read at CALL time, not at import — `tools/persona_lab/stack.py:ports_for`
records what the other way costs: a module-level constant froze at its default
before any fixture ran, and the override silently did nothing while looking
like it worked.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_it_starts_its_own_server_by_default(monkeypatch):
    import ui_smoke

    monkeypatch.delenv("FENCEAI_SMOKE_BASE_URL", raising=False)
    assert ui_smoke.target_base_url() == f"http://localhost:{ui_smoke.PORT}"
    assert ui_smoke.attached() is False


def test_it_attaches_to_a_base_url_when_given_one(monkeypatch):
    import ui_smoke

    monkeypatch.setenv("FENCEAI_SMOKE_BASE_URL", "http://localhost:8080")
    assert ui_smoke.target_base_url() == "http://localhost:8080"
    assert ui_smoke.attached() is True


def test_a_trailing_slash_does_not_become_a_double_one(monkeypatch):
    """Every call site appends a path, so `…8080//api/health` is one typo away
    and a 404 from it would read as a broken server."""
    import ui_smoke

    monkeypatch.setenv("FENCEAI_SMOKE_BASE_URL", "http://localhost:8080/")
    assert ui_smoke.target_base_url() == "http://localhost:8080"


def test_a_blank_value_is_not_an_attachment(monkeypatch):
    """`FENCEAI_SMOKE_BASE_URL=` exported empty must behave as unset, or a
    stale export in a shell profile silently disables the server launch and the
    run fails with nothing listening."""
    import ui_smoke

    monkeypatch.setenv("FENCEAI_SMOKE_BASE_URL", "   ")
    assert ui_smoke.attached() is False
    assert ui_smoke.target_base_url() == f"http://localhost:{ui_smoke.PORT}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/tools/test_ui_smoke_target.py -q`
Expected: 4 failures — `AttributeError: module 'ui_smoke' has no attribute
'target_base_url'`.

- [ ] **Step 3: Add the two functions**

In `tools/ui_smoke.py`, directly below the `PORT` / `CDP_PORT` constants
(currently lines 31–32):

```python
#: Point the whole suite at a server that is ALREADY running, instead of one
#: this script starts. Set to e.g. `http://localhost:8080` to check the
#: container: the thing being proven there is that the IMAGE serves this app,
#: and a uvicorn launched from the source tree would prove the opposite.
_BASE_URL_ENV = "FENCEAI_SMOKE_BASE_URL"


def target_base_url() -> str:
    """Where the app under test lives, with no trailing slash.

    Read at CALL time, not at import. `tools/persona_lab/stack.py:ports_for`
    records what the other way costs: a module-level constant froze at its
    default before any fixture could override it, and did nothing while looking
    exactly as though it worked.
    """
    given = os.environ.get(_BASE_URL_ENV, "").strip().rstrip("/")
    return given or f"http://localhost:{PORT}"


def attached() -> bool:
    """True when we did not start the server, and therefore must not stop it."""
    return bool(os.environ.get(_BASE_URL_ENV, "").strip())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/tools/test_ui_smoke_target.py -q`
Expected: 4 passed.

- [ ] **Step 5: Replace the five URL sites**

Each currently interpolates `PORT` directly. Replace with `target_base_url()`:

| Line (at 2f4efb0) | Now | Becomes |
|---|---|---|
| 420 | `url=f"http://localhost:{PORT}/"` | `url=target_base_url() + "/"` |
| 4899 | `f"http://localhost:{PORT}/api/health"` | `target_base_url() + "/api/health"` |
| 4909 | `Cdp(f"http://localhost:{PORT}/", …)` | `Cdp(target_base_url() + "/", …)` |
| 6917 | `url=f"http://localhost:{PORT}/"` | `url=target_base_url() + "/"` |
| 9066 | `f"http://localhost:{PORT}/#evidence="` | `target_base_url() + "/#evidence="` |

Leave the `CDP_PORT` URLs alone — Chrome is always ours, wherever the app runs.

- [ ] **Step 6: Branch the launch in `main()`**

Replace the app-side "something is already listening" abort (lines ~4826–4833)
with a branch that checks the opposite thing when attached:

```python
    if attached():
        # Inverted deliberately. When we own the server a listener means a stale
        # process serving old code; when we are attaching, a listener is the
        # entire premise, and its absence must be said plainly rather than
        # discovered 60 s later as a readiness timeout.
        try:
            urllib.request.urlopen(f"{target_base_url()}/api/health", timeout=5)
        except Exception as exc:
            print(f"FATAL: {_BASE_URL_ENV}={target_base_url()} but nothing "
                  f"answered /api/health there ({exc!r}) — start it first")
            return 2
    else:
        # a stale server on our port would silently serve old code/data — abort loudly
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/health", timeout=1)
            print(f"FATAL: something is already listening on :{PORT} — kill it first "
                  f"(pkill -f 'port {PORT}')")
            return 2
        except Exception:
            pass  # port free, good
```

Leave the CDP-port abort immediately below it exactly as it is, including its
comment: a browser already holding `:9333` answers `/json/version` and satisfies
the readiness loop with somebody else's profile, and that reasoning is
independent of where the app runs.

Then make the server launch conditional. The temp-DB and `Popen` block
(lines ~4854–4874) becomes:

```python
    server = None
    if not attached():
        db = tempfile.mktemp(suffix=".db")
        # ... existing comment about FENCEAI_DEV_USER being excluded, unchanged ...
        env = {**{k: v for k, v in os.environ.items() if k != "FENCEAI_DEV_USER"},
               "FENCEAI_DB": db, "FENCEAI_AI": "stub", "FENCEAI_IDENTITY": "dev"}
        server = subprocess.Popen(
            ["uv", "run", "uvicorn", "fenceai.api.app:app", "--port", str(PORT)],
            env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
```

In the readiness loop, only wait on the app's health when we started it (when
attached, the check above already proved it answers) — and in the teardown, only
kill `server` when it is not `None`. Find every later use of `server` and guard
it; the file kills the process group at the end of `main()`.

- [ ] **Step 7: Verify the smoke suite still works the ordinary way**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: 646/646, unchanged. This is the regression that matters most in this
task — the seam must be invisible when unused.

- [ ] **Step 8: Verify the guards that read this file are still green**

Run: `uv run pytest tests/web/test_smoke_cases_registered.py tests/tools -q`
Expected: all pass. `test_smoke_cases_registered.py` parses `_CHOICE_CASES` and
asserts every `_smoke_*` function is registered; this task adds no cases, so it
must stay green.

- [ ] **Step 9: Commit**

```bash
git add tools/ui_smoke.py tests/tools/test_ui_smoke_target.py
git commit -m "feat(tools): let the browser suite attach to a running server

FENCEAI_SMOKE_BASE_URL points all 646 checks at a server this script did
not start — which is how the container gets checked, since a uvicorn
launched from the source tree would prove the opposite of what is wanted.

Read at call time, not import: a module-level constant froze at its
default once before in this repo and did nothing while looking correct.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: CI builds the image

Slice 5 owns build, registry and deploy. This job is none of those: it builds
and runs, and pushes nothing. The precedent for putting it here is slice 1's own
amendment — *"a dual-run that nothing runs proves nothing"* — which applies
unchanged to a container test nothing runs.

**Files:**
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: `FENCEAI_TEST_DOCKER` from Task 2.
- Produces: a second required check on every PR.

- [ ] **Step 1: Add the job**

Append to `.github/workflows/tests.yml`, as a sibling of `pytest`:

```yaml
  container:
    # Slice 5 owns build-and-push. This job pushes nothing: it builds the image
    # and runs it, because `tests/deploy/test_container.py` skips without a
    # daemon and slice 1's amendment already ruled on that shape — "a dual-run
    # that nothing runs proves nothing". FENCEAI_TEST_DOCKER makes those tests
    # FAIL rather than skip if Docker is unusable, so this job cannot go green
    # by doing nothing.
    runs-on: ubuntu-latest
    env:
      FENCEAI_TEST_DOCKER: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      # No extras on the RUNNER on purpose. psycopg and PyJWT belong in the
      # IMAGE, and installing them here too would hide a deploy test that had
      # quietly come to depend on the host environment.
      - run: uv sync
      - name: Build the image and run it
        run: uv run pytest tests/deploy -q
```

- [ ] **Step 2: Verify the workflow parses**

Run: `uv run python -c "import tomllib" && python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/tests.yml')); print('yaml ok')"`
Expected: `yaml ok`. If PyYAML is not installed, skip this step — the push in
step 4 is the real check.

- [ ] **Step 3: Reproduce the job locally, exactly as CI will run it**

Run: `FENCEAI_TEST_DOCKER=1 uv run pytest tests/deploy -q`
Expected: 10 passed (6 Dockerfile + 3 compose + 4 container = 13; adjust to
whatever Tasks 1–3 actually left, and record the real number here).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: build the image and run it, on every PR

No registry and no deploy — those stay slice 5's. But a container test
that nothing runs proves nothing, which is the ruling slice 1's amendment
already made about the dual-run.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: The checkpoint — a fence built and a run generated, on Postgres

Spec §8: *"Each ends somewhere a person can watch it work. Green tests are not
the checkpoint."*

**Files:** none. This task runs things and records what they said.

- [ ] **Step 1: Bring the stack up from nothing**

```bash
docker compose down -v
docker compose up -d --build --wait
docker compose ps
```
Expected: `db` and `app` both `healthy`. `down -v` is not optional — the browser
suite asserts on seeded state, so it needs a database as fresh as the temporary
SQLite file it would otherwise have made itself.

- [ ] **Step 2: Confirm nothing is holding the browser's debug port**

Run: `ss -ltn | grep -E ':9333|:8080' || echo "9333 free, 8080 is the stack"`
Expected: 8080 listening (the container), 9333 free. A Chrome already on 9333
would satisfy the readiness wait with somebody else's profile, which `ui_smoke`
documents at length.

- [ ] **Step 3: Run all 646 browser checks against the container**

```bash
FENCEAI_SMOKE_BASE_URL=http://localhost:8080 \
  uv run --with websocket-client python tools/ui_smoke.py
```
Expected: **646/646**, against the image, on Postgres. Among them are the checks
that draw a fence and generate a run — which is the checkpoint spec §8 asks for.

If a check fails, do not assume the container. Re-run the same suite with no
`FENCEAI_SMOKE_BASE_URL` first: that separates "the image is wrong" from "the
seam is wrong" from "this check was already fragile", and slice 2 lost time
twice to symptoms that turned out to belong to the previous category.

- [ ] **Step 4: Prove the data really landed in Postgres**

```bash
docker compose exec db psql -U fenceai fenceai -c \
  'select count(*) as projects from projects'
docker compose exec db psql -U fenceai fenceai -c \
  'select count(*) as runs from runs'
```
Expected: non-zero counts for both. The run the browser generated is in
Postgres, which is the whole claim of this slice.

- [ ] **Step 5: Demonstrate Task 4's refusal on this very database**

The stack's database was created in dev mode, so it is exactly the trap:

```bash
docker compose run --rm -e FENCEAI_IDENTITY=iap \
  -e FENCEAI_IAP_AUDIENCE=/projects/1/global/backendServices/2 app
```
Expected: the container exits non-zero, printing
`refusing to serve this database under FENCEAI_IDENTITY=iap … admin@example.com
… Point FENCEAI_DB at a database that has never been booted in dev mode.`

Record the exact output in `plan/current-status.md`. This is the finding slice 4
would otherwise have discovered in front of the product owner.

- [ ] **Step 6: Leave the stack up and tell the user**

Report: the stack is up on http://localhost:8080, what the smoke run said, the
two row counts, and the refusal's message. The checkpoint is the user seeing it,
not the suite passing.

- [ ] **Step 7: Full suite once more, offline and dual-run**

```bash
uv run pytest -q
FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest -q
```
Expected: offline — every Postgres test skipped and nothing failed; dual-run —
the full count with zero failures. Record both numbers; a count with no vintage
goes stale silently, which is how three of them did in slice 2.

---

### Task 8: The eleven findings this slice does not fix, and the docs

**Files:**
- Create: `docs/reviews/2026-09-23-slice-2-carried-findings.md`
- Modify: `docs/v1-runbook.md`
- Modify: `docs/adr/0013-identity-is-delegated.md`
- Modify: `plan/current-status.md`

- [ ] **Step 1: Write the triage document**

Create `docs/reviews/2026-09-23-slice-2-carried-findings.md` with one section per
finding, each carrying: the finding, how it was found, what it costs, and its
disposition. The dispositions, decided with the user on 2026-09-23:

| # | Finding | Disposition |
|---|---|---|
| 1 | Per-capacity authorization enforced at three places only; a `sales` account can read `/api/audit`, author an ACTIVE knowledge version, retire a safety rule, publish a fence model, edit another salesperson's job | **A slice of its own, next.** Already named in spec §9 and declared in ADR-0013. The largest open item. |
| 2 | An unknown `kid` does not force a key refresh — a scheduled Google rotation costs up to 1h of company-wide refusal | **Slice 4.** Has teeth only once real Google keys are in play. Largest availability risk in the IAP adapter. |
| 3 | A database booted under `dev` and later run under `iap` is permanently locked out | **Done in slice 3** — `identity/dev.py:dev_seed_lockout`. |
| 4 | The IAP key grace window is not enforced between retries; keys past the declared boundary verify for up to 60s | **Slice 4**, with finding 2 — same file, same trip. |
| 5 | No CSRF token, no Origin check, no CORS middleware; exploitability rests entirely on IAP's cookie SameSite, which is Google's choice and documented nowhere | **Slice 4, as a stated assumption in ADR-0013 at minimum.** Documentation, not code — and therefore the one most easily forgotten. |
| 6 | `Selection.author` and `Override.author` are client-named and reach the decision graph as `author`/`chosen_by` | **With finding 1** — same surface: who the actor is. `tests/api/test_gate.py`'s guard docstring records it rather than pretending otherwise. |
| 7 | A binding can never be cleared; no route resets `subject`, so a recreated Google account is refused for ever | **With finding 1** — an admin-routes change. |
| 8 | `Principal.subject` is not stripped (email is), so a whitespace `sub` binds | **Next slice**, quick. |
| 9 | `POST /api/knowledge` 500s on a `type` outside the Literal (bare `str` DTO) | **Next slice**, quick. |
| 10 | `tools/ui_smoke.py`'s `wait_for` lets a CDP evaluation error RAISE, so a transient null aborts a whole run | **Deferred unless it bites during slice 3.** Narrow it when done — swallow only the evaluation error and print the last one in the timeout's detail. A blanket `try/except` turns a broken selector into a mute timeout, which is worse. |
| 11 | People table a11y: unlabelled selects and buttons, `<th>` without `scope` | **Next frontend slice.** |
| 12 | `#sign-in-error` is hard-bound to `error.no_identity`, the wrong sentence in the one moment it fires | **Next frontend slice**, with 11. |

Open the document with the sentence that makes it worth reading: every one of
these was found by running the code, not by reading it.

- [ ] **Step 2: Add the container section to the runbook**

Under a new `## Container and Postgres` heading in `docs/v1-runbook.md`, after
`## Run`: `docker compose up -d --build --wait`; the app on
`http://localhost:8080` and `FENCEAI_COMPOSE_PORT` to move it; `docker compose
exec db psql -U fenceai fenceai` to look inside; `docker compose down -v` to
start over, and why the browser suite needs that; and
`FENCEAI_SMOKE_BASE_URL=http://localhost:8080` to point the 646 checks at the
container. Add one line to `## Troubleshooting`: a container that exits at boot
naming `admin@example.com` is `dev_seed_lockout`, and the fix is a fresh
`FENCEAI_DB`, not a code change.

- [ ] **Step 3: Record the refusal in ADR-0013**

Add to `## Consequences`: the dev-seed lockout, that it was found by running the
code in review rather than by reading it, and that `iap` now refuses to serve a
database created in dev mode — naming `identity/dev.py:dev_seed_lockout` and
noting that the strictness is deliberate (it refuses on any seeded row, not only
an admin one). Cross-reference the triage document for the findings ADR-0013
still openly does not address.

- [ ] **Step 4: Update the live status**

In `plan/current-status.md`: slice 3 complete, the two suite counts with the
commit they were measured at, the smoke result against the container, the row
counts from Postgres, the refusal's exact message, and the pointer to
`docs/superpowers/ledgers/2026-09-17-identity-is-googles/` now that slice 2's
ledger is durable. Note what slice 4 inherits: findings 2, 4 and 5 all live in
the IAP adapter and ADR-0013.

- [ ] **Step 5: Verify the docs did not break a fitness test**

Run: `FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres uv run pytest tests/architecture tests/web/test_locale_bundles.py -q`
Expected: pass. No route and no table was added in this slice, so the doc tables
in `docs/architecture/04-backend.md` need no edit — confirm that rather than
assume it.

- [ ] **Step 6: Verify the frozen contract is untouched**

```bash
cd docs/integration-contract && sha256sum -c contract.sha256
```
Expected: OK. Run it **from that directory** — the paths inside are relative to
it, so running it from the repo root reports MISSING FILE, and that is not
drift.

- [ ] **Step 7: Commit**

```bash
git add docs/reviews/2026-09-23-slice-2-carried-findings.md docs/v1-runbook.md \
        docs/adr/0013-identity-is-delegated.md plan/current-status.md
git commit -m "docs: slice 3 checkpoint, and the eleven findings it carries forward

Every finding in the triage table was found by running slice 2's code,
not by reading it. Finding 3 is fixed here; the other eleven have a
named home rather than a hope.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 8: Run both project reviewers before declaring the slice done**

CLAUDE.md requires `architecture-critic` and `test-reviewer` after slices
touching domain abstractions or the frontend contracts, and before declaring a
milestone. Both mutate code, so this is not optional and not a formality: in
slice 2 they found two blockers and a live defect behind a green 3184-test run.

**A fix round needs its own review seat.** Three separate defects in slice 2 — a
KeyError, a log-injection sink and a false docstring — were introduced by fixes
for earlier review findings, each written carefully by someone who had just read
the finding. Whatever these reviewers produce, the fixes for it get reviewed
again before merge.

If agents are fanned out, exactly **one** may run `tests/tools`,
`tools/ui_smoke.py` or the full suite. They bind fixed ports and a collision
surfaces as 22 errors that read like a bug in whatever was just written.

---

## Self-Review

**Spec coverage.** §6's container recipe → Task 1 (two stages, both extras,
`$PORT`); §6's "no `.env` ever ships" → Task 1's `.dockerignore`; §6's config
list → Task 3's compose environment; §8 slice 3's "Dockerfile, `$PORT`, run
against a real Postgres" → Tasks 1–3; §8's checkpoint "build a fence and
generate a run, on Postgres" → Task 7. §6's Release paragraph (build, push,
`gcloud run deploy`) is deliberately **not** covered: it is slice 5's, and Task 6
takes only the build-and-run half, with its reasoning stated. §9's unscheduled
seams (`store/migrations/`, unpinning `max-instances`, staging, multi-tenancy)
stay unscheduled; `store/migrations/` does not exist at 2f4efb0 and this slice
does not create it. §10 is respected: nothing here touches the contract,
`generate()`, the scenarios, or a numeric column.

**Verified before writing, not assumed:** `uv lock --check` passes at 2f4efb0;
`pyproject.toml` declares no `readme`, so the builder needs no `README.md`; host
ports 8080 and 5433 are free and 5432 is the existing test Postgres; `ui_smoke`
imports cleanly with `tools/` on `sys.path` and has no import-time side effects;
only five sites in it construct an app URL; no test in the suite enters
`TestClient` more than once, so Task 4's refusal cannot break an existing dual
boot; `tests/api/conftest.py` gives every API test a fresh database, which is why
`under_iap` survives Task 4; user ids are minted `u_{uuid4().hex[:8]}`, so the
demo-id check is exact rather than a heuristic.

**Numbers to expect:** baseline 3992+1. Task 1 adds 6, Task 3 adds 3, Task 4
adds 10 (6 unit + 2 × 2 backends), Task 5 adds 4 → **4015 passed, 1 skipped**
with Postgres, plus 4 more when `FENCEAI_TEST_DOCKER=1`. Treat these as
predictions to check, not as facts; if the arithmetic disagrees with pytest,
pytest is right and the plan should be corrected in place.

**Known soft spot.** Task 5 Step 6 edits `main()` in a 4,900-line file by
description rather than by a complete rewritten listing, because the surrounding
comments are long and load-bearing and reproducing them here would invite a
lossy paste. The implementer must read lines 4820–4930 before editing, and Step 7
(646/646 with no `FENCEAI_SMOKE_BASE_URL`) is the regression that catches a
mistake there.
