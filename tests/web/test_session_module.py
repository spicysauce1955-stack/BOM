"""Who is signed in, and what that means for the screen (static/js/session.js).

The two functions here are pure so node can run them without a browser — the
`base-top.js` / `profile.js` split applied again, and for the same reason: the
decision (which view, is there a selector) is worth testing, and the DOM writing
that follows it is not.

**The assertion that earns this file** is
`test_signed_out_is_todays_app_and_not_a_locked_door`. Every existing user and all
428 browser checks are signed out. If signing out — or never signing in — stopped
being the full app on the `all` view, accounts would be a breaking change wearing
an addition's clothes, and the first thing anybody would notice is the smoke
suite going red for a reason nobody predicted.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { applyMe, lastProjectKey, pickProject, signedOutState } from "./js/session.js";

const out = {};
out.sales = applyMe({user: {id: "u_dana", name: "Dana", capacity: "sales"},
                     view: "sales", may_choose_view: false});
out.backoffice = applyMe({user: {id: "u_y", name: "Yossi", capacity: "backoffice"},
                          view: "backoffice", may_choose_view: false});
out.admin = applyMe({user: {id: "u_a", name: "Root", capacity: "admin"},
                     view: "all", may_choose_view: true});
out.out = signedOutState();
const list = [{id: "p_a"}, {id: "p_b"}, {id: "p_c"}];
out.pick_remembered = pickProject(list, "p_c");
out.pick_gone = pickProject(list, "p_deleted");
out.pick_none_remembered = pickProject(list, null);
out.pick_empty = pickProject([], "p_c");
out.pick_not_a_list = pickProject(undefined, "p_c");
out.key_dana = lastProjectKey("u_dana");
out.key_yossi = lastProjectKey("u_yossi");
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


def test_an_account_opens_on_the_view_the_server_named(out):
    """The browser does not work the view out from the capacity — the server
    answers it on `/api/me`. One implementation, and the one that can also refuse
    an action, rather than a second rule in JS that could drift from it."""
    assert out["sales"]["view"] == "sales"
    assert out["backoffice"]["view"] == "backoffice"
    assert out["admin"]["view"] == "all"


def test_only_an_admin_is_offered_the_selector(out):
    """An admin can "play" each role to see what it looks like. Nobody else is
    offered the control at all."""
    assert out["sales"]["selector"] is False
    assert out["backoffice"]["selector"] is False
    assert out["admin"]["selector"] is True


def test_the_selector_being_hidden_is_not_a_permission(out):
    """Stated as a test because the day somebody reads the hidden control as
    protection, this is what should have stopped them. `applyMe` carries no
    capability list and makes no decision about what may be DONE — it answers
    two presentation questions and nothing else."""
    assert set(out["sales"]) == {"user", "view", "selector"}


def test_the_account_is_carried_through_for_the_header(out):
    assert out["sales"]["user"]["name"] == "Dana"
    assert out["sales"]["user"]["capacity"] == "sales"


def test_signed_out_has_no_opinion_about_the_view(out):
    """`null` means *leave it alone*, and it is the point rather than a missing
    value.

    This test asserted `"all"` first, and was wrong. Signed out is today's app,
    and today's app REMEMBERS the view toggle across a reload — so naming a view
    here made every unsigned page load overwrite the preference somebody had
    chosen. The browser caught it on the check that reloads in sales mode and
    expects the vocabulary to survive; this file had happily pinned the defect.
    """
    assert out["out"]["view"] is None


def test_signed_out_is_todays_app_and_not_a_locked_door(out):
    """428 browser checks and every existing user are signed out. Signed out has
    to stay the full app with the selector offered, or accounts are a breaking
    change rather than an addition."""
    assert out["out"]["selector"] is True
    assert out["out"]["user"] is None


def test_sign_in_reopens_the_job_this_person_last_had_open(out):
    """The header picker is gone and a salesperson has no Jobs tab, so this is
    the ONLY way back to a job she was halfway through after signing out (which
    reloads). Before it, sign-in opened whichever project sorted first by a
    random id — possibly somebody else's."""
    assert out["pick_remembered"] == "p_c"


def test_a_remembered_job_that_no_longer_exists_falls_back_to_the_list(out):
    assert out["pick_gone"] == "p_a"
    assert out["pick_none_remembered"] == "p_a"
    assert out["pick_empty"] is None
    assert out["pick_not_a_list"] is None


def test_the_remembered_job_is_per_account(out):
    """A shared machine: the next person to sign in must not land in the job
    the previous one left open."""
    assert out["key_dana"] != out["key_yossi"]
    assert "u_dana" in out["key_dana"]
