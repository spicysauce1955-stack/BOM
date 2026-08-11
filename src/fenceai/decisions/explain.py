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
    {"pin_post", "suppress_post", "force_post_sku", "force_mounting", "force_vertical"}
)
_INPUT_FACT_ACTIONS = frozenset(
    {"topology_node", "run_geometry", "gate_event", "knowledge_version"}
)

# Display units: the graph always stores int mm (ADR-0002); prose may render them
# in the reader's chosen unit, exactly like the UI (web/static/js/units.js).
_UNIT_WORDS = {"en": {"mm": "mm", "cm": "cm"}, "he": {"mm": 'מ"מ', "cm": 'ס"מ'}}
_LENGTH_LISTS = frozenset({"widths", "alt_widths"})

# Enum VALUES that appear as words inside a sentence get translated; ids, SKUs and
# knowledge refs never pass through here (they stay verbatim Latin in every
# language). English is identity — the enum name IS the English word.
_ENUM_PARAMS = frozenset({"kind", "mounting", "surface", "surfaces", "vertical", "mode", "chosen"})
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
        "choose_vertical_mode": "Vertical mode '{mode}' chosen at {slope_permille}‰ grade.",
        "resolve_max_span": "Maximum span resolved to {value_mm} {u}.",
        "resolve_span_quantities": (
            "Quantities per span: {rails_per_span} rails, {screws_per_span} screws."
        ),
        "resolve_demand_products": (
            "Demand products: rail {rail_sku}, screws {screw_sku}, "
            "concrete {concrete_sku}, caps {cap_sku}."
        ),
        "place_gate": "Gate opening from {start_mm} to {end_mm} {u}.",
        "select_gate_kit": "Gate kit {kit_sku} selected.",
        "knowledge_conflict": (
            "Conflict on '{slot}' between {contenders} — surfaced for review."
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
        "excessive_step": (
            "Step of {step_mm} {u} exceeds the buildable maximum of {max_mm} {u} — "
            "needs an engineered solution."
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
        "insufficient_post_length": (
            "Post needs {required_mm} {u} ({exposed_mm} exposed + {embed_mm} embedded) "
            "but the product is only {available_mm} {u} long."
        ),
        "sliver_span": (
            "Span {span} is {width_mm} {u} — below the preferred minimum of {min_mm} {u}."
        ),
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
        "choose_vertical_mode": "נבחר מצב אנכי '{mode}' בשיפוע {slope_permille}‰.",
        "resolve_max_span": "המפתח המרבי נקבע ל-{value_mm} {u}.",
        "resolve_span_quantities": (
            "כמויות לכל מפתח: {rails_per_span} מוטות, {screws_per_span} ברגים."
        ),
        "resolve_demand_products": (
            "מוצרי הדרישה: מוט {rail_sku}, ברגים {screw_sku}, "
            "בטון {concrete_sku}, כיפות {cap_sku}."
        ),
        "place_gate": "פתח שער מתחנה {start_mm} עד {end_mm} {u}.",
        "select_gate_kit": "נבחרה ערכת שער {kit_sku}.",
        "knowledge_conflict": "סתירה על '{slot}' בין {contenders} — הוצפה לבדיקה.",
        "node_surface_disagreement": (
            "קטעים שנפגשים בצומת {node_id} חלוקים לגבי משטח הבסיס ({surfaces}); "
            "נעשה שימוש ב-'{chosen}'."
        ),
        "tilted_stepped": (
            "הקטע {run_id} משלב עמודים נטויים ({mode}) עם פאנלים מדורגים — "
            "בדקו את כוונת התכנון."
        ),
        "place_post_tilt": " העמוד נטוי {tilt_deg}° מהאנך.",
        "excessive_step": (
            'מדרגה של {step_mm} {u} חורגת מהמקסימום הניתן לביצוע ({max_mm} {u}) — '
            "נדרש פתרון הנדסי."
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
        "insufficient_post_length": (
            'העמוד דורש {required_mm} {u} ({exposed_mm} חשוף + {embed_mm} מוטמן) '
            'אך אורך המוצר הוא {available_mm} {u} בלבד.'
        ),
        "sliver_span": (
            "המפתח {span} הוא {width_mm} {u} — מתחת למינימום המועדף של {min_mm} {u}."
        ),
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
        if k.endswith("_mm"):
            out[k] = _display(v, units)
        elif k in _LENGTH_LISTS and isinstance(v, (list, tuple)):
            out[k] = [_display(x, units) for x in v]
        elif k in _ENUM_PARAMS:
            out[k] = (", ".join(_word(x, lang) for x in v)
                      if isinstance(v, (list, tuple)) else _word(v, lang))
        else:
            out[k] = v
    out["u"] = _UNIT_WORDS.get(lang, _UNIT_WORDS["en"]).get(units, units)
    return t[key].format(**out)


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
        case "resolve_demand_products":
            base = _fmt(t, "resolve_demand_products", lang, units,
                rail_sku=p.get("rail_sku"), screw_sku=p.get("screw_sku"),
                concrete_sku=p.get("concrete_sku"), cap_sku=p.get("cap_sku"),
            )
        case "place_gate":
            base = _fmt(t, "place_gate", lang, units, start_mm=p.get("start_mm"), end_mm=p.get("end_mm"))
        case "select_gate_kit":
            base = _fmt(t, "select_gate_kit", lang, units, kit_sku=p.get("kit_sku"))
        case "knowledge_conflict":
            base = _fmt(t, "knowledge_conflict", lang, units,
                slot=p.get("slot"), contenders=", ".join(p.get("contenders", []))
            )
        case "node_surface_disagreement":
            base = _fmt(t, "node_surface_disagreement", lang, units,
                node_id=p.get("node_id"), surfaces=list(p.get("surfaces", [])),
                chosen=p.get("chosen"),
            )
        case "tilted_stepped":
            base = _fmt(t, "tilted_stepped", lang, units, run_id=p.get("run_id"), mode=p.get("mode"))
        case "excessive_step":
            base = _fmt(t, "excessive_step", lang, units, step_mm=p.get("step_mm"), max_mm=p.get("max_mm"))
        case "excessive_gap":
            base = _fmt(t, "excessive_gap", lang, units, gap_mm=p.get("gap_mm"), max_mm=p.get("max_mm"))
        case "max_height_exceeded":
            base = _fmt(t, "max_height_exceeded", lang, units,
                height_mm=p.get("height_mm"), max_mm=p.get("max_mm"))
        case "gate_on_slope":
            base = _fmt(t, "gate_on_slope", lang, units,
                slope_permille=p.get("slope_permille"), max_permille=p.get("max_permille"))
        case "insufficient_post_length":
            base = _fmt(t, "insufficient_post_length", lang, units,
                required_mm=p.get("required_mm"), exposed_mm=p.get("exposed_mm"),
                embed_mm=p.get("embed_mm"), available_mm=p.get("available_mm"))
        case "sliver_span":
            base = _fmt(t, "sliver_span", lang, units,
                span=p.get("span"), width_mm=p.get("width_mm"), min_mm=p.get("min_mm")
            )
        case action if action in _OVERRIDE_ACTIONS:
            base = _fmt(t, "override_applied", lang, units,
                override_id=p.get("override_id"), action=node.action
            )
        case action if action in _INPUT_FACT_ACTIONS:
            base = _fmt(t, "input_fact", lang, units, action=node.action, payload=p)
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
