// Tab panels: annotations, knowledge, review queue, BOM, inventory.

import { apiGet, apiSend, esc } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { on, reloadProject, state } from "./state.js";
import { fmt, fmtLen, inputStep, toDisplayValue, toMm, tu, unitLabel } from "./units.js";

// ---------- small DOM helpers (builder rows are DOM-built, no innerHTML) ----------
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  node.append(...children);
  return node;
}

function option(value, label, selected) {
  const o = el("option", { value, text: label });
  if (selected) o.selected = true;
  return o;
}

// small labelled field: <label><span class=meta>label</span> input</label>
const field = (labelKey, input) =>
  el("label", { class: "builder-field" }, el("span", { class: "meta", text: tu(labelKey) }), input);

function productLabel(products, sku) {
  const name = products[sku]?.name_i18n?.[currentLocale()] || products[sku]?.name;
  return name ? `${sku} — ${name}` : sku;
}

// SKU <select> from the cached catalog (localized names); optional adds a "none" entry
function skuSelect(products, current, optional, onchange) {
  const sel = el("select", { title: t(optional ? "knowledge.builder.sku_optional" : "knowledge.builder.sku") });
  if (optional) sel.appendChild(option("", t("knowledge.builder.none"), !current));
  const skus = Object.keys(products).sort();
  for (const sku of skus) sel.appendChild(option(sku, productLabel(products, sku), current === sku));
  if (current && !skus.includes(current)) sel.appendChild(option(current, current, true));
  sel.addEventListener("change", () => onchange(sel.value || null));
  return sel;
}

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
      try { actions = JSON.parse(document.getElementById("k-actions").value); }
      catch { alert(t("knowledge.actions_json_invalid")); return null; }
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
      let parsed;
      try { parsed = JSON.parse(ta.value); } catch { return alert(t("knowledge.actions_json_invalid")); }
      if (!Array.isArray(parsed)) return alert(t("knowledge.actions_json_invalid"));
      builderActions = parsed;
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
      let parsed;
      try { parsed = JSON.parse(ta.value); } catch { return alert(t("inventory.json_invalid")); }
      if (!parsed || !Array.isArray(parsed.items)) return alert(t("inventory.json_invalid"));
      inventoryObj = parsed;
      invAdvancedOpen = false;
      drawInventoryTable();
    }
    updateAdvancedUi("inventory-editor", "inventory-json", "btn-inv-advanced", invAdvancedOpen);
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
      try { inv = JSON.parse(document.getElementById("inventory-json").value); }
      catch { return alert(t("inventory.json_invalid")); }
    } else {
      if (!inventoryObj) return;
      inv = inventoryObj;
    }
    await apiSend("PUT", `/api/projects/${state.projectId}/inventory`, inv);
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

// show/hide the structured editor vs. the raw-JSON textarea; the toggle button's
// data-i18n key is swapped so applyStatic keeps it correct across locale changes
function updateAdvancedUi(editorId, textareaId, btnId, open) {
  document.getElementById(editorId).hidden = open;
  document.getElementById(textareaId).hidden = !open;
  const btn = document.getElementById(btnId);
  btn.dataset.i18n = open ? "knowledge.builder.back" : "knowledge.builder.advanced";
  btn.textContent = t(btn.dataset.i18n);
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
// BomLine carries only the English `name`; localized names live on the catalog
// Product (`name_i18n`). Fetch the catalog once and map sku -> product for display.
let catalogProducts = null;
async function loadCatalogProducts() {
  if (!catalogProducts) {
    try {
      catalogProducts = (await apiGet("/api/catalog")).products || {};
    } catch {
      catalogProducts = {};
    }
  }
  return catalogProducts;
}

function lineName(products, line) {
  return products[line.sku]?.name_i18n?.[currentLocale()] || line.name;
}

async function renderBom() {
  const div = document.getElementById("bom-body");
  if (!state.result) { div.innerHTML = `<em>${t("bom.generate_first")}</em>`; return; }
  const [data, products, quotes] = await Promise.all([
    apiGet(`/api/runs/${state.result.run.id}/bom`),
    loadCatalogProducts(),
    apiGet(`/api/projects/${state.projectId}/quotes`).catch(() => []),
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
    + quotesHtml(quotes)
    + bomHtml(data.bom, products);
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
    <th>${t("bom.line_total")}</th><th>${t("quote.status")}</th><th></th></tr>`;
  for (const q of quotes) {
    html += `<tr><td dir="auto">${esc(q.label) || `<bdi class="meta">${esc(q.id.slice(0, 14))}</bdi>`}</td>
      <td class="num">${esc((q.created_at || "").slice(0, 16).replace("T", " "))}</td>
      <td class="num">${(q.total_cents / 100).toFixed(2)}</td>
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
          · <bdi>inv ${esc(q.inventory_hash)}</bdi> · <bdi>kb ${esc(q.knowledge_snapshot_hash)}</bdi></span>
          <button id="btn-quote-back">${t("quote.back_live")}</button>
        </div>` + bomHtml(q.bom, products);
      document.getElementById("btn-quote-back").addEventListener("click", renderBom);
    }));
}

function bomHtml(bom, products) {
  let html = `<div class="panel"><h3>${t("bom.title")} — ${t("bom.total")} €${(bom.total_cents / 100).toFixed(2)}</h3>
  <table><tr><th>${t("bom.sku")}</th><th>${t("bom.purchase")}</th><th>${t("bom.engineering")}</th>
  <th>${t("bom.overage")}</th><th>${t("bom.unit_price")}</th><th>${t("bom.line_total")}</th><th>${t("bom.notes")}</th></tr>`;
  for (const l of bom.lines) {
    html += `<tr><td><span class="sku">${esc(l.sku)}</span><br><span class="meta" dir="auto">${esc(lineName(products, l))}</span></td>
      <td><span class="num">${l.purchase_qty}</span> × ${esc(l.purchase_unit)}</td>
      <td><span class="num">${l.engineering_unit === "mm" ? esc(fmt(l.engineering_qty))
        : l.engineering_qty}</span> ${esc(l.engineering_unit === "mm" ? unitLabel()
        : l.engineering_unit)}</td>
      <td class="num">${l.overage_qty || ""}</td>
      <td class="num">${(l.unit_price_cents / 100).toFixed(2)}</td>
      <td class="num">${(l.total_cents / 100).toFixed(2)}</td>
      <td>${esc((l.notes || []).join("; "))}</td></tr>`;
  }
  html += "</table></div>";
  for (const [sku, plan] of Object.entries(bom.cut_plans || {})) {
    html += `<div class="panel"><h3>${t("bom.cut_plan")} — <span class="sku">${esc(sku)}</span>
      ${plan.certified_optimal ? `<span class="tag active">${t("bom.optimal")}</span>`
        : `<span class="tag medium">${t("bom.heuristic", { bound: plan.lp_lower_bound })}</span>`}</h3>
      <table><tr><th>${t("bom.bar_source")}</th><th>${tu("bom.stock")}</th><th>${tu("bom.cuts")}</th><th>${tu("bom.leftover")}</th></tr>`;
    for (const b of plan.bars) {
      html += `<tr><td><bdi>${esc(b.source)}</bdi></td><td class="num">${esc(fmt(b.stock_length_mm))}</td>
        <td class="num">${esc(b.pieces.map((p) => fmt(p.length_mm)).join(" + "))}</td>
        <td class="num">${esc(fmt(b.leftover_mm))}${b.leftover_reusable ? " ♻" : ""}</td></tr>`;
    }
    html += "</table></div>";
  }
  if ((bom.allocations || []).length) {
    html += `<div class="panel"><h3>${t("bom.allocations")}</h3>
      <table><tr><th>${t("bom.item")}</th><th>${t("bom.sku")}</th><th>${t("bom.used")}</th></tr>`;
    for (const a of bom.allocations)
      html += `<tr><td><bdi>${esc(a.inventory_item_id)}</bdi></td><td><span class="sku">${esc(a.sku)}</span></td>
        <td class="num">${a.length_used_mm ? esc(fmtLen(a.length_used_mm)) : a.qty}</td></tr>`;
    html += "</table></div>";
  }
  return html;
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
  const num = (key, labelKey, isLength = key.endsWith("_mm")) => {
    const raw = a[key] ?? "";
    const i = el("input", { type: "number",
      step: isLength ? inputStep() : "1",
      value: raw === "" || !isLength ? raw : toDisplayValue(raw) });
    i.addEventListener("change", () => {
      a[key] = isLength ? (toMm(i.value) ?? 0) : Math.round(i.valueAsNumber || 0);
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
    for (const p of KNOWN_PARAMS) s.appendChild(option(p, t("action.param." + p), a.param === p));
    s.appendChild(option("__other", t("action.param.other"), isOther));
    s.addEventListener("change", () => {
      a.param = s.value === "__other" ? "" : s.value;
      renderBuilderRows();  // swap the free-text param input in/out
    });
    row.appendChild(field("knowledge.builder.param", s));
    if (isOther) {
      const i = el("input", { type: "text", dir: "ltr", class: "sku", size: 20,
        placeholder: t("knowledge.builder.param_placeholder"), value: a.param });
      i.addEventListener("input", () => { a.param = i.value.trim(); });
      row.appendChild(i);
    }
    // a set_param value is a length exactly when its param name says so
    const paramIsLength = String(a.param || "").endsWith("_mm");
    row.appendChild(num("value",
      paramIsLength ? "knowledge.builder.value_len" : "knowledge.builder.value",
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

// ---------- impact preview (shared by review queue + knowledge form) ----------
function renderImpactReport(container, report) {
  let html = `<div class="impact"><b>${t("impact.summary",
    { affected: report.projects_affected, checked: report.projects_checked })}</b>`;
  for (const i of report.impacts) {
    if (!i.changed) continue;
    html += `<div class="impact-row"><bdi>${esc(i.project_name || i.project_id)}</bdi>: `;
    if (i.generation_failed) {
      html += `<span class="tag rejected">${t("impact.generation_fails")}</span>
        <span class="meta" dir="auto">${esc(i.generation_failed)}</span>`;
    } else {
      const delta = (i.bom_delta_cents / 100).toFixed(2);
      const sign = i.bom_delta_cents > 0 ? "+" : "";
      html += `${t("impact.spans", { before: i.spans_before, after: i.spans_after })} · `
        + `${t("impact.posts", { added: i.posts_added, removed: i.posts_removed, modified: i.posts_modified })} · `
        + `<span class="num">${sign}${delta}€</span>`;
      if (i.vs_accepted_delta_cents !== null && i.vs_accepted_delta_cents !== undefined) {
        const vs = (i.vs_accepted_delta_cents / 100).toFixed(2);
        const vsSign = i.vs_accepted_delta_cents > 0 ? "+" : "";
        html += ` · ${t("impact.vs_accepted", { delta: `${vsSign}${vs}` })}`;
      }
    }
    html += "</div>";
  }
  if (!report.projects_affected) html += `<div class="meta">${t("impact.none")}</div>`;
  html += "</div>";
  container.innerHTML = html;
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
