"""The starter panels behind "New model" (static/js/panel-templates.js).

A card that lands a draft the publish gate then refuses is worse than no card:
the author is invited into a document they cannot finish, for a reason that is
not on the screen they were given. So every starter is built in node exactly as
the button builds it, and then judged by the loader, by `validate_model` — the
publish gate itself — and by the preview, which has to price it with nothing
unsupplied.

That last one is why the spec's five product families are not these five.
tongue-and-groove and dogear are board PROFILES; this catalog supplies neither,
and a starter naming a SKU that does not exist previews as a gap and is refused
at the gate. What the five ARE is five structures the mechanism can express,
over products that exist — which is the thing a starter has to be.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.catalog.demo import demo_catalog
from fenceai.fencemodel.model import FenceModel, validate_model
from fenceai.fencemodel.preview import PreviewRequest, preview_panel

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { TEMPLATES } from "./js/panel-templates.js";

console.log(JSON.stringify({
  keys: TEMPLATES.map((tpl) => tpl.key),
  templates: Object.fromEntries(
    TEMPLATES.map((tpl) => [tpl.key, tpl.build(`M-${tpl.key.toUpperCase()}`)])),
  // the id the card would claim, against a library that already holds it
  free_ids: TEMPLATES.map((tpl) => tpl.id_base),
}));
"""


@pytest.fixture(scope="module")
def out():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _preview(doc):
    return preview_panel(FenceModel.model_validate(doc),
                         PreviewRequest(height_mm=1800, width_mm=2500),
                         demo_catalog())


def test_there_are_five_starters(out):
    assert len(out["keys"]) == 5
    assert len(set(out["keys"])) == 5


def test_every_starter_is_a_model_the_publish_gate_accepts(out):
    """`validate_model` IS the gate. A green here is the claim that a panel
    started from a card can be published without the author fixing anything
    they were never shown."""
    for key, doc in out["templates"].items():
        model = FenceModel.model_validate(doc)
        assert validate_model(model, demo_catalog()) == [], key


def test_every_starter_prices_a_panel_with_nothing_missing(out):
    """A structure nothing in the catalog supplies previews as a gap. A starter
    has to arrive already answerable, or the first thing it teaches is that the
    tool does not work."""
    for key, doc in out["templates"].items():
        preview = _preview(doc)
        assert preview.unsupplied == [], (key, preview.unsupplied)
        assert preview.total_cents > 0, key


def test_every_starter_draws_something(out):
    """The gallery card IS the drawing, and the canvas opens on it. A starter
    with no members is a card showing an empty box."""
    for key, doc in out["templates"].items():
        assert _preview(doc).elevation.members, key


def test_the_five_starters_are_five_different_panels(out):
    """Cards producing the same document are one card wearing five hats."""
    drawn = {key: json.dumps(doc["default_spec"], sort_keys=True)
             for key, doc in out["templates"].items()}
    assert len(set(drawn.values())) == len(drawn)


def test_the_overlapping_starter_really_overlaps(out):
    """Board-on-board is the case the negative gap exists for, and a starter
    that quietly authored a positive one would leave the whole product family
    undemonstrated — which is how the field came to need a hint in the first
    place."""
    pattern = out["templates"]["board_on_board"]["default_spec"]["infill"]["pattern"]
    assert any(m["gap_after_mm"] < 0 for m in pattern), pattern
    # ... and it still advances, which is the bound `validate_model` holds
    assert all(m["width_mm"] + m["gap_after_mm"] > 0 for m in pattern), pattern


def test_the_horizontal_starter_lays_its_boards_across_the_bay(out):
    """The other axis, so the canvas's own handles are exercised both ways."""
    infill = out["templates"]["horizontal"]["default_spec"]["infill"]
    assert infill["orientation"] == "horizontal"
    members = _preview(out["templates"]["horizontal"]).elevation.members
    assert all(m.w_mm > m.h_mm for m in members if m.kind == "infill"), members


def test_a_starter_names_itself_in_both_languages(out):
    """The name travels to a server that has no locale bundle, so it is data on
    the model rather than a key — and a starter named in one language is a model
    that reads as its own id in the other."""
    for key, doc in out["templates"].items():
        assert set(doc["name_i18n"]) == {"en", "he"}, key
        assert all(v.strip() for v in doc["name_i18n"].values()), key


def test_every_starter_card_has_a_name_and_a_line_in_both_bundles(out):
    """The CARD's own words, which are UI and therefore locale keys — unlike the
    model name above, which is data."""
    from tests.web.test_locale_bundles import _bundles

    en, he = _bundles()
    missing = [f"{lang}:{k}"
               for key in [*out["keys"], "blank"]
               for k in (f"model.template.{key}.name", f"model.template.{key}.desc")
               for lang, table in (("en", en), ("he", he)) if k not in table]
    assert not missing, missing


def test_every_starter_id_is_a_plain_identifier(out):
    """It becomes a save key and a URL segment; `freeId` then appends -2 to it."""
    import re

    for base in out["free_ids"]:
        assert re.fullmatch(r"M-[A-Z0-9-]+", base), base
