"""The queue screen's pure half (static/js/queue.js).

The three functions here decide what a row SAYS; the rendering that follows is
not worth testing and the decisions are. `base-top.js` / `profile.js` again.

**The assertion that earns this file** is `test_only_an_untaken_job_offers_the
_button`. Offering "Take it" on a job somebody else holds turns a name into a
race — two people press it, one wins, and the loser's screen said they could.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { bucketFor, waitedWord, withCell } from "./js/queue.js";

const out = {};
out.waited = [0, 59, 60, 3599, 3600, 86399, 86400, 259200].map(waitedWord);
out.buckets = ["drafting", "waiting", "planning", "planned", "quoted",
               "returned", "delivered", "cancelled"].map(bucketFor);
out.nobody = withCell({assignee: null}, "u_yossi");
out.mine = withCell({assignee: "u_yossi"}, "u_yossi");
out.theirs = withCell({assignee: "u_maya"}, "u_yossi");
out.signedOut = withCell({assignee: null}, null);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_waiting_is_said_in_whole_units(out):
    """"3 d" is what an office person says. "3 d 4 h 12 m" is a number pretending
    to be a decision."""
    assert out["waited"] == ["now", "now", "1 m", "59 m", "1 h", "23 h", "1 d", "3 d"]


def test_the_two_buckets_match_the_backends_two_lists(out):
    """Pinned against `lifecycle.py`'s split rather than restated, because two
    answers to "is this job finished" is how a job disappears from both lists."""
    from fenceai.project.lifecycle import FINISHED_STATES, OPEN_STATES

    order = ["drafting", "waiting", "planning", "planned", "quoted",
             "returned", "delivered", "cancelled"]
    for status, got in zip(order, out["buckets"]):
        want = "finished" if status in FINISHED_STATES else "open"
        assert got == want, status
        assert status in (FINISHED_STATES | OPEN_STATES)


def test_nobody_is_a_real_state_and_not_a_blank_cell(out):
    """It is the whole reason a queue exists."""
    assert out["nobody"]["who"] == "queue.nobody"   # the key, unresolved in node
    assert out["nobody"]["takeable"] is True


def test_only_an_untaken_job_offers_the_button(out):
    """Offering "Take it" on a job somebody else holds turns a name into a race:
    two people press it, one wins, and the loser's screen had said they could.
    The server refuses the second with `command_wrong_state` either way — this is
    the half that stops a person being invited to lose."""
    assert out["mine"]["takeable"] is False
    assert out["theirs"]["takeable"] is False


def test_your_own_row_is_marked_so_the_eye_finds_it(out):
    assert out["mine"]["mine"] is True
    assert out["theirs"]["mine"] is False


def test_signed_out_still_reads_rather_than_crashing(out):
    """`state.me` is null before `/api/me` answers, and the list may paint first."""
    assert out["signedOut"]["takeable"] is True
