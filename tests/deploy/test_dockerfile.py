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
    """Only what the image EXECUTES. A comment mentioning `uv sync` is not an
    instruction, and two of them in this Dockerfile say `uv sync` while
    carrying no flags at all."""
    return [ln for ln in _logical_lines()
            if ln.startswith("RUN") and "uv sync" in ln]


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
    against queue.js. The checkpoint suite signs in like a person.

    Asserted as "not set as a key" rather than "absent from the file", because
    compose.yaml earns the right to SAY why the variable is missing — and that
    comment is the thing most likely to be deleted by someone re-adding the
    variable later.
    """
    offenders = [ln for ln in COMPOSE.read_text(encoding="utf-8").splitlines()
                 if re.match(r"^\s*FENCEAI_DEV_USER\s*:", ln)]
    assert not offenders, f"set as a compose environment key: {offenders}"
