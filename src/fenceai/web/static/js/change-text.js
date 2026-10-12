// One change in a job's history, as a sentence — no DOM, no fetch, node-tested.
//
// A change arrives as `code + params` (fenceai/project/changes.py) and becomes
// `change.<code>` with its params dropped in. Three things happen to a param on
// the way, and they are the whole of this module:
//
//   * a WORD param is looked up in its own vocabulary — a job state, a surface,
//     a kind of landmark, an area of the job. Stored as the value the backend
//     uses, so the same row reads in Hebrew and English;
//   * a PERSON param — who a job was assigned to — is a user id, turned into a
//     name with the map the route hands over, never stored as a name;
//   * a LENGTH (`…_mm`) goes through `unitParams`, so it reads in the reader's
//     unit beside `{u}`, like every other length on screen.
//
// Everything is escaped and bidi-isolated by `sentence`'s rule: a Latin id
// inside a Hebrew sentence must not reorder the punctuation around it. A note's
// text is the salesperson's own words and goes through the same escape — and the
// substitution is ONE pass over the template, so a note that happens to contain
// `{section}` is shown as written rather than filled in.

import { esc } from "./api.js";
import { t } from "./i18n.js";
import { enumWord, unitParams } from "./units.js";

const STATE_PARAMS = new Set(["from_state", "to_state"]);
const SURFACE_PARAMS = new Set(["surface", "from_surface", "to_surface"]);
const PERSON_PARAMS = new Set(["from_person", "to_person"]);
// a blank here is "nobody had said", which must read as a dash, not as nothing
const BLANKABLE = new Set(["from", "to", "section", "from_model", "to_model", "model"]);

/** Who did it, for the line above a group of changes. `user:<id>` resolves by
 *  the route's map; anything else (`seed`, an agent) is the system. */
export function actorName(actor, names = {}) {
  if (names[actor]) return names[actor];
  if (String(actor).startsWith("user:")) return String(actor).slice(5);
  return t("change.system");
}

function word(change, key, value, names) {
  const code = change.code;
  if (STATE_PARAMS.has(key)) return t(`queue.status.${value}`);
  if (SURFACE_PARAMS.has(key)) return enumWord(value);
  if (PERSON_PARAMS.has(key)) return value ? (names[value] || value) : t("change.nobody");
  if (key === "landmark") return t(`context.kind.${value}`);
  if (key === "area") return t(`change.area.${value}`);
  if (key === "what") return t(`change.${code === "acknowledged" ? "ack" : "stated"}.${value}`);
  if (typeof value === "boolean") return t(value ? "common.yes" : "common.no");
  if (BLANKABLE.has(key) && (value === null || value === "")) return t("change.blank");
  // A section no longer drawn keeps the letter it had, and says so: no current
  // letter is its name (`changes.reletter`).
  if (key === "section" && change.params?.section_gone)
    return `${value} (${t("change.gone")})`;
  return value;
}

/** One change as HTML: the template escaped, each param escaped and isolated. */
export function changeHtml(change, { names = {} } = {}) {
  const code = change?.code || "";
  const key = `change.${code}`;
  let template = t(key);
  const params = {};
  if (template === key) {
    // an unknown code still says SOMETHING true rather than printing a key
    template = t("change.area_changed");
    params.area = code;
  } else {
    for (const [k, v] of Object.entries(change.params || {}))
      params[k] = k.endsWith("_mm") ? v : word(change, k, v, names);
  }
  const filled = unitParams(params);
  return esc(template).replace(/\{(\w+)\}/g, (whole, k) =>
    Object.hasOwn(filled, k) ? `<bdi>${esc(String(filled[k] ?? ""))}</bdi>` : whole);
}

/** Is this change a turn in WHOSE desk the job is on — drawn as a divider? */
export function isMilestone(change) {
  return change?.code === "status_changed";
}
