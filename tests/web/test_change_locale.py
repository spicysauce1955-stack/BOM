"""Every change the history can record has a sentence, in both languages.

A change is platform text — `code + params` — so the reader's language is the
screen's business (fenceai/project/changes.py). A code without a sentence would
render as its raw key, which is the failure this test makes impossible to ship.
The two bundles' key sets are already held equal by
`tests/web/test_locale_bundles.py`; this asserts the change keys exist at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fenceai.project.changes import AREAS, CHANGE_CODES, UNKNOWN_AREA, _STATED_FIELDS
from fenceai.project.model import SALE_READ, WARNINGS_REVIEWED

I18N = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static" / "i18n"

NEEDED = sorted(
    {f"change.{code}" for code in CHANGE_CODES}
    | {f"change.area.{area}" for area in (*AREAS, UNKNOWN_AREA)}
    | {"change.gone", "change.blank", "change.nobody", "change.system"}
    | {f"change.stated.{field}" for field in _STATED_FIELDS}
    | {f"change.ack.{kind}" for kind in (SALE_READ, WARNINGS_REVIEWED)}
)


@pytest.mark.parametrize("lang", ["en", "he"])
def test_every_change_has_a_sentence(lang):
    bundle = json.loads((I18N / f"{lang}.json").read_text())
    missing = [k for k in NEEDED if not bundle.get(k)]
    assert not missing, f"{lang}.json is missing {missing}"


@pytest.mark.parametrize("lang", ["en", "he"])
def test_a_length_in_a_change_sentence_carries_its_unit(lang):
    """Lengths render in the reader's unit, so a `…_mm` placeholder needs `{u}`."""
    bundle = json.loads((I18N / f"{lang}.json").read_text())
    bare = [k for k in NEEDED if "_mm}" in bundle[k] and "{u}" not in bundle[k]]
    assert not bare, bare
