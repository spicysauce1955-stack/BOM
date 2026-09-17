"""`people.js`'s pure half, in node.

`peopleRows` decides nothing about who may write a capacity — the server does
that, on `POST /api/users` and `PATCH /api/users/{id}`, which do not exist yet
(a later task adds them). This module runs ahead of them: everything it is
tested by is pure or static, exactly as the brief asks.

Same shape as `test_session_module.py` and `test_base_top_module.py`: a
module-scoped `SCRIPT`, `node --input-type=module -e`, `cwd=STATIC`. There is
no shared `run_node` helper in this suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { peopleRows } from "./js/people.js";
console.log(JSON.stringify(peopleRows([
  {id:"u1", name:"Dana", email:"d@e.com", capacity:"sales",
   active:true, subject:"sub-1"},
  {id:"u2", name:"New", email:"n@e.com", capacity:"sales",
   active:true, subject:""},
  {id:"u3", name:"Gone", email:"g@e.com", capacity:"backoffice",
   active:false, subject:"sub-3"},
])));
"""


@pytest.fixture(scope="module")
def rows():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_grant_nobody_has_used_says_so(rows):
    """An empty `subject` is a row an admin made that nobody has signed in
    against yet — the normal state between granting and arriving, and the one
    an admin hunting a mistyped address has to be able to see."""
    assert [r["bound"] for r in rows] == [True, False, True]


def test_a_deactivated_person_is_still_listed(rows):
    """Deactivated, never deleted: the audit log names people who have left, so
    a row must keep resolving to a name for ever. A panel that hid them would
    make reactivating impossible."""
    assert rows[2]["active"] is False
    assert rows[2]["name"] == "Gone"


def test_every_field_the_row_needs_is_carried_and_nothing_extra(rows):
    """`bound` is derived; everything else is passed through verbatim. Pinning
    the whole key set catches a rename (say, `capacity` -> `role`) that a
    narrower assertion would miss even though it breaks every column."""
    assert set(rows[0]) == {"id", "name", "email", "capacity", "active", "bound"}
    assert rows[0]["id"] == "u1"
    assert rows[0]["email"] == "d@e.com"
    assert rows[0]["capacity"] == "sales"


EDGE_SCRIPT = """
import { peopleRows } from "./js/people.js";
console.log(JSON.stringify({
  empty: peopleRows([]),
  missing: peopleRows(undefined),
}));
"""


@pytest.fixture(scope="module")
def edge():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", EDGE_SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_an_empty_or_missing_list_is_an_empty_table_not_a_crash(edge):
    """`initPeople` calls this with whatever `GET /api/users` answers; a screen
    with one account (the first admin) still has to render, not throw — and a
    failed fetch that leaves `users` undefined must not throw either."""
    assert edge["empty"] == []
    assert edge["missing"] == []
