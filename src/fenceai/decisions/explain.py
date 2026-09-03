"""Tier-1 explanations: deterministic templates rendered FROM the decision graph
(decision-model.md). Zero hallucination risk; works offline; the optional LLM polish
tier (ADR-0009) rewrites these fragments and is validated against node ids.

Templates live in per-language tables (UI v2 §4): the graph is the single source of
truth and only the surface language changes — same structure, same interpolated
values. Knowledge refs and SKUs are interpolated verbatim (Latin) in every language.
"""

from __future__ import annotations

from fenceai.decisions.graph import DecisionGraph, DecisionNode

_OVERRIDE_ACTIONS = frozenset(
    {"pin_post", "suppress_post", "force_post_sku", "force_mounting",
     "force_vertical",
     # A bay built exactly as a person placed it. It belongs here rather than
     # falling through to `generic`, which renders `{action}: {payload}` — a
     # departure from a published maximum is the last thing that should reach a
     # reader as a dict.
     "lock_bay"}
)
_INPUT_FACT_ACTIONS = frozenset(
    {"topology_node", "run_geometry", "gate_event", "knowledge_version"}
)

# Display units: the graph always stores int mm (ADR-0002); prose may render them
# in the reader's chosen unit, exactly like the UI (web/static/js/units.js).
_UNIT_WORDS = {"en": {"mm": "mm", "cm": "cm"}, "he": {"mm": 'מ"מ', "cm": 'ס"מ'}}
_LENGTH_LISTS = frozenset({"widths", "alt_widths", "heights_mm"})

# Enum VALUES that appear as words inside a sentence get translated; ids, SKUs and
# knowledge refs never pass through here (they stay verbatim Latin in every
# language). English is identity — the enum name IS the English word.
_ENUM_PARAMS = frozenset({"kind", "mounting", "surface", "surfaces", "vertical", "mode",
                          "chosen", "authored"})
_ENUM_WORDS: dict[str, dict[str, str]] = {
    "en": {},
    "he": {
        # post kinds
        "line": "שורה", "end": "קצה", "corner": "פינה", "junction": "צומת",
        "gate": "שער", "transition": "מעבר",
        # mounting / base surface
        "ground": "קרקע", "masonry": "קיר בנוי",
        "soil": "קרקע", "concrete": "בטון", "masonry_wall": "קיר בנוי",
        # vertical modes
        "level": "מאוזן", "stepped": "מדורג", "raked": "משופע", "follow": "עוקב",
        # post orientation
        "plumb": "אנכי לחלוטין", "perpendicular": "ניצב לקרקע", "custom": "זווית מותאמת",
        # MemberContinuity — the authored assertion, quoted inside a sentence
        "derived": "נגזר", "per_bay": "לפי מפתח", "continuous": "רציף",
    },
}


def _display(value, units: str):
    """mm -> the reader's unit. Mirrors units.js toDisplayValue: cm keeps one
    decimal and whole centimetres lose the trailing '.0'."""
    if units != "cm" or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    q = round(value) / 10
    return int(q) if q == int(q) else q


def _word(value, lang: str):
    return _ENUM_WORDS.get(lang, {}).get(value, value)

# One template per decision-graph action, per language. `_alt` / `_wall` / `_step`
# are optional sentence fragments appended when the payload carries those fields;
# `_governed` / `_defeated` / `_pinned` are the provenance suffixes.
TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "place_post": (
            "Post at station {station_mm} {u} ({kind}, {mounting} mount, {sku}) "
            "on {surface} base."
        ),
        # A choice set: two answers were admissible and this is the one built.
        # TWO templates, because "nobody chose" and "you chose" are different
        # facts — one sentence covering both would assert a decision that may
        # never have happened, which is the conflation the fifth kind exists to
        # prevent (spec §3).
        "resolve_choice_set": (
            "Segment {segment}: bay widths {widths}, chosen by {chosen_by} "
            "over {displaced}."
        ),
        "resolve_choice_set_default": (
            "Segment {segment}: bay widths {widths}. Nobody has chosen, so the "
            "usual answer stands; {alternatives} was also admissible."
        ),
        "layout_spans": "Segment {segment} divided into spans {widths}.",
        "layout_spans_alt": (
            " Alternative {alt_widths} was rejected because of {rejected_because}."
        ),
        "create_span": (
            "Span of {width_mm} {u}, height {height_mm} {u}, vertical mode "
            "'{vertical}' (height source: {height_source})."
        ),
        "create_span_wall": (
            " Height reduced by the wall top ({wall_top_mm} {u}, event {wall_event})."
        ),
        "create_span_step": " Steps {step_mm} {u} against the grade.",
        # one key per provenance, the same shape select_gate_kit uses: where a
        # choice came from is a different sentence, not a word slotted into one
        "select_model_event": "Built to fence model {model_ref}, set by a section event.",
        "select_model_project": "Built to fence model {model_ref}, the project's default.",
        "select_model_builtin": "Built to fence model {model_ref}, the built-in default.",
        "select_model_options": " Options: {options}.",
        # variant provenance is a different SENTENCE per outcome, not a word in
        # one: "variant 2 of 3" and "no variant applied" share no shape
        "select_variant": (
            "Variant {variant_number} of {of} applies to this bay (model {model_ref})."
        ),
        "select_variant_default": (
            "No variant of model {model_ref} applies to this bay; it is built to "
            "the default panel."
        ),
        "select_variant_failed": " Conditions of variant(s) {failed} were not met.",
        "select_variant_not_reached": (
            " Variant(s) {not_reached} were not evaluated: the first satisfied "
            "condition wins."
        ),
        "select_product": (
            "Slot {slot} is narrowed to {sku} by option {axis} = {value}."
        ),
        "select_supply": (
            "{chosen} supplies {slot}, chosen from {n} eligible products under "
            "the '{preset}' objective."
        ),
        "select_supply_beat": " It costs {chosen_cents}c against {runner_up} at {runner_up_cents}c.",
        "select_supply_unbuildable": " {unbuildable} cannot supply this part at all.",
        "resolve_panel": "Panel {model_ref} built from {slots}.",
        # the cut length, and — for a member measured against the panel's own
        # frame — the two members it was measured between, so the number is
        # arrived at in the prose rather than announced by it
        "resolve_panel_cut": " {slot} is cut to {length_mm} {u}.",
        "resolve_panel_between": (
            " {slot} is cut to {length_mm} {u}, measured between {base_slot} at "
            "{base_position_mm} {u} and {top_slot} at {top_position_mm} {u}; it "
            "starts {span_start_mm} {u} up the panel."
        ),
        "choose_vertical_mode": "Vertical mode '{mode}' chosen at {slope_permille}‰ grade.",
        "resolve_max_span": "Maximum span resolved to {value_mm} {u}.",
        "resolve_span_quantities": (
            "Quantities per span: {rails_per_span} rails, {screws_per_span} screws."
        ),
        "resolve_post_embedment": (
            "Posts are set {embed_mm} {u} into the ground ({n} post(s))."
        ),
        "resolve_demand_products": (
            "Demand products: rail {rail_sku}, screws {screw_sku}, "
            "concrete {concrete_sku}, caps {cap_sku}."
        ),
        "place_gate": "Gate opening from {start_mm} to {end_mm} {u}.",
        "select_gate_kit": "Gate kit {kit_sku} taken from gate event {event_id} as entered.",
        "select_gate_kit_catalog": (
            "Gate kit {kit_sku} selected from the catalog: it declares a fit for the "
            "{opening_width_mm} {u} opening of gate event {event_id}."
        ),
        "knowledge_conflict": (
            "Conflict on '{slot}' between {contenders} — surfaced for review."
        ),
        # A gap says what nobody told us, and — where a value was needed anyway —
        # what the run proceeded on. The sentence names the fallback because a
        # reader who cannot see the number cannot judge the plan.
        "uncovered_param": (
            "No rule states '{param}' for section {run_id}; laid out to a "
            "fallback of {value_mm} {u}, which nothing in the knowledge governs."
        ),
        # The same sentence for a COUNT, and it is a separate template for one
        # reason: `{value}`, never `{value_mm}`. Only a `*_mm` key converts to
        # the reader's display unit, so borrowing the line above would explain
        # two rails as "a fallback of 0.2 cm".
        "uncovered_quantity": (
            "No rule states '{param}' for {model_ref} in section {run_id}; built "
            "to a default of {value}, which nothing in the knowledge governs."
        ),
        "missing_default": (
            "No rule names a default product for role '{role}'; {n} element(s) "
            "stand with no product."
        ),
        "site_condition_missing": (
            "{n} site condition(s) that decide how this fence is built are not "
            "set ({dimensions}); the rules and fence-model options that depend "
            "on them did not apply."
        ),
        "node_surface_disagreement": (
            "Runs meeting at node {node_id} disagree on base surface ({surfaces}); "
            "'{chosen}' was used."
        ),
        "tilted_stepped": (
            "Section {run_id} combines tilted posts ({mode}) with stepped panels — "
            "check the design intent."
        ),
        "place_post_tilt": " Post tilted {tilt_deg}° from vertical.",
        # The post and the cap are PRICED choices, so what they were bought
        # instead of belongs in the sentence — the same shape `layout_spans_alt`
        # uses for a rejected span layout, and for the same reason.
        "place_post_alt": " {sku} was preferred over {rejected}.",
        "place_post_cap": " Capped with {cap_sku}.",
        "place_post_cap_alt": " {cap_sku} was preferred over {cap_rejected}.",
        "gate_past_run_end": (
            "The gate asks for {asked_mm} {u} at station {station_mm} {u}, but only "
            "{available_mm} {u} of the section remains."
        ),
        "excessive_step": (
            "Step of {step_mm} {u} exceeds the buildable maximum of {max_mm} {u} — "
            "needs an engineered solution."
        ),
        "clear_gap_exceeded": (
            "A gap of {value_mm} {u} in section {run_id} exceeds the {limit_mm} {u} "
            "limit, in {n} bay(s)."
        ),
        "rail_separation_insufficient": (
            "In section {run_id} the rail above the bottom one sits {value_mm} {u} up, "
            "under the {limit_mm} {u} anti-climb limit, in {n} bay(s)."
        ),
        "pattern_residual_large": (
            "Section {run_id} leaves {value_mm} {u} of the pattern unfilled, over the "
            "{limit_mm} {u} tolerance, in {n} bay(s)."
        ),
        "span_not_exact": (
            "Section {run_id} does not divide into {exact_mm} {u} bays: "
            "{remainder_mm} {u} is left over as an odd bay."
        ),
        "exact_span_over_max": (
            "Model {model_ref} is made in {exact_mm} {u} bays, wider than the "
            "{max_mm} {u} maximum span; section {run_id} was laid out freely."
        ),
        "excessive_gap": (
            "Stepped span leaves a {gap_mm} {u} gap underneath (limit {max_mm} {u})."
        ),
        "max_height_exceeded": (
            "Plumb height reaches {height_mm} {u} at the downhill end — above the "
            "{max_mm} {u} limit."
        ),
        "gate_on_slope": (
            "Gate opening sits on a {slope_permille}‰ slope (limit {max_permille}‰) "
            "— the ground needs leveling."
        ),
        "gate_kit_width_mismatch": (
            "Kit {sku} fits a {kit_width_mm} {u} opening, but this opening is "
            "{opening_width_mm} {u}."
        ),
        "insufficient_post_length": (
            "Post needs {required_mm} {u} ({exposed_mm} exposed + {embed_mm} embedded) "
            "but the product is only {available_mm} {u} long."
        ),
        "sliver_span": (
            "Span {span} is {width_mm} {u} — below the preferred minimum of {min_mm} {u}."
        ),
        "height_not_supported": (
            "Fence model {model_ref} does not support {n} panel height(s) in "
            "section {run_id}: {heights_mm} {u}."
        ),
        "panel_length_unresolved": (
            "Model {model_ref} resolves no cut length for slot {slot} in {n} "
            "bay(s) of section {run_id}."
        ),
        # The sentence a smaller purchase is answered with. A credit leaves no
        # line of its own on the BOM — it makes one shorter — so the arithmetic
        # is stated in full: what was needed, what came in the box, what is left
        # to buy. A reader given only the difference cannot check it.
        "credit_contained": (
            "Slot {slot} needs {of} {role}; {qty} of them ship inside {contained}, "
            "so the panel buys {remaining}."
        ),
        "contained_credit_unmatched": (
            "{contained} credits slot {slot}, which model {model_ref} does not "
            "build in {n} bay(s) of section {run_id}: nothing is credited there."
        ),
        "contained_credit_surplus": (
            "{contained} ships {qty} more than slot {slot} needs in {n} bay(s) of "
            "section {run_id}: the surplus credits nothing."
        ),
        # Obligation 14. The sentence names both inputs — the stock length and
        # the bays — because "why is this one piece" is asked of the cut list,
        # and an answer that named only the length would read as a coincidence.
        "derive_continuity": (
            "{slot} runs through {bays} bay(s) of section {run_id} as one "
            "{length_mm} {u} piece, {qty} of them: {stock_length_mm} {u} stock "
            "reaches that far."
        ),
        "derive_continuity_authored": (
            "{slot} runs through {bays} bay(s) of section {run_id} as one "
            "{length_mm} {u} piece, {qty} of them, because the model says so."
        ),
        "continuity_override_disagrees": (
            "{slot} in section {run_id} is authored continuity “{authored}”, "
            "which is built ({built_bays} bay(s) per piece) — the stock length "
            "and the spacing derive {derived_bays}."
        ),
        "continuity_override_unbuildable": (
            "{slot} in section {run_id} is authored continuous, but "
            "{stock_length_mm} {u} stock cannot reach past one {span_mm} {u} "
            "bay, so it is cut per bay."
        ),
        "continuity_stock_length_unknown": (
            "{slot} in section {run_id} is detailed to run through its posts "
            "and no product for it states a stock length, so nothing bounds how "
            "far one piece reaches: {built_bays} bay(s) per piece."
        ),
        # The input FACTS a section's story opens with. They used to fall through
        # to `input_fact`, which prints the raw payload dict — acceptable while
        # they appeared only as an indented `←` ancestor, and not once the
        # section view puts them at the top of what a person reads.
        # Count-dependent phrasing follows the locale bundles' convention
        # (`strategy.posts_one`, `structure.height_one`): a `_one` key chosen on
        # the count. Hebrew has no "(s)" escape — "שבו נפגשים 1 קטעים" is simply
        # wrong — and an END node, where a single section stops, is the common
        # case rather than the corner one.
        "topology_node": "Node {node_id} of the drawing, where {runs} sections meet.",
        "topology_node_one": "Node {node_id} of the drawing, where one section ends.",
        "run_geometry": "Section {run_id} is {length_mm} {u} long, falling {slope_permille}‰.",
        "gate_event": "A gate was asked for between {start_mm} {u} and {end_mm} {u}.",
        "override_applied": "User override {override_id} applied ({action}).",
        "input_fact": "Input fact: {action} {payload}.",
        "generic": "{action}: {payload}",
        "_governed": " Governed by {refs}.",
        "_defeated": " Defeated alternatives from {refs}.",
        "_pinned": " This decision is pinned by a user override.",
    },
    "he": {
        "place_post": (
            "עמוד בתחנה {station_mm} {u} ({kind}, עיגון {mounting}, {sku}) "
            "על בסיס {surface}."
        ),
        "resolve_choice_set": (
            "קטע {segment}: רוחבי מפתחים {widths}, בבחירת {chosen_by} במקום "
            "{displaced}."
        ),
        "resolve_choice_set_default": (
            "קטע {segment}: רוחבי מפתחים {widths}. אף אחד לא בחר, ולכן נשארת "
            "התשובה הרגילה; גם {alternatives} היה קביל."
        ),
        "layout_spans": "המקטע {segment} חולק למפתחים {widths}.",
        "layout_spans_alt": " החלופה {alt_widths} נדחתה בגלל {rejected_because}.",
        "create_span": (
            "מפתח ברוחב {width_mm} {u}, גובה {height_mm} {u}, מצב אנכי "
            "'{vertical}' (מקור הגובה: {height_source})."
        ),
        "create_span_wall": (
            " הגובה הופחת בשל ראש הקיר ({wall_top_mm} {u}, אירוע {wall_event})."
        ),
        "create_span_step": " מדורג ב-{step_mm} {u} כנגד השיפוע.",
        "select_model_event": "נבנה לפי דגם הגדר {model_ref}, שנקבע באירוע קטע.",
        "select_model_project": "נבנה לפי דגם הגדר {model_ref}, ברירת המחדל של הפרויקט.",
        "select_model_builtin": "נבנה לפי דגם הגדר {model_ref}, ברירת המחדל המובנית.",
        "select_model_options": " אפשרויות: {options}.",
        "select_variant": "וריאנט {variant_number} מתוך {of} חל על מפתח זה (דגם {model_ref}).",
        "select_variant_default": (
            "אף וריאנט של הדגם {model_ref} אינו חל על מפתח זה; הוא נבנה לפי פאנל "
            "ברירת המחדל."
        ),
        "select_variant_failed": " התנאים של וריאנט {failed} לא התקיימו.",
        "select_variant_not_reached": (
            " וריאנט {not_reached} לא נבדק: הוריאנט הראשון שתנאו מתקיים הוא הקובע."
        ),
        "select_product": "הרכיב {slot} צומצם ל-{sku} לפי האפשרות {axis} = {value}.",
        "select_supply": (
            "{chosen} מספק את {slot}, ונבחר מתוך {n} מוצרים כשירים לפי יעד "
            "ה-'{preset}'."
        ),
        "select_supply_beat": " עלותו {chosen_cents} סנט מול {runner_up} ב-{runner_up_cents} סנט.",
        "select_supply_unbuildable": " {unbuildable} אינו יכול לספק את החלק הזה כלל.",
        "resolve_panel": "הפאנל {model_ref} נבנה מ-{slots}.",
        "resolve_panel_cut": " {slot} נחתך ל-{length_mm} {u}.",
        "resolve_panel_between": (
            " {slot} נחתך ל-{length_mm} {u}, נמדד בין {base_slot} בגובה "
            "{base_position_mm} {u} לבין {top_slot} בגובה {top_position_mm} {u}; "
            "הוא מתחיל {span_start_mm} {u} מתחתית הפאנל."
        ),
        "choose_vertical_mode": "נבחר מצב אנכי '{mode}' בשיפוע {slope_permille}‰.",
        "resolve_max_span": "המפתח המרבי נקבע ל-{value_mm} {u}.",
        "resolve_span_quantities": (
            "כמויות לכל מפתח: {rails_per_span} מוטות, {screws_per_span} ברגים."
        ),
        "resolve_post_embedment": (
            "העמודים מוטמנים {embed_mm} {u} באדמה ({n} עמודים)."
        ),
        "resolve_demand_products": (
            "מוצרי הדרישה: מוט {rail_sku}, ברגים {screw_sku}, "
            "בטון {concrete_sku}, כיפות {cap_sku}."
        ),
        "place_gate": "פתח שער מתחנה {start_mm} עד {end_mm} {u}.",
        "select_gate_kit": "ערכת השער {kit_sku} נלקחה מאירוע השער {event_id} כפי שהוזנה.",
        "select_gate_kit_catalog": (
            "ערכת השער {kit_sku} נבחרה מהקטלוג: היא מוצהרת כמתאימה לפתח של "
            "{opening_width_mm} {u} באירוע השער {event_id}."
        ),
        "knowledge_conflict": "סתירה על '{slot}' בין {contenders} — הוצפה לבדיקה.",
        "uncovered_param": (
            "אין כלל הקובע '{param}' עבור הקטע {run_id}; התכנון בוצע לפי ברירת "
            "מחדל של {value_mm} {u}, שאינה נשענת על אף ידע."
        ),
        "uncovered_quantity": (
            "אין כלל הקובע '{param}' עבור {model_ref} בקטע {run_id}; הבנייה בוצעה "
            "לפי ברירת מחדל של {value}, שאינה נשענת על אף ידע."
        ),
        "missing_default": (
            "אין כלל הקובע מוצר ברירת מחדל לתפקיד '{role}'; {n} רכיבים עומדים "
            "ללא מוצר."
        ),
        "site_condition_missing": (
            "{n} תנאי אתר שקובעים כיצד נבנית הגדר אינם מוגדרים ({dimensions}); "
            "הכללים ואפשרויות דגם הגדר התלויים בהם לא הופעלו."
        ),
        "node_surface_disagreement": (
            "קטעים שנפגשים בצומת {node_id} חלוקים לגבי משטח הבסיס ({surfaces}); "
            "נעשה שימוש ב-'{chosen}'."
        ),
        "tilted_stepped": (
            "הקטע {run_id} משלב עמודים נטויים ({mode}) עם פאנלים מדורגים — "
            "בדקו את כוונת התכנון."
        ),
        "place_post_tilt": " העמוד נטוי {tilt_deg}° מהאנך.",
        "place_post_alt": " {sku} הועדף על פני {rejected}.",
        "place_post_cap": " כיפה: {cap_sku}.",
        "place_post_cap_alt": " {cap_sku} הועדפה על פני {cap_rejected}.",
        "gate_past_run_end": (
            "השער מבקש {asked_mm} {u} בתחנה {station_mm} {u}, אך נותרו במקטע "
            "{available_mm} {u} בלבד."
        ),
        "excessive_step": (
            'מדרגה של {step_mm} {u} חורגת מהמקסימום הניתן לביצוע ({max_mm} {u}) — '
            "נדרש פתרון הנדסי."
        ),
        "clear_gap_exceeded": (
            "מרווח של {value_mm} {u} בקטע {run_id} חורג מהמגבלה של {limit_mm} {u}, "
            "ב-{n} מפתחים."
        ),
        "rail_separation_insufficient": (
            "בקטע {run_id} המסילה שמעל התחתונה נמצאת {value_mm} {u} מעליה, מתחת "
            "למגבלת מניעת הטיפוס של {limit_mm} {u}, ב-{n} מפתחים."
        ),
        "pattern_residual_large": (
            "בקטע {run_id} נותרו {value_mm} {u} לא ממולאים בתבנית, מעל הסבולת של "
            "{limit_mm} {u}, ב-{n} מפתחים."
        ),
        "span_not_exact": (
            "קטע {run_id} אינו מתחלק למפתחים של {exact_mm} {u}: נותרו "
            "{remainder_mm} {u} כמפתח חריג."
        ),
        "exact_span_over_max": (
            "דגם {model_ref} מיוצר במפתחים של {exact_mm} {u}, רחבים מהמפתח המרבי "
            "{max_mm} {u}; קטע {run_id} נפרס באופן חופשי."
        ),
        "excessive_gap": (
            'הפאנל המדורג משאיר מרווח של {gap_mm} {u} מתחתיו (המגבלה {max_mm} {u}).'
        ),
        "max_height_exceeded": (
            'הגובה האנכי מגיע ל-{height_mm} {u} בקצה הנמוך — מעל המגבלה של {max_mm} {u}.'
        ),
        "gate_on_slope": (
            "פתח השער יושב על שיפוע של {slope_permille}‰ (המגבלה {max_permille}‰) — "
            "יש לפלס את הקרקע."
        ),
        "gate_kit_width_mismatch": (
            "הערכה {sku} מתאימה לפתח של {kit_width_mm} {u}, אך רוחב הפתח הוא "
            "{opening_width_mm} {u}."
        ),
        "insufficient_post_length": (
            'העמוד דורש {required_mm} {u} ({exposed_mm} חשוף + {embed_mm} מוטמן) '
            'אך אורך המוצר הוא {available_mm} {u} בלבד.'
        ),
        "sliver_span": (
            "המפתח {span} הוא {width_mm} {u} — מתחת למינימום המועדף של {min_mm} {u}."
        ),
        "height_not_supported": (
            "דגם הגדר {model_ref} אינו תומך ב-{n} מגובהי הפאנל בקטע {run_id}: "
            "{heights_mm} {u}."
        ),
        "panel_length_unresolved": (
            "דגם {model_ref} אינו מחשב אורך חיתוך עבור החריץ {slot} ב-{n} "
            "מפתחים בקטע {run_id}."
        ),
        "credit_contained": (
            "החריץ {slot} דורש {of} {role}; {qty} מהם מגיעים בתוך {contained}, "
            "ולכן הפאנל רוכש {remaining}."
        ),
        "contained_credit_unmatched": (
            "{contained} מזכה את החריץ {slot}, שדגם {model_ref} אינו בונה ב-{n} "
            "מפתחים בקטע {run_id}: לא מזוכה שם דבר."
        ),
        "contained_credit_surplus": (
            "{contained} כולל {qty} יותר מהנדרש בחריץ {slot} ב-{n} מפתחים בקטע "
            "{run_id}: העודף אינו מזכה דבר."
        ),
        "derive_continuity": (
            "{slot} עובר דרך {bays} מפתחים בקטע {run_id} כפריט אחד באורך "
            "{length_mm} {u}, {qty} כאלה: מוט באורך {stock_length_mm} {u} מגיע "
            "עד לשם."
        ),
        "derive_continuity_authored": (
            "{slot} עובר דרך {bays} מפתחים בקטע {run_id} כפריט אחד באורך "
            "{length_mm} {u}, {qty} כאלה, משום שכך נקבע בדגם."
        ),
        "continuity_override_disagrees": (
            "ל{slot} בקטע {run_id} הוגדרה רציפות “{authored}”, וכך נבנה "
            "({built_bays} מפתחים לפריט) — אורך המלאי והמרווח גוזרים "
            "{derived_bays}."
        ),
        "continuity_override_unbuildable": (
            "ל{slot} בקטע {run_id} הוגדרה רציפות, אך מוט באורך "
            "{stock_length_mm} {u} אינו מגיע מעבר למפתח אחד ({span_mm} {u}), "
            "ולכן הוא נחתך לפי מפתח."
        ),
        "continuity_stock_length_unknown": (
            "ל{slot} בקטע {run_id} תוכנן מעבר דרך העמודים ואף מוצר עבורו אינו "
            "מצהיר אורך מלאי, ולכן דבר אינו תוחם עד כמה מגיע מוט אחד: "
            "{built_bays} מפתחים למוט."
        ),
        "topology_node": "צומת {node_id} בשרטוט, שבו נפגשים {runs} קטעים.",
        "topology_node_one": "צומת {node_id} בשרטוט, שבו מסתיים קטע אחד.",
        "run_geometry": "אורך קטע {run_id} הוא {length_mm} {u}, בשיפוע {slope_permille}‰.",
        "gate_event": "התבקש שער בין {start_mm} {u} ל-{end_mm} {u}.",
        "override_applied": "דריסת משתמש {override_id} הוחלה ({action}).",
        "input_fact": "עובדת קלט: {action} {payload}.",
        "generic": "{action}: {payload}",
        "_governed": " נקבע לפי {refs}.",
        "_defeated": " גבר על {refs}.",
        "_pinned": " החלטה זו ננעצה על ידי המשתמש.",
    },
}


def _refs(graph: DecisionGraph, node: DecisionNode, edge_type: str) -> list[str]:
    return sorted(
        e.knowledge_ref for e in graph.in_edges(node.id) if e.type == edge_type and e.knowledge_ref
    )


def _fmt(t: dict[str, str], key: str, lang: str, units: str, **kw) -> str:
    """Render one template: `*_mm` values (and length lists) in the reader's unit,
    enum values as words in the reader's language, `{u}` as the unit word. Ids,
    SKUs, refs and raw payloads pass through untouched."""
    out = {}
    for k, v in kw.items():
        # the list branch comes FIRST: a length list may also end in `_mm`
        # (`heights_mm`), and `_display` on a list silently returns it in
        # millimetres — which reads as centimetres beside a `{u}` saying cm
        if k in _LENGTH_LISTS and isinstance(v, (list, tuple)):
            out[k] = [_display(x, units) for x in v]
        elif k.endswith("_mm"):
            out[k] = _display(v, units)
        elif k in _ENUM_PARAMS:
            out[k] = (", ".join(_word(x, lang) for x in v)
                      if isinstance(v, (list, tuple)) else _word(v, lang))
        else:
            out[k] = v
    out["u"] = _UNIT_WORDS.get(lang, _UNIT_WORDS["en"]).get(units, units)
    return t[key].format(**out)


def _widths(widths) -> str:
    """A bay list as a reader would say it, not as Python prints it.

    `[1667, 1667, 1666]` in a sentence is a list literal wearing a sentence's
    clothes. The separator is a middle dot because the plan canvas and the
    dimension strings already use one for a chain of bays, and because a comma
    reads as a list of unrelated things.
    """
    return " · ".join(str(w) for w in (widths or []))


def explain_node(
    graph: DecisionGraph, node: DecisionNode, lang: str = "en", units: str = "mm"
) -> str:
    t = TEMPLATES.get(lang, TEMPLATES["en"])
    governed = _refs(graph, node, "governed_by")
    defeated = _refs(graph, node, "defeated")
    p = node.payload
    match node.action:
        case "place_post":
            base = _fmt(t, "place_post", lang, units,
                station_mm=p.get("station_mm"), kind=p.get("kind"),
                mounting=p.get("mounting"), sku=p.get("sku"), surface=p.get("surface"),
            )
            if p.get("tilt_deg"):
                base += _fmt(t, "place_post_tilt", lang, units, tilt_deg=p["tilt_deg"])
            if p.get("rejected"):
                base += _fmt(t, "place_post_alt", lang, units,
                             sku=p.get("sku"), rejected=", ".join(p["rejected"]))
            if p.get("cap_sku"):
                base += _fmt(t, "place_post_cap", lang, units, cap_sku=p["cap_sku"])
            if p.get("cap_rejected"):
                base += _fmt(t, "place_post_cap_alt", lang, units,
                             cap_sku=p.get("cap_sku"),
                             cap_rejected=", ".join(p["cap_rejected"]))
        case "layout_spans":
            alt = p.get("alternatives") or []
            base = _fmt(t, "layout_spans", lang, units, segment=p.get("segment"), widths=p.get("widths"))
            if alt:
                base += _fmt(t, "layout_spans_alt", lang, units,
                    alt_widths=alt[0]["widths"], rejected_because=alt[0]["rejected_because"]
                )
        case "create_span":
            base = _fmt(t, "create_span", lang, units,
                width_mm=p.get("width_mm"), height_mm=p.get("height_mm"),
                vertical=p.get("vertical"), height_source=p.get("height_source"),
            )
            if "adjusted_by_wall_profile" in p:
                base += _fmt(t, "create_span_wall", lang, units,
                    wall_top_mm=p.get("wall_top_mm"), wall_event=p["adjusted_by_wall_profile"]
                )
            if "step_mm" in p:
                base += _fmt(t, "create_span_step", lang, units, step_mm=p["step_mm"])
        case "select_model":
            base = _fmt(t, f"select_model_{p.get('source', 'builtin')}", lang, units,
                model_ref=p.get("model_ref"))
            options = p.get("options") or {}
            if options:
                base += _fmt(t, "select_model_options", lang, units,
                    options=", ".join(f"{k}={v}" for k, v in sorted(options.items())))
        case "select_variant":
            index = p.get("variant_index")
            if index is None:
                base = _fmt(t, "select_variant_default", lang, units,
                    model_ref=p.get("model_ref"))
            else:
                # 1-based in prose: "variant 0" is a programmer's answer to
                # "which one of the three did we build?"
                base = _fmt(t, "select_variant", lang, units,
                    model_ref=p.get("model_ref"), variant_number=index + 1,
                    of=p.get("of"))
            if p.get("failed"):
                base += _fmt(t, "select_variant_failed", lang, units,
                    failed=", ".join(str(i + 1) for i in p["failed"]))
            if p.get("not_reached"):
                base += _fmt(t, "select_variant_not_reached", lang, units,
                    not_reached=", ".join(str(i + 1) for i in p["not_reached"]))
        case "select_supply":
            candidates = p.get("candidates", [])
            base = _fmt(t, "select_supply", lang, units,
                chosen=p.get("chosen"), slot=p.get("slot_key") or p.get("role"),
                n=len(candidates), preset=p.get("preset"))
            # the runner-up is the evidence: "cheaper than the others" is not an
            # explanation, "cheaper than THAT one, by this much" is
            priced = [c for c in candidates if c.get("cost_cents") is not None]
            winner = next((c for c in priced if c["sku"] == p.get("chosen")), None)
            runner_up = next((c for c in priced if c["sku"] != p.get("chosen")), None)
            if winner and runner_up:
                base += _fmt(t, "select_supply_beat", lang, units,
                    chosen_cents=winner["cost_cents"], runner_up=runner_up["sku"],
                    runner_up_cents=runner_up["cost_cents"])
            unbuildable = [c["sku"] for c in candidates if not c.get("feasible", True)]
            if unbuildable:
                base += _fmt(t, "select_supply_unbuildable", lang, units,
                    unbuildable=", ".join(unbuildable))
        case "select_product":
            base = _fmt(t, "select_product", lang, units, slot=p.get("slot"),
                sku=p.get("sku"), axis=p.get("axis"), value=p.get("value"))
        case "resolve_panel":
            slot_payloads = p.get("slots", [])
            slots = ", ".join(f"{s['qty']} {s['role']}" for s in slot_payloads)
            base = _fmt(t, "resolve_panel", lang, units,
                model_ref=p.get("model_ref"), slots=slots)
            # one fragment per slot that HAS a cut length, formatted rather than
            # pre-joined: a length inside an already-built string would still say
            # millimetres to a reader who asked for centimetres
            for s in slot_payloads:
                if s.get("length_mm") is None:
                    continue
                between = s.get("between") or {}
                if "base" in between and "top" in between:
                    base += _fmt(t, "resolve_panel_between", lang, units,
                        slot=s["key"], length_mm=s["length_mm"],
                        span_start_mm=s.get("span_start_mm"),
                        base_slot=between["base"]["slot"],
                        base_position_mm=between["base"]["position_mm"],
                        top_slot=between["top"]["slot"],
                        top_position_mm=between["top"]["position_mm"])
                else:
                    base += _fmt(t, "resolve_panel_cut", lang, units,
                        slot=s["key"], length_mm=s["length_mm"])
        case "choose_vertical_mode":
            base = _fmt(t, "choose_vertical_mode", lang, units,
                mode=p.get("mode"), slope_permille=p.get("slope_permille")
            )
        case "resolve_max_span":
            base = _fmt(t, "resolve_max_span", lang, units, value_mm=p.get("value"))
        case "resolve_span_quantities":
            base = _fmt(t, "resolve_span_quantities", lang, units,
                rails_per_span=p.get("rails_per_span"), screws_per_span=p.get("screws_per_span")
            )
        case "resolve_post_embedment":
            base = _fmt(t, "resolve_post_embedment", lang, units,
                embed_mm=p.get("embed_mm"), n=p.get("n"))
        case "resolve_demand_products":
            base = _fmt(t, "resolve_demand_products", lang, units,
                rail_sku=p.get("rail_sku"), screw_sku=p.get("screw_sku"),
                concrete_sku=p.get("concrete_sku"), cap_sku=p.get("cap_sku"),
            )
        case "place_gate":
            base = _fmt(t, "place_gate", lang, units, start_mm=p.get("start_mm"), end_mm=p.get("end_mm"))
        case "select_gate_kit":
            key = ("select_gate_kit_catalog" if p.get("source") == "catalog"
                   else "select_gate_kit")
            base = _fmt(t, key, lang, units, kit_sku=p.get("kit_sku"),
                event_id=p.get("event_id"), opening_width_mm=p.get("opening_width_mm"))
        case "knowledge_conflict":
            base = _fmt(t, "knowledge_conflict", lang, units,
                slot=p.get("slot"), contenders=", ".join(p.get("contenders", []))
            )
        case "uncovered_param":
            base = _fmt(t, "uncovered_param", lang, units,
                # `value_mm`, not `value`: only a `*_mm` key converts to the
                # reader's display unit, and today's only uncovered param IS a
                # length (`resolve_max_span` says it the same way)
                param=p.get("param"), run_id=p.get("run_id"), value_mm=p.get("value"))
        case "uncovered_quantity":
            base = _fmt(t, "uncovered_quantity", lang, units,
                param=p.get("param"), run_id=p.get("run_id"),
                model_ref=p.get("model_ref"), value=p.get("value"))
        case "missing_default":
            base = _fmt(t, "missing_default", lang, units,
                role=p.get("role"), n=p.get("n"))
        case "site_condition_missing":
            base = _fmt(t, "site_condition_missing", lang, units,
                dimensions=p.get("dimensions"), n=p.get("n"))
        case "node_surface_disagreement":
            base = _fmt(t, "node_surface_disagreement", lang, units,
                node_id=p.get("node_id"), surfaces=list(p.get("surfaces", [])),
                chosen=p.get("chosen"),
            )
        case "tilted_stepped":
            base = _fmt(t, "tilted_stepped", lang, units, run_id=p.get("run_id"), mode=p.get("mode"))
        case "gate_past_run_end":
            base = _fmt(t, "gate_past_run_end", lang, units,
                asked_mm=p.get("asked_mm"), available_mm=p.get("available_mm"),
                station_mm=p.get("station_mm"))
        case "excessive_step":
            base = _fmt(t, "excessive_step", lang, units, step_mm=p.get("step_mm"), max_mm=p.get("max_mm"))
        case "excessive_gap":
            base = _fmt(t, "excessive_gap", lang, units, gap_mm=p.get("gap_mm"), max_mm=p.get("max_mm"))
        case "exact_span_over_max":
            base = _fmt(t, "exact_span_over_max", lang, units, run_id=p.get("run_id"),
                model_ref=p.get("model_ref"), exact_mm=p.get("exact_mm"),
                max_mm=p.get("max_mm"))
        case "span_not_exact":
            base = _fmt(t, "span_not_exact", lang, units, run_id=p.get("run_id"),
                exact_mm=p.get("exact_mm"), remainder_mm=p.get("remainder_mm"))
        case "clear_gap_exceeded" | "rail_separation_insufficient" | "pattern_residual_large":
            # one shape for the three panel-limit checks: they differ in which
            # measurement they take, not in what they have to say about it
            base = _fmt(t, node.action, lang, units, run_id=p.get("run_id"),
                value_mm=p.get("value_mm"), limit_mm=p.get("limit_mm"), n=p.get("n"))
        case "max_height_exceeded":
            base = _fmt(t, "max_height_exceeded", lang, units,
                height_mm=p.get("height_mm"), max_mm=p.get("max_mm"))
        case "gate_on_slope":
            base = _fmt(t, "gate_on_slope", lang, units,
                slope_permille=p.get("slope_permille"), max_permille=p.get("max_permille"))
        case "gate_kit_width_mismatch":
            base = _fmt(t, "gate_kit_width_mismatch", lang, units, sku=p.get("sku"),
                kit_width_mm=p.get("kit_width_mm"),
                opening_width_mm=p.get("opening_width_mm"))
        case "insufficient_post_length":
            base = _fmt(t, "insufficient_post_length", lang, units,
                required_mm=p.get("required_mm"), exposed_mm=p.get("exposed_mm"),
                embed_mm=p.get("embed_mm"), available_mm=p.get("available_mm"))
        case "sliver_span":
            base = _fmt(t, "sliver_span", lang, units,
                span=p.get("span"), width_mm=p.get("width_mm"), min_mm=p.get("min_mm")
            )
        case "height_not_supported":
            base = _fmt(t, "height_not_supported", lang, units,
                model_ref=p.get("model_ref"), run_id=p.get("run_id"),
                n=p.get("n"), heights_mm=p.get("heights_mm", []))
        case "panel_length_unresolved":
            base = _fmt(t, "panel_length_unresolved", lang, units,
                model_ref=p.get("model_ref"), slot=p.get("slot"),
                run_id=p.get("run_id"), n=p.get("n"))
        case "credit_contained":
            base = _fmt(t, "credit_contained", lang, units,
                slot=p.get("slot"), role=p.get("role"), of=p.get("of"),
                qty=p.get("qty"), contained=p.get("contained"),
                remaining=p.get("remaining"))
        case "contained_credit_unmatched" | "contained_credit_surplus":
            base = _fmt(t, node.action, lang, units,
                model_ref=p.get("model_ref"), contained=p.get("contained"),
                slot=p.get("slot"), qty=p.get("qty"),
                run_id=p.get("run_id"), n=p.get("n"))
        case "derive_continuity":
            # two sentences for two different reasons, because they are two
            # different answers: a derived piece is as long as the stock allows,
            # and an authored one is as long as the guide said. Naming a stock
            # length in the authored sentence would credit the derivation for a
            # decision it did not make.
            base = _fmt(
                t,
                "derive_continuity" if p.get("basis") == "stock_length"
                else "derive_continuity_authored",
                lang, units,
                slot=p.get("slot"), bays=p.get("bays"), run_id=p.get("run_id"),
                length_mm=p.get("length_mm"), qty=p.get("qty"),
                stock_length_mm=p.get("stock_length_mm"))
        case "continuity_override_disagrees":
            base = _fmt(t, "continuity_override_disagrees", lang, units,
                slot=p.get("slot"), run_id=p.get("run_id"),
                authored=p.get("authored"), built_bays=p.get("built_bays"),
                derived_bays=p.get("derived_bays"))
        case "continuity_override_unbuildable":
            base = _fmt(t, "continuity_override_unbuildable", lang, units,
                slot=p.get("slot"), run_id=p.get("run_id"),
                stock_length_mm=p.get("stock_length_mm"), span_mm=p.get("span_mm"))
        case "continuity_stock_length_unknown":
            base = _fmt(t, "continuity_stock_length_unknown", lang, units,
                slot=p.get("slot"), run_id=p.get("run_id"),
                built_bays=p.get("built_bays", 1))
        case action if action in _OVERRIDE_ACTIONS:
            base = _fmt(t, "override_applied", lang, units,
                override_id=p.get("override_id"), action=node.action
            )
        case "topology_node":
            runs = p.get("runs")
            base = _fmt(t, "topology_node_one" if runs == 1 else "topology_node",
                        lang, units, node_id=p.get("node_id"), runs=runs)
        case "run_geometry":
            base = _fmt(t, "run_geometry", lang, units, run_id=p.get("run_id"),
                        length_mm=p.get("length_mm"),
                        slope_permille=p.get("slope_permille"))
        case "gate_event":
            base = _fmt(t, "gate_event", lang, units,
                        start_mm=p.get("start_mm"), end_mm=p.get("end_mm"))
        case action if action in _INPUT_FACT_ACTIONS:
            # `knowledge_version` alone reaches this now: it is a REF, and its
            # payload is that ref. The three facts above are sentences, because
            # the section view puts them at the top of what a person reads.
            base = _fmt(t, "input_fact", lang, units, action=node.action, payload=p)
        case "resolve_choice_set":
            base = _fmt(t, "resolve_choice_set", lang, units,
                widths=_widths(p.get("widths")), segment=p.get("segment"),
                chosen_by=p.get("chosen_by"),
                displaced=_widths(p.get("displaced")),
            )
        case "resolve_choice_set_default":
            base = _fmt(t, "resolve_choice_set_default", lang, units,
                widths=_widths(p.get("widths")), segment=p.get("segment"),
                alternatives=" / ".join(
                    _widths(w) for w in (p.get("alternatives") or [])),
            )
        case _:
            base = _fmt(t, "generic", lang, units, action=node.action, payload=p)
    if governed:
        base += _fmt(t, "_governed", lang, units, refs=", ".join(governed))
    if defeated:
        base += _fmt(t, "_defeated", lang, units, refs=", ".join(defeated))
    if node.status == "pinned":
        base += t["_pinned"]
    return base


def explain_element(
    graph: DecisionGraph, element_id: str, lang: str = "en", units: str = "mm"
) -> list[str]:
    """Why does this element exist / look the way it does? Rendered from the graph."""
    out: list[str] = []
    for node in graph.nodes_for_element(element_id):
        out.append(explain_node(graph, node, lang, units))
        for anc in graph.ancestors(node.id):
            if anc.kind in ("input_fact", "rule_firing", "override_applied", "conflict"):
                out.append("  ← " + explain_node(graph, anc, lang, units))
    return out
