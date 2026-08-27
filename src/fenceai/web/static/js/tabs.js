// Tab panels: annotations, knowledge, review queue, BOM, inventory.

import { apiGet, apiSend, esc } from "./api.js";
import {
  el, field, loadCatalogProducts, option, skuSelect, updateAdvancedUi,
} from "./builder-ui.js";
import { currentLocale, t } from "./i18n.js";
import { renderImpactReport } from "./impact.js";
import { emit, on, reloadProject, state } from "./state.js";
import {
  fmt, fmtLen, inputStep, money, roleWord, sentence, toDisplayValue, toMm, tu,
  unitLabel,
} from "./units.js";
import { loadStructure, sectionOf, tagOf } from "./structure-data.js";
import { gapsPanelHtml } from "./gaps.js";
import {
  modelWarningsHtml, productWarningRowHtml,
} from "./doc-warnings.js";
import { supplyProblemsHtml } from "./warnings.js";

export function initTabs() {
  document.querySelectorAll("#tabs button").forEach((btn) =>
    btn.addEventListener("click", () => {
      document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "knowledge") renderKnowledge();
      if (btn.dataset.tab === "review") renderCandidates();
      if (btn.dataset.tab === "bom") renderBom();
      emit("tab-changed", btn.dataset.tab);   // other tabs own their own rendering
    }));

  document.getElementById("btn-add-ann").addEventListener("click", async () => {
    const text = document.getElementById("ann-text").value.trim();
    if (!text) return;
    await apiSend("POST", `/api/projects/${state.projectId}/annotations`,
      { target_ref: document.getElementById("ann-target").value, text });
    document.getElementById("ann-text").value = "";
    await reloadProject();
  });
  const knowledgeBody = () => {
    let actions;
    if (kAdvancedOpen) {
      actions = parseActions(document.getElementById("k-actions").value);
      if (!actions) { alert(t("knowledge.actions_json_invalid")); return null; }
    } else {
      actions = builderActions;
    }
    return {
      object_id: document.getElementById("k-object").value.trim(),
      type: document.getElementById("k-type").value,
      title: document.getElementById("k-title").value, actions, author: "expert-admin",
    };
  };
  initKnowledgeBuilder();
  document.getElementById("btn-k-add-action").addEventListener("click", () => {
    builderActions.push(defaultActionFor("set_param"));
    renderBuilderRows();
  });
  document.getElementById("btn-k-advanced").addEventListener("click", () => {
    const ta = document.getElementById("k-actions");
    if (!kAdvancedOpen) {
      ta.value = JSON.stringify(builderActions, null, 2);
      kAdvancedOpen = true;
    } else {
      // NEVER gate the way out on the thing that is broken: invalid JSON used to
      // block save, impact preview AND this button, so the only escape from a
      // stray comma was a page reload. Offer the exit, discard on confirmation.
      const parsed = parseActions(ta.value);
      if (parsed) builderActions = parsed;
      else if (!confirm(t("knowledge.actions_json_discard"))) return;
      kAdvancedOpen = false;
      renderBuilderRows();
    }
    updateAdvancedUi("k-builder", "k-actions", "btn-k-advanced", kAdvancedOpen);
  });
  document.getElementById("btn-inv-add-row").addEventListener("click", async () => {
    if (!inventoryObj) return;
    const products = await loadCatalogProducts();
    inventoryObj.items.push({
      id: `inv_${Date.now()}`, sku: Object.keys(products).sort()[0] || "",
      kind: "full_stock", qty: 1, length_mm: null,
    });
    drawInventoryTable();
  });
  document.getElementById("btn-inv-advanced").addEventListener("click", () => {
    const ta = document.getElementById("inventory-json");
    if (!invAdvancedOpen) {
      if (inventoryObj) ta.value = JSON.stringify(inventoryObj, null, 2);
      invAdvancedOpen = true;
    } else {
      const parsed = parseInventory(ta.value);   // same escape hatch as the rule editor
      if (parsed) inventoryObj = parsed;
      else if (!confirm(t("inventory.json_discard"))) return;
      invAdvancedOpen = false;
      drawInventoryTable();
    }
    updateAdvancedUi("inventory-editor", "inventory-json", "btn-inv-advanced",
                     invAdvancedOpen, "inventory.back");
  });
  document.getElementById("btn-add-knowledge").addEventListener("click", async () => {
    const body = knowledgeBody();
    if (!body) return;
    await apiSend("POST", "/api/knowledge", body);
    renderKnowledge();
  });
  document.getElementById("btn-knowledge-impact").addEventListener("click", async () => {
    const body = knowledgeBody();
    if (!body) return;
    const out = document.getElementById("knowledge-impact-out");
    out.innerHTML = `<em>${t("impact.computing")}</em>`;
    renderImpactReport(out, await apiSend("POST", "/api/knowledge/preview-impact", body));
  });
  document.getElementById("btn-propose").addEventListener("click", async () => {
    const out = await apiSend("POST", `/api/projects/${state.projectId}/propose-knowledge`);
    alert(out.length ? t("review.proposed_n", { n: out.length }) : t("review.no_new"));
    renderCandidates();
  });
  document.getElementById("btn-save-inventory").addEventListener("click", async () => {
    let inv;
    if (invAdvancedOpen) {
      inv = parseInventory(document.getElementById("inventory-json").value);
      if (!inv) return alert(t("inventory.json_invalid"));
    } else {
      if (!inventoryObj) return;
      inv = inventoryObj;
    }
    await apiSend("PUT", `/api/projects/${state.projectId}/inventory`, inv);
    emit("inventory-saved");   // cut-piece provenance depends on the yard
    alert(t("inventory.saved"));
    await renderInventory();
  });

  on("project-loaded", () => {
    renderAnnTargets(); renderAnnotations(); renderInventory(); maybeRenderBom();
  });
  on("result-changed", maybeRenderBom);
  const relocalize = () => {
    renderAnnTargets(); renderAnnotations(); maybeRenderBom();
    if (builderActions) renderBuilderRows();
    if (inventoryObj) drawInventoryTable();
    if (document.getElementById("tab-knowledge").classList.contains("active")) renderKnowledge();
    if (document.getElementById("tab-review").classList.contains("active")) renderCandidates();
  };
  on("locale-changed", relocalize);
  on("units-changed", relocalize);   // same surfaces, different numbers
}

// The raw-JSON editors are two-way, so both parsers answer the same question:
// "can this text become the structured thing?" — null means no, and the caller
// decides whether that blocks a save (it does) or an exit (it must not).
function parseActions(text) {
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed : null;
  } catch { return null; }
}

function parseInventory(text) {
  try {
    const parsed = JSON.parse(text);
    return parsed && Array.isArray(parsed.items) ? parsed : null;
  } catch { return null; }
}

function renderAnnTargets() {
  const sel = document.getElementById("ann-target");
  sel.innerHTML = "";
  const o = document.createElement("option");
  o.value = "project";
  o.textContent = t("annotations.whole_project");
  sel.appendChild(o);
  for (const r of state.project?.topology.runs || []) {
    const opt = document.createElement("option");
    opt.value = `run:${r.id}`;
    opt.textContent = r.id;
    sel.appendChild(opt);
  }
}

function maybeRenderBom() {
  if (document.getElementById("tab-bom").classList.contains("active")) renderBom();
}

// ---------- BOM ----------
function lineName(products, line) {
  return products[line.sku]?.name_i18n?.[currentLocale()] || line.name;
}

async function renderBom() {
  const div = document.getElementById("bom-body");
  if (!state.result) { div.innerHTML = `<em>${t("bom.generate_first")}</em>`; return; }
  let data;
  try {
    data = await apiGet(`/api/runs/${state.result.run.id}/bom`);
  } catch (err) {
    // 409: the catalog moved since this run was generated — a real state, not a
    // failure (same shape as structure-data.js's topology_changed handling).
    // 400 run_predates_fence_model: likewise a nameable state, and localized by
    // its code rather than shown as the engine's raw English sentence.
    const msg = String(err?.message || "");
    const key = msg.includes("catalog_changed") ? "bom.catalog_changed"
      : msg.includes("run_predates_fence_model") ? "error.run_predates_fence_model"
      : null;
    if (!key) throw err;
    div.innerHTML = `<div class="panel meta">${esc(t(key))}</div>`;
    return;
  }
  const [products, quotes] = await Promise.all([
    loadCatalogProducts(),
    apiGet(`/api/projects/${state.projectId}/quotes`).catch(() => []),
    // The grouped panel names its rows from `structure-data.js`, and this tab
    // was the only consumer that neither awaited nor subscribed to it — so a
    // /structure fetch that resolved after this render left `run1` and raw span
    // ids on screen for good. `assembly.js` awaits it for the same reason.
    loadStructure().catch(() => null),
  ]);
  div.innerHTML = `<div class="panel">
      <button id="btn-save-quote" class="primary">${t("quote.save")}</button>
      <span id="quote-label-form" class="inline-form" hidden>
        <input id="quote-label-input" dir="auto" size="24"
          placeholder="${esc(t("quote.label_placeholder"))}">
        <button id="btn-quote-confirm" class="primary">${t("common.confirm")}</button>
        <button id="btn-quote-cancel">${t("common.cancel")}</button>
      </span>
    </div>`
    // ABOVE the priced table, because it changes how that table must be read:
    // an unresolved line is a part the fence needs and the total does not
    // include. `bom.warnings` and `unresolved` were populated by the API and
    // rendered by nothing, so the BOM was silently short a line.
    + supplyProblemsHtml(data.bom.warnings, data.unresolved)
    // ...and, above the same table, what the RUN could not resolve. A missing
    // line and a missing rule are two different questions with one answer
    // between them - "why is this BOM short?" - and reading only the first sends
    // the reader looking for a product when the hole is in the knowledge.
    + gapsPanelHtml(state.result?.strategy?.gaps)
    + quotesHtml(quotes)
    + groupedBomHtml(data.grouped, products)
    // directly above the priced table, for the reason the problems panel is
    // above it too: it says what that table was priced AGAINST, and a total read
    // without its yard is a number two people can disagree about for ever
    + supplyProvenanceHtml(data.supply)
    // What the DOCUMENTS say about the products on that table. This is the
    // "once per line group" surface §3.3.5 names, and it is the only bucket this
    // tab draws: the annexe belongs to the PLAN and renders on the structure
    // sheet, and printing it here as well would be the same notice twice.
    + bomHtml(data.bom, products, { unresolved: data.unresolved,
                                    quoted: data.quoted_warnings });
  const quoteForm = document.getElementById("quote-label-form");
  const quoteInput = document.getElementById("quote-label-input");
  const saveQuote = async () => {
    // empty label is allowed — the quote falls back to its id in the table
    await apiSend("POST", `/api/runs/${state.result.run.id}/quote`,
      { label: quoteInput.value.trim() });
    renderBom();
  };
  document.getElementById("btn-save-quote").addEventListener("click", () => {
    quoteForm.hidden = !quoteForm.hidden;
    if (!quoteForm.hidden) quoteInput.focus();
  });
  document.getElementById("btn-quote-confirm").addEventListener("click", saveQuote);
  quoteInput.addEventListener("keydown", (e) => { if (e.key === "Enter") saveQuote(); });
  document.getElementById("btn-quote-cancel").addEventListener("click", () => {
    quoteForm.hidden = true;
  });
  wireQuoteButtons(div, products);
}

function quotesHtml(quotes) {
  if (!quotes.length) return "";
  let html = `<div class="panel"><h3>${t("quote.title")}</h3>
    <table><tr><th>${t("quote.label")}</th><th>${t("quote.date")}</th>
    <th>${tu("bom.line_total")}</th><th>${t("quote.status")}</th><th></th></tr>`;
  for (const q of quotes) {
    html += `<tr><td dir="auto">${esc(q.label) || `<bdi class="meta">${esc(q.id.slice(0, 14))}</bdi>`}</td>
      <td class="num">${esc((q.created_at || "").slice(0, 16).replace("T", " "))}</td>
      <td class="num">${esc(money(q.total_cents))}</td>
      <td><span class="tag ${q.status === "accepted" ? "active" : q.status === "superseded" ? "retired" : "medium"}">${t("quote." + q.status)}</span></td>
      <td><button data-view-quote="${esc(q.id)}">${t("quote.view")}</button>
        ${q.status === "draft" ? `<button data-accept-quote="${esc(q.id)}">${t("quote.accept")}</button>` : ""}</td></tr>`;
  }
  return html + "</table></div>";
}

function wireQuoteButtons(div, products) {
  div.querySelectorAll("[data-accept-quote]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await apiSend("POST", `/api/quotes/${btn.dataset.acceptQuote}/accept`);
      renderBom();
    }));
  div.querySelectorAll("[data-view-quote]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const q = await apiGet(`/api/quotes/${btn.dataset.viewQuote}`);
      div.innerHTML = `<div class="panel impact">
          <b>${t("quote.snapshot_banner", { label: q.label || q.id.slice(0, 14) })}</b>
          <span class="meta"> · ${esc((q.created_at || "").slice(0, 16).replace("T", " "))}
          · <bdi>inv ${esc(q.inventory_hash)}</bdi> · <bdi>kb ${esc(q.knowledge_snapshot_hash)}</bdi>
          ${q.supply_id ? `· <bdi class="sku">${esc(q.supply_id)}</bdi>` : ""}</span>
          <button id="btn-quote-back">${t("quote.back_live")}</button>
        </div>` + bomHtml(q.bom, products);
      document.getElementById("btn-quote-back").addEventListener("click", renderBom);
    }));
}

/** What this BOM was priced AGAINST — the yard, the objective, and the id of the
 *  supply run that names the pair.
 *
 *  A run id answers "what fence is this" and nothing else. Two readings of ONE
 *  unchanged run legitimately produce different money and different cut lists,
 *  because inventory and the objective preset move underneath them; the backend
 *  has named that second thing since the design/supply split, and until this
 *  function nothing put the name on screen. A reader holding two printouts could
 *  see the totals differ and had no way to learn why.
 *
 *  Pure over its argument, so it is pinned under node
 *  (`tests/web/test_supply_provenance_module.py`) rather than in a browser.
 *
 *  The preset is prose and goes through `t()`; a preset with no label degrades to
 *  its raw token, because showing `bom.preset_fewest_new_stock` to a customer is
 *  worse than showing the token an engineer can look up. The id and the hash are
 *  opaque and get `<bdi>` + `.sku`, exactly as SKUs do — RTL must not reorder a
 *  hash into a different-looking hash. */
export function supplyProvenanceHtml(supply) {
  if (!supply?.id) return "";     // nothing to say is said with nothing
  const presetKey = `bom.preset_${supply.objective_preset}`;
  const preset = t(presetKey);
  return `<div class="panel meta supply-provenance">
      ${esc(t("bom.priced_against"))}
      <bdi class="sku">${esc(t("bom.yard"))} ${esc(supply.inventory_hash)}</bdi>
      · ${esc(preset === presetKey ? supply.objective_preset : preset)}
      · <bdi class="sku">${esc(supply.id)}</bdi>
    </div>`;
}

/** The same demand, grouped by what CAUSED it: a section, a panel, or the supply
 *  decision that put the product on the list.
 *
 *  It carries no money, and that is the design rather than an omission. A BOM
 *  line is a PURCHASE pooled per sku across the whole run — one bar is cut for
 *  two bays — so a per-section price would be an apportionment nothing measured,
 *  arriving with the authority of a priced table. The flat table below is where
 *  money is true.
 *
 *  Tags come from `structure-data.js`, the single tag source for this tab and
 *  both drawings; an element it cannot name (a stale report) falls back to its
 *  own id rather than to a blank cell that reads as "no section". */
/** The quantity cell and its unit cell, together, because they have to agree.
 *
 *  A qty is a COUNT ("8 each", "12 cut") unless its unit says it is a length.
 *  `fmt` is the mm -> display converter and nothing else, so putting every qty
 *  through it reported `0.8 each` to anyone who had switched the app to cm —
 *  wrong by a factor of ten, in the one table built to answer "what does this
 *  section need". And when the unit IS `mm` the number must be converted AND
 *  the label swapped for `unitLabel()`, or a converted figure sits under a
 *  literal "mm" while the priced table below it, on the same screen, says cm.
 *  This is the guard `bomHtml` already applies to the same two fields; the
 *  grouped view copied the number and not the guard. */
function qtyCells(qty, unit) {
  return unit === "mm"
    ? `<td class="num">${esc(fmt(qty))}</td><td>${esc(unitLabel())}</td>`
    : `<td class="num">${esc(String(qty))}</td><td>${esc(unit)}</td>`;
}

export function groupedBomHtml(grouped, products) {
  const groups = grouped?.groups || [];
  if (!groups.length) return "";
  const KINDS = ["section", "node", "bay", "decision"];
  // Three different ids, one tag source. A BAY's key IS an element id; a
  // SECTION's is a run id, which `tagOf` does not index (it maps elements); and
  // a NODE's names the post standing there, whose element id is `post@<node>`.
  // Getting this wrong is not a crash, it is `run1` printed where the schedule
  // and both drawings say `A` — a third name for one thing, which is exactly
  // what one tag source exists to prevent.
  const name = (g) => {
    if (g.kind === "decision") return esc(g.chosen);
    const tag = g.kind === "section" ? sectionOf(g.element_id)?.tag
      : g.kind === "node" ? tagOf(`post@${g.element_id}`)
        : tagOf(g.element_id);
    return tag ? esc(tag) : `<bdi>${esc(g.element_id)}</bdi>`;
  };
  let html = `<div class="panel" id="bom-grouped">
    <h3>${t("bom.grouped_title")}</h3>
    <div class="meta">${t("bom.grouped_hint")}</div>`;
  for (const kind of KINDS) {
    const of = groups.filter((g) => g.kind === kind);
    if (!of.length) continue;
    html += `<h4 data-group-kind="${kind}">${t(`bom.group_${kind}`)}</h4>`;
    for (const g of of) {
      html += `<div class="group-row" data-group="${esc(g.element_id)}"
                    data-kind="${kind}">
        <div class="group-head"><strong>${name(g)}</strong>`;
      if (g.kind === "decision" && g.rejected.length)
        // the runner-up belongs BESIDE the choice: "cheaper than the others" is
        // not an explanation, and this is the view that raised the question.
        // `sentence`, not `esc(t(...))`: these params are Latin skus and a
        // preset name inside a Hebrew sentence's parentheses, and escaping
        // AFTER interpolating leaves them to reorder on screen.
        html += ` <span class="meta">${sentence("bom.group_beat", {
          rejected: g.rejected.join(", "), preset: g.preset })}</span>`;
      html += `</div><table>`;
      for (const line of g.lines) {
        const p = products?.[line.sku];
        html += `<tr><td class="sku">${esc(line.sku)}</td>
          <td dir="auto">${esc(p ? lineName(products, { sku: line.sku, name: p.name }) : "")}</td>
          ${qtyCells(line.qty, line.unit)}
          <td class="num">${line.cut_length_mm == null ? ""
            : esc(fmtLen(line.cut_length_mm))}</td></tr>`;
      }
      html += `</table></div>`;
    }
  }
  const bucket = (rows, key) => {
    if (!rows?.length) return "";
    let out = `<div class="group-row"><div class="group-head"><strong>${t(key)}</strong></div><table>`;
    for (const r of rows)
      out += `<tr><td class="sku">${esc(r.sku)}</td><td></td>
        ${qtyCells(r.qty, r.unit)}<td></td></tr>`;
    return out + `</table></div>`;
  };
  // reported, never balanced away — the same two buckets the structure sheet
  // carries, for the same reason
  html += bucket(grouped.unassigned, "bom.group_unassigned");
  html += bucket(grouped.from_stock, "bom.group_from_stock");
  // A line nothing could supply is part of what a section NEEDS and appears on
  // no purchase line — so a section missing a part read as complete here. The
  // same failure the panel preview names: "a panel one part short must not
  // preview as complete".
  // `roleWord` on the fallback: `role` is a backend enum, so a slot with no key
  // printed a raw "rail" — untranslated English in a Hebrew-first UI, in the
  // `.sku` cell that forces ltr on what is a translated WORD, not an id.
  html += bucket((grouped.unresolved || []).map((u) => ({
    sku: u.slot_key || roleWord(u.role), qty: u.engineering_qty, unit: "",
  })), "bom.group_unresolved");
  return html + `</div>`;
}


/** The priced table.
 *
 *  `unresolved` is what the fence NEEDS and no product could supply. It used to
 *  live only in the panel above this one, so the table itself — the thing a
 *  reader prints, sends and adds up — looked complete while being short a part,
 *  and the total at its head read as the price of the fence rather than the
 *  price of the part of it that can be bought. The design's rule is blunt about
 *  it: "a BOM missing something must LOOK like it is missing something". So the
 *  missing lines are rows in this table, carrying no money, and the heading says
 *  the total excludes them.
 *
 *  Optional, because a saved quote is rendered through here too and carries no
 *  unresolved list: a quote cannot be saved while a part has no supplier, so
 *  there is nothing to say about one.
 *
 *  `quoted` is optional for a sharper reason, and the quote path deliberately
 *  passes none. A `Quote` is an immutable commercial document: annotating a
 *  historical one with what its manufacturer's document says TODAY would print
 *  text on a page nobody accepted. The live BOM gets the notices; the frozen
 *  document keeps what was frozen.
 *
 *  Exported for the same reason `groupedBomHtml` and `assemblyPlanHtml` are: it
 *  is a pure function of its arguments and node can test it. The test review
 *  found every quoted-warning call site on this tab reachable only through the
 *  browser — a mutant that made `quotedRow` return "" removed every product
 *  notice from the BOM and the whole pytest suite stayed green. */
export function bomHtml(bom, products, { unresolved = [], quoted = null } = {}) {
  // Once per line group, and a BOM line IS the line group: `Bom.lines` are
  // already pooled per sku across the whole run, so there is nothing left to
  // deduplicate here — which is exactly why this is the surface the contract
  // names for a product-scoped warning.
  const seenSku = new Set();
  const short = (unresolved || []).length;
  let html = `<div class="panel${short ? " incomplete" : ""}">
  <h3>${t("bom.title")} — ${t("bom.total")} ${esc(money(bom.total_cents))}
  ${short ? `<span class="tag low">${esc(t(short === 1 ? "bom.total_excludes_one"
      : "bom.total_excludes", { n: short }))}</span>` : ""}</h3>
  ${modelWarningsHtml(quoted)}
  <table><tr><th>${t("bom.sku")}</th><th>${t("bom.purchase")}</th><th>${t("bom.engineering")}</th>
  <th>${t("bom.overage")}</th><th>${tu("bom.unit_price")}</th><th>${tu("bom.line_total")}</th><th>${t("bom.notes")}</th></tr>`;
  for (const l of bom.lines) {
    html += `<tr><td><span class="sku">${esc(l.sku)}</span><br><span class="meta" dir="auto">${esc(lineName(products, l))}</span></td>
      <td><span class="num">${l.purchase_qty}</span> × ${esc(l.purchase_unit)}</td>
      <td><span class="num">${l.engineering_unit === "mm" ? esc(fmt(l.engineering_qty))
        : l.engineering_qty}</span> ${esc(l.engineering_unit === "mm" ? unitLabel()
        : l.engineering_unit)}</td>
      <td class="num">${l.overage_qty || ""}</td>
      <td class="num">${esc(money(l.unit_price_cents))}</td>
      <td class="num">${esc(money(l.total_cents))}</td>
      <td>${esc((l.notes || []).join("; "))}</td></tr>`
      + productWarningRowHtml(quoted, l.sku, seenSku);
  }
  // A row with no sku, no unit price and no total — because that is precisely
  // what is known about it. `roleWord` rather than the raw enum: `role` is a
  // backend word, and an untranslated "rail" in the first column of a Hebrew
  // table reads as an identifier rather than as the part it names.
  for (const u of unresolved || []) {
    html += `<tr class="unfulfilled"><td>${esc(roleWord(u.role))}`
      + (u.slot_key && u.slot_key !== u.role
        ? ` <span class="meta">${esc(u.slot_key)}</span>` : "")
      + `<br><span class="meta">${esc(t("bom.unfulfilled_note"))}</span></td>
      <td>—</td>
      <td><span class="num">${esc(String(u.engineering_qty))}</span></td>
      <td></td><td>—</td><td>—</td>
      <td>${esc(t("bom.unfulfilled"))}</td></tr>`;
  }
  html += "</table></div>";
  for (const [sku, plan] of Object.entries(bom.cut_plans || {})) {
    // no solver vocabulary and no bound number: the reader wants to know whether
    // the bar count can still come down, not what a relaxation computed
    // `cut-plan` is a scoping hook, not decoration: this panel's STOCK column is
    // what the display-unit check reads, and an unscoped scan of every table in
    // the tab reads whichever table happens to be first.
    html += `<div class="panel cut-plan"><h3>${t("bom.cut_plan")} — <span class="sku">${esc(sku)}</span>
      ${plan.certified_optimal ? `<span class="tag active">${t("bom.optimal")}</span>`
        : `<span class="tag medium">${t("bom.best_found")}</span>`}</h3>
      <table><tr><th>${t("bom.bar_source")}</th><th>${tu("bom.stock")}</th><th>${tu("bom.cuts")}</th><th>${tu("bom.leftover")}</th></tr>`;
    for (const b of plan.bars) {
      html += `<tr><td>${b.source === "new" ? t("bom.source_new") : `<bdi>${esc(b.source)}</bdi>`}</td>
        <td class="num">${esc(fmt(b.stock_length_mm))}</td>
        <td class="num">${esc(b.pieces.map((p) => fmt(p.length_mm)).join(" + "))}</td>
        <td class="num">${esc(fmt(b.leftover_mm))}${b.leftover_reusable ? " ♻" : ""}</td></tr>`;
    }
    html += "</table>";
    // "was my shelf even consulted?" — silence used to be the only answer
    if (plan.bars.every((b) => b.source === "new"))
      html += `<div class="meta">${t("bom.inventory_not_used")}</div>`;
    html += "</div>";
  }
  if ((bom.allocations || []).length) {
    html += `<div class="panel"><h3>${t("bom.allocations")}</h3>
      <table><tr><th>${t("bom.item")}</th><th>${t("bom.sku")}</th><th>${t("bom.used")}</th></tr>`;
    for (const a of bom.allocations)
      html += `<tr><td><bdi>${esc(a.inventory_item_id)}</bdi></td><td><span class="sku">${esc(a.sku)}</span></td>
        <td class="num">${a.length_used_mm ? esc(fmtLen(a.length_used_mm)) : a.qty}</td></tr>`;
    html += "</table></div>";
  }
  html += remnantsHtml(bom.projected_remnants || []);
  return html;
}

// The planner computes the offcuts this plan leaves and the API ships them; until
// now nothing rendered them, so a procurement user could not tell what goes back
// on the shelf. Identical pieces are grouped — 12 rows of "1497" is not a report.
function remnantsHtml(remnants) {
  if (!remnants.length) return "";
  const groups = new Map();
  for (const r of remnants) {
    const key = `${r.sku}|${r.length_mm}`;
    groups.set(key, { sku: r.sku, length_mm: r.length_mm, n: (groups.get(key)?.n || 0) + 1 });
  }
  let html = `<div class="panel"><h3>${t("bom.projected_remnants")}</h3>
    <div class="meta">${t("bom.projected_remnants_hint")}</div>
    <table><tr><th>${t("bom.sku")}</th><th>${tu("inventory.length_mm")}</th><th>${t("bom.remnant_count")}</th></tr>`;
  for (const g of [...groups.values()].sort((a, b) => a.sku.localeCompare(b.sku) || b.length_mm - a.length_mm))
    html += `<tr><td><span class="sku">${esc(g.sku)}</span></td>
      <td class="num">${esc(fmt(g.length_mm))}</td><td class="num">${g.n}</td></tr>`;
  return html + "</table></div>";
}

// ---------- annotations ----------
async function renderAnnotations() {
  const div = document.getElementById("annotation-list");
  div.innerHTML = "";
  for (const ann of state.project?.annotations || []) {
    const card = document.createElement("div");
    card.className = "card";
    let html = `<div class="meta"><bdi>${esc(ann.id)}</bdi> · ${esc(ann.target_ref)} · ${esc(ann.author)}</div>
      <div class="verbatim" dir="auto">“${esc(ann.text)}”</div>
      <button data-act="interpret">${t("annotations.interpret")}</button>`;
    for (const rec of ann.interpretations) {
      html += `<div class="meta">${t("annotations.by")} <bdi>${esc(rec.interpreter)}</bdi></div>`;
      for (const c of rec.candidates) {
        html += `<div>→ <b>${esc(c.kind)}</b> <bdi>${esc(JSON.stringify(c.params))}</bdi>
          <span class="tag ${c.confidence}">${t("confidence." + c.confidence)}</span>
          <span class="tag ${c.status}">${t("status." + c.status)}</span>`;
        if (c.status === "proposed")
          html += ` <button data-confirm="${esc(c.id)}" data-ann="${esc(ann.id)}">${t("annotations.confirm")}</button>`;
        html += "</div>";
        if (c.ambiguity_note) html += `<div class="meta">⚠ ${esc(c.ambiguity_note)}</div>`;
      }
      for (const u of rec.unparsed_spans)
        html += `<div class="meta">${t("annotations.unparsed")}: <span dir="auto">“${esc(u)}”</span></div>`;
    }
    // project-wide annotations need a run chosen at confirm time — inline picker, no prompt()
    html += `<div class="inline-form" data-run-picker hidden>
        <span class="meta">${t("annotations.pick_run")}</span>
        <select data-f="run">${(state.project?.topology.runs || [])
          .map((r) => `<option value="${esc(r.id)}">${esc(r.id)}</option>`).join("")}</select>
        <button data-f="ok" class="primary">${t("common.confirm")}</button>
        <button data-f="cancel">${t("common.cancel")}</button>
      </div>`;
    card.innerHTML = html;
    card.querySelector('[data-act="interpret"]').addEventListener("click", async () => {
      await apiSend("POST", `/api/projects/${state.projectId}/annotations/${ann.id}/interpret`);
      await reloadProject();
    });
    const confirmIntent = async (candidateId, annotationId, runId) => {
      await apiSend("POST",
        `/api/projects/${state.projectId}/intents/${candidateId}/confirm`,
        { annotation_id: annotationId, run_id: runId });
      await reloadProject();
    };
    const picker = card.querySelector("[data-run-picker]");
    card.querySelectorAll("[data-confirm]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const runId = ann.target_ref.startsWith("run:") ? ann.target_ref.slice(4) : null;
        if (runId) return confirmIntent(btn.dataset.confirm, btn.dataset.ann, runId);
        picker.dataset.candidate = btn.dataset.confirm;
        picker.dataset.annId = btn.dataset.ann;
        picker.hidden = false;
      }));
    picker.querySelector('[data-f="ok"]').addEventListener("click", async () => {
      const runId = picker.querySelector('[data-f="run"]').value;
      if (!runId) return;
      await confirmIntent(picker.dataset.candidate, picker.dataset.annId, runId);
    });
    picker.querySelector('[data-f="cancel"]').addEventListener("click", () => {
      picker.hidden = true;
    });
    div.appendChild(card);
  }
}

// ---------- knowledge ----------
async function renderKnowledge() {
  const versions = await apiGet("/api/knowledge");
  const div = document.getElementById("knowledge-list");
  div.innerHTML = "";
  for (const v of versions) {
    const card = document.createElement("div");
    card.className = "card";
    let html = `<span class="tag ${v.type}">${t("type." + v.type)}</span>
      <span class="tag ${v.status}">${t("status." + v.status)}</span>
      <b><bdi>${esc(v.object_id)}@v${v.version}</bdi></b> — <span dir="auto">${esc(v.title_i18n?.[currentLocale()] || v.title)}</span>
      <div class="meta">${t("knowledge.scope")} <bdi>${esc(JSON.stringify(v.scope))}</bdi> · ${esc(v.attributed_to)}
        ${v.derived_from?.length ? "· " + t("knowledge.derived_from") + " <bdi>" + esc(v.derived_from.join(", ")) + "</bdi>" : ""}</div>`;
    if (v.source_text) html += `<div class="verbatim" dir="auto">“${esc(v.source_text)}”</div>`;
    html += `<div class="meta">${t("knowledge.actions")}: <bdi>${esc(JSON.stringify(v.actions))}</bdi></div>`;
    if (v.status === "active") html += `<button data-retire="1">${t("knowledge.retire")}</button>`;
    card.innerHTML = html;
    card.querySelector("[data-retire]")?.addEventListener("click", async () => {
      await apiSend("POST", `/api/knowledge/${v.object_id}/${v.version}/retire`);
      renderKnowledge();
    });
    div.appendChild(card);
  }
}

// ---------- knowledge rule builder (sentence-style action rows) ----------
// Builder state is the plain actions array — exactly what POST /api/knowledge takes.
// The Advanced (JSON) textarea is a two-way escape hatch (kAdvancedOpen switches
// which of the two is the source of truth for save/preview).
let builderActions = null;
let kAdvancedOpen = false;
let inventoryObj = null;
let invAdvancedOpen = false;

const ACTION_KINDS = [
  "set_param", "default_component", "require_mounting", "require_post_reinforcement",
  "prefer_equal_spans", "prefer_min_span_width", "prefer_span_width", "prefer_vertical",
  "add_note", "flag_for_review",
];
const KNOWN_PARAMS = [
  "max_span_mm", "rails_per_span", "screws_per_span", "base_top_step_boundary_mm",
];
const COMPONENT_ROLES = ["post_ground", "rail", "screw", "concrete", "cap"];
const SURFACES = ["soil", "concrete", "masonry_wall"];

function defaultActionFor(kind) {
  switch (kind) {
    case "set_param": return { kind, param: "max_span_mm", value: 1800 };
    case "default_component": return { kind, role: "post_ground", sku: "" };
    case "require_mounting": return { kind, surface: "soil", mounting: "ground", sku: null };
    case "require_post_reinforcement": return { kind, context: "gate", sku: null };
    case "prefer_equal_spans": return { kind, weight: 1 };
    case "prefer_min_span_width": return { kind, min_mm: 0, weight: 1 };
    case "prefer_span_width": return { kind, width_mm: 0, weight: 1 };
    case "prefer_vertical": return { kind, mode: "level", weight: 1 };
    case "add_note": return { kind, text: "" };
    default: return { kind: "flag_for_review", reason: "" };
  }
}

async function initKnowledgeBuilder() {
  if (builderActions === null) {
    // the hidden textarea's initial JSON is the single source for the default row
    try { builderActions = JSON.parse(document.getElementById("k-actions").value); }
    catch { builderActions = []; }
    if (!Array.isArray(builderActions)) builderActions = [];
  }
  await renderBuilderRows();
}

async function renderBuilderRows() {
  const products = await loadCatalogProducts();
  const host = document.getElementById("k-action-rows");
  host.innerHTML = "";
  builderActions.forEach((a, idx) => host.appendChild(builderRow(a, idx, products)));
}

function builderRow(a, idx, products) {
  const row = el("div", { class: "builder-row" });

  const kindSel = el("select", { class: "builder-kind", title: t("knowledge.builder.action") });
  for (const k of ACTION_KINDS) kindSel.appendChild(option(k, t("action." + k), a.kind === k));
  kindSel.addEventListener("change", () => {
    builderActions[idx] = defaultActionFor(kindSel.value);
    renderBuilderRows();
  });
  row.appendChild(kindSel);

  // plain counts (weights) stay raw; `*_mm` action fields are lengths and follow
  // the display unit — the stored action keeps int mm either way
  // `lengthNow` is re-evaluated on every commit, never captured: the free-text
  // param box writes a.param on `input` WITHOUT re-rendering the row, so a
  // render-time flag would store centimetres as millimetres (10x, in rule data)
  const num = (key, labelKey, lengthNow = () => key.endsWith("_mm")) => {
    const raw = a[key] ?? "";
    const isLength = lengthNow();
    const i = el("input", { type: "number",
      step: isLength ? inputStep() : "1",
      value: raw === "" || !isLength ? raw : toDisplayValue(raw) });
    i.addEventListener("change", () => {
      a[key] = lengthNow() ? (toMm(i.value) ?? 0) : Math.round(i.valueAsNumber || 0);
    });
    return field(labelKey, i);
  };
  const text = (key, labelKey) => {
    const i = el("input", { type: "text", dir: "auto", size: 28, value: a[key] ?? "" });
    i.addEventListener("input", () => { a[key] = i.value; });
    return field(labelKey, i);
  };
  const choice = (key, values, labelFor, labelKey) => {
    const s = el("select");
    for (const v of values) s.appendChild(option(v, labelFor(v), a[key] === v));
    s.addEventListener("change", () => { a[key] = s.value; });
    return field(labelKey, s);
  };
  const sku = (optional) =>
    field(optional ? "knowledge.builder.sku_optional" : "knowledge.builder.sku",
      skuSelect(products, a.sku, optional, (v) => { a.sku = v; }));

  if (a.kind === "set_param") {
    const isOther = !KNOWN_PARAMS.includes(a.param);
    const s = el("select");
    for (const p of KNOWN_PARAMS) s.appendChild(option(p, tu("action.param." + p), a.param === p));
    s.appendChild(option("__other", t("action.param.other"), isOther));
    s.addEventListener("change", () => {
      const wasLength = String(a.param || "").endsWith("_mm");
      a.param = s.value === "__other" ? "" : s.value;
      // the value belongs to the OLD parameter. A length carried into a count is
      // a different quantity in a different unit — 1800 survived two switches
      // into screws_per_span. Reset unless the kind of number is unchanged;
      // the sibling action-kind select has always done this via defaultActionFor.
      if (String(a.param || "").endsWith("_mm") !== wasLength) a.value = 0;
      renderBuilderRows();  // swap the free-text param input in/out
    });
    row.appendChild(field("knowledge.builder.param", s));
    if (isOther) {
      const i = el("input", { type: "text", dir: "ltr", class: "sku", size: 20,
        placeholder: t("knowledge.builder.param_placeholder"), value: a.param });
      i.addEventListener("input", () => { a.param = i.value.trim(); });
      row.appendChild(i);
    }
    // a set_param value is a length exactly when its param name says so — and
    // the param name can change under this row without a re-render
    const paramIsLength = () => String(a.param || "").endsWith("_mm");
    row.appendChild(num("value",
      paramIsLength() ? "knowledge.builder.value_len" : "knowledge.builder.value",
      paramIsLength));
  } else if (a.kind === "default_component") {
    if (!a.sku) a.sku = Object.keys(products).sort()[0] || "";
    row.appendChild(choice("role", COMPONENT_ROLES, (r) => t("action.role." + r), "knowledge.builder.role"));
    row.appendChild(sku(false));
  } else if (a.kind === "require_mounting") {
    row.appendChild(choice("surface", SURFACES, (s) => t("surface." + s), "knowledge.builder.surface"));
    row.appendChild(choice("mounting", ["ground", "masonry"],
      (m) => t("action.mounting." + m), "knowledge.builder.mounting"));
    row.appendChild(sku(true));
  } else if (a.kind === "require_post_reinforcement") {
    row.appendChild(choice("context", ["gate"], (c) => t("action.context." + c), "knowledge.builder.context"));
    row.appendChild(sku(true));
  } else if (a.kind === "prefer_equal_spans") {
    row.appendChild(num("weight", "knowledge.builder.weight"));
  } else if (a.kind === "prefer_min_span_width") {
    row.appendChild(num("min_mm", "knowledge.builder.min_mm"));
    row.appendChild(num("weight", "knowledge.builder.weight"));
  } else if (a.kind === "prefer_span_width") {
    row.appendChild(num("width_mm", "knowledge.builder.width_mm"));
    row.appendChild(num("weight", "knowledge.builder.weight"));
  } else if (a.kind === "prefer_vertical") {
    row.appendChild(choice("mode", ["level", "stepped", "raked"],
      (m) => t("action.mode." + m), "knowledge.builder.mode"));
    row.appendChild(num("weight", "knowledge.builder.weight"));
  } else if (a.kind === "add_note") {
    row.appendChild(text("text", "knowledge.builder.note"));
  } else if (a.kind === "flag_for_review") {
    row.appendChild(text("reason", "knowledge.builder.reason"));
  }

  const rm = el("button", { type: "button", class: "remove-row", title: t("common.remove"), text: "✕" });
  rm.addEventListener("click", () => {
    builderActions.splice(idx, 1);
    renderBuilderRows();
  });
  row.appendChild(rm);
  return row;
}

// ---------- review queue ----------
async function renderCandidates() {
  const candidates = await apiGet("/api/candidates");
  const div = document.getElementById("candidate-list");
  div.innerHTML = candidates.length ? "" : `<em>${t("review.empty")}</em>`;
  for (const c of candidates) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<span class="tag candidate">${t("status.proposed")}</span>
      <b><bdi>${esc(c.object_id)}@v${c.version}</bdi></b> — <span dir="auto">${esc(c.title_i18n?.[currentLocale()] || c.title)}</span>
      <div class="meta">${t("knowledge.scope")} <bdi>${esc(JSON.stringify(c.scope))}</bdi> ·
        ${t("knowledge.derived_from")} <bdi>${esc(c.derived_from.join(", "))}</bdi></div>
      ${c.source_text ? `<div class="verbatim" dir="auto">“${esc(c.source_text)}”</div>` : ""}
      <div class="meta">${t("knowledge.actions")}: <bdi>${esc(JSON.stringify(c.actions))}</bdi></div>
      <button data-preview="1">${t("impact.preview")}</button>
      <button data-a="approve">${t("review.approve")}</button>
      <button data-a="scope_restrict">${t("review.approve_narrower")}</button>
      <button data-a="reject">${t("review.reject")}</button>
      <div class="inline-form" data-form="reject" hidden>
        <input data-f="reason" dir="auto" size="30"
          placeholder="${esc(t("review.reject_reason_placeholder"))}">
        <button data-f="ok" class="primary">${t("common.confirm")}</button>
        <button data-f="cancel">${t("common.cancel")}</button>
      </div>
      <div class="inline-form" data-form="scope" hidden>
        <select data-f="dim" title="${esc(t("review.scope_dim"))}">
          ${["project_id", "series", "surface", "context"]
            .map((d) => `<option value="${d}">${t("review.dim." + d)}</option>`).join("")}
          <option value="__other">${t("review.dim.other")}</option>
        </select>
        <input data-f="dim-other" class="sku" size="14"
          placeholder="${esc(t("review.dim.other_placeholder"))}" hidden>
        <input data-f="value" dir="auto" size="16"
          placeholder="${esc(t("review.scope_value_placeholder"))}">
        <button data-f="ok" class="primary">${t("common.confirm")}</button>
        <button data-f="cancel">${t("common.cancel")}</button>
      </div>
      <div class="impact-out"></div>`;
    card.querySelector("[data-preview]").addEventListener("click", async () => {
      const out = card.querySelector(".impact-out");
      out.innerHTML = `<em>${t("impact.computing")}</em>`;
      const report = await apiSend(
        "POST", `/api/candidates/${c.object_id}/${c.version}/preview`);
      renderImpactReport(out, report);
    });
    const submitReview = async (body) => {
      await apiSend("POST", `/api/candidates/${c.object_id}/${c.version}/review`,
        { reviewer: "expert-admin", ...body });
      renderCandidates(); renderKnowledge();
    };
    const rejectForm = card.querySelector('[data-form="reject"]');
    const scopeForm = card.querySelector('[data-form="scope"]');
    card.querySelectorAll("button[data-a]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const action = btn.dataset.a;
        if (action === "approve") return submitReview({ action });
        // reject / scope_restrict reveal their inline form instead of a prompt()
        const form = action === "reject" ? rejectForm : scopeForm;
        const other = action === "reject" ? scopeForm : rejectForm;
        form.hidden = !form.hidden;
        other.hidden = true;
        if (action === "reject" && !form.hidden)
          form.querySelector('[data-f="reason"]').focus();
      }));
    rejectForm.querySelector('[data-f="ok"]').addEventListener("click", () =>
      submitReview({
        action: "reject",
        reason: rejectForm.querySelector('[data-f="reason"]').value.trim() || "no reason given",
      }));
    const dimSel = scopeForm.querySelector('[data-f="dim"]');
    const dimOther = scopeForm.querySelector('[data-f="dim-other"]');
    dimSel.addEventListener("change", () => {
      dimOther.hidden = dimSel.value !== "__other";
      if (!dimOther.hidden) dimOther.focus();
    });
    scopeForm.querySelector('[data-f="ok"]').addEventListener("click", () => {
      const key = dimSel.value === "__other" ? dimOther.value.trim() : dimSel.value;
      const value = scopeForm.querySelector('[data-f="value"]').value.trim();
      if (!key || !value) return;
      submitReview({ action: "scope_restrict", edited_scope: { ...c.scope, [key]: value } });
    });
    for (const form of [rejectForm, scopeForm])
      form.querySelector('[data-f="cancel"]').addEventListener("click", () => {
        form.hidden = true;
      });
    div.appendChild(card);
  }
}

// ---------- inventory ----------
const INVENTORY_KINDS = ["full_stock", "remnant", "opened_package"];

async function renderInventory() {
  if (!state.projectId) return;
  inventoryObj = await apiGet(`/api/projects/${state.projectId}/inventory`);
  if (!Array.isArray(inventoryObj.items)) inventoryObj.items = [];
  document.getElementById("inventory-json").value = JSON.stringify(inventoryObj, null, 2);
  await drawInventoryTable();
}

async function drawInventoryTable() {
  if (!inventoryObj) return;
  const products = await loadCatalogProducts();
  const host = document.getElementById("inventory-table-host");
  host.innerHTML = "";
  if (!inventoryObj.items.length) {
    host.appendChild(el("div", { class: "meta", text: t("inventory.empty") }));
    return;
  }
  const table = el("table", { id: "inventory-table" },
    el("tr", {},
      el("th", { text: t("bom.sku") }), el("th", { text: t("inventory.kind") }),
      el("th", { text: t("inventory.qty") }), el("th", { text: tu("inventory.length_mm") }),
      el("th")));
  inventoryObj.items.forEach((item, idx) => table.appendChild(inventoryRow(item, idx, products)));
  host.appendChild(table);
}

function inventoryRow(item, idx, products) {
  const tr = el("tr");
  tr.appendChild(el("td", {}, skuSelect(products, item.sku, false, (v) => { item.sku = v; })));

  const kindSel = el("select");
  for (const k of INVENTORY_KINDS) kindSel.appendChild(option(k, t("inventory.kind." + k), item.kind === k));
  kindSel.addEventListener("change", () => {
    item.kind = kindSel.value;
    if (item.kind !== "remnant") item.length_mm = null;
    drawInventoryTable();  // show/hide the length column input
  });
  tr.appendChild(el("td", {}, kindSel));

  const qty = el("input", { type: "number", min: "0", value: item.qty ?? 1 });
  qty.addEventListener("change", () => { item.qty = Math.round(qty.valueAsNumber || 0); });
  tr.appendChild(el("td", {}, qty));

  const lenTd = el("td");
  if (item.kind === "remnant") {
    const len = el("input", { type: "number", min: "0", step: inputStep(),
      value: item.length_mm == null ? "" : toDisplayValue(item.length_mm) });
    len.addEventListener("change", () => {
      item.length_mm = len.value === "" ? null : (toMm(len.value) ?? 0);
    });
    lenTd.appendChild(len);
  } else {
    lenTd.append("—");
  }
  tr.appendChild(lenTd);

  const rm = el("button", { type: "button", class: "remove-row", title: t("common.remove"), text: "✕" });
  rm.addEventListener("click", () => {
    inventoryObj.items.splice(idx, 1);
    drawInventoryTable();
  });
  tr.appendChild(el("td", {}, rm));
  return tr;
}
