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

import { emit, state } from "./state.js";

/** What a `/api/session` answer means for the screen. Pure, for node. */
export function sessionState(body) {
  const ok = body.status === "ok";
  return {
    status: body.status,
    code: body.code || null,
    email: body.email || "",
    user: ok ? body.user : null,
    view: ok ? body.view : null,
    selector: ok ? body.may_choose_view : true,
  };
}

/** Write one of those shapes to the page.
 *
 *  `view.js` is imported lazily rather than at the top, and that is deliberate:
 *  `view.js` imports `i18n.js` which imports `state.js`, and a static import here
 *  would put this module inside that cycle for no gain — nothing needs `setView`
 *  until somebody has actually signed in or out.
 */
async function apply(shape) {
  state.me = shape.user;
  state.mayChooseView = shape.selector;
  state.authStatus = shape.status;
  state.authCode = shape.code;
  state.authEmail = shape.email;
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

export const currentUser = () => state.me;
