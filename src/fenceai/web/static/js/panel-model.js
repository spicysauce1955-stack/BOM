// The fence model as DATA: the closed vocabularies the schema fixes, and the
// shape of every row an "+ Add" button appends.
//
// Pure — no DOM, no state, no fetch — because three surfaces now read it: the
// editor's lifecycle (model-editor.js), the inspector that renders a selected
// element's controls (panel-inspector.js), and the starter templates
// (panel-templates.js). A second copy of BASES is two answers to "which fixing
// bases exist", and they diverge the first time one of them is extended.
//
// The vocabularies are pinned against `fencemodel/model.py` in BOTH directions
// by tests/web/test_panel_model_module.py: a value offered and not in the schema
// is a save that 422s, and one in the schema and not here is a product line
// nobody can author.

// --- the closed vocabularies, read from fencemodel/model.py -------------------
export const ROLES = ["post", "cap", "concrete", "rail", "screw", "infill", "spacer"];
export const LENGTH_RULES = ["clear_between_posts", "centre_to_centre", "overlap",
  "panel_height",
  // the one rule that reads the "starts at" / "ends at" selects below; under any
  // other rule the schema now refuses a member that sets them
  "between_frame"];
export const PLACEMENT_KINDS = ["distributed", "from_bottom", "from_top", "fraction"];
export const JUSTIFICATIONS = ["start", "end", "center", "spread_to_fit"];
// `trim_last` and `extension_clip` are schema-expressible and NOT built
// (`model.py::_unsupported_features`: fit_pattern treats both exactly as
// `truncate`, which is a different BOM). Offering them would author a model the
// publish gate then refuses, so the editor offers what the resolver honours —
// and an existing document carrying one still shows it, rather than being
// silently rewritten to something it does not say.
export const EXCESS = ["truncate", "space"];
export const BASES = [
  "per_member_crossing", "per_member", "per_end_member",
  "per_gap", "per_frame_member", "per_panel",
];
export const APPROVALS = ["auto", "suggest_only"];
export const GRADES = ["residential", "commercial", "industrial"];
// `numeric` is schema-expressible and unbuilt, for the same reason `trim_last`
// is: nothing reads `Axis.kind`, and resolution answers every axis out of its
// declared `values`. W4 added the `_unsupported_features` entry that refuses it
// — this list is the other half of that change.
export const AXIS_KINDS = ["enum"];
// Knowledge params a count may defer to. The point of `count_param` is that
// rail count stays DEFEASIBLE knowledge — a company rule may still win it — so
// the field is offered as a param name and not as an authored integer.
export const COUNT_PARAMS = ["rails_per_span", "screws_per_span"];

export const SWATCH_RE = /^#[0-9a-fA-F]{6}$/;

// --- pure shapes (no DOM, no state): what a fresh row of each kind is --------

export function blankModel(id) {
  return {
    id, version: 1, name_i18n: {}, grade: "residential", status: "draft",
    height_support: { kind: "continuous", min_mm: 0, max_mm: 10000 },
    layout_policy: [], option_axes: [],
    default_spec: { frame: [], infill: null, fixings: [] },
    variants: [],
  };
}

export function defaultEligibility() {
  return { members: [] };
}

// The ONE place a member is built, called by the "+ Add product" button and by
// the test that judges its shape — a second literal in either would let them
// agree with each other while disagreeing with the schema.
//
// `kind` is not decoration: `Eligibility.members` is a discriminated union, so
// a member without it is a 422 `union_tag_not_found` on the whole document, and
// the author is told only "the action failed".
export function defaultEligibleMember(sku, priority = 1) {
  return { kind: "catalog_item", sku: sku || "", priority, approval: "auto" };
}

export function defaultRequirement(role) {
  return {
    role, qty: 1, length_rule: null, overlap_mm: 0,
    option_axis: null, sku_by_option: {}, eligibility: defaultEligibility(),
  };
}

export function defaultPlacement(kind) {
  switch (kind) {
    case "from_bottom": return { kind, offset_mm: 0 };
    case "from_top": return { kind, offset_mm: 0 };
    case "fraction": return { kind, permille: 500 };
    default:
      return { kind: "distributed", count: 2, count_param: null,
               bottom_inset_mm: 0, top_inset_mm: 0 };
  }
}

export function defaultSlot(key) {
  return {
    key, orientation: "horizontal", placement: defaultPlacement("distributed"),
    requirement: defaultRequirement("rail"),
  };
}

export function defaultMember(key) {
  return {
    key, width_mm: 100, thickness_mm: 0, face_offset_mm: 0, gap_after_mm: 20,
    base_ref: null, top_ref: null,
    requirement: { ...defaultRequirement("infill"), length_rule: "panel_height" },
  };
}

export function defaultInfill() {
  return {
    orientation: "vertical", pattern: [defaultMember("slat")],
    justification: "spread_to_fit", excess: "space", edge_margin_mm: 0,
    supply: "components",
  };
}

export function defaultFixing(key) {
  return {
    key, basis: "per_panel", qty_per_basis: 1, qty_param: null,
    requirement: defaultRequirement("screw"),
  };
}

export function defaultAxis(key) {
  return { key, label_i18n: {}, kind: "enum", values: [], available_when: null };
}

// A NEW variant starts from a condition that is already valid AST and already
// says something ("panels 1800 and taller"), because the alternative — an empty
// box — makes the first thing an author meets a 422 about a discriminator.
export function defaultVariant() {
  return {
    condition: {
      op: "cmp", cmp: ">=",
      left: { op: "field", path: "panel.height_mm" },
      right: { op: "lit", value: 1800 },
    },
    spec: { frame: [], infill: null, fixings: [] },
  };
}

// A published version is NEVER mutated: editing one opens a COPY, and the
// session that holds it carries no version, so the first save POSTs and the
// SERVER assigns the next free one. The copy keeps the source's `version`
// field — it is what the document said, the editor does not get to invent a
// number, and nothing sends this one anywhere as an instruction.
//
// DEEP, and that is the load-bearing half: a shallow copy shares `default_spec`
// with the document the library handed over, so the first keystroke would
// rewrite the panel an accepted quote was priced against — in memory, where
// nothing reports it.
export function draftCopyOf(model) {
  return { ...structuredClone(model), status: "draft" };
}

export function duplicateOf(model, newId) {
  return { ...structuredClone(model), id: newId, version: 1, status: "draft" };
}

// The spec the row editors are pointed at: the default panel, or one variant's.
export function specOf(model, index) {
  return index < 0 ? model.default_spec : model.variants[index]?.spec;
}

// --- which id a session may save under ---------------------------------------

// Ids are identifiers, never prose — no locale key. Uniqueness is not cosmetic:
// a POST reusing an existing id does not create a model, it opens the NEXT
// VERSION of that one, so duplicating twice would quietly turn the second copy
// into v2 of the first. Takes the listing rather than reading it, so the rule
// can be tested without a library.
export function freeId(base, rows = []) {
  const taken = new Set((rows || []).map((r) => r.id));
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

// The id already in the library, if the one being typed collides with it.
//
// Only a session that means to create a NEW model can collide. A draft copy of
// a published version also carries no version number, and its id is the
// existing model's ON PURPOSE — that is what makes the save land as that
// model's next version. Reading "no version yet" as "must be new" refuses
// exactly the save that "Edit" exists to make.
// True only while this session could still choose its id: it means to create a
// model AND has not yet been saved under one. After the first save the id is
// the model's own, so it is in the listing BY DEFINITION and asking again would
// refuse every later save of the thing just created.
export const canChooseId = (s) => !!s?.isNew && s.version === null;

// The id a save would collide with, or null. Pure, and exported, because the
// four session kinds are easy to collapse into a wrong rule: "no version yet"
// reads like "new", and a draft copy of a published version has no version
// either — refusing THAT is refusing the save "Edit" exists to make.
export function idCollision(session, rows) {
  if (!canChooseId(session)) return null;
  const id = (session.model?.id || "").trim();
  return (rows || []).some((row) => row.id === id) ? id : null;
}
