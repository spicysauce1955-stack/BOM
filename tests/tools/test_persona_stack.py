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


def test_a_stack_that_does_not_come_up_says_which_half_did_not():
    """The failure that cost a whole CI run, and named the wrong thing.

    `start()` used to `time.sleep(4)` and then make one unguarded request to
    Chrome's debugging port. On a cold runner four seconds is not enough, the
    connection was refused, and the exception left the server holding its port
    — so every later test in the file failed with `port NNNN is already in
    use`. Twenty-two errors, all of them reporting a port collision, none of
    them mentioning a browser that had not finished starting.

    So this asserts the diagnosis, not just the failure: the message has to
    name the half that never answered."""
    from persona_lab import stack

    class _Running:
        pid = -1                      # killpg on a negative pid is swallowed
        returncode = None

        def poll(self):
            return None

    with pytest.raises(RuntimeError) as err:
        stack._wait_for_both(_Running(), _Running(), 1, 2, timeout=0.5)

    message = str(err.value)
    assert "the app on :1" in message, message
    assert "chrome's debugging port :2" in message, message


def test_a_process_that_dies_is_reported_as_dead_not_as_slow():
    """Waiting out the full timeout for something that already exited turns a
    clear error into a slow, vague one."""
    from persona_lab import stack

    class _Running:
        pid = -1
        returncode = None

        def poll(self):
            return None

    class _Dead:
        pid = -1
        returncode = 3

        def poll(self):
            return 3

    with pytest.raises(RuntimeError, match=r"app exited with code 3"):
        stack._wait_for_both(_Dead(), _Running(), 1, 2, timeout=30)

    with pytest.raises(RuntimeError, match=r"chrome exited with code 3"):
        stack._wait_for_both(_Running(), _Dead(), 1, 2, timeout=30)
