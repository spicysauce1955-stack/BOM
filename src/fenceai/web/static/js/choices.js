// The open questions this plan carries, and the answers it was not built with.
//
// A choice set is the FIFTH kind (spec §3): a hard constraint says *must*, a
// preference says *nicer if*, an objective says *minimise this*, an override
// says *the engine got this wrong here* — and a choice set says **two right
// answers**. Nothing was wrong, so nothing here writes an override; neither
// point is nicer, so nothing here writes a preference. The only honest resolver
// is a person, or the stated default.
//
// **Answering does NOT generate.** Generation stays behind the explicit button
// (spec §16), so a click writes the selection, reloads the PROJECT and marks the
// answer PENDING — the same treatment a dropped post gets. `state.result` is
// left exactly as it was: the plan on screen is still the plan that was built,
// and saying otherwise by silently re-running would be a different lie from the
// one where the row springs back.
//
// **Obligation 5 lives in `valueLabel`.** "Convert units once, at the boundary,
// and keep the source lexeme for display": a footing row published as `24"` is
// shown as `24" (610 mm)`, because a panel showing only our millimetres has
// thrown away the thing a reader checks against — and inventing a lexeme where
// the publisher gave none is worse than showing none.
//
// The two label functions are exported for the node test (`deltaLabel`,
// `valueLabel`) because they are the parts that are wrong at 3 a.m.: a sign, a
// plural, and an obligation. The renderer is DOM and belongs in the smoke suite.
//
// Design: docs/superpowers/specs/2026-09-03-design-choices-and-placement-design.md

import { apiSend, esc } from "./api.js";
import { pushSnapshot } from "./history.js";
import { t } from "./i18n.js";
import { on, reloadProject, state } from "./state.js";
import { sentence, toDisplayValue, tu } from "./units.js";

// Axes are OPEN (spec §5.3) — a point carries only what it differs on — so this
// list is a display ORDER and never a filter. It exists because the backend
// builds `delta` from a Python set intersection, whose iteration order is not
// stable across processes: without a sort the same question would print its
// axes in a different order after a server restart.
const AXIS_ORDER = ["posts", "bays", "boards", "cuts", "pieces",
                     "concrete_l", "holes", "warnings"];

const axisRank = (k) => {
  const i = AXIS_ORDER.indexOf(k);
  return i < 0 ? AXIS_ORDER.length : i;
};

/** What choosing this point would change, relative to what was built.
 *
 *  An EMPTY delta says "no material change" and not nothing: a blank row reads
 *  as a panel that failed to load, and the whole point of the row is that the
 *  two answers cost the same. The minus is U+2212, not a hyphen — these sit
 *  beside numbers in a Hebrew-first UI, and a hyphen-minus there is a dash. */
export function deltaLabel(point) {
  const delta = (point && point.delta) || {};
  const keys = Object.keys(delta)
    .filter((k) => Number(delta[k]) !== 0)
    .sort((a, b) => axisRank(a) - axisRank(b) || (a < b ? -1 : a > b ? 1 : 0));
  if (!keys.length) return t("choices.delta.none");
  return keys.map((k) => axisTerm(k, Number(delta[k]))).join(" · ");
}

function axisTerm(axis, n) {
  const abs = Math.abs(n);
  const key = `choices.delta.${axis}.${abs === 1 ? "one" : "other"}`;
  let word = t(key, { n: abs });
  // An axis the bundles have no word for is still a real measurement — the
  // registry is open. Print the count and the axis name rather than dropping a
  // difference the reader is being asked to weigh.
  if (word === key) word = t("choices.delta.unknown", { n: abs, axis });
  return (n < 0 ? "−" : "+") + word;
}

/** One bound parameter value, in the publisher's words and then in ours.
 *
 *  Contract obligation 5. `24" (610 mm)` where a lexeme exists; a bare
 *  `610 mm` where it does not — never an invented lexeme, which would attribute
 *  a form of words to a publisher who never used it. Our half converts to the
 *  reader's display unit like every other length; the lexeme never does,
 *  because it is a quotation. */
export function valueLabel(point, key) {
  const value = point?.bindings?.[key];
  const lexeme = point?.lexemes?.[key];
  if (!Number.isFinite(Number(value))) return lexeme ? String(lexeme) : "";
  return lexeme
    ? tu("choices.value_with_lexeme", { lexeme, value_mm: value })
    : tu("choices.value", { value_mm: value });
}

// A width list in the reader's display unit. The backend's `label` is raw
// millimetres joined with a dot — correct as an id, wrong as a rendered length
// the moment somebody works in centimetres.
function widthsLabel(point) {
  const widths = point.widths || [];
  if (!widths.length) return String(point.label || "");
  return tu("choices.widths",
            { widths: widths.map((w) => toDisplayValue(w)).join(" · ") });
}

function paramLabel(param) {
  const key = `choices.binding.${param}`;
  const word = t(key);
  return word === key ? param : word;   // unknown parameter: show it raw, never blank
}

// Does this stored answer name this point? A selection carries WHAT was chosen
// (spec §12) — the widths or the bindings — never the name of the generator that
// proposed it, so the comparison is on values.
function pointIsSelected(point, selection) {
  if (!selection) return false;
  const widths = point.widths || [];
  if (widths.length || (selection.widths || []).length)
    return JSON.stringify(widths) === JSON.stringify(selection.widths || []);
  const keys = Object.keys(point.bindings || {});
  if (!keys.length) return false;
  return keys.every((k) => (selection.bindings || {})[k] === point.bindings[k]);
}

function selectionFor(set, selections) {
  return (selections || []).find(
    (c) => c.choice_set === set.id && c.scope === set.scope) || null;
}

/** Render the questions into `host` — and into nothing else.
 *
 *  `sets === null` means there is no run to carry questions, which is a
 *  different sentence from a run that left none. */
export function renderChoices(host, sets, selections) {
  if (!host) return;
  const head = `<h3>${esc(t("choices.title"))}</h3>`;
  if (sets === null || sets === undefined) {
    host.innerHTML = `${head}<div class="meta">${esc(t("choices.no_run"))}</div>`;
    return;
  }
  if (!sets.length) {
    host.innerHTML = `${head}<div class="meta">${esc(t("choices.empty"))}</div>`;
    return;
  }
  host.innerHTML = head
    + `<div class="meta">${esc(t("choices.hint"))}</div>`
    + sets.map((set) => setHtml(set, selectionFor(set, selections))).join("");
}

function setHtml(set, selection) {
  const points = set.points || [];
  const withdraw = selection
    ? `<button type="button" class="choice-withdraw"
         data-set="${esc(set.id)}" data-scope="${esc(set.scope)}"
         >${esc(t("choices.withdraw"))}</button>`
    : "";
  return `<div class="choice-set" data-set="${esc(set.id)}"
      data-scope="${esc(set.scope)}" style="margin-block-start:8px">
    <h4 style="margin:6px 0 2px;font-size:13px">${esc(t(set.question))}</h4>
    <div class="meta" style="color:#64748b;font-size:12px">
      ${sentence("choices.scope", { scope: set.scope })}
      · ${esc(t("choices.options_n", { n: points.length }))}
    </div>
    ${points.map((p) => pointHtml(set, p, selection)).join("")}
    ${withdraw}
  </div>`;
}

function pointHtml(set, point, selection) {
  const chosen = pointIsSelected(point, selection);
  // PENDING is the honest state and the class carries it exactly once: the
  // person answered, the plan on screen was built from the other answer, and
  // nothing will change until they press generate.
  const pending = chosen && !point.is_default;
  const cls = ["choice-point", chosen ? "chosen" : "", pending ? "choice-pending" : ""]
    .filter(Boolean).join(" ");
  const badge = point.is_default
    ? `<span class="tag active">${esc(t("choices.built"))}</span>`
    : chosen ? `<span class="tag proposed">${esc(t("choices.answer_pending"))}</span>`
    : "";
  const by = chosen && selection?.author
    ? `<span class="meta" style="color:#64748b;font-size:11px">${
        esc(t("choices.chosen_by", { author: selection.author }))}</span>`
    : "";
  return `<button type="button" class="${cls}" data-set="${esc(set.id)}"
      data-scope="${esc(set.scope)}" data-point="${esc(point.id)}"
      aria-pressed="${chosen ? "true" : "false"}"
      style="display:block;inline-size:100%;text-align:start;margin:3px 0;
             padding:5px 8px;border:1px solid ${chosen ? "#2563eb" : "#d4dae2"};
             border-radius:6px;background:${chosen ? "#dbeafe" : "#fff"};
             font-size:13px;cursor:pointer">
    <span class="choice-answer">${answerHtml(point)}</span>
    <span class="choice-delta meta"
      style="color:#64748b;font-size:12px;margin-inline-start:6px"
      >${esc(deltaLabel(point))}</span>
    ${badge}${by}
  </button>`;
}

// The figures are LTR-isolated (`.num`) and the words are not: a Hebrew
// parameter label inside a `.num` span reorders on screen.
function answerHtml(point) {
  if ((point.widths || []).length)
    return `<bdi class="num">${esc(widthsLabel(point))}</bdi>`;
  const keys = Object.keys(point.bindings || {});
  if (!keys.length) return `<bdi class="num">${esc(String(point.label || ""))}</bdi>`;
  return keys.map((k) =>
    `${esc(paramLabel(k))} <bdi class="num">${esc(valueLabel(point, k))}</bdi>`
  ).join(" · ");
}

// ---------------------------------------------------------------- the panel

// The panel owns its own host: index.html is not this task's file, and a module
// that reaches into another module's subtree is the thing the module map
// forbids. Created once, beside the site conditions, which is the other
// project-level INPUT to a generation.
function ensureHost() {
  if (typeof document === "undefined") return null;
  let host = document.getElementById("choices");
  if (host) return host;
  const side = document.querySelector(".side-col");
  if (!side) return null;
  host = document.createElement("div");
  host.className = "panel";
  host.id = "choices";
  const after = document.getElementById("site-conditions");
  side.insertBefore(host, after ? after.nextSibling : side.firstChild);
  return host;
}

export function render() {
  const host = ensureHost();
  if (!host) return;
  renderChoices(host,
                state.result ? (state.result.choice_sets || []) : null,
                state.project ? (state.project.choices || []) : []);
  wire(host);
}

function wire(host) {
  for (const el of host.querySelectorAll(".choice-point"))
    el.addEventListener("click",
      () => choose(el.dataset.set, el.dataset.scope, el.dataset.point));
  for (const el of host.querySelectorAll(".choice-withdraw"))
    el.addEventListener("click", () => withdraw(el.dataset.set, el.dataset.scope));
}

function findPoint(setId, scope, pointId) {
  const set = (state.result?.choice_sets || [])
    .find((s) => s.id === setId && s.scope === scope);
  return [set, (set?.points || []).find((p) => p.id === pointId) || null];
}

async function choose(setId, scope, pointId) {
  const [, point] = findPoint(setId, scope, pointId);
  if (!point || !state.projectId) return;
  // pushSnapshot -> mutate -> save, in that order. `project.choices` is IN the
  // snapshot (history.js), so undoing this pops this gesture rather than the
  // drawing edit before it.
  pushSnapshot("choice");
  await apiSend("PUT", `/api/projects/${state.projectId}/choices`, {
    choice_set: setId, scope,
    widths: point.widths || [], bindings: point.bindings || {},
    author: "user",
  });
  // reloadProject, NEVER openProject: this is a non-topology mutation and
  // openProject would wipe the user's undo stack. It also leaves `state.result`
  // alone, which is the whole no-auto-generation rule in one line.
  await reloadProject();
}

async function withdraw(setId, scope) {
  if (!state.projectId) return;
  pushSnapshot("choice-withdraw");
  await apiSend("DELETE",
    `/api/projects/${state.projectId}/choices/${encodeURIComponent(setId)}`
    + `?scope=${encodeURIComponent(scope)}`);
  await reloadProject();
}

export function initChoices() {
  on("project-loaded", render);
  on("result-changed", render);
  on("locale-changed", render);
  on("units-changed", render);   // the same widths, in the reader's unit
  render();
}
