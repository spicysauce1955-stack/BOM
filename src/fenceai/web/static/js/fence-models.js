// The model library as the UI sees it: one cached listing, and the one place
// that knows how a model id becomes a name in the active language.
//
// No DOM and no rendering — it answers questions, and announces a change on the
// state.js bus, which is the only way modules speak. Four surfaces need the same
// answers: the Models tab's editor, the Panel tab's picker, the canvas aside's
// "what is this fence built from" row, and the fence_model event popover on the
// tool rail. A second copy of the cache would let them disagree about which
// models exist — which is why the editor renders THIS listing rather than
// fetching its own, even though it is the one surface that writes. Same shape as
// structure-data.js: a shared read-through cache the renderers consult.

import { apiGet } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { emit } from "./state.js";

let listingPromise = null;

export function loadModelListing() {
  listingPromise ??= apiGet("/api/fence-models")
    // a failed fetch must not poison the cache: clear it so the next opener
    // retries, exactly as editor.js does for the catalog
    .catch(() => { listingPromise = null; return []; });
  return listingPromise;
}

// A read-through cache is only correct while nothing writes behind it, and the
// model editor writes: publishing a version changes which models are
// SELECTABLE, so a picker still holding the old listing offers a model that no
// longer exists and hides one that now does.
//
// One function does the whole of it — drop the cache, re-read, announce —
// because correctness otherwise depends on every write site remembering all
// three, and this module is where "which models exist" is answered. The editor
// renders THIS listing rather than fetching its own, so there is one answer.
export async function refreshModelListing() {
  listingPromise = null;
  const listing = await loadModelListing();
  emit("fence-models-changed");
  return listing;
}

// A model's name in the active language, falling back to English and then to the
// id — never blank, and never English prose in a Hebrew-first UI when the model
// authored a Hebrew name.
export function modelName(row) {
  if (!row) return "";
  return row.name_i18n?.[currentLocale()] || row.name_i18n?.en || row.id;
}

// Only a PUBLISHED version can be chosen. A draft-only or fully retired model
// stays in the list — hiding it makes it look deleted, and "why is my model
// gone" is a worse question than "why can I not pick it" — but it is offered
// disabled, with the reason spelled out.
export const isSelectable = (row) =>
  !!row && row.active_version !== null && row.active_version !== undefined
  && row.status === "active";

export function modelOptionLabel(row) {
  const named = `${modelName(row)} (${row.id})`;
  return isSelectable(row) ? named : `${named} — ${t("panel.not_selectable")}`;
}

export function rowFor(listing, modelId) {
  return (listing || []).find((r) => r.id === modelId) || null;
}

/** What the WHOLE fence is built to — the project default and every model any
 *  stretch was actually sold as, in one verdict.
 *
 *  Audit B03. `What was sold` writes a `fence_model` interval event on the run;
 *  the canvas aside's row read `project.fence_model` alone, so a job with both
 *  stretches sold as M-SLAT reported *"No model chosen"* — while the handover
 *  sheet, three centimetres away, reported the job ready. `report/handover.py`
 *  emits `no_model_chosen` only when there is no default AND millimetres nothing
 *  covers, and two surfaces answering one question differently is the defect.
 *
 *  Pure over its argument, and it deliberately does NOT recompute coverage.
 *  `_uncovered_mm` is the handover sheet's job and belongs to the surface that
 *  reports completeness; a second copy of that arithmetic in JS would be a
 *  second answer to *"is this job complete?"*, which is the bug this fixes.
 *  This row answers only *what is it built to*.
 *
 *  `models` always carries the models found on stretches BESIDE the default —
 *  with a default set they are the exceptions to it, and without one they are
 *  the whole answer. An empty list with `kind: "none"` is nobody has said. */
export function projectModelState(project) {
  const chosen = project?.fence_model?.model_id || null;
  const perRun = new Set();
  for (const run of project?.topology?.runs || [])
    for (const ev of run.interval_events || [])
      if (ev.payload?.kind === "fence_model" && ev.payload.model_id)
        perRun.add(ev.payload.model_id);
  perRun.delete(chosen);
  // Sorted so the row reads the same on every render: a Set iterates in
  // insertion order, which is the order the events happen to sit in.
  const models = [...perRun].sort();
  if (chosen) return { kind: "default", model_id: chosen, models };
  if (!models.length) return { kind: "none", models: [] };
  return { kind: models.length === 1 ? "per_run" : "mixed", models };
}
