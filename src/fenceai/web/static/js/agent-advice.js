// The agent's suggestions for the current run — slice 1 of the advisory-agent
// framework (spec §5.3).
//
// It renders BESIDE the question it concerns and never replaces anything: a
// suggestion that stood in for a warning or a choice would let a wrong guess
// cost a record instead of a dismissal. This module owns `#agent-advice` and
// nothing else — it never reaches into the choice-set panel or any other
// module's DOM subtree.
//
// Slice 1 advises only. There is no keep/reverse here on purpose: a refusal
// that leaves no record lets the agent re-propose what was already refused,
// and the record arrives with slice 2.
//
// The distinction this whole slice exists to protect: `evaluated: false`
// ("I did not look") must never render as an empty proposal list ("nothing to
// report") — they are different sentences to a person, so they get different
// locale keys (`agent.not_evaluated` vs `agent.none`).
import { apiGet, esc } from "./api.js";
import { t } from "./i18n.js";
import { on, state } from "./state.js";

const MARKER_KEY = {
  measured: "agent.marker.measured",
  read: "agent.marker.read",
  inferred: "agent.marker.inferred",
};

function claimRow(claim) {
  const marker = t(MARKER_KEY[claim.marker] || "agent.marker.inferred");
  // `claim.text` is agent-authored — exactly the untrusted case `esc()` is for.
  return `<li class="agent-claim agent-claim--${esc(claim.marker)}">
    <span class="agent-claim__marker">${esc(marker)}</span>
    <span class="agent-claim__text">${esc(claim.text)}</span>
  </li>`;
}

function proposalCard(proposal) {
  const claims = (proposal.claims || []).map(claimRow).join("");
  return `<article class="agent-proposal">
    <h4>${esc(t("agent.title"))}</h4>
    <ul class="agent-claims">${claims}</ul>
    <p class="agent-note">${esc(t("agent.stub_notice"))}</p>
  </article>`;
}

function renderEmpty(host, key) {
  host.innerHTML = `<p class="agent-empty">${esc(t(key))}</p>`;
}

/** Pure rendering from a `TaskResult` (or `null`, meaning "could not be
 *  established at all" — no run, or a failed fetch). Exported so it can be
 *  exercised without a live server, the same split `handover.js` keeps
 *  between its `render()` and its `refresh()`. */
export function renderAdvice(result, host) {
  if (!host) return;
  if (!result || result.evaluated !== true) {
    // "I did not look" — never rendered as "nothing to report".
    renderEmpty(host, "agent.not_evaluated");
    return;
  }
  const proposals = result.proposals || [];
  if (!proposals.length) {
    renderEmpty(host, "agent.none");
    return;
  }
  host.innerHTML = proposals.map(proposalCard).join("");
}

// The advice route's only two documented refusals (tests/api/test_advice_route.py):
// a 404 whose `detail` is a bare English string ("run X not found"), and a 409
// whose `detail.code` is `"topology_changed"` (the same refusal `/structure`
// gives when the drawing moved under a stored run). The 409 gets the SAME
// locale key `structure-data.js` and friends already use for it; every other
// failure — including the 404's raw English sentence — reduces to the same
// sentence as `evaluated: false`, because from this panel's chair the effect is
// identical: nothing can be said about this run's advice right now. Neither
// branch ever reads the raw body text onto the page — `apiGet` already put it
// in the console for whoever needs it.
function errorKeyFor(err) {
  try {
    const detail = JSON.parse(String(err?.message || "")).detail;
    if (detail && detail.code === "topology_changed") return "error.topology_changed";
  } catch {
    /* not JSON, or no code — falls through to the generic case below */
  }
  return "agent.not_evaluated";
}

let cache = null;    // last successful TaskResult, or null
let failKey = null;  // locale key for the last failed fetch, or null

function currentRunId() {
  return state.result?.run?.id || null;
}

function container() {
  return typeof document === "undefined" ? null : document.getElementById("agent-advice");
}

function render() {
  const el = container();
  if (!el) return;
  if (failKey) { renderEmpty(el, failKey); return; }
  renderAdvice(cache, el);
}

async function refresh() {
  const runId = currentRunId();
  cache = null;
  failKey = null;
  if (!runId) { render(); return; }
  try {
    const result = await apiGet(`/api/runs/${encodeURIComponent(runId)}/advice`);
    if (currentRunId() !== runId) return;  // the run moved on while we waited
    cache = result;
  } catch (err) {
    if (currentRunId() !== runId) return;
    failKey = errorKeyFor(err);
  }
  render();
}

export function initAgentAdvice() {
  render();
  refresh();
  // Both events, like every other per-run panel (`handover.js`,
  // `structure-data.js`): `result-changed` fires on a fresh generation, but
  // persisting a topology EDIT clears `state.result` and fires only
  // `project-loaded` — without it this panel would keep showing advice about
  // a run the drawing has since moved past.
  on("project-loaded", refresh);
  on("result-changed", refresh);
  // Re-render the CACHED result in the new language; no need to re-fetch.
  on("locale-changed", render);
}
