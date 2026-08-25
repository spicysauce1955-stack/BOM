// The fence model as DATA: the vocabularies a select may offer, and the shape of
// every row an "+ Add" button appends.
//
// Pure — no DOM, no state, no fetch — because three surfaces now read it: the
// editor's lifecycle (model-editor.js), the inspector that renders a selected
// element's controls (panel-inspector.js), and the starter templates
// (panel-templates.js). A second copy of the fixing bases is two answers to
// "which fixing bases exist", and they diverge the first time one of them is
// extended.
//
// TWO KINDS OF VOCABULARY LIVE HERE, and the difference is the whole point:
//
//   * the CLOSED ones below are `Literal` in `fencemodel/model.py` AND a branch
//     somewhere, so extending one is a release either way. They are written out
//     here and pinned against the schema in both directions by
//     tests/web/test_panel_model_module.py.
//   * the OPEN ones — length rules, fixing bases, objective presets — are the
//     three the engine-architecture spec (§3, §4) moves behind handler
//     registries, where adding a member is a REGISTRATION and not a release.
//     Writing those out here would mean a `per_corner` basis that the API
//     accepts and the editor cannot offer, until a person notices a red test and
//     hand-edits an array. So they are not written out: `setVocabularies()` is
//     fed `GET /api/vocabularies` and `vocabulary()` hands them out.
//
// Still no fetch in this module — builder-ui.js owns the request, exactly as it
// owns the catalog and part caches — which is what keeps this file runnable in
// node with nothing stubbed.

// --- the OPEN vocabularies: served, never guessed -----------------------------

let SERVED = null;

/** Take the answer to `GET /api/vocabularies`. Anything else — a rejected
 *  fetch, a body of the wrong shape — puts the editor back in "I do not know
 *  what the backend accepts", which is a state it can render honestly. */
export function setVocabularies(payload) {
  SERVED = payload && typeof payload === "object" && !Array.isArray(payload)
    ? payload : null;
}

/** The members of one served vocabulary, or NULL for "unknown".
 *
 *  Null is not an empty list and the callers must not collapse the two. An empty
 *  select reads as "you never chose one"; a stale hardcoded fallback reads as a
 *  working choice and then 422s on save. Null means the editor declines to guess
 *  — see `choice()` in panel-inspector.js, which renders it as a disabled
 *  control that still shows what the document already says.
 *
 *  A served-but-EMPTY list answers null too: there is nothing to offer either
 *  way, and the honest rendering of "nothing to offer" is the same one. */
export function vocabulary(name) {
  const v = SERVED?.[name];
  return Array.isArray(v) && v.length ? v : null;
}

// One accessor per served vocabulary, rather than three exported name strings.
// The old `LENGTH_RULES` / `BASES` were ARRAYS: a name string exported under the
// same identifier would let `values.includes(v)` quietly become a substring test
// in any call site that was not updated. Renaming instead makes a missed call
// site a module-load error naming the export, which is the loudest failure
// available and the one worth having.
export const lengthRules = () => vocabulary("length_rules");
export const fixingBases = () => vocabulary("fixing_bases");
export const objectivePresets = () => vocabulary("objective_presets");

// --- the closed vocabularies, read from fencemodel/model.py -------------------
export const ROLES = ["post", "cap", "concrete", "rail", "screw", "infill", "spacer"];
export const PLACEMENT_KINDS = ["distributed", "from_bottom", "from_top", "fraction"];
export const JUSTIFICATIONS = ["start", "end", "center", "spread_to_fit"];
// `trim_last` and `extension_clip` are schema-expressible and NOT built
// (`model.py::_unsupported_features`: fit_pattern treats both exactly as
// `truncate`, which is a different BOM). Offering them would author a model the
// publish gate then refuses, so the editor offers what the resolver honours —
// and an existing document carrying one still shows it, rather than being
// silently rewritten to something it does not say.
export const EXCESS = ["truncate", "space"];
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

// `part_id: ""` is the schema's own default and means *this slot names no part
// yet*. Written out rather than left off so the picker has a field to set and
// `eligibilitySource` a field to read on a row the "+ Add" button just made —
// an absent key and an empty one answer the same, and only one of them is what
// the document says.
export function defaultRequirement(role) {
  return {
    part_id: "", role, qty: 1, length_rule: null, overlap_mm: 0,
    option_axis: null, sku_by_option: {}, eligibility: defaultEligibility(),
    // What ships inside this piece, and what those pieces supply in this panel.
    // `contained` is FILLED by the backend from the part and is round-tripped
    // rather than authored here — sending it back empty on a part-named slot is
    // harmless (resolution overwrites it) and sending it back MISSING is how the
    // editor silently drops a field on every save.
    contained: [], credits: {},
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

// --- the part picker's logic, kept pure so node can test it ------------------
// panel-inspector.js is DOM; this is not. The same split base-top.js already has,
// and the reason the picker can be tested without a browser.

/** Which of four shapes a slot is. Mirrors `PartRequirement.eligibility_source`
 *  exactly — two answers to one question would drift, and this one decides which
 *  pane an author sees. `part_id` first: resolution fills `predicate` on a
 *  part-named slot, and a resolved document must not read as rule-authored. */
export function eligibilitySource(req) {
  if (!req) return "unspecified";
  if (req.part_id) return "part";
  if (req.eligibility?.predicate) return "authored_predicate";
  if (req.eligibility?.members?.length) return "authored_members";
  return "unspecified";
}

// The dimension fields each holder authors, and that a PART fills once one is
// named. Mirrors `_refuse_authored_dimensions`' two call sites in
// `fencemodel/model.py` — `FrameSlot("thickness_mm")` and
// `Member("width_mm", "thickness_mm")` — and it is the same exclusion `role` is,
// one level up: the fields sit on the HOLDER rather than on the requirement, so
// `PartRequirement._part_or_authored` cannot see them and a second validator has
// to. A fixing rule and the post carry none, so they are absent rather than empty.
//
// The editor reads this twice: to HIDE the control (a width field on a slot whose
// part owns the width is an invitation to a 422 nobody can explain) and to CLEAR
// what a holder already carries when a part is chosen, in the same act.
export const PART_DIMENSIONS = {
  frame: ["thickness_mm"],
  infill: ["width_mm", "thickness_mm"],
};

/** The version of a part that a document naming `id` MEANS.
 *
 *  Mirrors `PartLibrary.latest_active`, and it has to: `part_id` is unpinned on
 *  purpose (a slot stores `rail-38`, never `rail-38@v3`), so the backend resolves
 *  the newest ACTIVE version at generation. `/api/parts` returns EVERY version
 *  ascending, drafts and retired included — so taking the first row would show v1's
 *  facts beside a bay priced against v2, label an active part "not published" the
 *  moment someone drafted a v3, and list one id once per version in the picker.
 *
 *  The fallback is the highest version of any status, because a part that has only
 *  ever been a draft still EXISTS: rendering it as missing would tell the author
 *  their slot names nothing, which sends them to a different repair. */
export function latestPart(parts, id) {
  if (!id) return null;
  const rows = (parts || []).filter((p) => p.id === id);
  if (!rows.length) return null;
  const active = rows.filter((p) => p.status === "active");
  return (active.length ? active : rows)
    .reduce((best, p) => (p.version > best.version ? p : best));
}

/** Parts grouped by type, both levels sorted — a picker that reshuffles between
 *  renders makes an author lose their place.
 *
 *  ONE ENTRY PER ID, not per version. The picker's value is the bare `part_id`, so
 *  two versions of one part are two options that write the same thing and read as a
 *  duplicate the author has to guess between. Which version each row SHOWS is
 *  `latestPart`'s answer, so the option label and the chips below it are the same
 *  version the generator will resolve. */
export function partsByType(parts) {
  const byType = new Map();
  for (const id of new Set((parts || []).map((p) => p.id))) {
    const part = latestPart(parts, id);
    if (!part) continue;
    if (!byType.has(part.type)) byType.set(part.type, []);
    byType.get(part.type).push(part);
  }
  return [...byType.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([type, list]) => ({
      type, parts: list.slice().sort((a, b) => a.id.localeCompare(b.id)),
    }));
}

/** What the part requires, one chip per declared fact. The author picked a name;
 *  this is how they see what the name MEANS without leaving the slot.
 *
 *  STRUCTURED, never prose. An earlier draft returned a `text` built here, and
 *  the text was English — in a Hebrew-first app, from the one module that may
 *  not import i18n (this file is import-free so node can run it, which is the
 *  whole reason the picker's logic is testable at all). So the fact travels and
 *  panel-inspector.js renders it through `model.chip.<agree>`: the phrasing is
 *  data in both bundles, and no sentence is assembled where no locale exists. */
export function specChips(part) {
  return (part?.spec || []).map((f) => ({
    key: f.key, agree: f.agree, value: f.value ?? null, unit: f.unit ?? null,
  }));
}

/** Everything the slot pane needs about the part, joined from the slot, the
 *  library and the preview the editor already fetched.
 *
 *  `candidates` and `chosen` come off `PreviewPart.eligible_skus` and `.sku` — no
 *  new request, because the candidate set is already on the wire.
 *
 *  `counted` says whether the preview ANSWERED for this slot at all, and it is not
 *  the same question as `candidates === 0`. `preview_panel` emits rows for the
 *  frame, the infill and the fixings only — never for M-VINYL's post or cap — so a
 *  slot with no row has an UNKNOWN candidate set, not an empty one. Reported apart
 *  because a zero printed for "nobody asked" reads as a measurement, and the two
 *  slots the rule-authored pane exists FOR are exactly the ones with no row. */
export function partSummary(req, { parts = [], preview = null, slotKey = "" } = {}) {
  const source = eligibilitySource(req);
  const part = latestPart(parts, req?.part_id);
  const row = (preview?.parts || []).find((p) => p.slot_key === slotKey)
    || (preview?.unsupplied || []).find((p) => p.slot_key === slotKey) || null;
  return {
    source,
    part,
    chips: specChips(part),
    counted: row !== null,
    candidates: (row?.eligible_skus || []).length,
    eligibleSkus: row?.eligible_skus || [],
    chosen: row?.sku || "",
    // a slot naming a part the library does not have. Reported, never rendered as
    // an empty select — an empty select reads as "you never chose one".
    missing: source === "part" && !part,
  };
}
