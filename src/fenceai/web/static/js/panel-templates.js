// The starter panels behind "New model".
//
// Cloning a model into a fresh independent draft is a shipped feature
// (`duplicateOf`), reached by picking a row out of the library. These are the
// same thing under a friendlier door: a handful of curated STRUCTURES, each
// arriving as an ordinary draft with no special "templated" state to track or
// escape — which is how "a template never locks you in" comes for free.
//
// Five structures, not five product families. The design named privacy
// tongue-and-groove, picket, semi-privacy dogear, horizontal slat and ranch
// rail; T&G and dogear are board PROFILES, which this model does not express
// and this catalog does not supply, and a starter naming a SKU that does not
// exist previews as a gap and is then refused at the publish gate. So each card
// is a structure the mechanism CAN say, over products that exist —
// `test_panel_templates_module.py` holds both halves of that by running every
// one of them through `validate_model` and the real preview.
//
// Built out of the same `default*` factories the "+ Add" buttons call, never out
// of literals: two constructions of a slot are how the buttons and the cards
// come to build different documents.

import {
  defaultEligibleMember, defaultFixing, defaultInfill, defaultMember,
  defaultSlot, blankModel,
} from "./panel-model.js";

const RAIL = "RAIL-3000";
const BOARD = "SLAT-100";
const SCREW = "SCREW-S10";

/** A frame slot of `count` evenly-spaced rails, cut post centre to post centre.
 *
 * `count_param` is set for the same reason `M-LEGACY` sets it: rail count is
 * DEFEASIBLE knowledge, so a company rule about it must still be able to win. */
function rails(count) {
  const slot = defaultSlot("rail");
  slot.placement.count = count;
  slot.placement.count_param = "rails_per_span";
  slot.requirement.length_rule = "centre_to_centre";
  slot.requirement.eligibility.members.push(defaultEligibleMember(RAIL));
  return slot;
}

/** One board of the pattern. `gap` MAY be negative — that is an overlap. */
function board(key, { width_mm = 100, gap_after_mm = 20, face_offset_mm = 0 } = {}) {
  const member = defaultMember(key);
  member.width_mm = width_mm;
  member.gap_after_mm = gap_after_mm;
  member.face_offset_mm = face_offset_mm;
  member.requirement.eligibility.members.push(defaultEligibleMember(BOARD));
  return member;
}

function fixings(basis, qty = 1) {
  const fixing = defaultFixing("screw");
  fixing.basis = basis;
  fixing.qty_per_basis = qty;
  fixing.requirement.eligibility.members.push(defaultEligibleMember(SCREW));
  return fixing;
}

function starter(id, name_i18n, spec) {
  const model = blankModel(id);
  model.name_i18n = name_i18n;
  model.default_spec = spec;
  return model;
}

export const TEMPLATES = [
  {
    key: "slat",
    id_base: "M-SLAT-NEW",
    build: (id) => starter(id, { en: "Vertical slat", he: "שלבים אנכיים" }, {
      frame: [rails(2)],
      infill: { ...defaultInfill(), pattern: [board("slat")] },
      fixings: [fixings("per_member_crossing")],
    }),
  },
  {
    key: "picket",
    id_base: "M-PICKET",
    // the same structure with the boards spread apart: a picket fence is a slat
    // fence whose gap is bigger than a hand, and the model says so in one number
    build: (id) => starter(id, { en: "Picket", he: "כלונסאות" }, {
      frame: [rails(2)],
      infill: {
        ...defaultInfill(), justification: "center", excess: "truncate",
        pattern: [board("picket", { gap_after_mm: 70 })],
      },
      fixings: [fixings("per_member_crossing")],
    }),
  },
  {
    key: "board_on_board",
    id_base: "M-BOARD-ON-BOARD",
    // The case the NEGATIVE gap exists for. Two boards in the cycle, each set
    // 30 mm inside its neighbour and one of them held back off the face: the
    // pattern still advances 70 mm per board, which is the bound
    // `validate_model` holds, and there is no line of sight through it.
    build: (id) => starter(id, { en: "Board on board", he: "קרש על קרש" }, {
      frame: [rails(2)],
      infill: {
        ...defaultInfill(),
        pattern: [
          board("board_back", { gap_after_mm: -30, face_offset_mm: -18 }),
          board("board_front", { gap_after_mm: -30 }),
        ],
      },
      fixings: [fixings("per_member_crossing")],
    }),
  },
  {
    key: "horizontal",
    id_base: "M-HORIZONTAL",
    // boards across the bay rather than up it, cut to the opening between the
    // posts — the other axis, and the one a slat model cannot be turned into by
    // changing a number
    build: (id) => starter(id, { en: "Horizontal boards", he: "קרשים אופקיים" }, {
      frame: [],
      infill: {
        ...defaultInfill(), orientation: "horizontal",
        pattern: [horizontalBoard()],
      },
      fixings: [fixings("per_member", 2)],
    }),
  },
  {
    key: "ranch",
    id_base: "M-RANCH",
    // no infill at all: three rails and the view through them
    build: (id) => starter(id, { en: "Ranch rail", he: "מסילות פתוחות" }, {
      frame: [rails(3)],
      infill: null,
      fixings: [fixings("per_frame_member", 4)],
    }),
  },
];

/** A board laid across the bay: its length rule reads the OPENING rather than
 *  the panel height, which is what "horizontal" changes about a board. */
function horizontalBoard() {
  const member = board("board", { gap_after_mm: 25 });
  member.requirement.length_rule = "clear_between_posts";
  return member;
}
