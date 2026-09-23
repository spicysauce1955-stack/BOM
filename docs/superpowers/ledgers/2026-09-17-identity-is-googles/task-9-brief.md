### Task 9: The people panel

**Files:**
- Create: `src/fenceai/web/static/js/people.js`
- Modify: `src/fenceai/web/static/index.html` (tab button + `#tab-people`), `src/fenceai/web/static/app.js` (init), `src/fenceai/web/static/js/view.js:52-123`
- Test: `tests/web/test_people_module.py`

**Interfaces:**
- Consumes: `GET /api/users`, `POST /api/users`, `PATCH /api/users/{id}` (Task 6); `esc` from `api.js`; `t` from `i18n.js`.
- Produces: `initPeople()`; `peopleRows(users) -> [{id, name, email, capacity, active, bound}]` pure.

- [ ] **Step 1: Write the failing node test**

Same shape as Task 8 Step 1 — a module-scoped `SCRIPT`, `node --input-type=module -e`, `cwd=STATIC`. There is no `run_node` helper to call.

```python
SCRIPT = """
import { peopleRows } from "./js/people.js";
console.log(JSON.stringify(peopleRows([
  {id:"u1", name:"Dana", email:"d@e.com", capacity:"sales",
   active:true, subject:"sub-1"},
  {id:"u2", name:"New", email:"n@e.com", capacity:"sales",
   active:true, subject:""},
  {id:"u3", name:"Gone", email:"g@e.com", capacity:"backoffice",
   active:false, subject:"sub-3"},
])));
"""


def test_a_grant_nobody_has_used_says_so(rows):
    """An empty `subject` is a row an admin made that nobody has signed in
    against yet — the normal state between granting and arriving, and the one
    an admin hunting a mistyped address has to be able to see."""
    assert [r["bound"] for r in rows] == [True, False, True]


def test_a_deactivated_person_is_still_listed(rows):
    """Deactivated, never deleted: the audit log names people who have left, so
    a row must keep resolving to a name for ever. A panel that hid them would
    make reactivating impossible."""
    assert rows[2]["active"] is False
    assert rows[2]["name"] == "Gone"
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/web/test_people_module.py -q`
Expected: FAIL — no such module.

- [ ] **Step 3: Write `people.js`**

```javascript
// Who may use this, and what each of them may do. The admin's panel, and the
// only screen in the app that WRITES a capacity.
//
// Owned entirely by this module: nothing else touches `#tab-people`, and this
// touches no other subtree. It talks to the rest of the app through `state.js`
// alone.
//
// Hiding this tab for a non-admin is a PRESENTATION fact and no protection at
// all — `POST /api/users` checks the capacity on the server, and that check is
// the one that matters. `view.js` carries the same paragraph.

import { apiGet, apiSend, esc } from "./api.js";
import { t } from "./i18n.js";
import { state } from "./state.js";

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
    bound: Boolean(u.subject),
  }));
}

function rowHtml(r) {
  const never = r.bound ? "" :
    ` <span class="muted">(${esc(t("people.never_signed_in"))})</span>`;
  return `<tr data-user="${esc(r.id)}"${r.active ? "" : ' class="inactive"'}>
    <td>${esc(r.name)}</td>
    <td><bdi class="sku">${esc(r.email)}</bdi>${never}</td>
    <td>${capacitySelect(r)}</td>
    <td><button class="toggle">${esc(t(r.active ? "people.deactivate"
                                               : "people.reactivate"))}</button></td>
  </tr>`;
}
```

Complete the module with `capacitySelect`, `render`, `initPeople` (a `change` listener PATCHing the capacity, a `click` listener toggling `active`, and a form POSTing a new grant), each refusal rendered by `t("error." + code)`.

- [ ] **Step 4: Add the tab**

In `index.html`, after the `models` button (line 67):

```html
    <button data-tab="people" data-i18n="tabs.people">People</button>
```

and a `<section id="tab-people" class="tab">` holding an `<h2 data-i18n="people.title">`, a `<table id="people-table">` and an add form with email, name and a capacity `<select>`.

In `view.js`, add `"people"` to `ALL_TABS`, and `'[data-tab="people"]'` to both `SALES_HIDDEN` and `BACKOFFICE_HIDDEN` — the admin view is the only one that shows it.

In `app.js`, call `initPeople()` beside `initEvidence()`.

- [ ] **Step 5: Run the web tests**

Run: `uv run pytest tests/web -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fenceai/web/static tests/web/test_people_module.py
git commit -m "feat(web): the people panel — the one screen that writes a capacity"
```

---

