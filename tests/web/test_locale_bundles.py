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
    "no_feasible_item",
    "substitute_needs_approval",
    "height_not_supported",
    "panel_length_unresolved",
    "clear_gap_exceeded",
    "rail_separation_insufficient",
    "pattern_residual_large",
    "span_not_exact",
    "exact_span_over_max",
    # A model asked for a CAP nothing covers. The same code appears in
    # REFUSAL_CODES below, and the two are not a duplication: for a post it is a
    # refusal (without one there is no fence), for a cap it is a note on an
    # answer (a post without a cap is still a fence). Two severities, two
    # sentences, one fact.
    "no_item_covers_part_spec",
]
CRITIQUE_CODES = ["narrow_span"]

# Codes rendered as `error.<code>` rather than `warning.<code>`: a refusal, not a
# note on an answer. `core.errors.ReadRefused` (a stored run that cannot be read)
# and the `GenerationFailure` variants that carry a code — the failures a USER
# can cause from the editors, which must not fall through to the client's
# generic "the action failed (422)".
REFUSAL_CODES = [
    "run_predates_fence_model",
    "fence_model_unknown_sku",
    "fence_model_invalid",
    "fence_model_not_found",
    "fence_model_reserved",
    "fence_model_not_a_draft",
    # 409s the read paths raise when a stored run can no longer be served as it
    # was generated. Refusals like the rest, and they were never listed.
    "catalog_changed",
    # the shape of a Product moved, which is a different fact from a price
    # moving and needs a different sentence — a reader told "the catalog
    # changed" goes looking for an edit that never happened
    "catalog_schema_changed",
    "topology_changed",
    "unresolved_supply",
    # `core.errors.RequestRefused`: the panel preview was asked for a product
    # that slot cannot be supplied by (or for a slot the panel has not got). A
    # refusal the user causes by clicking, so it must say which slot and which
    # product rather than "the action failed (422)".
    "sku_not_eligible",
    # A model's post specification that no product satisfies. `post_spec_conflict`
    # is two models disagreeing about the post between them;
    # `post_routing_mismatch` is ROUTING alone excluding every candidate, which
    # is a fence that cannot be assembled rather than a worse buy; and
    # `no_item_covers_part_spec` is the generic case. A single merged code would
    # leave "no post found" a mystery, which is what they exist to avoid.
    "post_spec_conflict",
    "post_routing_mismatch",
    "no_item_covers_part_spec",
]


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
    """If a new code appears in the backend, this test forces the author to put it
    in exactly one of the three lists above — and each list's own test then forces
    the matching entries into BOTH bundles.

    One scan over every emitting file rather than one per kind: `code="x"` reads
    the same whether it is a StrategyWarning, a ReadRefused or a GenerationFailure,
    and a regex that tried to tell them apart would be the thing that quietly
    stopped matching."""
    import re

    src = Path(__file__).resolve().parents[2] / "src" / "fenceai"
    scanned = [
        src / "strategy" / "generator.py",
        src / "ai" / "stub.py",
        src / "fulfillment" / "supply.py",
        src / "fencemodel" / "resolve.py",
        src / "demand" / "derive.py",
        # the ROUTES emit codes too, in HTTP detail bodies, and they were
        # invisible to this guard twice over: the file was not scanned, and a
        # route writes `"code": "x"` rather than `code="x"`. Both forms now.
        src / "api" / "app.py",
    ]
    emitted: set[str] = set()
    for path in scanned:
        text = path.read_text()
        emitted |= set(re.findall(r'code="([a-z_]+)"', text))
        emitted |= set(re.findall(r'"code":\s*"([a-z_]+)"', text))
    emitted.discard("generic")  # CritiqueNote default, never emitted explicitly
    known = set(WARNING_CODES) | set(CRITIQUE_CODES) | set(REFUSAL_CODES)
    assert emitted == known, {"unlisted": sorted(emitted - known),
                              "listed_but_gone": sorted(known - emitted)}


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
    """`{u}` and `{c}` are supplied by units.tu()/unitParams() — a plain t("key")
    would leave the placeholder in the UI.

    `{c}` (the currency symbol) rides the same mechanism as `{u}` for the same
    reason: the symbol lives in exactly one bundle key, so a column header that
    wants it has to ask the layer that knows it."""
    import re

    js_dir = STATIC / "js"
    sources = {p.name: p.read_text() for p in [*js_dir.glob("*.js"), STATIC / "app.js"]}
    en, _ = _bundles()
    # EVERY call whose first argument is a {u}- or {c}-bearing key must go through
    # tu() or hand the param in explicitly — `t("key", {width_mm: 5})` (params, but
    # no unit) is the mistake that actually happens.
    offenders = []
    for placeholder in ("u", "c"):
        keys = [k for k, v in en.items() if "{%s}" % placeholder in str(v)]
        supplied = re.compile(r"\s*\{[^}]*\b%s\s*:" % placeholder)
        for key in keys:
            call = re.compile(
                r'([a-zA-Z_]*)\(\s*["\'`]' + re.escape(key) + r'["\'`]\s*(,|\))')
            for fname, src in sources.items():
                for m in call.finditer(src):
                    fn = m.group(1)
                    if fn == "tu":
                        continue
                    if fn != "t":
                        continue  # some other function that happens to take the key
                    tail = src[m.end():m.end() + 200]
                    if m.group(2) == "," and supplied.match(tail):
                        continue  # t("key", { u: ... }) supplies the label itself
                    offenders.append((fname, key, placeholder))
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
    unitParams().

    It lives in `warnings.js` because three panels render the same shape (the
    editor's strategy warnings, the BOM tab's supply warnings, the structure
    sheet's); a copy per tab is how one of them would quietly stop converting."""
    src = (STATIC / "js" / "warnings.js").read_text()
    fn = src[src.index("export function localizedByCode"):
             src.index("function labelledParams")]
    assert "unitParams(" in fn, "warning params must be unit-converted and carry {u}"


def test_only_one_module_localizes_a_warning_by_code():
    """A second copy of the code->sentence mapping is how the BOM tab and the
    editor come to disagree about what `no_feasible_item` says."""
    js_dir = STATIC / "js"
    definers = [
        p.name for p in [*js_dir.glob("*.js"), STATIC / "app.js"]
        if "function localizedByCode" in p.read_text()
    ]
    assert definers == ["warnings.js"], definers


def test_one_module_owns_each_shared_renderer():
    """Same reason as the warning localizer above, for the two surfaces W4
    added a third caller to.

    `renderImpactReport` answers "this change would affect N of your projects"
    for the review queue, the knowledge form AND the model editor's publish
    gate; `skuSelect` is the single place that knows a product is shown as
    "SKU — localized name". A copy of either in the new editor is how it comes
    to disagree with the knowledge tab — about what a failed hypothetical
    generation says, or about whether product names localize at all."""
    import re

    js_dir = STATIC / "js"
    sources = {p.name: p.read_text() for p in [*js_dir.glob("*.js"), STATIC / "app.js"]}
    for fn, owner in [("renderImpactReport", "impact.js"),
                      ("skuSelect", "builder-ui.js"),
                      ("loadCatalogProducts", "builder-ui.js"),
                      ("updateAdvancedUi", "builder-ui.js"),
                      # money was the counter-example that made this rule worth
                      # widening: `€${(cents/100).toFixed(2)}` was copied into
                      # five modules, and moving the whole app to ₪ meant finding
                      # all five plus two bundle strings plus three smoke checks.
                      ("money", "units.js"),
                      ("moneyDelta", "units.js"),
                      ("currencySymbol", "units.js")]:
        # word-bounded: `function money` also matches `function moneyDelta`, so
        # the single-owner rule for the shorter name was partly aliased by the
        # longer one — a second `money` in another module would have passed as
        # long as that module also defined a `moneyDelta`
        pattern = re.compile(r"\b(?:function|const)\s+" + re.escape(fn) + r"\b")
        definers = [name for name, src in sources.items() if pattern.search(src)]
        assert definers == [owner], (fn, definers)
    # One definition is only half of it: a module that stops IMPORTING the
    # shared renderer and inlines its own innerHTML defines nothing new and
    # diverges anyway, which is the failure the docstring is actually about.
    #
    # The Models tab is two modules now — the editor owns the session and the
    # publish gate, the inspector owns the controls over one selected element —
    # so each is checked for the renderer it is the caller OF. Asserting both
    # against the editor alone would pass with the inspector growing its own
    # product picker, which is precisely the divergence being guarded.
    editor = sources["model-editor.js"]
    inspector = sources["panel-inspector.js"]
    assert 'from "./impact.js"' in editor and "renderImpactReport" in editor
    assert 'from "./builder-ui.js"' in inspector and "skuSelect" in inspector
    assert "skuSelect" not in editor, (
        "the product picker belongs to the inspector; a second caller in the "
        "editor is a second answer to how a product is named")


def test_every_value_the_model_vocabulary_offers_has_a_word_in_both_bundles():
    """The editor renders its closed vocabularies through COMPUTED keys —
    `t("model.basis." + b)` and a dozen siblings — which key-parity scanning
    cannot see, because neither bundle contains the literal.

    This is the hole the other tests open: `test_the_editor_and_the_schema_agree
    _on_the_closed_vocabularies` forces panel-model.js's arrays to track `model.py`,
    so adding a `LengthRule` makes the editor offer it automatically — and
    without this, that ships a green suite with a raw `model.length_rule.foo`
    on screen in both languages."""
    import re

    en, he = _bundles()
    src = (STATIC / "js" / "panel-model.js").read_text()

    def values(name):
        body = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
        assert body, name
        return re.findall(r'"([a-z_]+)"', body.group(1))

    expected = set()
    for const, prefix in [("ROLES", "role."), ("LENGTH_RULES", "model.length_rule."),
                          ("PLACEMENT_KINDS", "model.placement."),
                          ("JUSTIFICATIONS", "model.justification."),
                          ("EXCESS", "model.excess."), ("BASES", "model.basis."),
                          ("APPROVALS", "model.approval."), ("GRADES", "model.grade."),
                          ("AXIS_KINDS", "model.axis_kind."),
                          ("COUNT_PARAMS", "action.param.")]:
        expected |= {prefix + v for v in values(const)}
    # the keys built from a literal rather than from a const array
    expected |= {"model.orientation.horizontal", "model.orientation.vertical",
                 "model.length_rule.none", "model.option_axis.none",
                 "model.count_param_none", "model.ref_none",
                 "model.spec.default", "model.spec.variant"}
    expected |= {f"status.{s}" for s in ("draft", "active", "retired")}
    expected |= {f"model.invalid.{c}"
                 for c in ("fence_model_invalid", "fence_model_unknown_sku")}

    missing = sorted(f"{lang}:{k}" for lang, table in (("en", en), ("he", he))
                     for k in expected if k not in table)
    assert not missing, missing


# The vocabularies the canvas renders as a SENTENCE rather than as a label:
# "Screws at: where every board meets every rail", not "basis: per_member_crossing".
# The VALUES stay a typed, code-defined enum — fulfillment and resolution read
# them, so adding one is a code change with tests. Only the PHRASING is data,
# which is what makes it correctable without a release.
SENTENCE_VOCABULARIES = [
    ("BASES", "model.basis."),
    ("PLACEMENT_KINDS", "model.placement."),
    ("JUSTIFICATIONS", "model.justification."),
    ("EXCESS", "model.excess."),
    ("LENGTH_RULES", "model.length_rule."),
]

# ... and the two the inspector renders as sentences from LITERALS rather than
# from a const array, which the scan above cannot see. Deleting these from both
# bundles passes key parity and every other test, and the select then renders a
# raw `model.orientation.sentence.vertical` in both languages.
LITERAL_SENTENCE_KEYS = [
    "model.orientation.sentence.horizontal", "model.orientation.sentence.vertical",
    "model.approval.sentence.auto", "model.approval.sentence.suggest_only",
]


def test_every_sentence_vocabulary_value_has_both_a_label_and_a_phrasing():
    """The canvas reads `model.basis.sentence.<v>`; the compact places still read
    `model.basis.<v>`. A value carrying only one of the two renders either a raw
    key inside a Hebrew sentence or a sentence where a chip should be — and
    neither is visible to key-parity scanning, because both keys are computed."""
    import re

    en, he = _bundles()
    src = (STATIC / "js" / "panel-model.js").read_text()
    missing = []
    for const, prefix in SENTENCE_VOCABULARIES:
        body = re.search(rf"const {const} = \[(.*?)\];", src, re.S)
        assert body, const
        values = re.findall(r'"([a-z_]+)"', body.group(1))
        assert values, const
        for value in values:
            for key in (f"{prefix}{value}", f"{prefix}sentence.{value}"):
                for lang, table in (("en", en), ("he", he)):
                    if key not in table:
                        missing.append(f"{lang}:{key}")
    for key in LITERAL_SENTENCE_KEYS:
        for lang, table in (("en", en), ("he", he)):
            if key not in table:
                missing.append(f"{lang}:{key}")
    assert not missing, missing


def test_the_inspector_renders_its_vocabularies_as_sentences():
    """The keys existing is half of it: nothing else notices if the inspector
    stops ASKING for them.

    `sentenceChoice` is the one place that turns a value into its phrasing, and
    a version of it that fell back to the label key would leave every bundle
    entry above unreachable — the whole "a closed enum reads as a sentence"
    feature gone, with a green suite and a UI that still works."""
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    body = src[src.index("function sentenceChoice"):]
    body = body[:body.index("\n}\n")]
    assert "sentence." in body, (
        "sentenceChoice must render the phrasing key, not the label key")
    # ... and every vocabulary that HAS a phrasing is rendered with one. Two
    # spellings are legitimate: handed to `sentenceChoice` as a prefix, or built
    # inline where the control does more than set a field (the placement select
    # rebuilds the whole placement object on change).
    for const, prefix in SENTENCE_VOCABULARIES:
        assert f'"{prefix}"' in src or f"{prefix}sentence." in src, (const, prefix)


def test_every_material_and_finish_in_the_catalog_has_a_word_in_both_bundles():
    """The material drawer renders `attrs.material` / `attrs.finish` through
    COMPUTED keys (`t("material." + value)`), which key-parity scanning cannot
    see — the same hole `test_every_value_the_model_editor_offers…` covers for
    the editor's arrays.

    The vocabulary is derived from the CATALOG rather than listed here, because
    material is catalog DATA: nothing in code enumerates it, so the only way to
    keep the words honest is to ask the products what they are made of. Adding a
    product with a new material now fails this suite instead of shipping an
    English word into a Hebrew UI.
    """
    from fenceai.catalog.demo import demo_catalog

    en, he = _bundles()
    expected = set()
    for product in demo_catalog().products.values():
        for attr, prefix in (("material", "material."), ("finish", "finish.")):
            value = product.attrs.get(attr)
            if value is not None:
                expected.add(prefix + str(value))
    assert expected, "the demo catalog declares no materials at all"

    missing = sorted(f"{lang}:{k}" for lang, table in (("en", en), ("he", he))
                     for k in expected if k not in table)
    assert not missing, missing


def test_the_supply_gap_is_rendered_on_both_the_bom_and_structure_tabs():
    """`Bom.warnings`, `StructureReport.warnings` and `StructureReport.unresolved`
    were populated by the API and read by NO JS, so a bay with a part nothing can
    supply produced a BOM and a setting-out sheet that were silently short a line
    — and `warning.no_eligible_item` was an unreachable string in both bundles."""
    for name in ("tabs.js", "structure.js"):
        src = (STATIC / "js" / name).read_text()
        assert "supplyProblemsHtml(" in src, name


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


# core.errors.ReadRefused / GenerationFailure: a run that cannot be read, or a
# generation that refused, as code + params. These surfaced as raw English text in
# a Hebrew-first UI (and, on the structure tab, as "no structure yet" — which is
# false: there IS structure, it just cannot be read without regenerating). The
# list itself is kept current by test_backend_code_list_is_current above.
def test_refusal_codes_have_locale_entries():
    en, he = _bundles()
    for code in REFUSAL_CODES:
        assert f"error.{code}" in en and f"error.{code}" in he, code


def test_a_coded_refusal_is_not_swallowed_by_the_generic_failure_sentence():
    """`api.js` shows one alert for every failed POST/PUT. A 422 that names
    itself must render its own sentence, or a user who mistyped a SKU is told
    only "the action failed (422)" — after losing the strategy."""
    src = (STATIC / "js" / "api.js").read_text()
    fn = src[src.index("function errorAlertText"):]
    assert "`error.${detail.code}`" in fn


# The role vocabulary (demand/derive.py: RequirementLine.role) is rendered INSIDE
# a Hebrew sentence by the supply warnings, so a raw "rail" there is untranslated
# English. `enum.*` is the wrong namespace for it: `concrete` is a base surface
# AND a role, and the slab is not the bag.
ROLE_VOCABULARY = ["post", "cap", "concrete", "rail", "screw", "infill", "spacer",
                   "gate_kit"]


def test_every_role_has_a_word_in_both_bundles():
    en, he = _bundles()
    missing = sorted(f"{lang}:{r}" for lang, table in (("en", en), ("he", he))
                     for r in ROLE_VOCABULARY if f"role.{r}" not in table)
    assert not missing, missing


def test_every_role_a_real_generation_emits_is_in_that_vocabulary():
    """The static list above cannot go stale silently: whatever the generator
    plus `derive_requirements` actually produce must be in it."""
    from fenceai.catalog.demo import demo_catalog
    from fenceai.demand.derive import derive_requirements
    from fenceai.knowledge.demo import demo_knowledge
    from fenceai.strategy.generator import generate
    from fenceai.topology.model import GatePayload
    from tests.conftest import add_point_event, straight_topology

    topo = straight_topology(20000)
    add_point_event(topo, "run1", "ev1", 2000,
                    GatePayload(width_mm=1000, kit_sku="GATE-KIT-1000"))
    catalog = demo_catalog()
    result = generate(topo, demo_knowledge(), catalog)
    roles = {r.role for r in derive_requirements(result.strategy, catalog,
                                                 result.run.demand_skus)}
    assert roles and roles <= set(ROLE_VOCABULARY), sorted(roles - set(ROLE_VOCABULARY))


def test_no_literal_currency_symbol_in_a_bundle_value():
    """The mirror of the unit rule above, for the same reason.

    A price is rendered by `units.money()`, which reads its symbol from
    `units.currency` — so a string that spells the symbol itself is a second
    place the currency lives, and the ₪ migration found five of those. It also
    catches the stale one: a bundle left saying € after the code moved on."""
    for name, table in zip(("en", "he"), _bundles()):
        offenders = [
            k for k, v in table.items()
            if k != "units.currency" and any(sym in str(v) for sym in "₪€$£¥")
        ]
        assert not offenders, (name, offenders)


def test_the_currency_symbol_is_declared_in_both_bundles():
    for name, table in zip(("en", "he"), _bundles()):
        assert table.get("units.currency", "").strip(), name


def test_every_joint_kind_and_consumption_model_has_a_word_in_both_bundles():
    """Two more COMPUTED key families, and the reason the material/finish test
    exists one screen up: `assembly.js` builds `joint.kind.${kind}` and
    `part-drawer.js` builds `consumption.${kind}` by concatenation, and `t()`
    returns the key itself when the bundle has no entry. A sixth JointKind or a
    new consumption model would render "joint.kind.rebate" into a Hebrew UI —
    silently, because nothing else reads those strings."""
    from typing import get_args

    from fenceai.catalog.model import Consumption
    from fenceai.fencemodel.model import JointKind

    en, he = _bundles()
    for value in get_args(JointKind):
        for name, table in (("en", en), ("he", he)):
            assert f"joint.kind.{value}" in table, (name, value)
    # the consumption union's discriminator values, straight off the models
    kinds = {get_args(member.model_fields["kind"].annotation)[0]
             for member in get_args(get_args(Consumption)[0])}
    assert kinds, "the consumption union must be readable, or this test is vacuous"
    for value in kinds:
        for name, table in (("en", en), ("he", he)):
            assert f"consumption.{value}" in table, (name, value)
