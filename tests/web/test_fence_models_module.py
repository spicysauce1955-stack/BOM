"""The model library as the UI names it (static/js/fence-models.js), in node.

The browser suite cannot reach any of this: the seeded library is two PUBLISHED
models, so every option it renders is selectable and every name has a Hebrew
translation. The rules that matter are the ones about the models a real library
grows — a draft somebody is still editing, a version that was retired, a model
whose author never wrote a Hebrew name — and each of them is a way for the
picker to lie:

  * a draft-only model that is HIDDEN reads as deleted ("where did my model
    go?"), and one that is offered as selectable resolves to nothing at
    generation time, failing long after the choice was made;
  * a name that falls back to blank leaves a row the user cannot identify;
  * an English name shown in a Hebrew-first UI when a Hebrew one was authored.

The module is pure string-building over its arguments, so node renders it
against the real locale bundles exactly as the browser would.
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

// fence-models.js reaches api.js and i18n.js, whose stateful halves touch
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
const LISTING = [
  {id: "M-LEGACY", active_version: 1, has_draft: false, status: "active",
   name_i18n: {en: "Legacy panel", he: "פאנל מורשת"}},
  // published, but somebody is editing the next version: still selectable
  {id: "M-SLAT", active_version: 2, has_draft: true, status: "active",
   name_i18n: {en: "Slat panel", he: "פאנל שלבים"}},
  // never published: nothing to select, but it must still be SEEN
  {id: "M-DRAFT", active_version: null, has_draft: true, status: "draft",
   name_i18n: {en: "Half-built", he: "חצי בנוי"}},
  // was published, then retired
  {id: "M-OLD", active_version: null, has_draft: false, status: "retired",
   name_i18n: {en: "Discontinued", he: "הופסק"}},
  // an author who never wrote a Hebrew name, and one who wrote no name at all
  {id: "M-ENONLY", active_version: 1, has_draft: false, status: "active",
   name_i18n: {en: "English only"}},
  {id: "M-NONAME", active_version: 1, has_draft: false, status: "active",
   name_i18n: {}},
];
let fetches = 0;
globalThis.fetch = async (url) => {
  if (url === "/api/fence-models") {
    fetches += 1;
    return {ok: true, json: async () => LISTING};
  }
  return {ok: true, json: async () => JSON.parse(readFileSync(url, "utf8"))};
};

import { setLocale } from "./js/i18n.js";
import {
  isSelectable, loadModelListing, modelName, modelOptionLabel,
  projectModelState, rowFor,
} from "./js/fence-models.js";

const out = {};
await setLocale("he");
const listing = await loadModelListing();
await loadModelListing();
out.fetches = fetches;
out.ids = listing.map((r) => r.id);
out.selectable = listing.filter(isSelectable).map((r) => r.id);
out.he_names = Object.fromEntries(listing.map((r) => [r.id, modelName(r)]));
out.he_labels = Object.fromEntries(listing.map((r) => [r.id, modelOptionLabel(r)]));
out.missing_row = modelName(rowFor(listing, "M-NOPE"));
out.found_row = modelName(rowFor(listing, "M-SLAT"));

await setLocale("en");
out.en_names = Object.fromEntries(listing.map((r) => [r.id, modelName(r)]));
out.en_labels = Object.fromEntries(listing.map((r) => [r.id, modelOptionLabel(r)]));

// --- what the whole fence is built to (audit B03) ---
const run = (id, ...models) => ({
  id, interval_events: models.map((m, i) => ({
    id: `${id}-ev${i}`, payload: {kind: "fence_model", model_id: m},
  })),
});
const project = (fence_model, ...runs) => ({fence_model, topology: {runs}});

out.state_default = projectModelState(
  project({model_id: "M-SLAT"}, run("run1"), run("run2")));
// the B03 reproduction: no project default, both stretches sold as M-SLAT
out.state_per_run = projectModelState(
  project(null, run("run1", "M-SLAT"), run("run2", "M-SLAT")));
out.state_mixed = projectModelState(
  project(null, run("run1", "M-SLAT"), run("run2", "M-LEGACY")));
out.state_none = projectModelState(project(null, run("run1"), run("run2")));
// a default with one stretch sold as something else: the row must not report
// the default alone, or it names a model half the fence is not built to
out.state_exception = projectModelState(
  project({model_id: "M-LEGACY"}, run("run1"), run("run2", "M-SLAT")));
out.state_empty = projectModelState(null);
out.state_no_runs = projectModelState(project(null));

console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def lib():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_every_model_is_listed_including_the_ones_that_cannot_be_chosen(lib):
    """Hiding a draft makes it look deleted. "Why can I not pick it" is a
    question with an answer on screen; "where did it go" is not."""
    assert lib["ids"] == ["M-LEGACY", "M-SLAT", "M-DRAFT", "M-OLD", "M-ENONLY",
                          "M-NONAME"]


def test_only_a_published_version_is_selectable(lib):
    """A draft's document can still change under its version, and a retired
    model resolves to nothing — either one chosen would fail at generation,
    long after the choice was made."""
    assert lib["selectable"] == ["M-LEGACY", "M-SLAT", "M-ENONLY", "M-NONAME"]


def test_an_unselectable_model_says_why_in_the_active_language(lib):
    assert lib["he_labels"]["M-DRAFT"].endswith("לא פורסם")
    assert lib["he_labels"]["M-OLD"].endswith("לא פורסם")
    assert lib["en_labels"]["M-DRAFT"].endswith("not published")
    # and a selectable one carries no such suffix
    assert "לא פורסם" not in lib["he_labels"]["M-SLAT"]
    assert "not published" not in lib["en_labels"]["M-SLAT"]


def test_a_model_with_a_draft_beside_its_active_version_stays_selectable(lib):
    """`has_draft` describes work in progress, not the published line. Reading it
    as "not ready" would take a shipping model off the menu."""
    assert "M-SLAT" in lib["selectable"]


def test_the_name_is_the_active_language_and_the_label_names_the_id_too(lib):
    assert lib["he_names"]["M-SLAT"] == "פאנל שלבים"
    assert lib["en_names"]["M-SLAT"] == "Slat panel"
    # the id is what the topology event and the run snapshot record, so it is on
    # the row beside the name rather than replaced by it
    assert lib["he_labels"]["M-SLAT"] == "פאנל שלבים (M-SLAT)"


def test_a_name_never_renders_blank(lib):
    """A row the user cannot identify is worse than an untranslated one: English
    when only English was authored, and the id when nothing was."""
    assert lib["he_names"]["M-ENONLY"] == "English only"
    assert lib["he_names"]["M-NONAME"] == "M-NONAME"
    assert lib["missing_row"] == ""      # no row at all: the caller falls back
    assert lib["found_row"] == "פאנל שלבים"


def test_a_model_sold_per_stretch_is_not_reported_as_no_model_chosen(lib):
    """Audit B03. `What was sold` writes a `fence_model` INTERVAL EVENT on the
    run; the canvas aside read only `project.fence_model`, so a job with both
    stretches sold as M-SLAT still said *"No model chosen"* — and then sent the
    salesperson to the Panel tab, which their own role hides.

    It also disagreed with the handover sheet, which reports `no_model_chosen`
    only when there is no default AND millimetres nothing covers
    (`report/handover.py`). Two surfaces answering one question differently is
    the defect; the wording is downstream of it."""
    assert lib["state_per_run"] == {"kind": "per_run", "models": ["M-SLAT"]}
    assert lib["state_mixed"] == {"kind": "mixed",
                                  "models": ["M-LEGACY", "M-SLAT"]}


def test_a_project_default_is_still_the_headline(lib):
    assert lib["state_default"] == {"kind": "default", "model_id": "M-SLAT",
                                    "models": []}


def test_a_stretch_sold_against_the_default_is_named_beside_it(lib):
    """A default of M-LEGACY with one stretch sold as M-SLAT is not "built to
    M-LEGACY". The exception belongs on the row, or the office reads one model
    for a fence that carries two."""
    assert lib["state_exception"] == {"kind": "default", "model_id": "M-LEGACY",
                                      "models": ["M-SLAT"]}


def test_nothing_chosen_anywhere_still_says_nothing_chosen(lib):
    """The B03 fix must not make the row optimistic: with no default and no
    event, `no model chosen` is the true answer and the handover agrees."""
    assert lib["state_none"] == {"kind": "none", "models": []}
    assert lib["state_no_runs"] == {"kind": "none", "models": []}
    # a project that has not loaded yet is not a project with no model
    assert lib["state_empty"] == {"kind": "none", "models": []}


def test_the_listing_is_fetched_once_for_every_surface_that_asks(lib):
    """Three surfaces consult it — the Panel tab, the canvas aside and the event
    popover. A second copy of the cache would let them disagree about which
    models exist."""
    assert lib["fetches"] == 1
