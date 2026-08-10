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


def test_no_empty_translations():
    en, he = _bundles()
    for table in (en, he):
        empties = [k for k, v in table.items() if not str(v).strip()]
        assert not empties, empties
