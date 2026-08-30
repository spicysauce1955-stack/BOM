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

// v1.2's `ParamRef`: the SAME parameter under two different scopes. The first
// real published snapshot does exactly this with `footing_depth_mm`, which is
// the entire argument for the field — a subject naming only the parameter names
// two different holes at once, and a curator closing "the footing_depth_mm gap"
// closes whichever one they happened to be looking at.
//
// `point` carries the three shapes a real cell has: an enum token, a BOOLEAN
// (`hvhz`), and a string straight out of a published table, inch marks and all.
const scoped = (scopeId) => gap({
  id: "gap:footing:" + scopeId,
  subject: {
    kind: "param", id: "footing_depth_mm", tenant: "t1",
    scope: { kind: "fence_model", id: scopeId },
    point: { exposure_category: "D", hvhz: true, panel_height: '49" to 76"' },
  },
});

// `EntityRef.kind` is an OPEN registry (v1.2 §1.1): the other team adds a value
// and there is no release on this side. Nothing here may key a locale bundle on
// it. This is a kind this repo has never seen and never will.
const unknownRefKind = gap({
  kind: "unmodellable_entity", closes_by: "planning", severity: "informational",
  because: { code: "parameter_scope_unmappable", params: { parameter: "footing_depth_mm" } },
  subject: { kind: "entity", id: "shade_sail:SS-3", ref_kind: "shade_sail_assembly" },
  would_close: "an evaluator dimension for a shade_sail_assembly",
});

// A scope id and a condition point whose DIMENSION NAME and VALUE are both
// XSS-shaped. Both come from a published document by way of the Knowledge
// Platform — untrusted data by contract — and `point` is the newest place in
// this module where such a string reaches `innerHTML`.
const hostilePoint = gap({
  subject: {
    kind: "param", id: "footing_depth_mm",
    scope: { kind: "fence_model", id: '"><img src=x onerror=alert(5)>' },
    point: { "<b>dim</b>": '"><script>alert(6)</script>' },
  },
});

// A citation whose `id`/`belongs_to` are themselves XSS-shaped — `SourceRef`
// fields arrive from the Knowledge Platform and are untrusted data by
// contract, and `citesHtml` puts them inside an HTML-attribute context
// (`data-evidence-id="..."`) as well as text content, which is a second place
// for an unescaped quote or angle bracket to break out.
const hostileCites = gap({
  cites: [{ id: '"><script>alert(2)</script>', belongs_to: 'sha256:"><img src=x onerror=alert(3)>' }],
});

const out = {};
await setLocale("he");
out.he = gapsPanelHtml([gap({}), curator]);
out.he_hostile_cites = gapRowHtml(hostileCites);
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
out.he_scoped_a = gapRowHtml(scoped("FM-500"));
out.he_scoped_b = gapRowHtml(scoped("FM-900"));
out.he_unknown_ref_kind = gapRowHtml(unknownRefKind);
out.he_hostile_point = gapRowHtml(hostilePoint);
out.counts = warnsLineCount([gap({}), curator]);

await setLocale("en");
out.en = gapsPanelHtml([gap({}), curator]);
out.en_kinds = KINDS.map((k) => gapRowHtml(gap({ kind: k }))).join("\\n");
out.en_scoped_a = gapRowHtml(scoped("FM-500"));
out.en_unknown_ref_kind = gapRowHtml(unknownRefKind);

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


def test_two_gaps_about_one_parameter_under_different_scopes_are_distinguishable(panels):
    """THE regression v1.2's `ParamRef.scope` exists for. The first real
    published snapshot carries `footing_depth_mm` under two different scopes; a
    subject that prints only the parameter renders those two holes as the same
    row, and a curator who closes "the footing_depth_mm gap" closes one of them
    at random. Distinguishable ON SCREEN, not merely in `GapSubject.key()`."""
    a, b = panels["he_scoped_a"], panels["he_scoped_b"]
    assert a != b
    assert '<bdi class="sku">fence_model/FM-500</bdi>' in a
    assert '<bdi class="sku">fence_model/FM-900</bdi>' in b
    assert "FM-900" not in a and "FM-500" not in b
    # ...and the scope is LABELLED in the reader's language, in both
    assert '<span class="gap-scope">של <bdi class="sku">fence_model/FM-500</bdi></span>' in a
    assert '<span class="gap-scope">of <bdi class="sku">fence_model/FM-500</bdi></span>' \
        in panels["en_scoped_a"]


def test_a_condition_point_renders_from_its_parts_and_never_as_an_object(panels):
    """`ParamRef.point` is a mapping so the renderer can build the phrase from
    its parts — the contract's own reason for the shape. Two failures are
    possible and both are silent: interpolating the mapping (`[object Object]`
    on screen, in both languages), or interpolating a pre-joined English
    fragment into a Hebrew sentence. So each dimension is a WORD and each value
    is formatted by its type — `hvhz: true` reads `כן`, because `true` is
    neither Hebrew nor English."""
    he, en = panels["he_scoped_a"], panels["en_scoped_a"]
    for html in (he, en):
        assert "[object Object]" not in html
    # the dimensions this app has words for, in the reader's language
    assert "קטגוריית חשיפה" in he
    assert "אזור רוחות הוריקן (HVHZ)" in he
    assert "Exposure category" in en
    assert "High-velocity hurricane zone (HVHZ)" in en
    # the boolean is a word, not a JS literal
    assert '<span class="gap-point-value">כן</span>' in he
    assert '<span class="gap-point-value">yes</span>' in en
    assert ">true<" not in he and ">true<" not in en
    # a dimension no bundle names falls back to the raw name AS a raw name —
    # an identifier, isolated — never to the literal locale key
    assert '<bdi class="sku">panel_height</bdi>' in he
    assert "site.panel_height" not in he and "site.panel_height" not in en
    # a value quoted out of a published table keeps its inch marks, escaped and
    # LTR-isolated so they do not reorder the Hebrew around them
    assert '<bdi class="sku">49&quot; to 76&quot;</bdi>' in he


def test_an_open_registry_ref_kind_is_data_and_never_a_locale_key(panels):
    """`EntityRef.kind` is an OPEN registry: the Knowledge Platform adds an entry
    without an amendment and without a release here. `t("gaps.subject." + ref_kind)`
    would therefore put the literal string `gaps.subject.shade_sail_assembly` on
    screen the day they do, in both languages, with nothing red anywhere — which
    is exactly the failure `subject.kind` (CLOSED, key-checked from the Python
    Literal) exists separately to prevent."""
    for html in (panels["he_unknown_ref_kind"], panels["en_unknown_ref_kind"]):
        assert "gaps.subject." not in html, html[:400]
        # carried as data, isolated as the identifier it is
        assert '<bdi class="sku">shade_sail_assembly</bdi>' in html
        assert 'data-ref-kind="shade_sail_assembly"' in html


def test_a_scope_and_point_reaching_innerhtml_go_through_esc(panels):
    """A scope id and a condition point's dimension names and values are
    published-document text arriving through the Knowledge Platform — untrusted
    by contract, and `point` is the newest place in this module where such a
    string reaches `innerHTML`."""
    html = panels["he_hostile_point"]
    assert "<script>alert(6)" not in html
    assert "<img src=x" not in html
    assert '"><script>' not in html and '"><img' not in html
    assert "&lt;script&gt;alert(6)&lt;/script&gt;" in html
    assert "&lt;b&gt;dim&lt;/b&gt;" in html
    assert "&lt;img src=x onerror=alert(5)&gt;" in html


def test_a_citation_carries_the_evidence_link_contract_js_evidence_js_depends_on(panels):
    """`js/evidence.js`'s click delegation (module header, "DOM ownership")
    listens for `.evidence-link[data-evidence-id]` anywhere in the document —
    a shared, documented attribute contract, not a reach into `gaps.js`'s own
    DOM. If `citesHtml` stops emitting it, every citation in the gaps panel
    goes back to being inert text and no click anywhere opens the viewer,
    silently — nothing else in this suite would catch that."""
    he = panels["he"]
    assert 'class="evidence-link sku"' in he
    assert 'data-evidence-id="sr_91"' in he
    assert 'data-belongs-to="sha256:deadbeef"' in he
    # the visible text still leads with `belongs_to`, same as `attribution()`
    # in doc-warnings.js — `gaps.js`'s own rule, unchanged by the click markup
    assert "<bdi>sha256:deadbeef</bdi>" in he


def test_a_citation_with_xss_shaped_id_and_belongs_to_is_escaped_everywhere_it_lands(panels):
    """`SourceRef.id`/`belongs_to` are untrusted Knowledge Platform data
    (CLAUDE.md), and the click markup puts them in TWO places at once: an HTML
    ATTRIBUTE (`data-evidence-id="..."`) and element text. A regression here
    is a live XSS hole reachable by any citation on the gaps panel — mirrors
    `test_curator_text_reaching_innerhtml_goes_through_esc`'s rigor (raw-tag
    absence AND escaped-entity presence), applied to `cites` instead of
    `would_close`."""
    html = panels["he_hostile_cites"]
    # neither the id nor belongs_to ever appear as live markup
    assert "<script>" not in html
    assert "<img src=x" not in html
    # the attribute itself cannot be broken out of by a literal `">`
    assert '"><script>' not in html
    assert '"><img' not in html
    # ...and the escaped forms are present, in the attribute and in the text
    assert "data-evidence-id=\"&quot;&gt;&lt;script&gt;alert(2)&lt;/script&gt;\"" in html
    assert "data-belongs-to=\"sha256:&quot;&gt;&lt;img src=x onerror=alert(3)&gt;\"" in html
    assert "&lt;script&gt;alert(2)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(3)&gt;" in html


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
