"""`session.js`'s pure half, in node.

`sessionState` decides nothing about what may be DONE — it answers which
screen this is and who to name on it. Pure, so node can check it without a
browser: `base-top.js`'s split applied again.

This file used to test `applyMe`/`signedOutState`/`pickProject`/
`lastProjectKey` together (as of `e44377b`). The identity rewrite deleted
`applyMe` and `signedOutState` in favour of `sessionState`, and this file was
rewritten around the new function — but `pickProject` and `lastProjectKey`
were NOT deleted (the brief said to keep them exactly as they were, and
`session.js` does), and the rewrite silently dropped their tests along with
the ones for the functions that actually went away. Restored below, adapted
to `sessionState` where their subject moved.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { isRefused, lastProjectKey, pickProject, refusalTextKey,
         sessionState, showsAskAnAdmin } from "./js/session.js";

const out = {};
out.ok = sessionState({status:"ok", email:"d@e.com",
                       user:{id:"u1", name:"Dana", capacity:"sales"},
                       view:"sales", may_choose_view:false});
out.admin = sessionState({status:"ok", email:"a@e.com",
                          user:{id:"u_a", name:"Root", capacity:"admin"},
                          view:"all", may_choose_view:true});
out.none = sessionState({status:"no_capacity", email:"s@e.com", user:null});
out.off = sessionState({status:"deactivated", email:"g@e.com", user:null});
out.anon = sessionState({status:"no_identity", email:"", user:null});

// The no-access screen's three decisions, over every status the server can
// answer with plus one it cannot answer with yet.
out.refused = {};
for (const st of ["ok", "no_identity", "no_capacity", "deactivated",
                  "subject_mismatch", "quarantined", "", null, undefined])
  out.refused[String(st)] = isRefused(st);
out.text = {};
out.advice = {};
for (const code of ["no_capacity", "account_deactivated", "subject_mismatch",
                    "quarantined", null])
  { out.text[String(code)] = refusalTextKey(code);
    out.advice[String(code)] = showsAskAnAdmin(code); }

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
def ss():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_resolved_answer_carries_the_person_and_their_view(ss):
    assert ss["ok"]["user"]["name"] == "Dana"
    assert ss["ok"]["view"] == "sales"
    assert ss["ok"]["selector"] is False


def test_a_refused_answer_names_the_address_but_nobody(ss):
    """The screen that says "ask an admin" has to be able to name you TO the
    admin you are about to ask — so `email` survives where `user` does not."""
    assert ss["none"]["status"] == "no_capacity"
    assert ss["none"]["email"] == "s@e.com"
    assert ss["none"]["user"] is None


def test_deactivated_is_its_own_answer_and_not_no_capacity(ss):
    """They HAVE a row. Telling them to ask for access would send them asking
    for something they already have."""
    assert ss["off"]["status"] == "deactivated"


def test_nobody_at_all_leaves_the_view_alone(ss):
    """`view: null` means *leave it alone*, and that is the point rather than a
    missing value — returning "all" here made every unsigned page load
    overwrite the remembered toggle, which the browser smoke caught once
    already."""
    assert ss["anon"]["status"] == "no_identity"
    assert ss["anon"]["view"] is None


def test_only_an_admin_is_offered_the_selector(ss):
    """An admin can "play" each role to see what it looks like. Nobody else is
    offered the control at all. Moved here from `applyMe`'s file: the source
    changed to `may_choose_view` on a `sessionState` answer, but the rule —
    one boolean, passed through one-for-one — did not."""
    assert ss["ok"]["selector"] is False
    assert ss["admin"]["selector"] is True


def test_the_selector_being_hidden_is_not_a_permission(ss):
    """Stated as a test because the day somebody reads the hidden control as
    protection, this is what should have stopped them. `sessionState` carries
    no capability list and decides nothing about what may be DONE — hiding is
    CSS and `localStorage` is editable, so an account that forces itself into
    another view has changed what it SEES and none of what it may DO.

    `code` is in the set and is not a counter-example: it is the refusal code
    for a status that is NOT `ok` (null here), a string the no-access screen
    renders as a sentence. It grants nothing and is read by nothing that
    decides anything."""
    assert set(ss["ok"]) == {"status", "code", "email", "user", "view", "selector"}
    assert ss["ok"]["code"] is None


def test_sign_in_reopens_the_job_this_person_last_had_open(ss):
    """The header picker is gone and a salesperson has no Jobs tab, so this is
    the ONLY way back to a job she was halfway through after signing out
    (which reloads). Before it, sign-in opened whichever project sorted first
    by a random id — possibly somebody else's."""
    assert ss["pick_remembered"] == "p_c"


def test_a_remembered_job_that_no_longer_exists_falls_back_to_the_list(ss):
    assert ss["pick_gone"] == "p_a"
    assert ss["pick_none_remembered"] == "p_a"
    assert ss["pick_empty"] is None
    assert ss["pick_not_a_list"] is None


def test_the_remembered_job_is_per_account(ss):
    """A shared machine: the next person to sign in must not land in the job
    the previous one left open."""
    assert ss["key_dana"] != ss["key_yossi"]
    assert "u_dana" in ss["key_dana"]


# --- the no-access screen's decisions, executed rather than pattern-matched ------

def test_every_refusal_is_a_refusal_including_one_we_have_not_invented(ss):
    """`isRefused` is the complement of signed-in and signed-out.

    Written this way, and tested over a status that does not exist yet, because
    the failure it prevents is silent: a fourth `resolve` status matched by
    neither branch falls through to `out`, and the person Google already signed
    in is shown the sign-in picker and told to try again. This replaces a regex
    over `app.js` source text that pinned the same property by how it was
    SPELLED — it failed when the two `!==` operands were swapped, which changes
    nothing, and would have passed a rewrite that changed everything."""
    assert ss["refused"]["ok"] is False
    assert ss["refused"]["no_identity"] is False
    for status in ("no_capacity", "deactivated", "subject_mismatch", "quarantined"):
        assert ss["refused"][status] is True, status
    # Nothing answered yet is not a refusal: the page is still `pending`.
    for nothing in ("", "null", "undefined"):
        assert ss["refused"][nothing] is False, nothing


def test_each_refusal_reads_its_own_sentence_and_only_one_gets_the_advice(ss):
    """"Ask an administrator to give this address access" is the cure for
    `no_capacity` and for nothing else — a deactivated person and one whose
    address is bound to a different Google account were both sent to an admin
    who finds a row already there.

    Both answers default the same way, which is the bug this shape removes: the
    reason line used to fall back to `no_capacity` while the advice compared
    the raw code, so a code-less refusal read the `no_capacity` sentence with
    its advice hidden."""
    assert ss["text"]["no_capacity"] == "error.no_capacity"
    assert ss["text"]["account_deactivated"] == "error.account_deactivated"
    assert ss["text"]["subject_mismatch"] == "error.subject_mismatch"
    assert ss["text"]["quarantined"] == "error.quarantined"
    assert ss["text"]["null"] == "error.no_capacity"

    assert ss["advice"]["no_capacity"] is True
    assert ss["advice"]["null"] is True  # same default as the sentence above
    for code in ("account_deactivated", "subject_mismatch", "quarantined"):
        assert ss["advice"][code] is False, code
