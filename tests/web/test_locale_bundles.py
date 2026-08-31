"""Locale-bundle contract tests (test-review finding 2).

The frontend localizes warnings/critiques by `code` via `t("warning."+code, params)`.
That contract is pure JSON — testable without a browser: both bundles must have the
same key set, and every code the backend can emit must have an entry in both.

**The registry is SPLIT, and this file guards both halves** (build-order item 8,
contract obligation 10). The rule above applies to PLATFORM codes — engine
warnings, gap codes, refusals: we wrote the code, so we owe the sentence in both
languages. A warning QUOTED from a document is the other half: `text_raw` +
`lang`, carried verbatim, exempt by design and never key-checked. Zero of the
corpus's 81,794 elements are Hebrew, and translating a manufacturer's liability
sentence to satisfy a key-set test would be manufacturing a claim they never
made.

Note where the old undivided rule failed: a `message`/`text` fallback is BY
DEFINITION the case with no code, so "every code in both bundles" could never say
anything about it. The tests at the end of this file are the ones that can.
"""

from __future__ import annotations

import json
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

# every StrategyWarning.code the generator emits + every CritiqueNote.code
WARNING_CODES = [
    "orphaned_override",
    # continuity, derived from stock length against the resolved spacing
    # (boundary contract obligation 14) — emitted from strategy/continuity.py
    "continuity_override_disagrees",
    "continuity_override_unbuildable",
    "continuity_stock_length_unknown",
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
    # The two never-block gaps (contract §3.2.4): a run that used to refuse now
    # produces a plan with the hole named, and the hole is named HERE.
    "uncovered_max_span",
    "no_default_post",
    # ...and the two per-span COUNTS that were the same silent fallback minus
    # the report. One code each rather than one parameterised code, so the
    # sentence names the row a curator has to author; both keep the VALUES they
    # always had (2 rails, 8 screws) and only now say where they came from.
    "uncovered_rails_per_span",
    "uncovered_screws_per_span",
    # A rule in this snapshot asks about the site and the site did not answer.
    # A warning and NOT a gap: `closes_by` is knowledge|planning and this is
    # neither — it is a field on the project for a person here to fill in.
    "site_condition_missing",
    # Emitted by the `ParameterTable` loader as `Gap.code`. NOTHING RENDERS THESE
    # YET — the annexe (build order item 8) is the surface that will, and
    # `Strategy.gaps` has no reader today. They are here anyway: the guard's job
    # is to force a code into both bundles the moment the backend can produce it,
    # so that the surface which eventually reads them is not also the change that
    # has to invent their Hebrew.
    "uncovered_parameter_point",
    "parameter_authority_lapsed",
    "parameter_value_nonconforming",
    # A table scoped to an entity kind this engine has no dimension for. Closes
    # by a schema change HERE, not by a curator — the fixture found it, because a
    # table built in a unit test carries no scope at all.
    "parameter_scope_unmappable",
    # Contract v1.2. The lapsed check's twin — `valid_from` was declared on the
    # row and read nowhere, so a row not yet in force was applied silently.
    "parameter_not_yet_in_force",
    # §1.3 BINDING: under `unique`, no two rows may match the same point, and
    # "the check will tell you when that is false". It did not exist, so the
    # contradiction surfaced at run time as a `Conflict` attributed to us rather
    # than to the table that declared something untrue about itself.
    "parameter_rows_overlap",
    # Three of the contract's four hit policies change WHICH number comes out,
    # and all three were accepted and dropped. Refused now, with a gap that
    # closes by a resolver in this repo.
    "parameter_hit_policy_unsupported",
    # §1.4's source policy, applied at expansion. Two of these three are
    # INVISIBLE to the scan that keeps this list honest: `explain_rejection`
    # returns them from `source_policy.py` and the gap site passes the result
    # through as a variable, so no `code="..."` literal exists to find. That is
    # the case this hand-maintained list exists for — a code the scanner cannot
    # see is a code that reaches a screen as its own key in both languages.
    "source_inadmissible",
    "source_below_min_curation",
    # A table naming a task our TaskCode registry has no row for. Its rows are
    # used UNJUDGED, so this warning is the only thing saying so.
    "parameter_task_unrecognised",
    # ...and the same for a source class. Both registries may grow without an
    # amendment (§2), so neither may fail a load — and a row used unjudged has
    # to say so, or it is indistinguishable from one that passed.
    "source_class_unrecognised",
    # A span limit taken from a source the run DECLINED to trust. Its own code
    # rather than `uncovered_max_span`, because that one says "no rule states
    # this" — false here, and false in the misleading direction.
    "declined_max_span",
    # Obligation 3's other half: a row with NO citation at all. Judged anyway
    # (the axes are on the row), but reported — a provenance chip with no
    # document behind it is a claim a reader cannot check.
    "source_ref_missing",
    # Two published rows resolving to one identity. Neither verdict is recorded,
    # because attributing one to the wrong number is worse than attributing none.
    "ambiguous_version_ref",
    "panel_length_unresolved",
    # Containment. Both say a credit did NOT happen — a credit that lands
    # cleanly is a smaller purchase and needs no warning — and both exist
    # because a saving is invisible on the finished document: the line is
    # simply shorter, or gone. `unmatched` is a credit aimed at a slot this
    # bay does not build; `surplus` is a kit shipping more of a piece than the
    # panel wanted, capped at what it wanted.
    "contained_credit_unmatched",
    "contained_credit_surplus",
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
    # ... and the POST's own. The line above is the CAP's, and its sentence says
    # the post is uncapped — reusing it for a post nothing covers told an author
    # about a cap and pointed the repair at the wrong conjunct.
    "no_item_covers_post_spec",
]
CRITIQUE_CODES = ["narrow_span"]

# Codes rendered as `error.<code>` rather than `warning.<code>`: a refusal, not a
# note on an answer. `core.errors.ReadRefused` (a stored run that cannot be read)
# and the `GenerationFailure` variants that carry a code — the failures a USER
# can cause from the editors, which must not fall through to the client's
# generic "the action failed (422)".
REFUSAL_CODES = [
    "run_predates_fence_model",
    # a stored strategy whose derived member run points at a bay or slot that is
    # no longer in it — same class, same remedy
    "member_run_unreadable",
    # the site-conditions twin of `topology_changed`: a derived view refuses to
    # be laid over conditions the run was not generated against
    "site_conditions_changed",
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
    # A pin on a part that comes INSIDE another part. Deliberately not
    # `sku_not_eligible`: that sentence tells the reader to choose one of the
    # products offered for the slot, and no product is ever offered for a
    # contained piece — advice impossible to follow.
    "slot_not_purchasable",
    # A model's post specification that no product satisfies. `post_spec_conflict`
    # is two models disagreeing about the post between them;
    # `post_routing_mismatch` is ROUTING alone excluding every candidate, which
    # is a fence that cannot be assembled rather than a worse buy; and
    # `no_item_covers_part_spec` is the generic case. A single merged code would
    # leave "no post found" a mystery, which is what they exist to avoid.
    # A decision node id is positional, so a `decision_ref` asked for without
    # the run it was made in names different decisions in different runs. The
    # unsafe read is refused rather than warned about.
    "decision_ref_needs_run",
    # assembly steps read against a panel resolved from a different version of
    # the model — the same shape as `topology_changed`, one document down
    "model_changed",
    "post_spec_conflict",
    "post_routing_mismatch",
    "no_item_covers_part_spec",
]

# Rendered as `warning.<code>`, same as `WARNING_CODES` — but this engine never
# constructs these itself, so the source scan in `test_backend_code_list_is_current`
# will never find them, and they are deliberately kept out of that scan's `known`
# set. The Knowledge Platform may raise them directly as a published `Gap.because.code`
# (contract §2: "Platform warning & gap codes — whoever raises it; both locale
# bundles required"), and this side owes the sentence regardless of which side wrote
# the code.
PUBLISHED_GAP_CODES = [
    # A domain point the source AFFIRMATIVELY excludes (an authority's own
    # applicability bracket), distinct from `uncovered_parameter_point`'s "no row
    # covers this". Agreed with the Knowledge team rather than a new `GapKind` —
    # `conversation.md` T2/T4, `CANDIDATES.md` C4 (struck).
    "parameter_condition_excluded",
]


def _bundles():
    en = json.loads((STATIC / "i18n" / "en.json").read_text())
    he = json.loads((STATIC / "i18n" / "he.json").read_text())
    return en, he


def test_no_bundle_key_is_declared_twice():
    """`json.load` keeps the LAST value silently, so a duplicate key is not a
    parse error — it is a string that resolves to whatever happens to come
    later in the file. It bit for real: a new panel added `assembly.title` and
    `assembly.hint` above the Assembly TAB's own keys of the same name, and the
    tab's copy won, so the Panel tab's instruction sheet was headed "Assembly
    view" and told the reader to pick a bay from a list it does not have.

    Every other test in this file loads the bundle through `json`, so none of
    them can see this. The text has to be read as TEXT.
    """
    import collections
    import re

    for name in ("en", "he"):
        raw = (STATIC / "i18n" / f"{name}.json").read_text()
        keys = re.findall(r'^  "([^"]+)":', raw, re.M)
        dupes = sorted(k for k, n in collections.Counter(keys).items() if n > 1)
        assert not dupes, (name, dupes)


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


def test_every_published_gap_code_has_locale_entries():
    """The other half of `test_every_backend_code_has_locale_entries`, for codes
    this engine renders but never emits."""
    en, he = _bundles()
    for code in PUBLISHED_GAP_CODES:
        assert f"warning.{code}" in en and f"warning.{code}" in he, code


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
        # the PREVIEW emits codes too, and was invisible to this guard — the
        # same hole the routes had, found the same way (a new code shipped with
        # no locale entry because nothing scanned the file that raised it)
        src / "fencemodel" / "preview.py",
        src / "demand" / "derive.py",
        # the ParameterTable loader emits codes too, and was invisible to this
        # guard for the same reason every earlier hole was: the file was not on
        # the list. A code with no bundle entry renders as raw English inside a
        # Hebrew sentence the day something first shows it.
        src / "knowledge" / "parameters.py",
            src / "knowledge" / "snapshot.py",
        # Continuity's codes are LITERALS here and reach `StrategyWarning` as
        # `code=note.code` — a variable — so scanning the generator finds nothing
        # and the guard was blind to all three. Exactly the hole every entry
        # above was added to close: the file was not on the list.
        src / "strategy" / "continuity.py",
        # the ROUTES emit codes too, in HTTP detail bodies, and they were
        # invisible to this guard twice over: the file was not scanned, and a
        # route writes `"code": "x"` rather than `code="x"`. Both forms now.
        src / "api" / "app.py",
    ]
    # ...and every read model, because they emit codes now too. Named as a
    # DIRECTORY rather than file by file: `report/assembly.py` raised
    # `model_changed` and this guard could not see it, which is the same blind
    # spot the route files had before `api/app.py` was added to the list.
    scanned += sorted((src / "report").glob("*.py"))
    # A code TABLE — `NAME_CODES = {subject: "the_code"}` — writes its codes in
    # neither form below: they are dict VALUES, so a scan for `code="x"` sees
    # nothing and the guard goes blind exactly the way it did for continuity's
    # variable `code=note.code`. Closed by SHAPE rather than by adding one more
    # file to the list, because the next table will be in a file already on it.
    # The value side only: the keys are what the code is ABOUT (a parameter name,
    # a role), and they have no bundle entry to owe.
    table = re.compile(r"^[A-Z][A-Z0-9_]*CODES\b[^=]*=\s*\{(.*?)^\}", re.M | re.S)
    emitted: set[str] = set()
    for path in scanned:
        text = path.read_text()
        emitted |= set(re.findall(r'code="([a-z_]+)"', text))
        emitted |= set(re.findall(r'"code":\s*"([a-z_]+)"', text))
        for body in table.findall(text):
            emitted |= set(re.findall(r':\s*"([a-z_]+)"', body))
    emitted.discard("generic")  # CritiqueNote default, never emitted explicitly
    known = set(WARNING_CODES) | set(CRITIQUE_CODES) | set(REFUSAL_CODES)
    assert emitted == known, {"unlisted": sorted(emitted - known),
                              "listed_but_gone": sorted(known - emitted)}


# The evidence viewer's own half of the split (js/evidence.js `warningsHtml`,
# fenceai/knowledge/discovery_stub.py): a `SourceWarning.code + params` the
# Knowledge/Discovery side authors is a PARAMETERISED SENTENCE this repo
# translates — source-refs-design.md §3.2 is explicit these are "parameterised
# sentences we author, not text lifted from a document, so translating them is
# tractable", unlike a `DocumentWarning`'s verbatim quote (which this file
# deliberately never key-checks, per the module docstring). Rendered as
# `sourcewarning.<code>`, its own prefix rather than `warning.<code>`, because
# these codes are authored on the OTHER side of the boundary and are not
# `StrategyWarning`/`CritiqueNote` codes this engine emits — conflating the two
# namespaces would let a Discovery code collide with one of ours silently.
SOURCE_WARNING_CODES = [
    "SOURCE_VERSION_STATUS_UNKNOWN",
    "SOURCE_TEXT_FROM_OCR",
    "SOURCE_TEXT_LAYER_MOJIBAKE",
    "SOURCE_TABLE_NOT_RECONSTRUCTED",
    "SOURCE_READING_NOT_HUMAN_REVIEWED",
    "SOURCE_CELL_BOX_MISSING",
    "SOURCE_DOCUMENT_SUPERSEDED",
    "SOURCE_OCR_LOW_CONFIDENCE",
    "SOURCE_NO_IMAGE_AVAILABLE",
    "SOURCE_DERIVED_NOT_ACCEPTABLE",
]


def test_every_source_warning_code_has_locale_entries():
    en, he = _bundles()
    for code in SOURCE_WARNING_CODES:
        assert f"sourcewarning.{code}" in en and f"sourcewarning.{code}" in he, code


def test_source_warning_code_list_is_current():
    """The fixture-side twin of `test_backend_code_list_is_current` above: these
    codes are not emitted by any Python source this repo controls (they arrive
    verbatim from the vendored fixture, `discovery_stub.py`'s whole point), so
    the thing to scan for drift is the fixture itself. A future 8th record
    carrying a code missing from `SOURCE_WARNING_CODES` fails here instead of
    silently falling back to raw English on screen."""
    fixture_path = (STATIC.parent.parent / "knowledge" / "fixtures"
                     / "source-ref-examples.json")
    fixture = json.loads(fixture_path.read_text())
    emitted = {w["code"] for rec in fixture["source_refs"]
               for w in rec.get("warnings", [])}
    known = set(SOURCE_WARNING_CODES)
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


def test_every_gap_vocabulary_value_has_a_word_in_both_bundles():
    """`gaps.js` renders a gap's kind, severity, subject and `closes_by` through
    COMPUTED keys — `t("gaps.kind." + gap.kind)` and three siblings — so key
    parity cannot see any of them, and `WARNING_CODES` above covers only the
    SENTENCE a gap shares with its paired warning.

    The list is read off `core/gaps.py` rather than repeated here, because the
    failure this guards is the one that arrives from outside: the Knowledge
    Platform publishes a `Gap` of a kind this engine has never emitted, every
    Python type accepts it (the whole point of one shared type), and it lands on
    screen as the literal string `gaps.kind.unquantified` in both languages with
    nothing red anywhere. Six of the eight kinds are in exactly that position
    today.
    """
    import typing

    from fenceai.core.gaps import Gap, GapKind, GapSubject

    en, he = _bundles()
    expected = {f"gaps.kind.{k}" for k in typing.get_args(GapKind)}
    expected |= {f"gaps.subject.{k}"
                 for k in typing.get_args(GapSubject.model_fields["kind"].annotation)}
    # `closes_by` is rendered as a GROUP heading rather than as a chip on a row —
    # the split has to be structural or it does not deliver what §1.2.1 asks for
    # — so its two keys per value are the heading and its hint.
    for field, prefix in (("closes_by", "gaps.group_"),
                          ("severity", "gaps.severity."),
                          ("on", "gaps.on.")):
        values = [v for v in typing.get_args(Gap.model_fields[field].annotation)
                  if isinstance(v, str)]
        # `on` is `Literal[...] | None`, so its args nest one level down
        if not values:
            inner = next(a for a in typing.get_args(Gap.model_fields[field].annotation)
                         if a is not type(None))
            values = list(typing.get_args(inner))
        expected |= {prefix + v for v in values}
        if field == "closes_by":
            expected |= {prefix + v + "_hint" for v in values}
    expected |= {"gaps.title", "gaps.hint", "gaps.none", "gaps.cites",
                 "gaps.would_close", "gaps.would_close_note"}

    missing = sorted(f"{lang}:{k}" for lang, table in (("en", en), ("he", he))
                     for k in expected if k not in table)
    assert not missing, missing

def _js_vocabulary(name: str) -> list[str]:
    """A `const NAME = [...]` array out of panel-model.js — one of the CLOSED
    vocabularies, which the editor still writes out because extending one is a
    release either way."""
    import re

    src = (STATIC / "js" / "panel-model.js").read_text()
    body = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
    assert body, f"{name} is no longer a const array in panel-model.js"
    values = re.findall(r'"([a-z_]+)"', body.group(1))
    assert values, name
    return values


def _served_vocabulary(name: str) -> list[str]:
    """One of the OPEN vocabularies, from the backend that serves it.

    These are no longer written into panel-model.js: the editor asks
    `GET /api/vocabularies`, so a basis registered on the backend is offered by
    the select without anyone editing JS. Which is exactly why the LABELS have to
    be checked from here — a member that appears in a Hebrew select with no word
    in the bundle is the failure that change makes reachable, and the source of
    truth for "which members exist" is no longer a file this test can grep."""
    from fenceai.fencemodel.vocabulary import vocabularies

    values = vocabularies()[name]
    assert values, name
    return values


def test_every_value_the_model_vocabulary_offers_has_a_word_in_both_bundles():
    """The editor renders its vocabularies through COMPUTED keys —
    `t("model.basis." + b)` and a dozen siblings — which key-parity scanning
    cannot see, because neither bundle contains the literal.

    This is the hole the other tests open: `test_the_editor_and_the_backend_agree
    _on_the_vocabularies` forces the editor to offer exactly what the backend
    accepts, so a new `LengthRule` reaches the select with nobody touching the
    frontend — and without this, that ships a green suite with a raw
    `model.length_rule.foo` on screen in both languages.

    The runtime does not go blank when that happens (`vocabWord` shows the token
    rather than the dotted key), but a raw token in a Hebrew form is a defect,
    not a feature, and this is where it is caught before it ships."""
    en, he = _bundles()

    expected = set()
    for const, prefix in [("ROLES", "role."),
                          ("PLACEMENT_KINDS", "model.placement."),
                          ("JUSTIFICATIONS", "model.justification."),
                          ("EXCESS", "model.excess."),
                          ("APPROVALS", "model.approval."), ("GRADES", "model.grade."),
                          ("AXIS_KINDS", "model.axis_kind."),
                          ("COUNT_PARAMS", "action.param.")]:
        expected |= {prefix + v for v in _js_vocabulary(const)}
    for served, prefix in [("length_rules", "model.length_rule."),
                           ("fixing_bases", "model.basis."),
                           # the objective is not offered by the panel editor,
                           # but tabs.js already RENDERS it beside every BOM
                           # (`bom.preset_<v>`), so a preset added to the backend
                           # with no word shows a raw token to a customer
                           ("objective_presets", "bom.preset_")]:
        expected |= {prefix + v for v in _served_vocabulary(served)}
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
    ("PLACEMENT_KINDS", "model.placement."),
    ("JUSTIFICATIONS", "model.justification."),
    ("EXCESS", "model.excess."),
]

# ... and the two of them the backend now SERVES rather than the editor holding
# a copy. Same claim, different source: `_js_vocabulary` cannot answer "which
# fixing bases exist" any more, because the answer is no longer in the JS.
SERVED_SENTENCE_VOCABULARIES = [
    ("fixing_bases", "model.basis."),
    ("length_rules", "model.length_rule."),
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
    en, he = _bundles()
    missing = []
    sources = ([(_js_vocabulary(c), p) for c, p in SENTENCE_VOCABULARIES]
               + [(_served_vocabulary(n), p) for n, p in SERVED_SENTENCE_VOCABULARIES])
    for values, prefix in sources:
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
    # ... and it degrades to the VALUE, not to the key. Two of these vocabularies
    # are served by the backend now, so a member can exist before its word does —
    # and `t()` answers a missing key with the key, which would put
    # `model.basis.sentence.per_corner` inside a Hebrew form. The test above
    # keeps that from shipping; this keeps the runtime honest when it happens
    # anyway, against a backend newer than the bundles.
    assert "vocabWord(" in body, (
        "an unworded vocabulary member must render as its own token, never as a "
        "raw i18n key")
    # ... and every vocabulary that HAS a phrasing is rendered with one. Two
    # spellings are legitimate: handed to `sentenceChoice` as a prefix, or built
    # inline where the control does more than set a field (the placement select
    # rebuilds the whole placement object on change).
    for const, prefix in SENTENCE_VOCABULARIES + SERVED_SENTENCE_VOCABULARIES:
        assert f'"{prefix}"' in src or f"{prefix}sentence." in src, (const, prefix)


# The keys the inspector builds by CONCATENATION once the `key` field was
# deleted and the zeros became derived readouts. None of them is a literal in
# either bundle, so key-parity scanning is blind to all of them:
#
#   * `model.inspect.${word}` — an element is now CALLED "Rail" / "Board 2" /
#     "Fixings", built from what it is plus where it sits, and the word comes
#     from this family. Losing one renders `model.inspect.board` as the name of
#     every board in a Hebrew UI.
#   * `model.${side}` — a distributed slot's two insets.
#   * `model.element_n` and the `model.derived.*` sentences — the number and the
#     reason beside a figure the panel already answered.
#   * `model.chip.<agree>` and its `_len` sibling — the part picker renders one
#     chip per fact the part declares, and WHICH template it asks for is chosen
#     from the agreement and from whether the fact carries a unit. Neither name
#     is a literal the parity scan can see as belonging to anything, and a
#     missing one puts a raw `model.chip.eq_len` inside a Hebrew pane.
#   * `model.<dim>` — the width and thickness a part owns, rendered read-only
#     where their fields used to be.
COMPUTED_INSPECTOR_KEYS = [
    "model.inspect.rail", "model.inspect.board", "model.inspect.screws",
    "model.bottom_inset_mm", "model.top_inset_mm",
    "model.element_n", "model.rename_hint",
    "model.derived.margin", "model.derived.at", "model.derived.rails",
    "model.derived.from_param",
    "model.chip.supplies", "model.chip.among", "model.chip.between",
    "model.chip.eq", "model.chip.other",
    "model.chip.among_len", "model.chip.between_len", "model.chip.eq_len",
    "model.chip.other_len",
    "model.width_mm", "model.thickness_mm", "model.dim.from_part",
]


def test_the_generated_element_name_and_its_derived_readouts_have_words():
    en, he = _bundles()
    missing = sorted(f"{lang}:{k}" for lang, table in (("en", en), ("he", he))
                     for k in COMPUTED_INSPECTOR_KEYS if k not in table)
    assert not missing, missing


def test_the_element_word_family_is_the_one_the_inspector_asks_for():
    """The keys existing is half of it — the other half is that `elementLabel`
    still builds its name out of THIS family. A version that fell back to the
    raw key would leave every entry above unreachable, with a green suite and a
    pane that has quietly gone back to naming boards `slat`."""
    src = (STATIC / "js" / "panel-inspector.js").read_text()
    body = src[src.index("export function elementLabel"):]
    body = body[:body.index("\n}\n")]
    assert "model.inspect." in body and "model.element_n" in body


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


def test_every_step_scope_has_a_word_in_both_bundles():
    """Contract obligation 12 publishes five scopes and the sheet renders three
    of them, which is exactly the shape that goes stale: `run` and `site` have no
    surface today, so a bundle missing their words breaks nothing until phase two
    builds one and Hebrew starts printing the raw enum.

    Asserted over the LITERAL on `AssemblyStep.scope`, so adding a sixth scope
    fails here rather than in a screenshot."""
    from typing import get_args

    from fenceai.fencemodel.model import AssemblyStep

    values = set(get_args(AssemblyStep.model_fields["scope"].annotation))
    assert len(values) == 5, values
    en, he = _bundles()
    missing = sorted(
        f"{lang}:{v}" for lang, table in (("en", en), ("he", he)) for v in values
        if f"assembly.step_scope.{v}" not in table
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


def test_gap_warning_placeholders_match_the_params_a_real_run_emits():
    """Key presence is not enough: a bundle string interpolates `{name}`, and
    nothing checked those names against what the backend actually sends.

    Renaming `value_mm` on either side renders a literal `{value_mm}` to the
    reader in BOTH languages with a green suite — and the browser smoke suite
    cannot see it either, because no smoke scenario retires a rule, so neither
    of these strings is ever rendered in a page.

    Driven by a REAL run rather than a fixture, so the params are the ones the
    generator emits, not the ones a test author remembered.
    """
    import re

    from fenceai.catalog.demo import demo_catalog
    from fenceai.knowledge.model import KnowledgeBase
    from fenceai.strategy.generator import generate
    from tests.conftest import straight_topology

    result = generate(straight_topology(6000), KnowledgeBase(versions=[]), demo_catalog())
    emitted = {w.code: set(w.params) for w in result.strategy.warnings}
    assert {"uncovered_max_span", "no_default_post"} <= set(emitted)

    for lang in ("en", "he"):
        bundle = json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for code, params in emitted.items():
            placeholders = set(re.findall(r"\{(\w+)\}", bundle[f"warning.{code}"]))
            # `{u}` is the display-unit word, supplied by the renderer, never by
            # the backend (CLAUDE.md: locale strings use `{…_mm}` + `{u}`)
            missing = placeholders - params - {"u"}
            assert not missing, f"{lang} warning.{code} interpolates {missing}, never sent"


# --- the other half of the split: text we did not write ----------------------
#
# A quoted warning has no code to look up, so none of the tests above can say
# anything about it. These four can, and each is one way the split could quietly
# collapse back into "everything goes through t()".

def test_only_one_module_renders_a_quoted_warning():
    """The mirror of `test_only_one_module_localizes_a_warning_by_code`, and for
    the same reason: a second renderer is how one surface comes to translate,
    normalise or summarise a manufacturer's sentence while another prints it
    intact. `text_raw` is read in exactly one place.

    **A DESIGN-INTENT guard, not coverage**, and recorded as such the way this
    repo records the distinction elsewhere: it constrains source text. The test
    review evaded it in one line — `(p.warning || {})["text" + "_raw"]` in
    another module is a second renderer this cannot see, and it would ship
    unescaped. Do not count it as protection against a second renderer; count it
    as the statement that there must not be one.

    It reads through `_code_only` like its three neighbours. It did not, and that
    contradicted the helper's own stated reason for existing: any comment in
    `panel.js` explaining the `text_raw` rule failed the build, which makes
    writing down why the thing to avoid."""
    js_dir = STATIC / "js"
    renderers = [
        p.name for p in [*js_dir.glob("*.js"), STATIC / "app.js"]
        if "text_raw" in _code_only(p)
    ]
    assert renderers == ["doc-warnings.js"], renderers


def _code_only(path: Path) -> str:
    """The module with its full-line `//` comments removed.

    The greps below look for a call that must not exist, and the module they
    inspect EXPLAINS at length why it must not exist — so the first version of
    these tests failed on the prose that documents the rule. Comments are not
    code, and a test that cannot tell them apart makes the honest thing to do
    (writing down why) the thing that breaks the build."""
    import re
    return re.sub(r"^\s*//.*$", "", path.read_text(), flags=re.M)


def test_the_quoted_renderer_never_localizes_the_text_it_carries():
    """It may localize its own furniture — the annexe's title, the "quoted from"
    label — and it must not put the quoted text through anything. A
    `t("warning." + code)` in this module would be the split collapsing: the
    publisher's optional code is not in our registry, so the lookup would miss
    and fall back, and the fallback path is exactly where the old rule was blind.
    """
    src = _code_only(STATIC / "js" / "doc-warnings.js")
    assert "localizedByCode" not in src
    assert '"warning."' not in src and "`warning.${" not in src
    # ...and the text is emitted directly, escaped and never interpolated
    assert "esc(w.text_raw" in src


def test_a_publishers_own_code_is_not_in_our_bundles():
    """Inverted on purpose. A code the fixture's publisher sent, given a sentence
    in our bundles, would mean this side had decided what their code says. 142 of
    the corpus's 226 distinct warnings appear exactly once, so a code registry for
    them would be a vocabulary of one-offs — and `text_raw` is what renders
    anyway.

    Read off the FIXTURE rather than hardcoded: the first version pinned
    `not_pool_rated`, which was coincidentally complete because the fixture
    carried exactly one code, and a second publisher code added to it would have
    been unguarded."""
    en, he = _bundles()
    fixture = json.loads((Path(__file__).resolve().parents[2] / "docs"
                          / "integration-contract" / "fixtures"
                          / "snapshot-example.json").read_text())
    codes = {w["code"] for w in fixture["warnings"] if w.get("code")}
    assert codes, "the fixture carries no publisher code — this test sees nothing"
    for code in codes:
        assert f"warning.{code}" not in en, code
        assert f"warning.{code}" not in he, code


def test_the_quoted_surface_never_offers_to_translate():
    """A DESIGN-INTENT guard, and narrowed to the half that can only be stated as
    one: there is no translate affordance — not a button, not a title, not a
    locale key. Translating a manufacturer's liability sentence and publishing it
    as theirs manufactures a claim they never made, so the absence is the
    feature.

    The `"dir=" in src` half was dropped. It proved nothing about the direction
    being DERIVED from the quoted `lang`, which is the actual property, and that
    property has a real behavioural test — `tests/web/test_doc_warnings_module.py
    ::test_the_direction_follows_the_quoted_language_not_the_page`, which fails
    when `dirOf` is stubbed to a constant. A vocabulary check beside a
    behavioural one can only produce false confidence or a false failure on a
    comment containing the word."""
    src = _code_only(STATIC / "js" / "doc-warnings.js")
    assert "translate" not in src.lower()
