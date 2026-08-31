// The decisions of ONE section, and the conversation about each of them.
//
// The roadmap: "focus on specific sections of the fence and get only the
// decisions related to the selected section. change, comment or start a
// conversation about it!" The inspector answers per ELEMENT — click a post, see
// why it is there. This answers per SECTION, which is the question a person
// asks while looking at the drawing rather than at one post.
//
// It reads the section from `#run-select`, the picker this panel already has:
// "focus on a section" is a selection the side column makes, and a second
// picker for the same idea is how two parts of one panel come to disagree about
// which section is in front of you.
//
// **The boundary, which this file is the surface of.** A comment is verbatim
// human text and changes no fence. It becomes an interpretation, an
// interpretation becomes a PROPOSAL, and only a human confirms — so nothing
// here writes an override, and the thread says so rather than implying a
// comment did something.

import { apiGet, apiSend, esc } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { on, state } from "./state.js";
import { currentUnit, sentence } from "./units.js";

// The conversation, indexed by the decision it is about — fetched once per
// render rather than once per decision, because a section has many decisions
// and a request each would be a burst on every selection change.
let threads = new Map();
// which decision's comment box is open; only one at a time, because a form per
// decision is a wall of inputs on a section with twenty of them
let openOn = null;

export function initSectionDecisions() {
  const rerender = () => { render(); };
  on("selection-changed", rerender);
  on("result-changed", () => { openOn = null; render(); });
  on("locale-changed", rerender);
  on("units-changed", rerender);
  on("project-loaded", () => { openOn = null; render(); });
}

// `state.selection` only. The run picker is `inspector.js`'s DOM, and reading it
// from here worked solely because `app.js` happens to register that module
// first — reorder two lines and this panel renders empty. Modules communicate
// through state.js (CLAUDE.md), so inspector now SAYS which section is selected
// rather than merely showing it.
function sectionId() {
  return state.selection?.runId || null;
}

export async function render() {
  const host = document.getElementById("section-decisions");
  if (!host) return;
  const section = sectionId();
  if (!state.result || !section) {
    host.innerHTML = `<h3>${esc(t("decisions.title"))}</h3>
      <div class="meta">${esc(t("decisions.empty"))}</div>`;
    return;
  }
  const runId = state.result.run.id;
  // What this render is FOR. Two awaits follow, and a section switch or a
  // locale flip landing between them would paint the previous section's
  // decisions over the current one — the same in-flight rule structure-data.js
  // already lives by ("a fetch belongs to the run it was STARTED for").
  const forWhat = `${runId}\u0000${section}`;
  const stale = () => forWhat !== `${state.result?.run?.id}\u0000${sectionId()}`;
  let body;
  try {
    body = await apiGet(
      `/api/runs/${runId}/sections/${encodeURIComponent(section)}/decisions`
      + `?lang=${currentLocale()}&units=${currentUnit()}`);
  } catch (err) {
    // 409 topology_changed is a real state, not a failure: the drawing moved on
    // and "the decisions for section A" is no longer a true sentence. Named,
    // exactly as structure-data.js names the same refusal.
    if (stale()) return;
    // ...and the site-conditions twin of it: the fence was laid out to a site
    // the project no longer describes, so "the decisions for section A" is no
    // more true than it is over a moved drawing.
    const detail = String(err?.message || "");
    const key = detail.includes("topology_changed") ? "decisions.stale"
      : detail.includes("site_conditions_changed") ? "decisions.stale_site"
      : null;
    host.innerHTML = `<h3>${esc(t("decisions.title"))}</h3>
      <div class="meta">${esc(t(key || "decisions.unavailable"))}</div>`;
    return;
  }
  if (stale()) return;
  let earlier = 0;
  try {
    // The WHOLE project's conversation, split by the run it was made in. A
    // decision node id is positional, so a comment from another run cannot be
    // matched to a decision in this one — but it must not be silently absent
    // either, or the panel offers to "start" a conversation two people already
    // had. Counted and named at the PANEL, which is the finest grain at which
    // the statement is true.
    const all = await apiGet(`/api/projects/${state.projectId}/corrections`);
    if (stale()) return;
    threads = new Map();
    for (const c of all) {
      if (!c.decision_ref) continue;
      if (c.generation_run_id === runId)
        threads.set(c.decision_ref, [...(threads.get(c.decision_ref) || []), c]);
      else earlier += 1;
    }
  } catch {
    threads = new Map();   // the decisions are still worth showing without them
  }
  if (stale()) return;
  host.innerHTML = sectionHtml(body, threads, openOn, earlier);
  wire(host, runId);
}

/** Pure: `(section decisions, decision id -> its comments, which form is open)`
 *  -> the panel's markup. Takes its state as arguments rather than reading the
 *  module's, so node can render it exactly as the browser does — which is where
 *  the escaping rule and the empty cases are actually checked. */
/** What a cited fact's SOURCE was worth (§1.4 `admitted_by`), as one chip.
 *
 *  Rendered only where a verdict EXISTS. An absent verdict means the fact was
 *  never judged — an authored company rule has no document behind it — and
 *  showing "unverified" there would be a claim about provenance that does not
 *  apply, while showing nothing at all is the honest reading: this is our rule,
 *  not somebody's document.
 *
 *  `source_class` and `curation_level` are the two things obligation §3.3.2 asks
 *  to be shown wherever a value appears. The class is an OPEN registry, so it is
 *  rendered as data inside `<bdi>` and never used to build a locale key — the day
 *  the other side registers a class we have no word for, it must read as its own
 *  name rather than as a missing translation. */
function admittedHtml(verdict) {
  if (!verdict) return "";
  const level = t("decisions.curation_level").replace(
    "{level}", `<span class="num">${esc(String(verdict.curation_level))}</span>`);
  return `<span class="admitted" data-level="${esc(String(verdict.curation_level))}"
    >${esc(t("decisions.admitted_by"))}
    <bdi class="sku">${esc(verdict.source_class)}</bdi> · ${level}</span>`;
}

export function sectionHtml(body, threads = new Map(), openOn = null, earlier = 0) {
  const admitted = body.admitted || {};
  const rows = body.decisions.map((d) => {
    const said = threads.get(d.node_id) || [];
    return `<div class="decision" data-node="${esc(d.node_id)}">
      <div class="expl" dir="auto">${esc(d.sentence)}</div>
      ${d.governed_by.length
        ? `<div class="meta">${esc(t("decisions.governed_by"))}
             ${d.governed_by.map((ref) => `<span class="sku">${esc(ref)}</span>${
                 admittedHtml(admitted[ref])}`).join(", ")}</div>`
        : ""}
      ${said.map(commentHtml).join("")}
      ${said.length
        ? `<div class="meta">${esc(t("decisions.comment_note"))}</div>`
        : ""}
      <div class="decision-actions">
        <button data-act="say" data-node="${esc(d.node_id)}">${
          esc(said.length ? t("decisions.add_comment")
                          : t("decisions.start_conversation"))}</button>
      </div>
      ${openOn === d.node_id ? formHtml(d.node_id) : ""}
    </div>`;
  }).join("");
  // `sentence`, not `esc(t(key, params))`: these two carry a latin run id and a
  // figure INTO Hebrew prose, and escaping the finished sentence leaves the
  // parameter without a direction of its own — the id and the comma after it
  // reorder on screen, in the language the app opens in. Escape the template,
  // then drop each param in `<bdi>`-wrapped (units.js; warnings.js does the
  // same behind its code lookup).
  return `<h3>${esc(t("decisions.title"))}</h3>
    <div class="meta">${sentence("decisions.hint", { section: body.section_id })}</div>
    ${earlier
      ? `<div class="meta">${sentence("decisions.earlier", { count: earlier })}</div>`
      : ""}
    ${threadCount(threads)
      ? `<div class="decision-actions"><button data-act="propose">${
          esc(t("decisions.propose"))}</button>
         <span class="meta" id="propose-said"></span></div>`
      : ""}
    ${body.decisions.length ? rows
      : `<div class="meta">${esc(t("decisions.none_here"))}</div>`}`;
}

function threadCount(threads) {
  let n = 0;
  for (const said of threads.values()) n += said.length;
  return n;
}


/** Verbatim, and rendered as TEXT through `esc` — the existing convention for
 *  human prose (`tabs.js`'s `.verbatim`). What a person wrote is not markup. */
export function commentHtml(c) {
  return `<div class="verbatim" dir="auto">“${esc(c.comment || "")}”
    <span class="meta"><bdi>${esc(c.author || "")}</bdi>
      ${esc((c.created_at || "").slice(0, 16).replace("T", " "))}</span></div>`;
}

function formHtml(nodeId) {
  return `<div class="inline-form" data-form="${esc(nodeId)}">
    <input data-f="comment" dir="auto" size="30"
      placeholder="${esc(t("decisions.comment_placeholder"))}">
    <button data-act="send" data-node="${esc(nodeId)}" class="primary">${
      esc(t("decisions.send"))}</button>
    <button data-act="cancel">${esc(t("common.cancel"))}</button>
    <div class="meta">${esc(t("decisions.comment_note"))}</div>
  </div>`;
}

function wire(host, runId) {
  host.querySelectorAll('[data-act="say"]').forEach((b) => {
    b.addEventListener("click", () => {
      openOn = openOn === b.dataset.node ? null : b.dataset.node;
      render();
    });
  });
  host.querySelectorAll('[data-act="cancel"]').forEach((b) => {
    b.addEventListener("click", () => { openOn = null; render(); });
  });
  const propose = host.querySelector('[data-act="propose"]');
  if (propose) {
    propose.addEventListener("click", async () => {
      // The boundary, walked rather than merely described. A comment becomes a
      // knowledge CANDIDATE, which is inert until a person reviews it — the
      // route stores nothing active and this button cannot either.
      const said = host.querySelector("#propose-said");
      said.textContent = t("decisions.proposing");
      let made = [];
      try {
        made = await apiSend("POST",
          `/api/projects/${state.projectId}/propose-knowledge`, {});
      } catch {
        said.textContent = t("decisions.propose_failed");
        return;
      }
      // Nothing proposed is the ORDINARY answer and has to say so: the proposer
      // reads a narrow vocabulary, and a button that silently did nothing would
      // read as broken rather than as "nothing here suggests a rule yet".
      said.textContent = made.length
        ? t("decisions.proposed", { count: made.length })
        : t("decisions.proposed_none");
    });
  }
  host.querySelectorAll('[data-act="send"]').forEach((b) => {
    b.addEventListener("click", async () => {
      const form = host.querySelector(`[data-form="${CSS.escape(b.dataset.node)}"]`);
      const said = form?.querySelector('[data-f="comment"]')?.value.trim();
      if (!said) return;
      await apiSend("POST", `/api/projects/${state.projectId}/corrections`, {
        generation_run_id: runId,
        decision_ref: b.dataset.node,
        // the run scopes the ref: a decision id means what it means only within
        // the run that generated it (`core/ids.py`)
        before: {}, after: {}, comment: said, author: "expert",
      });
      openOn = null;
      render();
    });
  });
}
