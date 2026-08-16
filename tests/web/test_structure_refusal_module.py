"""Why the structure tab found nothing (static/js/structure-data.js), in node.

"Generate a strategy to see how it is laid out" is true for exactly ONE state:
no run. Every other state is a run that exists and cannot be read, and saying
that sentence about it is a lie the user cannot act on — it was wave H's whole
subject, and the fence-model 400 reached it again through a door nobody had
closed: any refusal without an explicit branch fell back to `null`, which the tab
reads as "no attempt yet".

Unreachable from the browser suite (there is no live trigger left for it, which
is exactly why the fallback needs its own test rather than an absence of
complaints), and pure enough to drive in node against a stubbed fetch.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null, querySelectorAll: () => [], documentElement: {},
};

import { state } from "./js/state.js";
import {
  isStale, loadStructure, refusalKey, staleCode, staleKind,
} from "./js/structure-data.js";

// one refusal body -> what the tab is left knowing
async function refusal(body, status = 400) {
  globalThis.fetch = async () => ({
    ok: status === 200, status, text: async () => body,
    json: async () => JSON.parse(body),
  });
  state.result = { run: { id: `run_${Math.random()}` } };   // a NEW run each time
  await loadStructure();
  return { stale: isStale(), kind: staleKind(), code: staleCode(),
           // the sentence each surface would show for this state
           structure: refusalKey("structure.empty"),
           assembly: refusalKey("assembly.no_run") };
}

const out = {};
out.topology = await refusal(JSON.stringify({ detail: {
  code: "topology_changed", run_topology_revision: 1 } }), 409);
out.catalog = await refusal(JSON.stringify({ detail: {
  code: "catalog_changed", run_catalog_hash: "abc" } }), 409);
out.predates = await refusal(JSON.stringify({ detail: {
  code: "run_predates_fence_model", span_id: "s1" } }));
// a code with no branch of its own — the case that used to read as "no run"
out.unknown_coded = await refusal(JSON.stringify({ detail: {
  code: "teapot_overflow", cups: 3 } }), 418);
// and a refusal that is not even JSON
out.unknown_plain = await refusal("upstream exploded", 500);
out.long_body = await refusal("x".repeat(400), 500);

// the ONE state that really is "nothing generated yet"
state.result = null;
await loadStructure();
out.no_run = { stale: isStale(), kind: staleKind(), code: staleCode(),
               structure: refusalKey("structure.empty"),
               assembly: refusalKey("assembly.no_run") };

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def refusals():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_no_run_is_the_only_state_that_is_not_stale(refusals):
    assert refusals["no_run"]["stale"] is False
    assert refusals["no_run"]["kind"] is None
    assert refusals["no_run"]["code"] == ""


def test_the_three_named_refusals_keep_their_own_branch(refusals):
    assert refusals["topology"]["kind"] == "topology"
    assert refusals["catalog"]["kind"] == "catalog"
    assert refusals["predates"]["kind"] == "predates"


def test_an_unrecognised_refusal_is_still_a_refusal(refusals):
    """It used to be `null`, which `structure.js` renders as "generate a strategy
    to see how it is laid out" — about a run that had been generated. `"unknown"`
    routes it to `structure.unreadable` instead."""
    for case in ("unknown_coded", "unknown_plain"):
        assert refusals[case]["stale"] is True, case
        assert refusals[case]["kind"] == "unknown", case


def test_an_unrecognised_refusal_can_still_name_itself(refusals):
    """Naming the code is not a great message. Claiming there is no structure is
    a false one."""
    assert refusals["unknown_coded"]["code"] == "teapot_overflow"
    assert refusals["unknown_plain"]["code"] == "upstream exploded"


def test_a_runaway_body_does_not_become_the_panel(refusals):
    """The full text is already in the console via apiGet's throw; a panel is not
    a log viewer."""
    assert len(refusals["long_body"]["code"]) <= 121
    assert refusals["long_body"]["code"].endswith("…")


def test_every_surface_says_the_same_thing_about_the_same_run(refusals):
    """The mapping from "why is there no report" to "what does the tab say" is
    ONE function, in the module that owns the refusal state. Two copies is how
    the Structure tab comes to say "generate a strategy" about a run whose
    catalog moved while the Assembly tab beside it says the truth — and a copy
    living inside a tab is a copy no test ever reaches."""
    expected = {
        "no_run": None,                # each surface names its own absence
        "topology": "structure.stale",
        "catalog": "structure.catalog_changed",
        "predates": "error.run_predates_fence_model",
        "unknown_coded": "structure.unreadable",
        "unknown_plain": "structure.unreadable",
        "long_body": "structure.unreadable",
    }
    for case, key in expected.items():
        row = refusals[case]
        if key is None:
            assert (row["structure"], row["assembly"]) \
                == ("structure.empty", "assembly.no_run"), case
        else:
            assert row["structure"] == row["assembly"] == key, case
