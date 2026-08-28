"""The evidence viewer (static/js/evidence.js), rendered in node against the
real vendored fixture and the real locale bundles.

`js/evidence.js` mixes pure HTML producers (`recordHtml`, `viewerInnerHtml`,
`shellHtml`) with the batch fetch (`resolveIds`) and a DOM scan (`idsOnScreen`)
— none of which touch `innerHTML` or need a real DOM, so all four are testable
here exactly like `gaps.js`'s `gapRowHtml` and `doc-warnings.js`'s
`quotedWarningHtml` are. The one function that actually mutates
`#evidence-viewer` (`render`, private) is left to the browser smoke suite —
this repo takes on no jsdom dependency to manufacture a DOM in node (no build
step, per CLAUDE.md).

The seven records exercised here are the real vendored fixture
(`fenceai/knowledge/fixtures/source-ref-examples.json`), not synthetic
doubles — the same file the backend route resolves against
(tests/api/test_source_refs_batch.py), so a markup change that breaks a real
degrade case (no quote, no document, no cell box) fails here.
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

const FIXTURE = JSON.parse(
  readFileSync("../../knowledge/fixtures/source-ref-examples.json", "utf8"));
const BY_ID = {};
for (const rec of FIXTURE.source_refs) BY_ID[rec.source_ref_id] = rec;

let fetchCalls = 0;
let lastBatchIds = null;

globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  documentElement: {},
  addEventListener: () => {},
};
globalThis.window = { addEventListener: () => {} };
globalThis.location = { hash: "", origin: "http://x.test", pathname: "/", search: "" };
globalThis.history = { replaceState: () => {} };
globalThis.fetch = async (url, init) => {
  if (url === "i18n/en.json" || url === "i18n/he.json") {
    return { ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")) };
  }
  fetchCalls += 1;
  const body = JSON.parse(init.body);
  lastBatchIds = body.ids;
  const resolved = [];
  const not_found = [];
  for (const id of body.ids) {
    const rec = BY_ID[id];
    if (rec) resolved.push(rec); else not_found.push(id);
  }
  return { ok: true, json: async () => ({ resolved, not_found }) };
};

import { setLocale } from "./js/i18n.js";
import {
  idsOnScreen, recordHtml, resolveIds, shellHtml, viewerInnerHtml,
} from "./js/evidence.js";

const REF_1 = "sref_00000000000000000000000000000001";  // element_quote, no pre-cut crop
const REF_3 = "sref_00000000000000000000000000000003";  // page, no quote at all
const REF_4 = "sref_00000000000000000000000000000004";  // visual_reading, agent reader
const REF_5 = "sref_00000000000000000000000000000005";  // element_quote, superseded doc
const REF_7 = "sref_00000000000000000000000000000007";  // derived, no document, no image

const out = {};
await setLocale("en");

// --- idsOnScreen: the shared `.evidence-link[data-evidence-id]` contract ---
globalThis.document.querySelectorAll = (sel) => {
  out.selector_used = sel;
  return [
    { dataset: { evidenceId: REF_1 } },
    { dataset: { evidenceId: REF_3 } },
    { dataset: { evidenceId: REF_1 } },   // duplicate, on purpose
    { dataset: {} },                       // no evidence id at all
  ];
};
out.ids_on_screen = idsOnScreen();
// restore the no-op BEFORE the next `setLocale`, which itself scans the DOM
// for `[data-i18n*]` nodes — leaving the capturing stub in place would let
// that later, unrelated scan overwrite `out.selector_used`.
globalThis.document.querySelectorAll = () => [];

// --- resolveIds: one batch call for everything missing, cache hits after ---
const first = await resolveIds([REF_1, REF_3, REF_7]);
out.first_call_count = fetchCalls;
out.first_fetched = first;
out.first_batch_ids = lastBatchIds;
const second = await resolveIds([REF_1, REF_3, REF_4]);   // REF_1/REF_3 cached
out.second_call_count = fetchCalls;
out.second_fetched = second;               // only REF_4 should have been missing
out.second_batch_ids = lastBatchIds;
const third = await resolveIds([REF_1]);   // fully cached — no call at all
out.third_call_count = fetchCalls;
out.third_fetched = third;

// --- the seven fixture records, rendered for real ---
out.record_1 = recordHtml(BY_ID[REF_1]);
out.record_3 = recordHtml(BY_ID[REF_3]);
out.record_4 = recordHtml(BY_ID[REF_4]);
out.record_5 = recordHtml(BY_ID[REF_5]);
out.record_7 = recordHtml(BY_ID[REF_7]);
out.all_kinds = FIXTURE.source_refs.map((r) => recordHtml(r)).join("\\n");

// --- the three lookup states ---
out.loading = viewerInnerHtml(undefined);
out.not_found = viewerInnerHtml(null);
out.resolved_via_viewer = viewerInnerHtml(BY_ID[REF_1]);

// --- the shell + deep link ---
out.shell = shellHtml(REF_1, "<div id=\\"marker\\"></div>",
  { origin: "http://x.test", pathname: "/index.html" });

// --- untrusted document content must never reach innerHTML unescaped ---
const hostile = JSON.parse(JSON.stringify(BY_ID[REF_1]));
hostile.text.quote = "<script>alert(1)</script> & \\"quoted\\"";
hostile.document.title = "<img src=x onerror=alert(2)>";
out.hostile = recordHtml(hostile);

// --- an unmapped warning code falls back to itself, not invented English ---
const unmapped = JSON.parse(JSON.stringify(BY_ID[REF_1]));
unmapped.warnings = [{ code: "SOURCE_CODE_NOBODY_HAS_SEEN", params: {} }];
out.unmapped_warning = recordHtml(unmapped);

await setLocale("he");
out.he_record_1 = recordHtml(BY_ID[REF_1]);
out.he_record_7 = recordHtml(BY_ID[REF_7]);
out.en_record_1 = null;  // placeholder, filled by re-render below with en active

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def rendered():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- idsOnScreen --------------------------------------------------------------

def test_ids_on_screen_dedupes_and_ignores_elements_with_no_id(rendered):
    assert rendered["selector_used"] == ".evidence-link[data-evidence-id]"
    assert sorted(rendered["ids_on_screen"]) == sorted(
        ["sref_00000000000000000000000000000001", "sref_00000000000000000000000000000003"]
    )


# --- resolveIds: the batch, not N, claim ---------------------------------------

def test_opening_several_citations_issues_one_batch_call_not_n(rendered):
    """Three ids, one POST — frontend design §3's whole argument."""
    assert rendered["first_call_count"] == 1
    assert sorted(rendered["first_batch_ids"]) == sorted([
        "sref_00000000000000000000000000000001",
        "sref_00000000000000000000000000000003",
        "sref_00000000000000000000000000000007",
    ])
    assert sorted(rendered["first_fetched"]) == sorted(rendered["first_batch_ids"])


def test_a_second_overlapping_batch_only_fetches_what_is_new(rendered):
    assert rendered["second_call_count"] == 2
    assert rendered["second_batch_ids"] == ["sref_00000000000000000000000000000004"]
    assert rendered["second_fetched"] == ["sref_00000000000000000000000000000004"]


def test_a_fully_cached_batch_issues_no_call_at_all(rendered):
    assert rendered["third_call_count"] == 2      # unchanged from the previous assertion
    assert rendered["third_fetched"] == []


# --- the real fixture records, rendered ----------------------------------------

def test_a_normal_quoted_paragraph_shows_the_quote_and_its_source(rendered):
    html = rendered["record_1"]
    assert "30&quot; deep" in html or "30\" deep" in html
    assert "pdf_text_layer" in html
    assert 'evidence-state-extracted' in html


def test_the_scanned_page_case_has_no_quote_and_says_so_honestly(rendered):
    """The design doc's hardest case: no quote, no bbox, the whole page IS the
    evidence. Must render as a valid state, never a blank or broken layout."""
    html = rendered["record_3"]
    assert "no cell grid could be recovered" in html
    assert "evidence-no-quote" in html
    assert "evidence-crop-placeholder" in html    # the page image, described
    assert "3400" in html                          # the page's real width_px


def test_the_visual_reading_shows_the_reader_and_the_missing_cell_box(rendered):
    html = rendered["record_4"]
    assert "calibration-A" in html
    assert '97&quot;' in html or '97"' in html
    assert "no cell box" in html.lower() or "cell" in html.lower()
    assert "row and column labels but not a cell box" in html


def test_the_derived_record_has_no_document_and_no_image_and_is_valid(rendered):
    html = rendered["record_7"]
    assert "hand-researched" in html
    assert "data/structural/barrette-outdoor-living-structural.json" in html
    assert "evidence-crop-placeholder" not in html   # no image at all, not a placeholder
    assert 'evidence-state-derived' in html


def test_every_one_of_the_seven_fixture_records_renders_without_a_raw_key_leaking(rendered):
    """The same discipline `test_gaps_module.py` enforces for `gaps.kind.*`: a
    lookup miss must not leave a raw `evidence.foo` string on screen."""
    assert "evidence." not in rendered["all_kinds"], rendered["all_kinds"][:400]


# --- the three lookup states ---------------------------------------------------

def test_the_pending_and_not_found_states_are_distinct_and_localized(rendered):
    assert rendered["loading"] != rendered["not_found"]
    assert "evidence." not in rendered["loading"]
    assert "evidence." not in rendered["not_found"]


def test_a_resolved_record_through_the_viewer_matches_direct_rendering(rendered):
    assert rendered["resolved_via_viewer"] == rendered["record_1"]


# --- the deep link ---------------------------------------------------------

def test_the_shell_carries_a_shareable_deep_link_for_the_given_location(rendered):
    shell = rendered["shell"]
    assert "http://x.test/index.html#evidence=" in shell
    assert "sref_00000000000000000000000000000001" in shell
    assert '<div id="marker"></div>' in shell        # inner content passed through


# --- untrusted content -------------------------------------------------------

def test_document_derived_text_never_reaches_innerhtml_unescaped(rendered):
    html = rendered["hostile"]
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x" in html
    assert "&amp;" in html


def test_an_unmapped_source_warning_code_falls_back_to_itself(rendered):
    """The same fallback contract `gaps.js` keeps for an unlisted `Gap.kind`:
    a code neither bundle carries is shown as itself, never invented English."""
    html = rendered["unmapped_warning"]
    assert "SOURCE_CODE_NOBODY_HAS_SEEN" in html


# --- both locales --------------------------------------------------------------

def test_the_furniture_is_localized_in_hebrew_and_the_metadata_stays_ltr(rendered):
    he = rendered["he_record_1"]
    assert "evidence." not in he
    assert 'dir="ltr"' in he            # the quote itself


def test_the_derived_record_is_honest_in_hebrew_too(rendered):
    he = rendered["he_record_7"]
    assert "data/structural/barrette-outdoor-living-structural.json" in he
    assert "evidence." not in he
