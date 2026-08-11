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

# One template per decision-graph action, per language. `_alt` / `_wall` / `_step`
# are optional sentence fragments appended when the payload carries those fields;
# `_governed` / `_defeated` / `_pinned` are the provenance suffixes.
TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "place_post": (
            "Post at station {station_mm} mm ({kind}, {mounting} mount, {sku}) "
            "on {surface} base."
        ),
        "layout_spans": "Segment {segment} divided into spans {widths}.",
        "layout_spans_alt": (
            " Alternative {alt_widths} was rejected because of {rejected_because}."
        ),
        "create_span": (
            "Span of {width_mm} mm, height {height_mm} mm, vertical mode "
            "'{vertical}' (height source: {height_source})."
        ),
        "create_span_wall": (
            " Height reduced by the wall top ({wall_top_mm} mm, event {wall_event})."
        ),
        "create_span_step": " Steps {step_mm} mm against the grade.",
        "choose_vertical_mode": "Vertical mode '{mode}' chosen at {slope_permille}‰ grade.",
        "resolve_max_span": "Maximum span resolved to {value} mm.",
        "resolve_span_quantities": (
            "Quantities per span: {rails_per_span} rails, {screws_per_span} screws."
        ),
        "resolve_demand_products": (
            "Demand products: rail {rail_sku}, screws {screw_sku}, "
            "concrete {concrete_sku}, caps {cap_sku}."
        ),
        "place_gate": "Gate opening from {start_mm} to {end_mm} mm.",
        "select_gate_kit": "Gate kit {kit_sku} selected.",
        "knowledge_conflict": (
            "Conflict on '{slot}' between {contenders} — surfaced for review."
        ),
        "node_surface_disagreement": (
            "Runs meeting at node {node_id} disagree on base surface ({surfaces}); "
            "'{chosen}' was used."
        ),
        "excessive_step": (
            "Step of {step_mm} mm exceeds the buildable maximum of {max_mm} mm — "
            "needs an engineered solution."
        ),
        "excessive_gap": (
            "Stepped span leaves a {gap_mm} mm gap underneath (limit {max_mm} mm)."
        ),
        "max_height_exceeded": (
            "Plumb height reaches {height_mm} mm at the downhill end — above the "
            "{max_mm} mm limit."
        ),
        "gate_on_slope": (
            "Gate opening sits on a {slope_permille}‰ slope (limit {max_permille}‰) "
            "— the ground needs leveling."
        ),
        "insufficient_post_length": (
            "Post needs {required_mm} mm ({exposed_mm} exposed + {embed_mm} embedded) "
            "but the product is only {available_mm} mm long."
        ),
        "sliver_span": (
            "Span {span} is {width_mm} mm — below the preferred minimum of {min_mm} mm."
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
            "עמוד בתחנה {station_mm} מ\"מ ({kind}, עיגון {mounting}, {sku}) "
            "על בסיס {surface}."
        ),
        "layout_spans": "המקטע {segment} חולק למפתחים {widths}.",
        "layout_spans_alt": " החלופה {alt_widths} נדחתה בגלל {rejected_because}.",
        "create_span": (
            "מפתח ברוחב {width_mm} מ\"מ, גובה {height_mm} מ\"מ, מצב אנכי "
            "'{vertical}' (מקור הגובה: {height_source})."
        ),
        "create_span_wall": (
            " הגובה הופחת בשל ראש הקיר ({wall_top_mm} מ\"מ, אירוע {wall_event})."
        ),
        "create_span_step": " מדורג ב-{step_mm} מ\"מ כנגד השיפוע.",
        "choose_vertical_mode": "נבחר מצב אנכי '{mode}' בשיפוע {slope_permille}‰.",
        "resolve_max_span": "המפתח המרבי נקבע ל-{value} מ\"מ.",
        "resolve_span_quantities": (
            "כמויות לכל מפתח: {rails_per_span} מוטות, {screws_per_span} ברגים."
        ),
        "resolve_demand_products": (
            "מוצרי הדרישה: מוט {rail_sku}, ברגים {screw_sku}, "
            "בטון {concrete_sku}, כיפות {cap_sku}."
        ),
        "place_gate": "פתח שער מתחנה {start_mm} עד {end_mm} מ\"מ.",
        "select_gate_kit": "נבחרה ערכת שער {kit_sku}.",
        "knowledge_conflict": "סתירה על '{slot}' בין {contenders} — הוצפה לבדיקה.",
        "node_surface_disagreement": (
            "קטעים שנפגשים בצומת {node_id} חלוקים לגבי משטח הבסיס ({surfaces}); "
            "נעשה שימוש ב-'{chosen}'."
        ),
        "excessive_step": (
            'מדרגה של {step_mm} מ"מ חורגת מהמקסימום הניתן לביצוע ({max_mm} מ"מ) — '
            "נדרש פתרון הנדסי."
        ),
        "excessive_gap": (
            'הפאנל המדורג משאיר מרווח של {gap_mm} מ"מ מתחתיו (המגבלה {max_mm} מ"מ).'
        ),
        "max_height_exceeded": (
            'הגובה האנכי מגיע ל-{height_mm} מ"מ בקצה הנמוך — מעל המגבלה של {max_mm} מ"מ.'
        ),
        "gate_on_slope": (
            "פתח השער יושב על שיפוע של {slope_permille}‰ (המגבלה {max_permille}‰) — "
            "יש לפלס את הקרקע."
        ),
        "insufficient_post_length": (
            'העמוד דורש {required_mm} מ"מ ({exposed_mm} חשוף + {embed_mm} מוטמן) '
            'אך אורך המוצר הוא {available_mm} מ"מ בלבד.'
        ),
        "sliver_span": (
            "המפתח {span} הוא {width_mm} מ\"מ — מתחת למינימום המועדף של {min_mm} מ\"מ."
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


def explain_node(graph: DecisionGraph, node: DecisionNode, lang: str = "en") -> str:
    t = TEMPLATES.get(lang, TEMPLATES["en"])
    governed = _refs(graph, node, "governed_by")
    defeated = _refs(graph, node, "defeated")
    p = node.payload
    match node.action:
        case "place_post":
            base = t["place_post"].format(
                station_mm=p.get("station_mm"), kind=p.get("kind"),
                mounting=p.get("mounting"), sku=p.get("sku"), surface=p.get("surface"),
            )
        case "layout_spans":
            alt = p.get("alternatives") or []
            base = t["layout_spans"].format(segment=p.get("segment"), widths=p.get("widths"))
            if alt:
                base += t["layout_spans_alt"].format(
                    alt_widths=alt[0]["widths"], rejected_because=alt[0]["rejected_because"]
                )
        case "create_span":
            base = t["create_span"].format(
                width_mm=p.get("width_mm"), height_mm=p.get("height_mm"),
                vertical=p.get("vertical"), height_source=p.get("height_source"),
            )
            if "adjusted_by_wall_profile" in p:
                base += t["create_span_wall"].format(
                    wall_top_mm=p.get("wall_top_mm"), wall_event=p["adjusted_by_wall_profile"]
                )
            if "step_mm" in p:
                base += t["create_span_step"].format(step_mm=p["step_mm"])
        case "choose_vertical_mode":
            base = t["choose_vertical_mode"].format(
                mode=p.get("mode"), slope_permille=p.get("slope_permille")
            )
        case "resolve_max_span":
            base = t["resolve_max_span"].format(value=p.get("value"))
        case "resolve_span_quantities":
            base = t["resolve_span_quantities"].format(
                rails_per_span=p.get("rails_per_span"), screws_per_span=p.get("screws_per_span")
            )
        case "resolve_demand_products":
            base = t["resolve_demand_products"].format(
                rail_sku=p.get("rail_sku"), screw_sku=p.get("screw_sku"),
                concrete_sku=p.get("concrete_sku"), cap_sku=p.get("cap_sku"),
            )
        case "place_gate":
            base = t["place_gate"].format(start_mm=p.get("start_mm"), end_mm=p.get("end_mm"))
        case "select_gate_kit":
            base = t["select_gate_kit"].format(kit_sku=p.get("kit_sku"))
        case "knowledge_conflict":
            base = t["knowledge_conflict"].format(
                slot=p.get("slot"), contenders=", ".join(p.get("contenders", []))
            )
        case "node_surface_disagreement":
            base = t["node_surface_disagreement"].format(
                node_id=p.get("node_id"), surfaces=", ".join(p.get("surfaces", [])),
                chosen=p.get("chosen"),
            )
        case "excessive_step":
            base = t["excessive_step"].format(step_mm=p.get("step_mm"), max_mm=p.get("max_mm"))
        case "excessive_gap":
            base = t["excessive_gap"].format(gap_mm=p.get("gap_mm"), max_mm=p.get("max_mm"))
        case "max_height_exceeded":
            base = t["max_height_exceeded"].format(
                height_mm=p.get("height_mm"), max_mm=p.get("max_mm"))
        case "gate_on_slope":
            base = t["gate_on_slope"].format(
                slope_permille=p.get("slope_permille"), max_permille=p.get("max_permille"))
        case "insufficient_post_length":
            base = t["insufficient_post_length"].format(
                required_mm=p.get("required_mm"), exposed_mm=p.get("exposed_mm"),
                embed_mm=p.get("embed_mm"), available_mm=p.get("available_mm"))
        case "sliver_span":
            base = t["sliver_span"].format(
                span=p.get("span"), width_mm=p.get("width_mm"), min_mm=p.get("min_mm")
            )
        case action if action in _OVERRIDE_ACTIONS:
            base = t["override_applied"].format(
                override_id=p.get("override_id"), action=node.action
            )
        case action if action in _INPUT_FACT_ACTIONS:
            base = t["input_fact"].format(action=node.action, payload=p)
        case _:
            base = t["generic"].format(action=node.action, payload=p)
    if governed:
        base += t["_governed"].format(refs=", ".join(governed))
    if defeated:
        base += t["_defeated"].format(refs=", ".join(defeated))
    if node.status == "pinned":
        base += t["_pinned"]
    return base


def explain_element(graph: DecisionGraph, element_id: str, lang: str = "en") -> list[str]:
    """Why does this element exist / look the way it does? Rendered from the graph."""
    out: list[str] = []
    for node in graph.nodes_for_element(element_id):
        out.append(explain_node(graph, node, lang))
        for anc in graph.ancestors(node.id):
            if anc.kind in ("input_fact", "rule_firing", "override_applied", "conflict"):
                out.append("  ← " + explain_node(graph, anc, lang))
    return out
