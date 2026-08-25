"""Site conditions: the draft <-> payload boundary (static/js/site.js).

`None` is not `False` and it is not `0`. The engine leans on the difference —
`evaluator` treats a MISSING context field as *not applicable*, so an unstated
dimension makes a rule stand aside while `false` makes it decide — and the place
that difference is easiest to destroy is a form, where "" and `false` and "not
stated" all look like the same emptiness.

So the mapping is a pure function and it is tested in node, not only by aiming a
mouse at a select: the browser suite can show that a value round-trips, and it
cannot cheaply show that `hvhz: false` survives a reload as `false` rather than
quietly becoming `null` again.
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
  s: {},
  getItem: (k) => globalThis.localStorage.s[k] ?? null,
  setItem: (k, v) => { globalThis.localStorage.s[k] = String(v); },
};
globalThis.document = { getElementById: () => null, querySelectorAll: () => [],
                        documentElement: {} };

import {
  EXPOSURE_CATEGORIES, SITE_DIMENSIONS, depthFromField, draftFromSite,
  fieldFromHvhz, hvhzFromField, siteChanged, sitePayload, unsetDimensions,
} from "./js/site.js";
import { state } from "./js/state.js";
import { toDisplayValue, toMm } from "./js/units.js";

const out = {};
out.dimensions = SITE_DIMENSIONS;
out.categories = EXPOSURE_CATEGORIES;

// ---- a project nobody has said anything about -----------------------------
out.empty_draft = draftFromSite({ revision: 0 });
out.empty_payload = sitePayload(out.empty_draft);
out.empty_unset = unsetDimensions(out.empty_payload);
out.no_site_at_all = sitePayload(draftFromSite(undefined));

// ---- null is not false: the whole point -----------------------------------
const said_no = draftFromSite({ hvhz: false, revision: 3 });
out.false_survives_draft = said_no.hvhz;
out.false_survives_payload = sitePayload(said_no).hvhz;
out.false_is_stated = unsetDimensions(sitePayload(said_no));
out.unset_stays_null = sitePayload(draftFromSite({ revision: 3 })).hvhz;
// ...and through the SELECT's field value, which is where "" and false meet
out.hvhz_fields = [fieldFromHvhz(true), fieldFromHvhz(false), fieldFromHvhz(null)];
out.hvhz_values = [hvhzFromField("true"), hvhzFromField("false"),
                   hvhzFromField(""), hvhzFromField(undefined)];

// ---- zero is not unset either ---------------------------------------------
const at_grade = sitePayload(draftFromSite({ frost_depth_mm: 0, revision: 1 }));
out.zero_depth = at_grade.frost_depth_mm;
out.zero_is_stated = unsetDimensions(at_grade);
// ...and it has to survive the FIELD, which is where `0` and "" are actually
// confused: the empty box is "nobody measured", `0` is a measured at-grade site
out.depth_field = ["", "   ", "0", "45", "900", "-5", "abc", "1.4"]
  .map((raw) => depthFromField(raw, "mm"));
// the same typing in cm — the boundary the display unit is crossed at
out.depth_field_cm = ["", "0", "90", "90.5", "-1"].map((raw) => depthFromField(raw, "cm"));
// a stated zero really does reach the wire as a zero
out.zero_through_the_field = sitePayload(
  { ...draftFromSite({}), frost_depth_mm: depthFromField("0", "mm").mm }).frost_depth_mm;

// ---- the payload's SHAPE: five declared keys, and never a revision ---------
// `SiteConditions` is `extra="forbid"`, so a stray key is a 422 rather than a
// field the server ignores; and `revision` is bumped by the route, so a client
// that sent one would be claiming authority over the counter every derived view
// checks itself against.
const full = sitePayload(draftFromSite({
  exposure_category: "C", hvhz: true, frost_depth_mm: 900,
  jurisdiction: "Miami-Dade County", code_edition: "ASCE 7-16", revision: 7,
}));
out.full_keys = Object.keys(full).sort();
out.full = full;

// ---- an unknown exposure category never reaches the wire ------------------
// `Literal["B","C","D"] | None` answers anything else with a 422; the control is
// a closed list, and the mapping refuses one too rather than trusting the DOM.
out.bogus_category = sitePayload({ exposure_category: "E" }).exposure_category;
out.bogus_stored = draftFromSite({ exposure_category: "E" }).exposure_category;

// ---- blank text is `null`, not "" -----------------------------------------
out.blank_text = sitePayload({ jurisdiction: "   ", code_edition: "" });
out.trimmed_text = sitePayload({ jurisdiction: "  Miami-Dade County  " }).jurisdiction;

// ---- the length round-trips losslessly through the display unit -----------
// Storage and payload are int mm; cm is a presentation preference. A depth typed
// in cm must come back the same millimetres it went in as.
const depths = [0, 1, 45, 900, 905, 1219, 99999];
out.mm_round_trip = depths.map((mm) => toMm(toDisplayValue(mm, "mm"), "mm"));
out.cm_round_trip = depths.map((mm) => toMm(toDisplayValue(mm, "cm"), "cm"));
out.cm_display = depths.map((mm) => toDisplayValue(mm, "cm"));
// and through the PAYLOAD, which is what actually leaves the browser
out.payload_round_trip = depths.map((mm) =>
  sitePayload(draftFromSite(
    { frost_depth_mm: toMm(toDisplayValue(mm, "cm"), "cm") })).frost_depth_mm);
out.units_default = state.units;

// ---- "did the site move" is answered on the FACTS -------------------------
// The same comparison `_refuse_moved_site` makes: re-saving identical conditions
// is not a change (guarding on the revision counter is the defect that bricked a
// run), and stating `false` where nothing was stated IS one.
const c = sitePayload(draftFromSite({ exposure_category: "C", revision: 2 }));
const c_again = sitePayload(draftFromSite({ exposure_category: "C", revision: 9 }));
out.same_facts_new_revision = siteChanged(c, c_again);
out.category_moved = siteChanged(c, sitePayload(draftFromSite({ exposure_category: "B" })));
out.saying_no_is_a_change = siteChanged(
  sitePayload(draftFromSite({})), sitePayload(draftFromSite({ hvhz: false })));

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def site():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_five_dimensions_are_the_backend_fields(site):
    """The panel's field names are the model's field names, so the 409's
    `changed` list and the `site_condition_missing` warning name things a reader
    can find on screen."""
    from fenceai.project.model import SiteConditions

    declared = [f for f in SiteConditions.model_fields if f != "revision"]
    assert site["dimensions"] == declared
    # the VOCABULARY comes from the model too, not from a copy of it here. A
    # category the panel does not offer is unreachable in the app; worse, one the
    # panel does not RECOGNISE is coerced to `null` by `draftFromSite` and then
    # written back as null on the next save of any other field — a stored site
    # condition erased by a form that could not read it. Registry additions are
    # explicitly not amendments (CLAUDE.md), so this list is meant to grow.
    import typing

    literal = SiteConditions.model_fields["exposure_category"].annotation
    categories = sorted(a for arg in typing.get_args(literal)
                        for a in typing.get_args(arg) if isinstance(a, str))
    assert categories, literal
    assert site["categories"] == categories


def test_a_site_nobody_has_described_is_five_nulls(site):
    assert site["empty_payload"] == {
        "exposure_category": None, "hvhz": None, "frost_depth_mm": None,
        "jurisdiction": None, "code_edition": None,
    }
    assert site["empty_unset"] == site["dimensions"]
    assert site["no_site_at_all"] == site["empty_payload"]


def test_false_is_a_statement_and_survives_the_round_trip(site):
    """`hvhz: false` says this site is NOT in a hurricane zone. `|| null` in
    either direction would turn that back into "nobody has said", and the rule
    that would have decided stands aside instead."""
    assert site["false_survives_draft"] is False
    assert site["false_survives_payload"] is False
    assert site["false_is_stated"] == ["exposure_category", "frost_depth_mm",
                                       "jurisdiction", "code_edition"]
    assert site["unset_stays_null"] is None
    assert site["hvhz_fields"] == ["true", "false", ""]
    assert site["hvhz_values"] == [True, False, None, None]


def test_zero_is_a_depth_not_an_absence(site):
    assert site["zero_depth"] == 0
    assert "frost_depth_mm" not in site["zero_is_stated"]
    assert site["zero_through_the_field"] == 0


def test_the_field_has_three_answers_and_zero_is_one_of_them(site):
    """Empty is "nobody has measured it"; `0` is a measured at-grade depth;
    anything unreadable is a typo that must be SHOWN rather than stored — and an
    invalid field never overwrites the last good figure (`{mm: null}` here is
    what the caller declines to apply)."""
    assert site["depth_field"] == [
        {"mm": None, "invalid": False},    # ""
        {"mm": None, "invalid": False},    # "   "
        {"mm": 0, "invalid": False},       # "0" — a depth, not an absence
        {"mm": 45, "invalid": False},
        {"mm": 900, "invalid": False},
        {"mm": None, "invalid": True},     # "-5" — no site has a negative frost line
        {"mm": None, "invalid": True},     # "abc"
        {"mm": 1, "invalid": False},       # storage is INTEGER mm
    ]
    assert site["depth_field_cm"] == [
        {"mm": None, "invalid": False},
        {"mm": 0, "invalid": False},
        {"mm": 900, "invalid": False},     # 90 cm typed, 900 mm stored
        {"mm": 905, "invalid": False},
        {"mm": None, "invalid": True},
    ]


def test_the_payload_is_the_five_declared_fields_and_never_a_revision(site):
    assert site["full_keys"] == sorted(site["dimensions"])
    assert site["full"] == {
        "exposure_category": "C", "hvhz": True, "frost_depth_mm": 900,
        "jurisdiction": "Miami-Dade County", "code_edition": "ASCE 7-16",
    }


def test_the_payload_validates_against_the_model_that_forbids_extras(site):
    """The mapping's output is not merely shaped like the body — it IS one."""
    from fenceai.project.model import SiteConditions

    parsed = SiteConditions(**site["full"])
    assert parsed.exposure_category == "C" and parsed.hvhz is True
    assert parsed.frost_depth_mm == 900
    assert parsed.revision == 0  # the route sets it; the client never does
    empty = SiteConditions(**site["empty_payload"])
    assert empty.facts() == {}


def test_an_exposure_category_the_model_does_not_declare_never_leaves(site):
    assert site["bogus_category"] is None
    assert site["bogus_stored"] is None


def test_blank_text_is_null_rather_than_an_empty_string(site):
    assert site["blank_text"] == {
        "exposure_category": None, "hvhz": None, "frost_depth_mm": None,
        "jurisdiction": None, "code_edition": None,
    }
    assert site["trimmed_text"] == "Miami-Dade County"


def test_frost_depth_round_trips_losslessly_in_both_display_units(site):
    depths = [0, 1, 45, 900, 905, 1219, 99999]
    assert site["mm_round_trip"] == depths
    assert site["cm_round_trip"] == depths
    assert site["payload_round_trip"] == depths
    # and cm really is a different presentation, not a no-op that would make the
    # round-trip assertion above vacuous
    assert site["cm_display"] == [0, 0.1, 4.5, 90, 90.5, 121.9, 9999.9]
    assert site["units_default"] == "mm"


def test_saving_the_site_is_not_a_topology_change():
    """The hazard CLAUDE.md names by name, and the one nothing else can see:
    `openProject()` here would reset history and wipe the undo stack of whoever
    was drawing, and every test in this repo would still pass. Neither symbol may
    appear in this module — a snapshot for a non-user change is the same defect
    from the other side."""
    # comments STRIPPED: this module's header explains the rule by naming the
    # call it must not make, and a scan that read prose would forbid saying so
    code = "\n".join(
        line for line in (STATIC / "js" / "site.js").read_text().splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )
    assert "reloadProject" in code
    assert "openProject" not in code
    assert "pushSnapshot" not in code


def test_the_panel_is_wired_into_the_page_and_the_bootstrap():
    """A module nothing imports and a host element nothing renders into are both
    silent: `initSite()` would simply never run, and the estimator would be back
    to `PUT /projects/{id}/site` with no error anywhere."""
    assert '<div class="panel" id="site-conditions">' in (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    assert 'from "./js/site.js"' in app and "initSite();" in app


def test_the_panel_asks_whether_the_FACTS_moved_not_the_counter(site):
    assert site["same_facts_new_revision"] is False
    assert site["category_moved"] is True
    assert site["saying_no_is_a_change"] is True
