// Who is signed in. The ONE module that talks to `/api/session` and `/api/me` —
// everything else reads `state.me` or listens for `signed-in` / `signed-out`.
//
// **Signed out, the page is the login screen and nothing else** (`app.js`,
// `html[data-auth]`). That is the front door of the UI and not a security
// boundary: nothing on the server refuses an unsigned request (yet), apart from
// `POST /projects/{id}/actions`. This layer records who is asking; the server is
// what may one day gate.
//
// **The view comes from the server, not from a rule here.** `/api/me` answers it,
// because the thing that decides which view you open on is the same thing that
// can refuse an action, and a second copy of the rule in JS is a copy that
// drifts. `identity/model.py: default_view` is the one implementation.
//
// And the selector being hidden is a PRESENTATION fact, never protection: hiding
// is CSS and `localStorage` is editable, so an account that forces itself into
// another view has changed what it SEES and none of what it may DO.

import { emit, state } from "./state.js";

/** What a `/api/me` answer means for the screen.
 *
 *  Pure, so node can test the decision without a browser — `base-top.js`'s split
 *  applied again. It carries no capability list and decides nothing about what
 *  may be done; it answers two presentation questions and stops.
 */
export function applyMe(me) {
  return { user: me.user, view: me.view, selector: me.may_choose_view };
}

/** Nobody signed in — and **no opinion about the view**.
 *
 *  `view: null` means *leave it alone*. Signed out, the page is the login screen
 *  and shows no view at all, so there is nothing to set; only a signed-in account
 *  names a view, because only then is there somebody whose account says which.
 */
export function signedOutState() {
  return { user: null, view: null, selector: true };
}

/** Write one of those two shapes to the page.
 *
 *  `view.js` is imported lazily rather than at the top, and that is deliberate:
 *  `view.js` imports `i18n.js` which imports `state.js`, and a static import here
 *  would put this module inside that cycle for no gain — nothing needs `setView`
 *  until somebody has actually signed in or out.
 */
async function apply(shape) {
  state.me = shape.user;
  state.mayChooseView = shape.selector;
  document.documentElement.dataset.selector = shape.selector ? "yes" : "no";
  // Only when somebody named one. A null view leaves whatever `initView()`
  // restored from storage, which is what keeps a signed-out reload on the view
  // the person last chose.
  if (shape.view) {
    const { setView } = await import("./view.js");
    setView(shape.view);
  }
  emit(shape.user ? "signed-in" : "signed-out", shape.user);
}

/** Ask who we are. A 401 is the ordinary answer, not an error.
 *
 *  @returns false when the server could not be reached at all — the caller
 *  must SAY so, because the page is otherwise a login form that silently does
 *  nothing, or (before this answered) a blank screen. */
export async function loadMe() {
  let r;
  try {
    r = await fetch("/api/me");
  } catch {
    await apply(signedOutState());
    return false;
  }
  await apply(r.ok ? applyMe(await r.json()) : signedOutState());
  return true;
}

/** @returns `"ok"`, `"refused"` (wrong email or password — one answer for
 *  both, as the server gives), or `"unreachable"`. */
export async function signIn(email, password) {
  let r;
  try {
    r = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    return "unreachable";
  }
  if (!r.ok) return "refused";
  await apply(applyMe(await r.json()));
  return "ok";
}

/** Where this browser remembers the job a person last had open. Per ACCOUNT,
 *  so the next person to sign in on a shared machine does not land in it. */
export function lastProjectKey(userId) {
  return `fenceai.lastProject.${userId}`;
}

/** The job to open after sign-in: the one this person last had open, if it
 *  still exists — otherwise the first in the list, or null for none.
 *
 *  Pure, for node. Without it a sign-in (and every reload, since signing out
 *  reloads) opened whichever project in the whole database sorted first by a
 *  random id — for a salesperson, who has no Jobs tab, that meant a job she
 *  was halfway through could not be got back, and she could land in somebody
 *  else's. */
export function pickProject(list, rememberedId) {
  if (!Array.isArray(list) || !list.length) return null;
  if (rememberedId && list.some((p) => p.id === rememberedId)) return rememberedId;
  return list[0].id;
}

export async function signOut() {
  await fetch("/api/session", { method: "DELETE" });
  await apply(signedOutState());
}

export const currentUser = () => state.me;
