// Tab panels: annotations, knowledge, review queue, BOM, inventory.

import { apiGet, apiSend, esc } from "./api.js";
import { currentLocale, t } from "./i18n.js";
import { on, reloadProject, state } from "./state.js";

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
    try { actions = JSON.parse(document.getElementById("k-actions").value); }
    catch { alert(t("knowledge.actions_json_invalid")); return null; }
    return {
      object_id: document.getElementById("k-object").value.trim(),
      type: document.getElementById("k-type").value,
      title: document.getElementById("k-title").value, actions, author: "expert-admin",
    };
  };
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
    try { inv = JSON.parse(document.getElementById("inventory-json").value); }
    catch { return alert(t("inventory.json_invalid")); }
    await apiSend("PUT", `/api/projects/${state.projectId}/inventory`, inv);
    alert(t("inventory.saved"));
  });

  on("project-loaded", () => {
    renderAnnTargets(); renderAnnotations(); renderInventory(); maybeRenderBom();
  });
  on("result-changed", maybeRenderBom);
  on("locale-changed", () => {
    renderAnnTargets(); renderAnnotations(); maybeRenderBom();
    if (document.getElementById("tab-knowledge").classList.contains("active")) renderKnowledge();
    if (document.getElementById("tab-review").classList.contains("active")) renderCandidates();
  });
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
    </div>`
    + quotesHtml(quotes)
    + bomHtml(data.bom, products);
  document.getElementById("btn-save-quote").addEventListener("click", async () => {
    const label = prompt(t("quote.label_prompt")) ?? "";
    await apiSend("POST", `/api/runs/${state.result.run.id}/quote`, { label });
    renderBom();
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
      <td><span class="num">${l.engineering_qty}</span> ${esc(l.engineering_unit)}</td>
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
      <table><tr><th>${t("bom.bar_source")}</th><th>${t("bom.stock")}</th><th>${t("bom.cuts")}</th><th>${t("bom.leftover")}</th></tr>`;
    for (const b of plan.bars) {
      html += `<tr><td><bdi>${esc(b.source)}</bdi></td><td class="num">${b.stock_length_mm}</td>
        <td class="num">${b.pieces.map((p) => p.length_mm).join(" + ")}</td>
        <td class="num">${b.leftover_mm}${b.leftover_reusable ? " ♻" : ""}</td></tr>`;
    }
    html += "</table></div>";
  }
  if ((bom.allocations || []).length) {
    html += `<div class="panel"><h3>${t("bom.allocations")}</h3>
      <table><tr><th>${t("bom.item")}</th><th>${t("bom.sku")}</th><th>${t("bom.used")}</th></tr>`;
    for (const a of bom.allocations)
      html += `<tr><td><bdi>${esc(a.inventory_item_id)}</bdi></td><td><span class="sku">${esc(a.sku)}</span></td>
        <td class="num">${a.length_used_mm ? a.length_used_mm + " mm" : a.qty}</td></tr>`;
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
    card.innerHTML = html;
    card.querySelector('[data-act="interpret"]').addEventListener("click", async () => {
      await apiSend("POST", `/api/projects/${state.projectId}/annotations/${ann.id}/interpret`);
      await reloadProject();
    });
    card.querySelectorAll("[data-confirm]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        let runId = ann.target_ref.startsWith("run:") ? ann.target_ref.slice(4) : null;
        if (!runId) {
          const options = state.project.topology.runs.map((r) => r.id).join(", ");
          runId = prompt(t("annotations.which_run", { options }),
            state.project.topology.runs[0]?.id);
          if (!runId) return;
        }
        await apiSend("POST",
          `/api/projects/${state.projectId}/intents/${btn.dataset.confirm}/confirm`,
          { annotation_id: btn.dataset.ann, run_id: runId });
        await reloadProject();
      }));
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
      <div class="impact-out"></div>`;
    card.querySelector("[data-preview]").addEventListener("click", async () => {
      const out = card.querySelector(".impact-out");
      out.innerHTML = `<em>${t("impact.computing")}</em>`;
      const report = await apiSend(
        "POST", `/api/candidates/${c.object_id}/${c.version}/preview`);
      renderImpactReport(out, report);
    });
    card.querySelectorAll("button[data-a]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const action = btn.dataset.a;
        const body = { action, reviewer: "expert-admin" };
        if (action === "reject") {
          body.reason = prompt(t("review.why_reject")) || "no reason given";
        } else if (action === "scope_restrict") {
          const extra = prompt(t("review.scope_prompt"));
          if (!extra || !extra.includes("=")) return;
          const [k, val] = extra.split("=");
          body.edited_scope = { ...c.scope, [k.trim()]: val.trim() };
        }
        await apiSend("POST", `/api/candidates/${c.object_id}/${c.version}/review`, body);
        renderCandidates(); renderKnowledge();
      }));
    div.appendChild(card);
  }
}

// ---------- inventory ----------
async function renderInventory() {
  if (!state.projectId) return;
  const inv = await apiGet(`/api/projects/${state.projectId}/inventory`);
  document.getElementById("inventory-json").value = JSON.stringify(inv, null, 2);
}
