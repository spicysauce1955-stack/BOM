// The model library as the UI sees it: one cached listing, and the one place
// that knows how a model id becomes a name in the active language.
//
// No DOM and no rendering. Three surfaces need the same two answers — the Panel
// tab's picker, the canvas aside's "what is this fence built from" row, and the
// fence_model event popover on the tool rail — and a second copy of the cache
// would let them disagree about which models exist. Same shape as
// structure-data.js: a shared read-through cache the renderers consult.

import { apiGet } from "./api.js";
import { currentLocale, t } from "./i18n.js";

let listingPromise = null;

export function loadModelListing() {
  listingPromise ??= apiGet("/api/fence-models")
    // a failed fetch must not poison the cache: clear it so the next opener
    // retries, exactly as editor.js does for the catalog
    .catch(() => { listingPromise = null; return []; });
  return listingPromise;
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
