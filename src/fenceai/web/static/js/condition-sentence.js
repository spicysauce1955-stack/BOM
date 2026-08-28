// A variant's condition, as a sentence.
//
// The stored shape is and stays `Expr` (knowledge/ast.py), evaluated by the
// backend's own evaluator. Every shipped model and every fixture conditions a
// variant one way — a field compared to a literal — so THAT shape gets words
// ("applies when panel height is at least 1800 mm") and everything else keeps
// the raw JSON box it has today.
//
// `readSentence` returning null is the parity guarantee, not a failure: a
// condition this cannot say is left alone rather than rewritten into one it can.
// An authoring surface that silently narrowed a document it merely opened is the
// same defect as a select that drops a value the schema allows.

// The facts a bay carries when its variant is chosen (`PanelContext.condition_ctx`).
// A path nothing supplies is a variant that never fires: `choose_variant` reads
// a missing field as "not applicable" rather than as an error, so the author
// would get silence and no way to see why.
//
// Pinned to exactly the NUMERIC facts a bay carries (see
// `test_every_numeric_fact_a_bay_carries_is_offered`) — a bay's own facts, not
// the site's. `site.*` is a separate list below, on purpose: it is a bool and
// an enum, not a millimetre, and folding it in here would make this export mean
// two different things depending on which entry you were looking at.
export const CONDITION_FIELDS = ["panel.height_mm", "panel.width_mm"];

// `site.*` dimensions a variant can condition on (`SiteConditions`,
// `project/site.py`) — bound into `condition_ctx()` alongside `panel.*` but
// never a number, so kept off `CONDITION_FIELDS` rather than widening what that
// export promises. `frost_depth_mm`, `jurisdiction` and `code_edition` are
// deliberately not here: out of scope for this authoring surface.
export const SITE_CONDITION_FIELDS = ["site.hvhz", "site.exposure_category"];

// The token vocabulary for an "enum" field — `SiteConditions.exposure_category`
// exactly (`Literal["B", "C", "D"]`, `project/site.py`).
export const CONDITION_ENUM_OPTIONS = { "site.exposure_category": ["B", "C", "D"] };

const FIELD_TYPES = { "site.hvhz": "boolean", "site.exposure_category": "enum" };

/** "number" | "boolean" | "enum" for a field path. "number" is the default —
 *  every `panel.*_mm` field, and anything this sentence does not recognise —
 *  so a document written by hand, or a future field this module has not
 *  caught up to, keeps today's numeric coercion instead of silently doing
 *  something new. */
export function fieldType(path) {
  return FIELD_TYPES[path] ?? "number";
}

// `Cmp.cmp` exactly, in the order a person reaches for them.
export const CONDITION_CMPS = [">=", ">", "==", "!=", "<", "<="];

// A boolean or an enum has no ordering an author should reach for: `panel.
// height_mm >= 1800` says something, `site.hvhz >= true` does not, and offering
// it is the same trap as the blank-value one below — accepted, and meaningless.
const EQUALITY_CMPS = ["==", "!="];

/** The comparisons that make sense for a field's type — all six for a number,
 *  equality only for a boolean or an enum. */
export function cmpsFor(path) {
  return fieldType(path) === "number" ? CONDITION_CMPS : EQUALITY_CMPS;
}

/** The three fields of a field-to-literal comparison, or null. */
export function readSentence(expr) {
  if (!expr || expr.op !== "cmp") return null;
  if (expr.left?.op !== "field" || typeof expr.left.path !== "string") return null;
  if (expr.right?.op !== "lit") return null;
  if (!CONDITION_CMPS.includes(expr.cmp)) return null;
  return { path: expr.left.path, cmp: expr.cmp, value: expr.right.value };
}

/** ... and the expression they mean.
 *
 * A half-typed NUMBER becomes 0 rather than "": `{op:"lit", value:""}`
 * validates and then compares a string to a millimetre, which is an
 * expression that is accepted and means nothing — the worst of the three
 * outcomes, because it neither works nor complains. A boolean field writes an
 * actual JSON boolean and an enum field an actual string token, for exactly
 * the same reason one level up: `site.hvhz == 0` also validates and also
 * means nothing, because `Number(value)` on a checkbox's "on"/"" is not the
 * bool the evaluator compares `site.hvhz` against.
 *
 * `value` arrives as whatever the caller's own control already produces —
 * `valueInput.checked` (a real bool) for a boolean field, a `<select>`'s
 * `.value` (already a string) for an enum one — so this does not re-coerce
 * either: a fallback for a shape no reachable caller sends is untested by
 * construction and reads as more defensive than it is. */
export function writeSentence({ path, cmp, value }) {
  const cmps = cmpsFor(path);
  const okCmp = cmps.includes(cmp) ? cmp : cmps[0];
  const kind = fieldType(path);
  let lit;
  if (kind === "boolean") {
    lit = value === true;
  } else if (kind === "enum") {
    lit = value;
  } else {
    const n = Number(value);
    lit = Number.isFinite(n) ? Math.round(n) : 0;
  }
  return {
    op: "cmp", cmp: okCmp,
    left: { op: "field", path },
    right: { op: "lit", value: lit },
  };
}
