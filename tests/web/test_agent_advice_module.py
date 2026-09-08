"""The advice panel's rendering (static/js/agent-advice.js).

`renderAdvice(result, host)` is the one exported, DOM-light function this
module owns: it takes a `TaskResult`-shaped object (or `null`) and a plain
object standing in for the host element, and sets `.innerHTML` on it. That is
enough surface to exercise real behaviour rather than grep for it — the first
version of this file was five source-scanning greps and passed on a module
that rendered nothing at all; two of the five broke on a harmless refactor
because the string they matched lived in a COMMENT, not in behaviour. Spec
§8b names exactly this defect, and Task 9 had it and fixed it the same way.

A grep survives here only where behaviour genuinely cannot reach it: that
`#choices` never appears in the source (a module reaching into another
module's host selector), and that no write verb appears anywhere in it
(slice 1 advises and does not act — there is no host state to observe that
distinguishes "never called fetch with PUT" from "never wrote to state").
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"
MODULE = STATIC / "js" / "agent-advice.js"

SCRIPT = """
globalThis.localStorage = {
  s: {},
  getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
// `liveHost` stands in for the real `#agent-advice` element through
// `initAgentAdvice`'s own wiring (below) — `container()` reads it back via
// `document.getElementById`, exactly as it would in a browser.
const liveHost = { innerHTML: "" };
globalThis.document = {
  getElementById: (id) => (id === "agent-advice" ? liveHost : null),
  querySelectorAll: () => [], querySelector: () => null, documentElement: {},
};
import { readFileSync } from "node:fs";
const proposalAdviceBody = {
  evaluated: true,
  proposals: [{ claims: [{ marker: "read", text: "2500 · 2500 · 2400" }] }],
};
globalThis.fetch = async (url) => ({
  ok: true,
  json: async () => (url.includes("/advice") ? proposalAdviceBody
    : JSON.parse(readFileSync(url, "utf8"))),
});

import { emit, state } from "./js/state.js";
import { initI18n, setLocale } from "./js/i18n.js";
import { setUnits } from "./js/units.js";
import { initAgentAdvice, renderAdvice } from "./js/agent-advice.js";

await initI18n();
// the app OPENS in Hebrew, so pin the language before anything reads a word
await setLocale("en");
state.units = "mm";

// A `read` claim's text is the SAME raw-millimetre widths label
// `choices.js` renders beside this panel (`generator.py`'s
// `" · ".join(str(w) for w in widths)`); the `inferred` claim carries prose
// with a payload an agent-authored string is exactly the untrusted case for.
const proposalResult = {
  evaluated: true,
  proposals: [{
    claims: [
      { marker: "read", text: "2500 · 2500 · 2400" },
      { marker: "inferred", text: "<script>alert(1)</script> reasoning" },
    ],
  }],
};

const withProposal = { innerHTML: "" };
renderAdvice(proposalResult, withProposal);

const declined = { innerHTML: "" };
renderAdvice({ evaluated: false, proposals: [] }, declined);

const nothing = { innerHTML: "" };
renderAdvice({ evaluated: true, proposals: [] }, nothing);

// must not throw when there is nowhere to render (a real early-return path)
renderAdvice(proposalResult, null);

state.units = "cm";
const inCm = { innerHTML: "" };
renderAdvice(proposalResult, inCm);

await setLocale("he");
const heDeclined = { innerHTML: "" };
renderAdvice({ evaluated: false, proposals: [] }, heDeclined);
await setLocale("en");
state.units = "mm";

// ---- initAgentAdvice's REAL wiring: the one path a pure renderAdvice()
// call cannot reach, and where N1 (a missing units-changed subscription)
// and N3 (the no-run state, decided in refresh(), never renderAdvice())
// actually live.
state.result = null;   // no run yet
initAgentAdvice();     // registers listeners exactly once for this script
const noRunHtml = liveHost.innerHTML;

state.result = { run: { id: "run1" } };
emit("result-changed", state.result);       // -> refresh() -> the stubbed fetch
await new Promise((r) => setTimeout(r, 0)); // let the fetch's microtasks settle
const liveMm = liveHost.innerHTML;

setUnits("cm");    // the real units-button path -> emits units-changed
const liveCm = liveHost.innerHTML;

console.log(JSON.stringify({
  withProposal: withProposal.innerHTML,
  declined: declined.innerHTML,
  nothing: nothing.innerHTML,
  inCm: inCm.innerHTML,
  heDeclined: heDeclined.innerHTML,
  noRunHtml, liveMm, liveCm,
}));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    # Also proves `renderAdvice(result, null)` above did not throw: an
    # uncaught exception mid-script would leave this non-zero.
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_proposals_claim_text_actually_renders(out):
    assert "2500" in out["withProposal"]
    assert "reasoning" in out["withProposal"]


def test_agent_authored_text_is_escaped_not_executed(out):
    assert "<script>" not in out["withProposal"]
    assert "&lt;script&gt;" in out["withProposal"]


def test_a_dimension_claim_is_unit_converted_and_isolated(out):
    """Finding I1: the same raw-mm dimension string `choices.js` shows beside
    this panel must convert with display units and stay LTR-isolated, or the
    two panels disagree and the digits reorder in RTL."""
    assert '<bdi class="num">' in out["withProposal"]
    assert "2500 · 2500 · 2400" not in out["inCm"]
    assert "250 · 250 · 240" in out["inCm"]


def test_evaluated_false_and_empty_proposals_render_differently(out):
    """"I did not look" is never "nothing to report" — audit B01 in
    miniature, and the reason this slice exists."""
    assert out["declined"] != out["nothing"]
    assert "Could not check" in out["declined"]
    assert "Nothing to suggest here" not in out["declined"]
    assert "Nothing to suggest here" in out["nothing"]
    assert "Could not check" not in out["nothing"]


def test_every_rendered_state_carries_the_sections_own_heading(out):
    """Finding I2: a bare "Could not check" has no subject. `<h3>` names the
    section in every state `renderAdvice` produces."""
    for rendered in (out["withProposal"], out["declined"], out["nothing"]):
        assert "<h3>" in rendered


def test_the_heading_and_the_empty_sentence_are_localized(out):
    assert out["heDeclined"] != out["declined"]
    assert "לא ניתן היה לבדוק" in out["heDeclined"]


def test_no_run_yet_gets_its_own_state_not_i_did_not_look(out):
    """Finding N3: `agent.no_run` lives in `refresh()`, not in `renderAdvice`
    — the one state the pure-function tests above cannot reach, exercised
    here through `initAgentAdvice`'s real wiring instead."""
    assert "Generate a strategy" in out["noRunHtml"]
    assert "Could not check" not in out["noRunHtml"]
    assert "Nothing to suggest here" not in out["noRunHtml"]


def test_a_units_toggle_re_renders_the_already_loaded_advice(out):
    """Finding N1: I1's unit conversion is worthless if nothing re-renders
    when the display-unit preference changes — the exact symptom (a stale
    mm figure beside a cm one) reappearing through the missing
    `units-changed` subscription rather than through the conversion itself.
    Drives it through the REAL wiring (`initAgentAdvice` + `setUnits`,
    which is what the units button actually calls), not a direct
    `renderAdvice()` call, so removing `on("units-changed", render)` alone
    is what this test is pinned against."""
    assert "2500 · 2500 · 2400" in out["liveMm"]
    assert "2500 · 2500 · 2400" not in out["liveCm"]
    assert "250 · 250 · 240" in out["liveCm"]


def test_the_module_never_touches_another_modules_dom():
    src = MODULE.read_text()
    assert "#choices" not in src, "no module touches another module's DOM subtree"


def test_the_module_never_writes_project_state():
    """Slice 1 advises and does not act. A keep/reverse path arrives in slice
    2 with the record that makes a refusal mean something."""
    src = MODULE.read_text()
    for mutator in ("saveTopology", "pushSnapshot", "method: \"PUT\"", "method: 'PUT'"):
        assert mutator not in src
