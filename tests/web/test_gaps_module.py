"""The gap surface (static/js/gaps.js), rendered in node against the real bundles.

The browser suite can only ever see the gaps this engine actually emits today —
one per kind that is wired, in one language, from one run. The properties that
make the panel worth building are properties of the SHAPE, and most of them are
about combinations the demo knowledge cannot produce:

  * every one of the eight `Gap` kinds reads as a phrase in both languages (a
    kind published by the other team next month must not land on screen as
    `gaps.kind.unquantified`);
  * `closes_by` GROUPS rather than decorates — the contract's actual requirement
    is that a curator is never shown an engineer's work, and a chip saying
    "planning" beside a row in a mixed list does not deliver that;
  * `severity` changes the weight of a row and never its group;
  * `would_close` is on the row, always, in every language — it is the field the
    contract makes binding and the one a click could hide;
  * and expert/curator text reaches `innerHTML` through `esc()`, which no
    fixture the engine produces will ever prove, because the engine writes those
    sentences itself.
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

// gaps.js reaches i18n / units / structure-data, whose stateful halves touch
// localStorage and the DOM at call time — stub both, and serve the REAL locale
// bundle so what node renders is what the browser renders.
globalThis.localStorage = {
  s: {}, getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { gapsPanelHtml, gapRowHtml, warnsLineCount } from "./js/gaps.js";

const KINDS = [
  "unmodellable_entity", "uncovered_condition", "unsatisfiable_requirement",
  "unquantified", "missing_value", "unmapped_part_kind", "disputed",
  "illegible_source",
];

// The engine's own `uncovered_max_span` gap, field for field
// (strategy/generator.py `_report_uncovered_max_span`).
const gap = (over) => ({
  id: "gap:run1:M-LEGACY@v1:max_span_mm", kind: "uncovered_condition",
  subject: { kind: "param", id: "max_span_mm" },
  because: {
    code: "uncovered_max_span",
    params: { element: "run1", run_id: "run1", model_ref: "M-LEGACY@v1",
              param: "max_span_mm", value_mm: 1800, n: 3, basis: "fallback" },
  },
  cites: [], would_close: "a max_span_mm row for series M-LEGACY@v1",
  closes_by: "knowledge", severity: "warns_line", ...over });

// A gap this engine cannot produce and the platform can: `unmodellable_entity`
// closes by a schema change HERE, and a gate is the contract's own example of
// one (obligation 18 — a gate is published as a `Gap`, never as a `FenceModel`).
// Synthetic on purpose: the whole argument for grouping by `closes_by` is about
// the rows a curator must not be handed, and there is no backend fixture that
// produces one to check the grouping against.
const curator = gap({
  kind: "unmodellable_entity", closes_by: "planning", severity: "informational",
  because: { code: "unmodellable_gate", params: { element: "gate@run1:2000-3000" } },
  subject: { kind: "entity", id: "gate@run1:2000-3000" },
  cites: [{ id: "sr_91", belongs_to: "sha256:deadbeef" }],
  would_close: "A GateModel with <script>alert(1)</script> handedness & swing.",
});

const out = {};
await setLocale("he");
out.he = gapsPanelHtml([gap({}), curator]);
out.he_empty_silent = gapsPanelHtml([]);
out.he_empty_stated = gapsPanelHtml([], { empty: true });
out.he_kinds = KINDS.map((k) => gapRowHtml(gap({
  kind: k,
  // the two kinds the contract binds to planning cannot claim otherwise
  closes_by: (k === "unmodellable_entity" || k === "unmapped_part_kind")
    ? "planning" : "knowledge",
  on: k === "disputed" ? "conditions" : null,
}))).join("\\n");
out.he_only_planning = gapsPanelHtml([curator]);
out.counts = warnsLineCount([gap({}), curator]);

await setLocale("en");
out.en = gapsPanelHtml([gap({}), curator]);
out.en_kinds = KINDS.map((k) => gapRowHtml(gap({ kind: k }))).join("\\n");

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def panels():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_nothing_to_report_renders_nothing_unless_asked(panels):
    """Callers concatenate the panel unconditionally, so silence is an empty
    STRING. The editor asks for the stated version instead, because on a surface
    whose whole subject is absence, "no gaps" is an answer and a missing panel
    looks exactly like a broken one."""
    assert panels["he_empty_silent"] == ""
    assert "לא נותר דבר לא פתור" in panels["he_empty_stated"]


def test_would_close_is_on_the_row_in_both_languages(panels):
    """The contract's binding clause, as a test: *"a gap that only says something
    is missing sends a curator hunting"*. Not behind a summary, not in a title
    attribute, not on hover."""
    for html in (panels["he"], panels["en"]):
        assert "a max_span_mm row for series M-LEGACY@v1" in html
        assert "<details" not in html and "title=" not in html


def test_the_curator_sentence_is_labelled_as_english_and_left_to_right(panels):
    """It is generated English prose with no code and no params, in a
    Hebrew-first page. Rendering it unmarked would present it as the app's own
    voice; translating it would manufacture a claim its author did not make. So
    it is quoted, tagged, and named for what it is."""
    he = panels["he"]
    assert 'lang="en"' in he and 'dir="ltr"' in he
    assert "gap-verbatim" in he
    assert "נכתב עבור אוצרי הידע" in he       # "written for the knowledge curators"


def test_closes_by_groups_the_queue_rather_than_decorating_a_row(panels):
    """The contract's other binding clause. A review queue that shows a curator
    work only an engineer can perform is a queue whose items are not actionable,
    and a chip in a mixed list does not fix that — the split has to be
    structural, which is what this asserts."""
    he = panels["he"]
    assert 'data-closes-by="knowledge"' in he and 'data-closes-by="planning"' in he
    assert "אוצר ידע יכול לסגור את אלה" in he       # a curator can close these
    assert "אלה דורשים שינוי במאגר הזה" in he       # these need a change here
    # ...and the knowledge group comes first: the reader most likely to be
    # looking is the one who can act
    assert he.index('data-closes-by="knowledge"') < he.index('data-closes-by="planning"')


def test_a_group_with_no_members_is_not_an_empty_heading(panels):
    only = panels["he_only_planning"]
    assert "אלה דורשים שינוי במאגר הזה" in only
    assert "אוצר ידע יכול לסגור את אלה" not in only


def test_severity_changes_the_weight_of_a_row_not_its_group(panels):
    he = panels["he"]
    assert 'class="gap warns_line"' in he and 'class="gap informational"' in he
    assert "משפיע על שורה" in he and "הערה" in he
    # the informational gate gap is in the planning group, exactly where its
    # `closes_by` puts it — severity moved nothing
    planning = he[he.index('data-closes-by="planning"'):]
    assert "unmodellable_gate" in planning
    assert panels["counts"] == 1


def test_every_gap_kind_reads_as_a_phrase_in_both_languages(panels):
    """A kind this engine does not emit today still arrives from the platform.
    The failure mode is silent: `t()` returns the key, so an unlisted kind
    renders `gaps.kind.unquantified` on screen and nothing goes red."""
    for html in (panels["he_kinds"], panels["en_kinds"]):
        assert "gaps.kind." not in html, html[:400]
    assert "אין שורה שמכסה את המקרה הזה" in panels["he_kinds"]
    assert "no row covers this case" in panels["en_kinds"]


def test_disputed_alone_says_which_reading_is_disputed(panels):
    """`on` is `disputed`'s field. On any other kind, printing it would be a
    claim the gap is not making."""
    rows = panels["he_kinds"].split("\n\n") or [panels["he_kinds"]]
    assert "לגבי התנאים" in panels["he_kinds"]      # "about the conditions"
    assert panels["he_kinds"].count("לגבי התנאים") == 1


def test_curator_text_reaching_innerhtml_goes_through_esc(panels):
    """`would_close` is authored on the other side of the boundary and every
    string from the Knowledge Platform is untrusted data by contract. The engine
    writes today's sentences itself, so no fixture the backend produces will ever
    exercise this."""
    for html in (panels["he"], panels["en"]):
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&amp;" in html  # the ampersand too, not only the angle brackets


def test_an_entity_subject_is_isolated_as_an_identifier(panels):
    """A gate id inside an RTL sentence reorders on screen without `<bdi>`, and
    `.sku` is what forces it left-to-right."""
    he = panels["he"]
    assert '<bdi class="sku">gate@run1:2000-3000</bdi>' in he
    assert '<bdi class="sku">max_span_mm</bdi>' in he


def test_the_sentence_comes_from_the_bundle_and_a_code_with_no_entry_shows_itself(panels):
    """A `Gap` carries no `message` — §1.2.1 gives it `because{code,params}` and
    nothing else, deliberately: a free-text fallback beside `because` is exactly
    what would become the rendered sentence in practice and let the locale
    entries rot, which is the contract's own argument for why a `Gap` (unlike a
    `StrategyWarning`) has no English side-channel at all.

    So a code WITH a bundle entry renders that entry, and a code the bundles do
    NOT carry — the normal case for a kind arriving from the platform under a
    code this repo has never seen — falls back to the raw code string itself,
    through the same localizer every warning uses (`warnings.js::localizedByCode`,
    the one place this repo does that fallback)."""
    assert "אין כלל הקובע מפתח מרבי" in panels["he"]
    assert "No rule states the maximum span" in panels["en"]
    planning_group = panels["he"][panels["he"].index('data-closes-by="planning"'):]
    assert "unmodellable_gate" in planning_group


def test_a_code_with_no_bundle_entry_is_marked_english_and_left_to_right(panels):
    """The fallback in the test above is not a sentence a Hebrew reader can read
    as their own app's voice — it is the raw machine code, and a page that showed
    it unmarked in an RTL flow would present untranslated snake_case as if it were
    a localized sentence. `unmodellable_gate` has no bundle entry on either side;
    `uncovered_max_span` does, on both."""
    he = panels["he"]
    localized = he[:he.index('data-closes-by="planning"')]
    unlocalized = he[he.index('data-closes-by="planning"'):]
    assert '<div class="gap-what" lang="en" dir="ltr">' not in localized
    assert '<div class="gap-what" lang="en" dir="ltr">' in unlocalized
