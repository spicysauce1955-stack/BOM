// Who may use this, and what each of them may do. The admin's panel, and the
// only screen in the app that WRITES a capacity.
//
// Owned entirely by this module: nothing else touches `#tab-people`, and this
// touches no other subtree. It talks to the rest of the app through `state.js`
// alone.
//
// Hiding this tab for a non-admin is a PRESENTATION fact and no protection at
// all — `POST /api/users` and `PATCH /api/users/{id}` check the capacity on
// the server, and that check is the one that matters. `view.js` carries the
// same paragraph.

import { apiSend, esc } from "./api.js";
import { t } from "./i18n.js";
import { on } from "./state.js";

// The three capacities a grant may carry. `signin.capacity.*` already names
// them — the sign-in chip shows the same three words to the person who holds
// one — so this reuses that key family instead of opening a second one for
// the same vocabulary that could drift from it.
const CAPACITIES = ["sales", "backoffice", "admin"];

/** Pure, for node: what a row on this screen SAYS. */
export function peopleRows(users) {
  return (users || []).map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    capacity: u.capacity,
    active: u.active,
    // Bound means somebody has actually signed in against this row. An admin
    // hunting a mistyped address needs to see which grants nobody has used.
    // `_public` (api/app.py) never sends the raw Google `subject` id itself —
    // no screen has a use for a colleague's account id, and every signed-in
    // capacity can reach this row — so it answers with `subject_bound`
    // instead, and that is the field this reads.
    bound: Boolean(u.subject_bound),
  }));
}

function option(value, label, selected) {
  return `<option value="${esc(value)}"${selected ? " selected" : ""}>${esc(label)}</option>`;
}

// The one control on this screen that WRITES a capacity. It carries no
// `data-user` of its own — the `change` listener below reads that off the
// row it lives in, the same way `queue.js`'s delegated listeners read `data-id`
// off `closest("tr")` rather than off the control that fired.
function capacitySelect(r) {
  return `<select class="people-capacity">${
    CAPACITIES.map((c) => option(c, t(`signin.capacity.${c}`), c === r.capacity)).join("")
  }</select>`;
}

function rowHtml(r) {
  const never = r.bound ? "" :
    ` <span class="muted">(${esc(t("people.never_signed_in"))})</span>`;
  return `<tr data-user="${esc(r.id)}"${r.active ? "" : ' class="inactive"'}>
    <td>${esc(r.name)}</td>
    <td><bdi class="sku">${esc(r.email)}</bdi>${never}</td>
    <td>${capacitySelect(r)}</td>
    <td><button type="button" class="toggle">${esc(t(r.active ? "people.deactivate"
                                               : "people.reactivate"))}</button></td>
  </tr>`;
}

function headHtml() {
  return `<tr><th>${esc(t("people.name"))}</th><th>${esc(t("people.email"))}</th>
    <th>${esc(t("people.capacity"))}</th><th>${esc(t("people.active"))}</th></tr>`;
}

/** Redraws the whole table. Rebuilt from scratch on every call, like
 *  `queue.js`'s list — a row that just wrote a capacity or a state re-reads
 *  the server's own answer rather than trusting what the click meant to do,
 *  so a refusal (the server's, not this screen's) never leaves a row lying
 *  about what it now is.
 *
 *  A failed fetch renders the refusal CODE the server sent, not silence: an
 *  admin staring at an empty table cannot tell "nobody has access" from "the
 *  request failed" unless the failure says which one it is. */
async function render() {
  const host = document.getElementById("people-table");
  if (!host) return;
  const r = await fetch("/api/users");
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const code = body?.detail?.code || "server_unreachable";
    host.innerHTML = `<tr><td colspan="4"><span class="warning error">${
      esc(t(`error.${code}`))}</span></td></tr>`;
    return;
  }
  const users = await r.json();
  host.innerHTML = headHtml() + peopleRows(users).map(rowHtml).join("");
}

export function initPeople() {
  const table = document.getElementById("people-table");
  if (!table) return;

  // Delegated, not bound per-row: `render()` replaces every `<tr>` on every
  // change, so a listener attached to one row would stop firing the instant
  // its own handler redrew the table out from under it.
  table.addEventListener("change", async (e) => {
    const sel = e.target.closest(".people-capacity");
    if (!sel) return;
    const id = sel.closest("tr").dataset.user;
    // A refusal here (capacity_insufficient if the caller's own admin grant
    // was revoked mid-session, or a 404 if somebody else just removed the
    // row) goes through the app's one write-refusal path: `apiSend` alerts
    // `t("error."+code)` itself, exactly as every other write on this app
    // does — and then RE-THROWS. The browser has already moved the
    // `<select>` to the rejected value the instant the person picked it, so
    // `finally` (not a bare call after `await`) is load-bearing here: without
    // it a refusal leaves the control lying about who holds the capacity
    // until an unrelated redraw happens to fix it. `render()` in `finally`
    // runs on both outcomes and repaints from the server's real state either
    // way, which is what undoes the select's own optimistic change on a
    // refusal.
    try {
      await apiSend("PATCH", `/api/users/${id}`, { capacity: sel.value });
    } finally {
      render();
    }
  });

  table.addEventListener("click", async (e) => {
    const btn = e.target.closest(".toggle");
    if (!btn) return;
    const tr = btn.closest("tr");
    const wasActive = !tr.classList.contains("inactive");
    // `last_admin` lands here exactly this way: deactivating the only admin
    // account is refused by the server, not by this screen guessing who else
    // holds the capacity.
    await apiSend("PATCH", `/api/users/${tr.dataset.user}`, { active: !wasActive });
    render();
  });

  const form = document.getElementById("people-add-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("people-new-email").value.trim();
    const name = document.getElementById("people-new-name").value.trim();
    const capacity = document.getElementById("people-new-capacity").value;
    if (!email || !name) return;
    // in-flight: a second press must not post the same grant twice — the same
    // guard `notes.js` puts on its add button, and for a sharper reason here.
    // Without it a double-click fired two POSTs, both of which read no existing
    // row on the server, and the second collided with `users.email`'s UNIQUE
    // constraint: a 500 and a generic alert where the answer is a plain
    // "that address already has a row". The server no longer 500s
    // (`Store.create_user_guarded`) — correctness lives there, not here — but
    // the second request is still a request nobody meant to send, and the
    // button that stays pressable during a write is what makes it happen.
    //
    // `finally`, not a line after the `await`: `apiSend` RE-THROWS every
    // refusal after showing its dialog, so a plain re-enable would be skipped
    // on exactly the outcome where the admin needs the control back — a
    // mistyped address would leave the form dead until a reload.
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      // `user_exists` (that address already has a row) surfaces the same way.
      await apiSend("POST", "/api/users", { email, name, capacity });
    } finally {
      if (submit) submit.disabled = false;
    }
    form.reset();
    render();
  });

  // Lazy, like the Knowledge/Review/BOM tabs `tabs.js` redraws on first
  // sight: nobody but an admin ever opens this tab, so drawing it on every
  // sign-in would fetch the whole user list for two capacities that can never
  // see it.
  let drawnOnce = false;
  on("tab-changed", (name) => {
    if (name !== "people") return;
    drawnOnce = true;
    render();
  });
  // A capacity word ("Sales" / "Admin") is prose, not an id — it has to be
  // redrawn in the new language exactly as `queue.js`'s own list is. But only
  // if this tab has ever been drawn: unconditionally, a locale flip undid the
  // laziness three lines above, fetched `/api/users`, and materialised the
  // whole company roster — names, addresses, capacities — into the DOM of a
  // salesperson who can never open this tab. `GET /api/users` is open to every
  // capacity by design (it feeds the assignee picker), so this was never a
  // server hole; it was us putting it on their page anyway.
  on("locale-changed", () => { if (drawnOnce) render(); });
}
