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
// locale keys (`agent.not_evaluated` vs `agent.none`). There is a THIRD
// sentence between them and it is the one that goes missing quietly: "I
// looked, I produced, and everything I produced was refused" —
// `agent.all_refused`, read off the counters (spec §8b). The section carries a
// PERSISTENT heading (`agent.title`) in every state, including both of those:
// a sentence with no subject reads as a stray fragment, not as an answer.
import { apiGet, esc } from "./api.js";
import { t } from "./i18n.js";
import { on, state } from "./state.js";
import { toDisplayValue, tu } from "./units.js";

const MARKER_KEY = {
  measured: "agent.marker.measured",
  read: "agent.marker.read",
  inferred: "agent.marker.inferred",
};

// A `read` claim's `text` here is `DesignPoint.label` (`generator.py`'s
// `" · ".join(str(w) for w in widths)`) — the SAME raw-millimetre dimension
// string `choices.js`'s `widthsLabel` converts, unit-suffixes and isolates,
// for the panel sitting directly beside this one. Anything else (every
// `inferred` claim, always prose) is left as plain escaped text — converting
// a sentence through a millimetre-to-centimetre table would mangle it.
const WIDTHS_LABEL = /^\d+(?:\s*·\s*\d+)*$/;

function claimTextHtml(claim) {
  const text = String(claim.text ?? "");
  if (!WIDTHS_LABEL.test(text.trim())) return esc(text);
  const widths = text.split("·").map((w) => toDisplayValue(Number(w.trim())));
  // `choices.widths` — the exact key/template the neighbouring panel already
  // renders the same shape of value through: `"{widths} {u}"`, unit-suffixed
  // and LTR-isolated so the digits do not reorder in a Hebrew (RTL) sentence.
  return `<bdi class="num">${esc(tu("choices.widths", { widths: widths.join(" · ") }))}</bdi>`;
}

function claimRow(claim) {
  const marker = t(MARKER_KEY[claim.marker] || "agent.marker.inferred");
  return `<li class="agent-claim agent-claim--${esc(claim.marker)}">
    <span class="agent-claim__marker">${esc(marker)}</span>
    <span class="agent-claim__text">${claimTextHtml(claim)}</span>
  </li>`;
}

function proposalCard(proposal) {
  const claims = (proposal.claims || []).map(claimRow).join("");
  return `<article class="agent-proposal">
    <ul class="agent-claims">${claims}</ul>
    <p class="agent-note">${esc(t("agent.stub_notice"))}</p>
  </article>`;
}

// The section's own name, present in EVERY state this module renders — the
// heading a bare "Could not check" was missing (finding I2): without it the
// sentence has no subject, which is the same defect this slice exists to
// prevent, one level up.
function sectionHtml(bodyHtml) {
  return `<h3>${esc(t("agent.title"))}</h3>${bodyHtml}`;
}

function emptyHtml(key) {
  return sectionHtml(`<p class="agent-empty">${esc(t(key))}</p>`);
}

/** Pure rendering from a `TaskResult` (or `null`, meaning "the agent's view
 *  on this run could not be established" — evaluated:false or an unreadable
 *  response; a run that does not exist yet is `agent.no_run`, decided by the
 *  caller before this is ever reached). Exported so it can be exercised
 *  without a live server, the same split `handover.js` keeps between its
 *  `render()` and its `refresh()`. */
export function renderAdvice(result, host) {
  if (!host) return;
  if (!result || result.evaluated !== true) {
    // "I did not look" — never rendered as "nothing to report".
    host.innerHTML = emptyHtml("agent.not_evaluated");
    return;
  }
  const proposals = result.proposals || [];
  if (!proposals.length) {
    // The THIRD state, and spec §8b is the reason it needs its own sentence:
    // "an agent whose proposals nobody keeps looks exactly like an agent that
    // is working." The agent looked, it produced, and every one of them was
    // refused by a §6 check as an agent defect — which is not "nothing to
    // suggest here". `dropped` and `claims_refused` cross the wire from
    // `run.py` precisely so this surface can tell the two apart; a panel that
    // reads neither turns `produced: 3, dropped: 3` into "all clear", which is
    // the silent failure the counters were built on day one to prevent.
    const refused = (result.dropped || 0) + (result.claims_refused || 0);
    host.innerHTML = emptyHtml(refused ? "agent.all_refused" : "agent.none");
    return;
  }
  host.innerHTML = sectionHtml(proposals.map(proposalCard).join(""));
}

// The advice route's only two documented refusals (tests/api/test_advice_route.py):
// a 404 whose `detail` is a bare English string ("run X not found"), and a 409
// whose `detail.code` is `"topology_changed"` (the same refusal `/structure`
// gives when the drawing moved under a stored run). The 409 gets the SAME
// locale key `structure-data.js` and friends already use for it; every other
// failure — including the 404's raw English sentence — reduces to the same
// sentence as `evaluated: false`, because from this panel's chair the effect
// is identical: nothing can be said about this run's advice right now. The
// 404's body is never parsed for content, only checked for a `code` that
// is not there — `apiGet` throws it as the rejected promise's message, and
// this function is the only place that ever reads that message.
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
let failKey = null;  // locale key for "no run" / a failed fetch, or null

function currentRunId() {
  return state.result?.run?.id || null;
}

function container() {
  return typeof document === "undefined" ? null : document.getElementById("agent-advice");
}

function render() {
  const el = container();
  if (!el) return;
  if (failKey) { el.innerHTML = emptyHtml(failKey); return; }
  renderAdvice(cache, el);
}

async function refresh() {
  const runId = currentRunId();
  cache = null;
  failKey = null;
  if (!runId) {
    // Its own sentence (finding I2), distinct from the other two it is easily
    // confused with: `evaluated: false` means the agent NEVER LOOKED (an empty
    // view slice, or the adapter failed) — never "it looked and found nothing",
    // which is `evaluated: true` with no proposals; and a failed fetch means we
    // could not ask. Here there is nothing yet to ask about.
    failKey = "agent.no_run";
    render();
    return;
  }
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
  // Re-render the CACHED result in the new language/unit; no need to
  // re-fetch. `units-changed` matters here because I1's fix gave this panel
  // a real dependency on the display-unit preference (`choices.js` and ten
  // other panels already subscribe for the same reason) — without it, one
  // click of the units button leaves this panel's dimensions on the OLD
  // unit while the choices panel beside it has already switched.
  on("locale-changed", render);
  on("units-changed", render);
}
