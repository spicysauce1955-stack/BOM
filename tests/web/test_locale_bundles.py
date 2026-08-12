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
    "gate_kit_width_mismatch",
    "no_gate_kit",
    "gate_past_run_end",
    "no_eligible_item",
    "substitute_needs_approval",
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

    src = Path(__file__).resolve().parents[2] / "src" / "fenceai"
    scanned = [
        src / "strategy" / "generator.py",
        src / "ai" / "stub.py",
        src / "fulfillment" / "supply.py",
        src / "fencemodel" / "resolve.py",
    ]
    emitted: set[str] = set()
    for path in scanned:
        emitted |= set(re.findall(r'code="([a-z_]+)"', path.read_text()))
    emitted.discard("generic")  # CritiqueNote default, never emitted explicitly
    assert emitted == set(WARNING_CODES) | set(CRITIQUE_CODES), emitted


UNIT_LITERAL_ALLOWED = {
    "units.mm", "units.cm", "units.toggle_title",  # the unit vocabulary itself
    # these two document the typed-length suffixes ("250cm") — not rendered values
    "hint.draw", "hint.draw_cm",
}


def test_lengths_carry_the_unit_placeholder_not_a_literal():
    """Display units are user-selectable (mm | cm): a string that hardcodes "mm"
    would keep saying mm after the user switches. Lengths render "{...} {u}"."""
    import re

    # Hebrew may spell the unit with the proper gershayim (U+05F4) or an ASCII quote
    pattern = re.compile(r'(?<![a-z_])[mc]m\b|[מס]["\u05f4]מ', re.IGNORECASE)
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
    # EVERY call whose first argument is a {u}-bearing key must go through tu()
    # or hand `u` in explicitly — `t("key", {width_mm: 5})` (params, but no unit)
    # is the mistake that actually happens.
    offenders = []
    for key in unit_keys:
        call = re.compile(r'([a-zA-Z_]*)\(\s*["\'`]' + re.escape(key) + r'["\'`]\s*(,|\))')
        for fname, src in sources.items():
            for m in call.finditer(src):
                fn = m.group(1)
                if fn == "tu":
                    continue
                if fn != "t":
                    continue      # some other function that happens to take the key
                tail = src[m.end():m.end() + 200]
                if m.group(2) == "," and re.match(r"\s*\{[^}]*\bu\s*:", tail):
                    continue      # t("key", { u: ... }) supplies the label itself
                offenders.append((fname, key))
    assert not offenders, offenders


def test_unit_label_keys_exist_and_are_non_empty():
    """`units.mm`/`units.cm` ARE the unit words — parity alone would not catch
    both bundles losing them together."""
    en, he = _bundles()
    for key in ("units.mm", "units.cm", "units.button", "units.toggle_title"):
        assert en.get(key, "").strip() and he.get(key, "").strip(), key


def test_warning_renderer_converts_its_dynamic_key_params():
    """Warnings/critiques are localized by a COMPUTED key (`warning.${code}`), so
    the call-site guards above are blind to them — the one thing that keeps their
    `{u}` and their millimetres honest is localizedByCode passing params through
    unitParams()."""
    src = (STATIC / "js" / "editor.js").read_text()
    fn = src[src.index("function localizedByCode"):src.index("function renderWarnings")]
    assert "unitParams(" in fn, "warning params must be unit-converted and carry {u}"


def test_no_empty_translations():
    en, he = _bundles()
    for table in (en, he):
        empties = [k for k, v in table.items() if not str(v).strip()]
        assert not empties, empties


def test_every_enum_value_has_a_word_in_both_bundles():
    """The UI renders enum values as words (post kind, mounting, base surface,
    vertical mode, post orientation) via units.enumWord -> t("enum.<value>").
    A missing key silently falls back to the raw English enum inside Hebrew."""
    from typing import get_args

    from fenceai.strategy.model import Post, Span
    from fenceai.topology.model import BasePayload, PostTiltPayload, TopLinePayload

    values = set()
    for model, field in [(Post, "kind"), (Post, "mounting"), (Span, "vertical"),
                         (BasePayload, "surface"), (PostTiltPayload, "mode"),
                         (TopLinePayload, "mode")]:
        values |= set(get_args(model.model_fields[field].annotation))
    en, he = _bundles()
    missing = sorted(
        f"{lang}:{v}" for lang, table in (("en", en), ("he", he)) for v in values
        if f"enum.{v}" not in table
    )
    assert not missing, missing


def test_frontend_and_backend_enum_lexicons_agree():
    """decisions/explain.py renders Hebrew decision prose; the bundle renders
    Hebrew warnings and labels. The same value must read the same in both."""
    from fenceai.decisions.explain import _ENUM_WORDS

    _, he = _bundles()
    mismatched = {
        v: (word, he[f"enum.{v}"])
        for v, word in _ENUM_WORDS["he"].items()
        if f"enum.{v}" in he and he[f"enum.{v}"] != word
    }
    assert not mismatched, mismatched


# ---- run-2 persona lab §4: three more ways untranslated text reached the user ----

def test_no_double_escaped_unicode_in_bundles():
    r"""A JSON value holding `“` (escaped backslash) renders the six literal
    characters, not the quote mark: he.json showed “test” as “test”."""
    import re

    for name, table in zip(("en", "he"), _bundles()):
        offenders = [k for k, v in table.items() if re.search(r"\\u[0-9a-fA-F]{4}", str(v))]
        assert not offenders, (name, offenders)


def _call_argument(src: str, open_paren: int) -> str:
    """The text between `(` at open_paren and its matching `)`."""
    depth = 0
    for i in range(open_paren, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return src[open_paren + 1:i]
    return src[open_paren + 1:]


def test_every_alert_and_confirm_is_localized():
    """A literal string in an alert()/confirm() is untranslated English in a
    Hebrew-first RTL app. Every string in one must be a t()/tu() lookup key."""
    import re

    js_dir = STATIC / "js"
    key_call = re.compile(r"\b(t|tu)\(\s*[\"'`][^\"'`]*[\"'`]")
    offenders = []
    for path in [*js_dir.glob("*.js"), STATIC / "app.js"]:
        src = path.read_text()
        for m in re.finditer(r"\b(?:alert|confirm)\(", src):
            arg = _call_argument(src, m.end() - 1)
            # drop the localized lookups; any string literal left is raw text
            stripped = key_call.sub("", arg)
            if re.search(r"[\"'`]", stripped):
                offenders.append((path.name, arg[:70]))
    assert not offenders, offenders


# learning/impact.py reports a failed hypothetical generation as code + params
IMPACT_FAILURE_CODES = ["generation_failed", "generation_failed_refs"]


def test_impact_failure_codes_have_locale_entries():
    en, he = _bundles()
    for code in IMPACT_FAILURE_CODES:
        assert f"impact.failure.{code}" in en and f"impact.failure.{code}" in he, code


def test_impact_failure_code_list_is_current():
    import re

    src = (
        Path(__file__).resolve().parents[2] / "src" / "fenceai" / "learning" / "impact.py"
    ).read_text()
    emitted = set(re.findall(r'code="([a-z_]+)"', src))
    assert emitted == set(IMPACT_FAILURE_CODES), emitted


# core.errors.ReadRefused: a stored run that cannot be read, as code + params.
# These surfaced as raw English ValueError text in a Hebrew-first UI (and, on the
# structure tab, as "no structure yet" — which is false: there IS structure, it
# just cannot be read without regenerating).
READ_REFUSAL_CODES = ["run_predates_fence_model"]


def test_read_refusal_codes_have_locale_entries():
    en, he = _bundles()
    for code in READ_REFUSAL_CODES:
        assert f"error.{code}" in en and f"error.{code}" in he, code


def test_read_refusal_code_list_is_current():
    import re

    src = Path(__file__).resolve().parents[2] / "src" / "fenceai"
    emitted: set[str] = set()
    for path in [src / "demand" / "derive.py"]:
        emitted |= set(re.findall(r'code="([a-z_]+)"', path.read_text()))
    assert emitted == set(READ_REFUSAL_CODES), emitted
