"""`session.js`'s pure half, in node.

`sessionState` decides nothing about what may be DONE — it answers which
screen this is and who to name on it. Pure, so node can check it without a
browser: `base-top.js`'s split applied again.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { sessionState } from "./js/session.js";

const out = {};
out.ok = sessionState({status:"ok", email:"d@e.com",
                       user:{id:"u1", name:"Dana", capacity:"sales"},
                       view:"sales", may_choose_view:false});
out.none = sessionState({status:"no_capacity", email:"s@e.com", user:null});
out.off = sessionState({status:"deactivated", email:"g@e.com", user:null});
out.anon = sessionState({status:"no_identity", email:"", user:null});
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
