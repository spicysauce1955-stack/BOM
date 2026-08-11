"""Locale-bundle contract tests (test-review finding 2).

The frontend localizes warnings/critiques by `code` via `t("warning."+code, params)`.
That contract is pure JSON — testable without a browser: both bundles must have the
same key set, and every code the backend can emit must have an entry in both.
"""

from __future__ import annotations

import json
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

# every StrategyWarning.code the generator emits + every CritiqueNote.code
WARNING_CODES = [
    "orphaned_override",
    "sliver_span",
    "unknown_product",
    "knowledge_conflict",
    "node_surface_disagreement",
    "excessive_step",
    "excessive_gap",
    "max_height_exceeded",
    "gate_on_slope",
    "insufficient_post_length",
    "tilted_stepped",
]
CRITIQUE_CODES = ["narrow_span"]


def _bundles():
    en = json.loads((STATIC / "i18n" / "en.json").read_text())
    he = json.loads((STATIC / "i18n" / "he.json").read_text())
    return en, he


def test_bundle_key_parity():
    en, he = _bundles()
    assert set(en) == set(he), {
        "only_en": sorted(set(en) - set(he)),
        "only_he": sorted(set(he) - set(en)),
    }


def test_every_backend_code_has_locale_entries():
    en, he = _bundles()
    for code in WARNING_CODES:
        assert f"warning.{code}" in en and f"warning.{code}" in he, code
    for code in CRITIQUE_CODES:
        assert f"critique.{code}" in en and f"critique.{code}" in he, code


def test_backend_code_list_is_current():
    """If a new warning/critique code appears in the backend, this test forces the
    author to add locale entries (and update the lists above)."""
    import re

    generator = (
        Path(__file__).resolve().parents[2] / "src" / "fenceai" / "strategy" / "generator.py"
    ).read_text()
    stub = (
        Path(__file__).resolve().parents[2] / "src" / "fenceai" / "ai" / "stub.py"
    ).read_text()
    emitted = set(re.findall(r'code="([a-z_]+)"', generator))
    emitted |= set(re.findall(r'code="([a-z_]+)"', stub))
    emitted.discard("generic")  # CritiqueNote default, never emitted explicitly
    assert emitted == set(WARNING_CODES) | set(CRITIQUE_CODES), emitted


UNIT_LITERAL_ALLOWED = {
    "units.mm", "units.cm", "units.toggle_title",  # the unit vocabulary itself
    "hint.draw",  # documents the typed-length suffixes ("250cm"), not a rendered value
}


def test_lengths_carry_the_unit_placeholder_not_a_literal():
    """Display units are user-selectable (mm | cm): a string that hardcodes "mm"
    would keep saying mm after the user switches. Lengths render "{...} {u}"."""
    import re

    pattern = re.compile(r'(?<![a-z_])mm\b|(?<![a-z_])cm\b|מ"מ|ס"מ')
    for name, table in zip(("en", "he"), _bundles()):
        offenders = [
            k for k, v in table.items()
            if k not in UNIT_LITERAL_ALLOWED and pattern.search(str(v))
        ]
        assert not offenders, (name, offenders)


def test_unit_bearing_keys_are_rendered_with_tu():
    """`{u}` is supplied by units.tu()/unitParams() — a plain t("key") would leave
    the placeholder in the UI."""
    import re

    js_dir = STATIC / "js"
    sources = {p.name: p.read_text() for p in [*js_dir.glob("*.js"), STATIC / "app.js"]}
    en, _ = _bundles()
    unit_keys = [k for k, v in en.items() if "{u}" in str(v)]
    # t("key") with no params; t("key", {u: ...}) supplies the label explicitly
    offenders = [
        (fname, key) for key in unit_keys for fname, src in sources.items()
        if re.search(r'(?<![a-z])t\(["`]' + re.escape(key) + r'["`]\s*\)', src)
    ]
    assert not offenders, offenders


def test_no_empty_translations():
    en, he = _bundles()
    for table in (en, he):
        empties = [k for k, v in table.items() if not str(v).strip()]
        assert not empties, empties
