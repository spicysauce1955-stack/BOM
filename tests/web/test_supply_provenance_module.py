"""The provenance line that says what a BOM was priced against (static/js/tabs.js).

`supplyProvenanceHtml` is a pure function of one SupplyRun, so it is pinned here
under node the way `bom_grouped_module` and `base_top_module` are.

What these tests guard: that the two facts distinguishing one printing of a run
from another — WHICH yard, and under which objective — actually reach the page,
localized, in both languages, with the opaque ids isolated so RTL cannot scramble
them. The backend has been able to answer "which inventory was this priced
against" since the design/supply split; before this function nothing rendered the
answer, so a reader holding two printouts was exactly as stuck as before.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { readFileSync } from "node:fs";

globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  querySelector: () => null,
  createElement: () => ({ style: {}, classList: { add() {} }, appendChild() {} }),
  documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { supplyProvenanceHtml } from "./js/tabs.js";

const SUPPLY = {
  id: "sup_537b210c0813",
  design_id: "run_1b2bf5bdf6f8",
  inventory_hash: "f4d1a17980b95de2",
  objective_preset: "least_cost",
};

const out = {};
await setLocale("en");
out.en = supplyProvenanceHtml(SUPPLY);
out.en_priority = supplyProvenanceHtml({ ...SUPPLY, objective_preset: "honour_priority" });
// a preset nothing has a label for must still render, showing the raw token
// rather than an empty gap or the key itself
out.en_unknown = supplyProvenanceHtml({ ...SUPPLY, objective_preset: "fewest_new_stock" });
// nothing to say is said with nothing, never with an empty chrome box
out.empty = supplyProvenanceHtml(null);
out.empty_id = supplyProvenanceHtml({ ...SUPPLY, id: "" });

await setLocale("he");
out.he = supplyProvenanceHtml(SUPPLY);

// the ids are opaque tokens and must never be interpolated raw
out.xss = supplyProvenanceHtml({ ...SUPPLY, id: '<img src=x onerror=alert(1)>' });

console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_provenance_line_names_the_yard_and_the_objective(tmp_path):
    script = STATIC / "_supply_provenance_test.mjs"
    script.write_text(SCRIPT)
    try:
        proc = subprocess.run(
            ["node", script.name], cwd=STATIC, capture_output=True, text=True,
        )
    finally:
        script.unlink()
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)

    # the supply id is what makes two printouts of one run distinguishable
    assert "sup_537b210c0813" in out["en"]
    # ...and the yard hash is what EXPLAINS the difference
    assert "f4d1a17980b95de2" in out["en"]
    # the objective is prose, so it is translated rather than shown as a token
    assert "least cost" in out["en"]
    assert "least_cost" not in out["en"]
    assert "stated preference" in out["en_priority"]

    # an unlabelled preset degrades to its raw token, never to a bare i18n key
    assert "fewest_new_stock" in out["en_unknown"]
    assert "bom.preset_" not in out["en_unknown"]

    # nothing to say -> nothing rendered
    assert out["empty"] == ""
    assert out["empty_id"] == ""

    # Hebrew renders the same facts, translated, with the opaque ids isolated so
    # RTL cannot reorder them into a different-looking hash
    assert "sup_537b210c0813" in out["he"]
    assert "עלות מזערית" in out["he"]
    assert "least cost" not in out["he"]
    # `<bdi` rather than `<bdi>`: the isolation is what matters, and asserting the
    # exact opening tag would fail on the `.sku` class that carries the numeric
    # font — a test that breaks on styling is a test nobody trusts
    assert out["he"].count("<bdi") == 2

    # and the id goes through esc() like every other interpolated value
    assert "<img src=x" not in out["xss"]
    assert "&lt;img" in out["xss"]
