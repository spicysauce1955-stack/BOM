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
export const CONDITION_FIELDS = ["panel.height_mm", "panel.width_mm"];

// `Cmp.cmp` exactly, in the order a person reaches for them.
export const CONDITION_CMPS = [">=", ">", "==", "!=", "<", "<="];

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
 * A half-typed value becomes 0 rather than "": `{op:"lit", value:""}` validates
 * and then compares a string to a millimetre, which is an expression that is
 * accepted and means nothing — the worst of the three outcomes, because it
 * neither works nor complains. */
export function writeSentence({ path, cmp, value }) {
  const n = Number(value);
  return {
    op: "cmp", cmp: CONDITION_CMPS.includes(cmp) ? cmp : CONDITION_CMPS[0],
    left: { op: "field", path },
    right: { op: "lit", value: Number.isFinite(n) ? Math.round(n) : 0 },
  };
}
