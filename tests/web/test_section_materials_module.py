"""What the yard cuts for one stretch (static/js/section-materials.js), in node.

The materials block on an office job card answers "what is this bit of fence
made of" beside the drawing, instead of sending the reader to the flat BOM. Two
of the things it has to get right are invisible on screen when they are wrong —
a card that quietly listed the WHOLE JOB looks exactly like a card that listed
its own stretch, and a count merged across the wrong key looks exactly like a
count merged across the right one. Both are arithmetic over the grouped BOM, so
both are checked here rather than by looking at a browser.

The module had no test at all, and a mutation run proved what that cost: the
group filter, the merge key, the qty/unit pairing, the shared-piece row and the
three-way empty state could each be broken without a single test in the repo
going red. One test below stands against each.

Fixtures are in `report/bom_groups.py`'s exact shape — `GroupedBom.groups`, each
a `BomGroup` with `kind`/`element_id`/`lines`, each line a `GroupedLine` with
`slot_key`, `cut_length_mm`, `length_basis` and `shared_with`. A fixture in any
other shape would test this module against data it will never be handed.
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
// `renderSectionMaterials` returns a DETACHED element and reads no application
// state, so the entire DOM it needs is `createElement` plus the handful of
// properties it sets on what comes back. That is the module's own contract
// (house style, same as `js/elevation.js`), not a convenience of this harness.
const element = () => ({
  dataset: {}, className: "", innerHTML: "",
  addEventListener() {}, contains: () => true,
});
globalThis.document = {
  createElement: element, getElementById: () => null,
  querySelector: () => null, querySelectorAll: () => [], documentElement: {},
};
globalThis.fetch = async (url) => ({
  ok: true, json: async () => JSON.parse(readFileSync(url, "utf8")),
});

import { setLocale } from "./js/i18n.js";
import { setUnits } from "./js/units.js";
import { linesForRun, renderSectionMaterials } from "./js/section-materials.js";

// Assert against the BUNDLE, never a copy of the wording: a copy edit is not a
// regression, and a spelled-out sentence passes even when the wrong key is read.
const EN = JSON.parse(readFileSync("./i18n/en.json", "utf8"));
const out = {};
await setLocale("en");

// A `GroupedLine`, defaults and all (report/bom_groups.py).
const L = (o) => ({ sku: "", qty: 0, unit: "each", role: "", slot_key: "",
                    cut_length_mm: null, length_basis: null, shared_with: [],
                    ...o });
const RAIL = { sku: "RAIL-3050", unit: "each", role: "rail",
               cut_length_mm: 2400, length_basis: "width" };

// One job: two stretches, a post shared at the node where they meet, a
// standalone gate beside them, one bay of run1, and the decision that bought
// the rails. Only the `section` group whose `element_id` IS "run1" belongs on
// run1's card; every other group here is a way of getting that wrong.
const GROUPED = {
  groups: [
    { kind: "section", element_id: "run1", chosen: "", rejected: [], preset: "",
      lines: [
        // two slots of the same product at the same cut: ONE row of 4
        L({ ...RAIL, qty: 2, slot_key: "rail#0" }),
        L({ ...RAIL, qty: 2, slot_key: "rail#1" }),
        // same nominal length, cut ON THE SLOPE: a different piece, its own row
        L({ ...RAIL, qty: 1, slot_key: "rail#0", length_basis: "slope" }),
        // a piece this stretch splits with the next one, twice over: they merge
        // with each other and with nothing else
        L({ ...RAIL, qty: 1, slot_key: "rail#0",
            shared_with: ["span@run2:0-1500"] }),
        L({ ...RAIL, qty: 1, slot_key: "rail#2",
            shared_with: ["span@run2:0-1500"] }),
        // a plain count — the line that reads "8 each"
        L({ sku: "POST-80", qty: 8, unit: "each", role: "post" }),
        // ...and a line whose unit IS a length, which must convert
        L({ sku: "WIRE-2", qty: 3000, unit: "mm", role: "infill" }),
      ] },
    { kind: "section", element_id: "run2", lines: [
        L({ sku: "OTHER-SECTION-RAIL", qty: 5, unit: "each", role: "rail" })] },
    // the post standing where the two runs meet: `Post.run_ref` is `node:n2`,
    // the strategy's own answer that it belongs to NEITHER run
    { kind: "node", element_id: "node:n2", lines: [
        L({ sku: "POST-NODE", qty: 1, unit: "each", role: "post" })] },
    // a gate that stands on no run at all
    { kind: "gate", element_id: "gate@g1", lines: [
        L({ sku: "GATE-KIT", qty: 1, unit: "each", role: "gate" })] },
    // a bay group is a strict SUBSET of the section's own lines, so folding it
    // in does not add a strange sku — it silently doubles a real count
    { kind: "bay", element_id: "span@run1:0-1500", lines: [
        L({ ...RAIL, qty: 2, slot_key: "rail#0" })] },
    { kind: "decision", element_id: "s01", chosen: "RAIL-3050",
      rejected: ["RAIL-2900"], preset: "least_cost", lines: [
        L({ sku: "DECISION-ONLY", qty: 9, unit: "each", role: "rail" })] },
  ],
  unassigned: [], from_stock: [], unresolved: [],
};

const before = JSON.stringify(GROUPED);
const run1 = linesForRun(GROUPED, "run1");
out.run1_state = run1.state;
out.run1_run_id = run1.runId;
out.run1 = run1.lines;
out.input_untouched = JSON.stringify(GROUPED) === before;
out.stable = JSON.stringify(linesForRun(GROUPED, "run1")) === JSON.stringify(run1);

// the three states, each from the input that actually produces it
out.state_no_run_null = linesForRun(null, "run1").state;
out.state_no_run_unnamed = linesForRun(GROUPED, null).state;
out.state_no_lines = linesForRun(
  { groups: [{ kind: "section", element_id: "run9", lines: [] }] }, "run9").state;
out.state_lines = run1.state;
// ...and a stretch with no group of its own is not "no plan": the plan exists
out.state_missing_section = linesForRun(GROUPED, "run7").state;

const html = (grouped, runId, opts) =>
  renderSectionMaterials(grouped, runId, opts).innerHTML;
const dataState = (grouped, runId, opts) =>
  renderSectionMaterials(grouped, runId, opts).dataset.state;

out.no_run_html = html(null, "run1");
out.no_run_state = dataState(null, "run1");
out.no_lines_html = html({ groups: [] }, "run1");
out.no_lines_state = dataState({ groups: [] }, "run1");
out.loading_html = html(null, "run1", { loading: true });
out.loading_state = dataState(null, "run1", { loading: true });

out.mm_html = html(GROUPED, "run1");
out.mm_state = dataState(GROUPED, "run1");
out.interactive_html = html(GROUPED, "run1", { onSelectElement: () => {} });

// The cm reader is the one the qty/unit pairing exists for: a COUNT must not go
// through the mm->display converter.
setUnits("cm");
out.cm_html = html(GROUPED, "run1");
setUnits("mm");

out.keys = {
  no_run: EN["job.materials_no_run"], none: EN["job.materials_none"],
  loading: EN["job.loading"], shared: EN["job.materials_shared"],
  shared_one: EN["job.materials_shared_note_one"],
  on_slope: EN["job.materials_on_slope"],
  mm: EN["units.mm"], cm: EN["units.cm"], each: EN["unit.each"],
};

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def sm():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def rows(lines, sku):
    return [line for line in lines if line["sku"] == sku]


# -- the pure half: which lines are this stretch's, and how they merge ----------

def test_a_card_lists_its_own_stretch_and_nothing_else(sm):
    """The whole reason `linesForRun` filters rather than flattens.

    A `section` group carries a RUN id in `element_id`, and the fixture puts
    every other way of belonging to this job beside it: the other stretch, the
    post at the node the two runs share, a standalone gate, one bay of this very
    run and the decision that bought the rails. Dropping the `kind`/`element_id`
    test folds all of them in, and the card then reads as the whole job's
    materials while looking exactly like a card that got it right.

    `node` and `gate` are the two the module argues about at length: a node post
    belongs to NEITHER run (`Post.run_ref` says `node:n2`), so putting it on both
    cards counts one post twice; a standalone gate is in no section at all.
    """
    skus = sorted({line["sku"] for line in sm["run1"]})
    assert skus == ["POST-80", "RAIL-3050", "WIRE-2"]
    for absent in ("OTHER-SECTION-RAIL", "POST-NODE", "GATE-KIT", "DECISION-ONLY"):
        assert absent not in skus


def test_a_bay_of_this_very_stretch_is_not_added_to_the_stretch(sm):
    """The fold-in that adds no strange sku and so shows up only as a number.

    A `bay` group holds the section's OWN lines, one element's worth at a time.
    Absorbing it does not make an unfamiliar product appear on the card — it
    silently reports six rails where the stretch has four, which is the failure
    a reader has no way to notice.
    """
    width = [line for line in rows(sm["run1"], "RAIL-3050")
             if line["lengthBasis"] == "width" and not line["sharedWith"]]
    assert len(width) == 1
    assert width[0]["qty"] == 4, "four rails, not the bay group's copy on top"


def test_two_slots_of_one_product_merge_into_a_single_row(sm):
    """`rail#0` and `rail#1` are one line on this card, deliberately.

    The backend merge key includes `slot_key` because the setting-out schedule
    reports parts per element. A card is not that sheet: two rows reading
    `RAIL-3050 · rail · 4 · 2400 mm` one above the other look like the same line
    entered twice, and a reader who counts them gets eight rails. So the qty AND
    the row count are both asserted — one row of 4, never two of 2.
    """
    width = [line for line in rows(sm["run1"], "RAIL-3050")
             if line["lengthBasis"] == "width" and not line["sharedWith"]]
    assert len(width) == 1, "slot_key must not split the row"
    assert width[0]["qty"] == 4
    assert width[0]["slotKey"], "the slot still travels on the piece"


def test_a_cut_on_the_slope_stays_its_own_row(sm):
    """`length_basis` stays in the key for `bom_groups.py`'s reason: a raked
    bay's rail is cut ON THE SLOPE, so two pieces of the same nominal length are
    two different cuts and merging them would report one — and the installer who
    cuts to the nominal number has wasted the bar."""
    bases = sorted(line["lengthBasis"] for line in rows(sm["run1"], "RAIL-3050"))
    assert bases.count("slope") == 1
    slope = [line for line in rows(sm["run1"], "RAIL-3050")
             if line["lengthBasis"] == "slope"]
    assert slope[0]["qty"] == 1, "the slope cut kept its own count"


def test_a_shared_piece_is_never_absorbed_into_the_unshared_count(sm):
    """Rule 3 of the module's existence, and it cuts both ways.

    A piece serving elements outside this stretch must not be added to the count
    of pieces that serve only this one — the whole point of marking it is that
    the reader should NOT add it to another card's total. Two such pieces with
    the same partner do merge with each other, and `sharedWith` has to survive
    that merge or the row it feeds is never drawn.
    """
    shared = [line for line in rows(sm["run1"], "RAIL-3050") if line["sharedWith"]]
    assert len(shared) == 1
    assert shared[0]["qty"] == 2, "the two shared pieces merged with each other"
    assert shared[0]["sharedWith"] == ["span@run2:0-1500"], \
        "sharing survives the merge or nothing marks the row"
    unshared = sum(line["qty"] for line in rows(sm["run1"], "RAIL-3050")
                   if not line["sharedWith"])
    assert unshared == 5, "the shared pair stayed out of the plain counts"


def test_the_three_states_are_three_answers(sm):
    """"Press Generate", "wait" and "this stretch needs nothing" are different
    things to tell a person, and only the first is a job to do.

    Collapsing them is audit finding B01's shape — a failed or absent read
    rendering as "nothing is wrong". Asserted on all three inputs that produce
    them, including the one that is easiest to get backwards: a job that HAS a
    plan in which this stretch happens to ask for nothing is `no-lines`, not
    `no-run`.
    """
    assert sm["state_no_run_null"] == "no-run"
    assert sm["state_no_run_unnamed"] == "no-run"
    assert sm["state_no_lines"] == "no-lines"
    assert sm["state_lines"] == "lines"
    assert sm["state_missing_section"] == "no-lines", \
        "a worked-out job with nothing for this stretch is not an unworked job"


def test_it_is_pure(sm):
    """Same contract `bayRects` keeps next door: arithmetic over data handed in,
    no DOM, no application state, the input untouched."""
    assert sm["input_untouched"]
    assert sm["stable"]
    assert sm["run1_run_id"] == "run1"


# -- the element: what the office actually reads -------------------------------

def test_each_empty_answer_says_its_own_sentence(sm):
    """The states again, one layer out, because this is where they reach a
    person. `data-state` alone would satisfy a test while all three rendered the
    same sentence — and "this stretch asks for no cut pieces" shown to somebody
    whose job has never been generated is a wrong answer shaped like a right
    one."""
    assert sm["no_run_state"] == "no-run"
    assert sm["keys"]["no_run"] in sm["no_run_html"]
    assert sm["keys"]["none"] not in sm["no_run_html"]

    assert sm["no_lines_state"] == "no-lines"
    assert sm["keys"]["none"] in sm["no_lines_html"]
    assert sm["keys"]["no_run"] not in sm["no_lines_html"]

    assert sm["loading_state"] == "loading"
    assert sm["keys"]["loading"] in sm["loading_html"]


def test_a_count_is_not_a_length(sm):
    """The scar `js/tabs.js::qtyCells` carries, and the reason it was lifted.

    A qty is a COUNT unless its unit says it is a length. Putting every qty
    through the mm->display converter reported `0.8 each` to anybody who had
    switched the app to cm — wrong by a factor of ten, on the one surface built
    to answer "what does this stretch need". The `mm` line is asserted beside it
    because the fix has to work in both directions: that number MUST convert,
    and its label must swap with it, or a converted figure sits under a literal
    "mm" while the rest of the screen says cm.
    """
    cm = sm["cm_html"]
    assert '<td class="num">8</td>' in cm, "eight posts are eight posts in cm"
    assert "0.8" not in cm
    assert f'>{sm["keys"]["each"]}</td>' in cm, "the count keeps its own word"
    # the same row in mm, so the assertion above cannot pass by never converting
    assert '<td class="num">8</td>' in sm["mm_html"]
    # ...and the line whose unit IS mm converts, label and all
    assert f'<td class="num">300</td><td>{sm["keys"]["cm"]}</td>' in cm
    assert f'<td class="num">3000</td><td>{sm["keys"]["mm"]}</td>' in sm["mm_html"]


def test_a_shared_piece_is_marked_where_it_is_read(sm):
    """A continuous rail crossing two stretches is ONE rail and appears whole in
    each of their groups (contract obligation 14). Per stretch that is the right
    number; read across two cards it is the same rail counted twice, and the only
    thing standing between a reader and that mistake is the row saying so.

    `bom_groups.GroupedLine.shared_with` was added to feed exactly this row, so a
    row that renders without it makes the field pointless and the count
    misleading in the one case it was meant for.
    """
    html = sm["mm_html"]
    assert "section-materials-share-row" in html
    assert sm["keys"]["shared"] in html
    assert sm["keys"]["shared_one"] in html, "one other element, said in the singular"
    assert "span@run2:0-1500" in html, "the element it also serves is NAMED"
    assert html.count('data-shared="1"') == 1, "only the shared row is marked"
    # with the opt-in callback the named element becomes a way to get there
    assert 'data-element="span@run2:0-1500"' in sm["interactive_html"]
    assert "data-element=" not in html, "inert without a callback"


def test_a_cut_on_the_slope_is_called_out_on_the_row(sm):
    """A raked bay's rail is longer than the bay is wide. Two rows of the same
    nominal length that do not say which is which send somebody to the saw with
    the wrong number."""
    assert sm["keys"]["on_slope"] in sm["mm_html"]
    assert sm["mm_state"] == "lines"
