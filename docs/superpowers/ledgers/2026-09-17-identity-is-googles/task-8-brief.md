### Task 8: The frontend — picker, banner, no-access screen

**Files:**
- Modify: `src/fenceai/web/static/index.html:14-27`, `src/fenceai/web/static/app.js:64-118,186`, `src/fenceai/web/static/js/session.js`, `src/fenceai/web/static/style.css`
- Modify: `src/fenceai/web/static/i18n/en.json`, `src/fenceai/web/static/i18n/he.json`
- Test: `tests/web/test_login_screen.py` (extend), `tests/web/test_locale_bundles.py` (passes as-is)

**Interfaces:**
- Consumes: `GET /api/session`, `POST /api/dev/identity` (Tasks 3-4).
- Produces: `loadSession() -> boolean`; `become(email) -> "ok" | "refused" | "unreachable"`; `signOut()`; `sessionState(body)` pure, returning `{user, view, selector, status, email}`.

- [ ] **Step 1: Write the failing node test**

Create `tests/web/test_session_module.py`. **There is no shared `run_node` helper** — copy `tests/web/test_base_top_module.py`'s shape exactly: a module-scoped `SCRIPT` string, run through `node --input-type=module -e` with `cwd=STATIC`, returning parsed JSON from one `console.log`.

```python
"""`session.js`'s pure half, in node.

`sessionState` decides nothing about what may be DONE — it answers which
screen this is and who to name on it. Pure, so node can check it without a
browser: `base-top.js`'s split applied again.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { sessionState } from "./js/session.js";

const out = {};
out.ok = sessionState({status:"ok", email:"d@e.com",
                       user:{id:"u1", name:"Dana", capacity:"sales"},
                       view:"sales", may_choose_view:false});
out.none = sessionState({status:"no_capacity", email:"s@e.com", user:null});
out.off = sessionState({status:"deactivated", email:"g@e.com", user:null});
out.anon = sessionState({status:"no_identity", email:"", user:null});
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def ss():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "--input-type=module", "-e", SCRIPT],
        cwd=STATIC, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_resolved_answer_carries_the_person_and_their_view(ss):
    assert ss["ok"]["user"]["name"] == "Dana"
    assert ss["ok"]["view"] == "sales"
    assert ss["ok"]["selector"] is False


def test_a_refused_answer_names_the_address_but_nobody(ss):
    """The screen that says "ask an admin" has to be able to name you TO the
    admin you are about to ask — so `email` survives where `user` does not."""
    assert ss["none"]["status"] == "no_capacity"
    assert ss["none"]["email"] == "s@e.com"
    assert ss["none"]["user"] is None


def test_deactivated_is_its_own_answer_and_not_no_capacity(ss):
    """They HAVE a row. Telling them to ask for access would send them asking
    for something they already have."""
    assert ss["off"]["status"] == "deactivated"


def test_nobody_at_all_leaves_the_view_alone(ss):
    """`view: null` means *leave it alone*, and that is the point rather than a
    missing value — returning "all" here made every unsigned page load
    overwrite the remembered toggle, which the browser smoke caught once
    already."""
    assert ss["anon"]["status"] == "no_identity"
    assert ss["anon"]["view"] is None
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/web/test_session_module.py -q`
Expected: FAIL — `sessionState` is not exported.

- [ ] **Step 3: Rewrite `session.js`'s exported surface**

Replace the header comment and the four functions. Keep `applyMe`'s successor pure; keep `lastProjectKey` and `pickProject` exactly as they are.

```javascript
// Who is signed in. The ONE module that talks to `/api/session` — everything
// else reads `state.me` or listens for `signed-in` / `signed-out`.
//
// **Google holds the identity; we hold the capacity.** There is no password
// here and no session cookie of ours. Under `iap` a signed assertion names the
// person before the request reaches the app; under `dev` a credential-less
// cookie does, set by the picker below. Either way this module asks one
// question — `GET /api/session` — and the server answers who, which view, and
// whether there is a capacity row at all.
//
// **Every API route now refuses a caller with no capacity row.** The screen is
// no longer the only thing between somebody and the data, which is what it
// was when it shipped.

/** What a `/api/session` answer means for the screen. Pure, for node. */
export function sessionState(body) {
  const ok = body.status === "ok";
  return {
    status: body.status,
    email: body.email || "",
    user: ok ? body.user : null,
    view: ok ? body.view : null,
    selector: ok ? body.may_choose_view : true,
  };
}

/** Ask who we are.
 *  @returns false when the server could not be reached at all — the caller
 *  must SAY so, or the page is a picker that silently does nothing. */
export async function loadSession() {
  let r;
  try {
    r = await fetch("/api/session");
  } catch {
    await apply(sessionState({ status: "no_identity", user: null }));
    return false;
  }
  if (!r.ok) {
    await apply(sessionState({ status: "no_identity", user: null }));
    return true;
  }
  await apply(sessionState(await r.json()));
  return true;
}

/** Become somebody, on a laptop. There is no credential: `POST
 *  /api/dev/identity` exists only under `FENCEAI_IDENTITY=dev`, and under
 *  `iap` this returns "refused" because the route is not there.
 *  @returns `"ok"`, `"refused"`, or `"unreachable"`. */
export async function become(email) {
  let r;
  try {
    r = await fetch("/api/dev/identity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
  } catch {
    return "unreachable";
  }
  if (!r.ok) return "refused";
  return (await loadSession()) ? "ok" : "unreachable";
}

/** Signing out stops being ours.
 *
 *  IAP keeps the promise better than a row we delete — revoking access is
 *  removing the grant, centrally, for every device at once — but the APP
 *  cannot do it. So this is a redirect, not a DELETE. Under `dev` there is a
 *  cookie to clear and nothing to revoke.
 */
export async function signOut() {
  try { await fetch("/api/dev/identity", { method: "DELETE" }); } catch { /* iap */ }
  location.href = "/?gcp-iap-mode=CLEAR_LOGIN_COOKIE";
}
```

Update `apply()` to take the new shape and set `document.documentElement.dataset.auth`:

```javascript
async function apply(shape) {
  state.me = shape.user;
  state.mayChooseView = shape.selector;
  state.authStatus = shape.status;
  state.authEmail = shape.email;
  document.documentElement.dataset.selector = shape.selector ? "yes" : "no";
  if (shape.view) {
    const { setView } = await import("./view.js");
    setView(shape.view);
  }
  emit(shape.user ? "signed-in" : "signed-out", shape.user);
}
```

Add `DELETE /api/dev/identity` to `app.py` beside the POST (same `if`), clearing the cookie and returning 204.

- [ ] **Step 4: Replace the form in `index.html`**

```html
  <!-- The front door. Google decides who reaches it; a capacity row decides
       what they may do once inside. Under `dev` this is a picker with no
       password — an impersonation switch, and named as one. `html[data-auth]`
       drives the hiding (style.css), `app.js` sets it. -->
  <section id="login-screen" aria-labelledby="login-title">
    <form id="sign-in">
      <h1 id="login-title">Fence AI</h1>
      <input id="sign-in-email" type="email" autocomplete="username" required
             data-i18n-placeholder="signin.email" placeholder="Email">
      <button type="submit" class="primary" data-i18n="signin.become">Continue</button>
      <p id="sign-in-error" class="warning error" hidden data-i18n="error.no_identity"></p>
      <p id="sign-in-unreachable" class="warning error" hidden data-i18n="error.server_unreachable"></p>
    </form>
  </section>

  <!-- IAP let them to the door; nobody has said what they may do inside. -->
  <section id="no-access" aria-labelledby="no-access-title" hidden>
    <h1 id="no-access-title" data-i18n="noaccess.title">No access yet</h1>
    <p data-i18n="noaccess.body">Ask an administrator to give this address access.</p>
    <p><span data-i18n="noaccess.signed_in_as">Signed in as</span>
       <bdi id="no-access-email" class="sku"></bdi></p>
    <button id="no-access-signout" data-i18n="signin.out">Sign out</button>
  </section>
```

- [ ] **Step 5: Rewrite `wireIdentity()` in `app.js`**

```javascript
function wireIdentity() {
  const form = document.getElementById("sign-in");
  const chip = document.getElementById("signed-in-as");
  const err = document.getElementById("sign-in-error");
  const unreachable = document.getElementById("sign-in-unreachable");
  const noAccess = document.getElementById("no-access");

  const render = () => {
    const me = state.me;
    const refused = state.authStatus === "no_capacity" ||
                    state.authStatus === "deactivated" ||
                    state.authStatus === "subject_mismatch";
    document.documentElement.dataset.auth = me ? "in" : (refused ? "denied" : "out");
    chip.hidden = !me;
    noAccess.hidden = !refused;
    if (refused)
      document.getElementById("no-access-email").textContent = state.authEmail;
    if (!me) return;
    document.getElementById("me-name").textContent = me.name;
    document.getElementById("me-capacity").textContent =
      t(`signin.capacity.${me.capacity}`);
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    unreachable.hidden = true;
    const outcome = await become(document.getElementById("sign-in-email").value);
    if (outcome === "refused") err.hidden = false;
    else if (outcome === "unreachable") unreachable.hidden = false;
  });
  document.getElementById("sign-out").addEventListener("click", signOut);
  document.getElementById("no-access-signout").addEventListener("click", signOut);

  on("signed-in", async () => { render(); await openWorkspace(); });
  on("signed-out", render);
  on("project-opened", (id) => {
    if (!state.me) return;
    try { localStorage.setItem(lastProjectKey(state.me.id), id); } catch { /* storage off */ }
  });
}
```

Change the import at line 31 to `import { become, lastProjectKey, loadSession, pickProject, signOut } from "./js/session.js";` and line 186 to `if (!(await loadSession()))`.

- [ ] **Step 6: Add the `denied` state to `style.css`**

Beside the existing `data-auth` rules, keyed on NOT so `pending` still hides everything:

```css
/* Three states now, not two. Keyed on :not() for the reason the other two
   are: a rule written as [data-auth="denied"] #no-access would flash the
   refusal on every signed-in reload. */
html:not([data-auth="denied"]) #no-access { display: none; }
html[data-auth="denied"] body > :not(#no-access) { display: none; }
```

- [ ] **Step 7: Add the locale keys to BOTH bundles**

`en.json` — add, and delete `signin.password` and `error.sign_in_failed`:

```json
"signin.become": "Continue",
"error.no_identity": "This browser is not signed in.",
"error.no_capacity": "This address has no access here yet.",
"error.account_deactivated": "This account has been deactivated.",
"error.subject_mismatch": "This address is registered to a different Google account. Ask an administrator.",
"error.capacity_insufficient": "You do not have permission to do that.",
"error.user_exists": "Somebody already has that address.",
"error.user_not_found": "No such person.",
"error.last_admin": "This is the only administrator left.",
"noaccess.title": "No access yet",
"noaccess.body": "Ask an administrator to give this address access.",
"noaccess.signed_in_as": "Signed in as",
"tabs.people": "People",
"people.title": "Who may use this",
"people.add": "Give somebody access",
"people.name": "Name",
"people.email": "Email",
"people.capacity": "May do",
"people.active": "Active",
"people.deactivate": "Deactivate",
"people.reactivate": "Reactivate",
"people.never_signed_in": "has not signed in yet"
```

`he.json` — the same keys, Hebrew values:

```json
"signin.become": "המשך",
"error.no_identity": "הדפדפן הזה אינו מחובר.",
"error.no_capacity": "לכתובת הזו אין עדיין גישה כאן.",
"error.account_deactivated": "החשבון הזה הושבת.",
"error.subject_mismatch": "הכתובת רשומה לחשבון Google אחר. פנו למנהל.",
"error.capacity_insufficient": "אין לכם הרשאה לפעולה הזו.",
"error.user_exists": "הכתובת הזו כבר שייכת למישהו.",
"error.user_not_found": "אין אדם כזה.",
"error.last_admin": "זה המנהל האחרון שנותר.",
"noaccess.title": "אין עדיין גישה",
"noaccess.body": "בקשו ממנהל לתת גישה לכתובת הזו.",
"noaccess.signed_in_as": "מחוברים בתור",
"tabs.people": "אנשים",
"people.title": "מי רשאי להשתמש",
"people.add": "תנו למישהו גישה",
"people.name": "שם",
"people.email": "דוא״ל",
"people.capacity": "רשאי/ת",
"people.active": "פעיל",
"people.deactivate": "השבתה",
"people.reactivate": "הפעלה מחדש",
"people.never_signed_in": "עדיין לא התחבר/ה"
```

- [ ] **Step 8: Update `test_login_screen.py`**

Replace `test_the_login_screen_holds_the_form_and_the_header_does_not` assertions about the password field, and add:

```python
def test_the_front_door_asks_for_no_password():
    """There is none. A field for one would be asking for a secret the system
    cannot check and must never store."""
    html = (STATIC / "index.html").read_text()
    assert 'type="password"' not in html
    assert "sign-in-password" not in html


def test_a_refused_arrival_gets_a_screen_of_their_own():
    """Not a blank app and not the picker again. IAP let them to the door;
    this is the screen that tells them what to ask for."""
    html = (STATIC / "index.html").read_text()
    assert 'id="no-access"' in html
    assert 'data-i18n="noaccess.body"' in html
    css = _css()
    assert re.search(
        r'html:not\(\[data-auth="denied"\]\)\s+#no-access\s*\{\s*display:\s*none', css)
    assert re.search(
        r'html\[data-auth="denied"\]\s+body\s*>\s*:not\(#no-access\)\s*\{\s*display:\s*none', css)
```

- [ ] **Step 9: Run the web tests**

Run: `uv run pytest tests/web -q`
Expected: PASS, including `test_locale_bundles.py`'s identical-key-set check.

- [ ] **Step 10: Commit**

```bash
git add src/fenceai/web/static tests/web
git commit -m "feat(web): a front door with no password, and a screen for somebody nobody has granted"
```

---

