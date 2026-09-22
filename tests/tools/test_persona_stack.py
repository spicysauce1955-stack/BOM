"""A persona stack is fully isolated: its own port, its own throwaway DB,
its own Chrome. Two personas must never be able to see each other's work."""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))


def test_ports_never_collide_across_the_roster():
    from persona_lab import stack

    pairs = [stack.ports_for(i) for i in range(len(stack.PERSONAS))]
    flat = [p for pair in pairs for p in pair]
    assert len(set(flat)) == len(flat)


def test_roster_is_the_five_from_the_spec():
    from persona_lab import stack

    assert stack.PERSONAS == [
        "expert", "knowledge-owner", "topology-author",
        "fulfillment", "approver",
    ]


@pytest.fixture
def booted(tmp_path):
    from persona_lab import stack

    if not shutil.which("google-chrome"):
        pytest.skip("google-chrome not available")
    run_dir = tmp_path / "expert"
    run_dir.mkdir()
    session = stack.start("expert", 0, run_dir)
    yield stack, run_dir, session
    stack.stop(run_dir)


def test_stack_serves_the_app_and_records_its_session(booted):
    _stack, run_dir, session = booted

    body = urllib.request.urlopen(
        f"http://localhost:{session['port']}/api/health", timeout=5
    ).read()
    # /api/health answers {"ok": true, "interpreter": ...} — the plan's draft
    # asserted a "status" key this app has never served
    assert json.loads(body)["ok"] is True

    on_disk = json.loads((run_dir / "session.json").read_text())
    assert on_disk["ws_url"].startswith("ws://")
    assert on_disk["persona"] == "expert"
    assert Path(on_disk["db"]).exists()


def test_stop_releases_the_port(booted):
    stack, run_dir, session = booted

    stack.stop(run_dir)
    with pytest.raises(Exception):
        urllib.request.urlopen(
            f"http://localhost:{session['port']}/api/health", timeout=2
        )


def test_the_spawned_server_is_told_which_identity_to_run():
    """`FENCEAI_IDENTITY` has no default and the app refuses to boot without
    it, so a lab that only INHERITS the variable works exactly as long as
    somebody else set it.

    Source-level on purpose, and this is the whole reason it is worth writing:
    `tests/conftest.py` puts `FENCEAI_IDENTITY=dev` in the environment
    process-wide, so a lab that had lost the variable would still boot under
    pytest and die only from a bare shell. A test that booted the stack and
    watched it come up would pass on the polluted environment — the same trap
    that made `stack.py` inherit `FENCEAI_DEV_USER` after it stopped setting
    it. Read the spawn env instead of the running process."""
    import re

    src = (TOOLS / "persona_lab" / "stack.py").read_text()
    # From `env={` to the next argument: the dict itself contains braces (a
    # comprehension over os.environ), so it cannot be matched brace-to-brace.
    env_block = re.search(r"\benv=\{(.*?)\n\s*cwd=", src, re.S)
    assert env_block, "stack.py no longer passes an explicit env= to Popen"
    assert '"FENCEAI_IDENTITY": "dev"' in env_block.group(1), (
        "the spawned server inherits FENCEAI_IDENTITY instead of being told it; "
        "the lab then runs only under pytest"
    )
