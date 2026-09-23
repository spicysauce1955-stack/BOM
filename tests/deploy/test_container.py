"""The image, built and run, rather than read.

Gated on `FENCEAI_TEST_DOCKER` for the same reason the Postgres half of the
suite is gated on `FENCEAI_TEST_POSTGRES` (`tests/conftest.py`): a laptop with
no daemon must stay comfortable. The gate is ASYMMETRIC on purpose — with the
variable SET and Docker unusable these tests FAIL rather than skip, because
slice 1's amendment already paid for the other arrangement: "a dual-run that
nothing runs proves nothing", and a container job that skips its own tests
exits 0 having proved exactly that.

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
def image(_require_docker) -> str:
    """Built once for the module. The image is left behind deliberately: it is
    layer-cached, and rebuilding it per test would dominate the run.

    Takes `_require_docker` explicitly rather than relying on autouse-first
    ordering: an explicit dependency edge means a future reorder of this file
    cannot start a multi-minute docker build before the gate is consulted.
    """
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
