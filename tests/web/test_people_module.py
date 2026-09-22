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
   active:true, subject_bound:true},
  {id:"u2", name:"New", email:"n@e.com", capacity:"sales",
   active:true, subject_bound:false},
  {id:"u3", name:"Gone", email:"g@e.com", capacity:"backoffice",
   active:false, subject_bound:true},
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
    """`subject_bound: false` is a row an admin made that nobody has signed in
    against yet — the normal state between granting and arriving, and the one
    an admin hunting a mistyped address has to be able to see. The API never
    sends the raw Google `subject` id itself (`_public`, `api/app.py`); this
    is the boolean it sends instead."""
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


def test_every_field_peoplerows_reads_is_one_public_actually_sends():
    """The contract this module has with the server, pinned from the Python
    side because that is where both halves are reachable in one test.

    `peopleRows` (this file) reads `u.<field>` off whatever `GET /api/users`
    returns; that response is `_public(user)` for every row (`api/app.py`).
    Nothing else ties the two together — the node tests above feed a fixture
    that agrees with whichever shape *this test's author* believes the API
    sends, which is exactly how `u.subject` kept being read here for a full
    review cycle after `_public` stopped sending it: `bound` silently went
    `false` for every account, on the one screen whose job is to say who may
    do what, and nothing failed.

    Reading `peopleRows`'s own source (rather than hand-maintaining a second
    list of field names in Python) is what makes this fail on EITHER side
    moving: a field renamed in `people.js` with no matching change in
    `_public`, or the reverse.
    """
    import re

    from fenceai.api.app import _public
    from fenceai.identity.model import User

    src = (STATIC / "js" / "people.js").read_text()
    start = src.index("export function peopleRows")
    # Textual, not a parser: this bounds the function body only because it has
    # no column-0 closing brace before its own — true today, and worth
    # re-checking if this function ever grows a nested top-level block.
    body = src[start:start + src[start:].index("\n}")]
    read_fields = set(re.findall(r"\bu\.(\w+)", body))
    assert read_fields, "no `u.<field>` reads found in peopleRows — did it move or get renamed?"

    sent = _public(User(id="u1", name="Dana", email="dana@example.com",
                        capacity="sales", subject="sub-1"))
    missing = read_fields - set(sent)
    assert not missing, (
        f"people.js's peopleRows reads {sorted(missing)} off a user row that "
        f"_public() never sends (it sends {sorted(sent)}) — the people panel "
        "will silently misread whatever depends on the missing field")


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


# ---------------------------------------------------------------------------
# `initPeople`'s capacity `<select>` handler, against a refused PATCH.
#
# `apiSend` (api.js) ALERTS a coded refusal and then RE-THROWS — every other
# write on this app relies on that throw to skip its own follow-up work, and
# that is correct for them. It is not correct here: the browser has already
# moved the `<select>` to the value the person just picked before this
# handler's `change` even fires, so on a refusal the control is left showing
# the value the server just rejected unless something repaints it.
#
# This is not a pure function — `initPeople` wires DOM listeners — so it is
# tested the way `test_evidence_module.py` tests `evidence.js`'s DOM-touching
# half: a hand-rolled `document`/`fetch` double, no jsdom dependency (CLAUDE.md
# takes on no build step). The double is just enough surface for `initPeople`
# to run for real: a fake `<table>` that remembers the listener it was given,
# a fake `change` event whose target resolves to a fake `<select>` inside a
# fake `<tr>`, and a `fetch` stub that refuses the PATCH with a real coded
# body and counts how many times `GET /api/users` is asked for afterward.
# ---------------------------------------------------------------------------
REFUSAL_SCRIPT = """
const state = { getUsersCalls: 0, patchCalls: [] };
globalThis.alert = () => {};                 // apiSend alerts; this test does not care what it says
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.fetch = async (url, init) => {
  if (!init || !init.method) {               // render()'s plain GET
    state.getUsersCalls += 1;
    return { ok: true, json: async () => [] };
  }
  if (init.method === "PATCH") {
    state.patchCalls.push({ url, body: JSON.parse(init.body) });
    return {
      ok: false, status: 403,
      text: async () => JSON.stringify({ detail: { code: "capacity_insufficient" } }),
      json: async () => ({ detail: { code: "capacity_insufficient" } }),
    };
  }
  throw new Error("unexpected fetch: " + url + " " + JSON.stringify(init));
};

const listeners = {};
const table = {
  addEventListener(type, fn) { listeners[type] = fn; },
  set innerHTML(v) { this._html = v; },
  get innerHTML() { return this._html || ""; },
};
const form = { addEventListener() {} };
globalThis.document = {
  getElementById: (id) => (id === "people-table" ? table
    : id === "people-add-form" ? form : null),
  querySelectorAll: () => [],
  documentElement: {},
  addEventListener: () => {},
};
globalThis.window = { addEventListener: () => {} };

import { initPeople } from "./js/people.js";
initPeople();

// Somebody picks "admin" in row u1's <select> — the browser has already set
// `sel.value` to it by the time `change` fires, exactly as it would for real.
const sel = {
  value: "admin",
  closest: (s) => (s === "tr" ? { dataset: { user: "u1" } } : null),
};
const changeEvent = { target: { closest: (s) => (s === ".people-capacity" ? sel : null) } };

try {
  await listeners.change(changeEvent);
} catch {
  // `apiSend` re-throws after alerting — every write handler in this app
  // leaves that uncaught in production too. Swallowed here only so this
  // script's own top level does not abort before it can report what
  // `initPeople`'s handler did before that rethrow.
}

console.log(JSON.stringify(state));
"""


@pytest.fixture(scope="module")
def refusal():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", REFUSAL_SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_refused_capacity_change_still_repaints_the_select(refusal):
    """The regression a review caught: re-rendering used to be a bare call
    after `await apiSend(...)`, which never runs once `apiSend` throws — so a
    refused PATCH left the `<select>` showing the value the server just
    rejected. `render()` now sits in `finally`, so a `GET /api/users` must
    follow the refused `PATCH` regardless of the throw. Before the fix this
    assertion sees `get_users_calls == 0`."""
    assert len(refusal["patchCalls"]) == 1
    assert refusal["patchCalls"][0]["body"] == {"capacity": "admin"}
    assert refusal["getUsersCalls"] == 1
