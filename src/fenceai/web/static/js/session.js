// Who is signed in. The ONE module that talks to `/api/session` and `/api/me` —
// everything else reads `state.me` or listens for `signed-in` / `signed-out`.
//
// **Signed out is not a locked door.** It is today's app, on the `all` view, with
// the selector everybody has right now. Every existing browser check runs that
// way and so does every person using this today, so accounts had to be an
// addition rather than a breaking change wearing one. Nothing on the server
// refuses an unsigned request either (yet) — this layer records who is asking, it
// does not gate.
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

/** Nobody signed in: the full app, the selector everybody has today — and
 *  **no opinion about the view**.
 *
 *  `view: null` means *leave it alone*, and that is the whole point rather than a
 *  missing value. Signed out is today's app, and today's app REMEMBERS the toggle
 *  in `localStorage` across a reload. Returning `"all"` here made every unsigned
 *  page load quietly overwrite that preference — the browser smoke caught it on
 *  the check that reloads in sales mode and expects the vocabulary to survive,
 *  and the node test above had asserted the wrong behaviour so it passed.
 *
 *  Only a signed-in account names a view, because only then is there somebody
 *  whose account says which one.
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

/** Ask who we are. A 401 is the ordinary answer, not an error. */
export async function loadMe() {
  const r = await fetch("/api/me");
  await apply(r.ok ? applyMe(await r.json()) : signedOutState());
}

/** @returns true when the credentials were accepted. */
export async function signIn(email, password) {
  const r = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) return false;
  await apply(applyMe(await r.json()));
  return true;
}

export async function signOut() {
  await fetch("/api/session", { method: "DELETE" });
  await apply(signedOutState());
}

export const currentUser = () => state.me;
