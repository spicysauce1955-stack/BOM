"""The words around the number (static/js/handover.js).

A `Quote` in this system is an immutable document with a status lifecycle that
somebody stands behind. What this panel shows is not that: it is a number
computed from whatever has been recorded so far, and the salesperson closed the
sale at the house from experience anyway. So the sentence under the figure
carries more weight than the digits, and the rule choosing it is pure and tested
here rather than left to a browser to notice.

The failure this guards is not a crash. It is a salesperson sending a customer a
number that reads as a commitment, computed from a layout with three things
still missing from it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { estimateNoteKey, estimateReady } from "./js/handover.js";

const clean = { gaps: [], estimate_ready: true };
const gappy = { gaps: [{ code: "address_missing" }], estimate_ready: true };
const blocked = { gaps: [{ code: "no_model_chosen", blocking: true }],
                  estimate_ready: false };

const out = {
  clean_note:    estimateNoteKey(clean, 250000),
  gappy_note:    estimateNoteKey(gappy, 250000),
  blocked_note:  estimateNoteKey(blocked, 250000),
  no_run_note:   estimateNoteKey(clean, null),
  missing_note:  estimateNoteKey(null, null),

  clean_shows:   estimateReady(clean, 250000),
  gappy_shows:   estimateReady(gappy, 250000),
  blocked_shows: estimateReady(blocked, 250000),
  no_run_shows:  estimateReady(clean, null),
  zero_shows:    estimateReady(clean, 0),
  missing_shows: estimateReady(null, 250000),
};
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_complete_job_gets_the_plain_estimate_wording(out):
    assert out["clean_note"] == "handover.estimate_note"
    assert out["clean_shows"] is True


def test_an_estimate_from_an_incomplete_layout_SAYS_it_will_move(out):
    """The one that matters. The number is still shown — a salesperson needs
    something to send today — but it must never sit there unqualified while
    three answers are outstanding."""
    assert out["gappy_note"] == "handover.estimate_stale"
    assert out["gappy_shows"] is True


def test_a_blocking_item_withholds_the_number_entirely(out):
    """No model chosen means the price has nothing behind it. Qualifying that
    with a sentence would not be enough: the digits are the part people
    remember."""
    assert out["blocked_note"] == "handover.estimate_blocked"
    assert out["blocked_shows"] is False


def test_before_anything_is_generated_there_is_no_number_and_a_reason(out):
    """"No run yet" is a state with its own sentence, not an error and not a
    zero. A blank where a price goes reads as free."""
    assert out["no_run_note"] == "handover.estimate_needs_run"
    assert out["no_run_shows"] is False


def test_a_genuine_zero_is_still_a_number(out):
    """`0` is falsy in JavaScript and a real total — an empty BOM priced at
    nothing. Suppressing it would show "press ⚙" to somebody who already had."""
    assert out["zero_shows"] is True


def test_a_failed_fetch_shows_no_number_rather_than_a_wrong_one(out):
    """The handover request can fail. Falling back to "here is your price"
    without the sheet that qualifies it is the worst available outcome."""
    assert out["missing_shows"] is False
    assert out["missing_note"] == "handover.estimate_blocked"
