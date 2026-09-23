# Slice 2's carried findings — triage and disposition

Every one of these was found by running the code, not by reading it.

Slice 2 (`docs/superpowers/specs/2026-09-17-identity-is-googles-design.md`, ADR-0013)
put a real gate in front of every `/api` route and deleted the password store
it replaced. Twelve findings surfaced while that slice's own reviewers and
implementers exercised the running app — a `sales` account probing routes it
should not reach, a CDP session watching `wait_for` swallow a real error, a
form submitted with a `type` the DTO never declared. None of them were caught
by reading `identity/` or `api/auth.py`; all twelve were caught by doing
something to the running system and watching what came back. This document
is the dispositions the user made with the implementer on 2026-09-23, so the
next few slices inherit a plan instead of a rediscovery.

Finding 3 is fixed, in this slice. The other eleven are not fixed here — each
has a named home below, not a hope of getting to it eventually.

## 1. Per-capacity authorization is enforced at three places only

**Finding.** ADR-0013's gate resolves every caller to an active capacity row
before any route body runs, but almost nothing downstream of that checks
*which* capacity the row holds. A `sales` account can read `/api/audit`,
author an ACTIVE knowledge version, retire a safety rule, publish a fence
model, and edit another salesperson's job — the only capacity-checked routes
in the whole app are `POST /api/users`, `PATCH /api/users/{id}` (`require_admin`)
and the command door's own per-kind check.

**How it was found.** Signed in as a `sales` capacity row and called routes a
salesperson has no product reason to reach; each answered 200.

**What it costs.** The largest open item in the identity work: default-deny
at the door does not imply per-capacity separation of duties behind it, and
right now there isn't any beyond the two admin routes.

**Disposition.** A slice of its own, next. Already named in spec §9 and
declared in ADR-0013's own Consequences ("Per-capacity authorization is still
a separate slice").

## 2. An unknown `kid` does not force a key refresh

**Finding.** `identity/iap.py` caches Google's public keys and verifies a
JWT's signature against the cached set, but when a JWT presents a `kid` the
cache does not hold, nothing forces an immediate refetch — the caller is
refused until the cache's own refresh timer comes around, which can be up to
an hour.

**How it was found.** Simulated a Google key rotation by minting a JWT signed
with a key not in the cache and watching every subsequent request refuse,
across the cache's full TTL, rather than recovering on the next legitimate
key.

**What it costs.** A scheduled Google key rotation — which Google performs
routinely and without asking this app first — costs up to an hour of
company-wide refusal: every real user locked out simultaneously, with no
action available to an admin to shorten it.

**Disposition.** Slice 4. Has teeth only once real Google keys are in play
(today's tests run against synthetic keys); it is the largest availability
risk in the IAP adapter.

## 3. A database booted under `dev` and later run under `iap` is locked out forever

**Finding.** `dev` mode seeds three demo accounts with fixed ids and
`@example.com` addresses. Nothing stopped the same database from later being
served under `FENCEAI_IDENTITY=iap`, where those rows can never be reached by
a real Google account (Google will never authenticate an `example.com`
address), and `FENCEAI_BOOTSTRAP_ADMIN` is disabled by design while any admin
row is active — so the seeded admin row blocks recovery forever.

**How it was found.** Booted a container against a database created by a
`dev`-mode boot, switched `FENCEAI_IDENTITY` to `iap`, and watched every
request refuse with no path back in.

**What it costs.** A deployment permanently and silently unusable, discovered
only when someone tries to sign in.

**Disposition. Done in slice 3** — `identity/dev.py:dev_seed_lockout` refuses
to boot at all when the target database carries a dev-seeded row and identity
is `iap`, naming the offending rows and the exact remedy in the refusal
message rather than letting the app come up and refuse every request one at
a time. See ADR-0013's Consequences and `docs/v1-runbook.md`'s
Troubleshooting section for the exact behaviour.

## 4. The IAP key grace window is not enforced between retries

**Finding.** Keys past their declared boundary (Google publishes a
recommended rotation grace period) continue to verify signatures for up to
60 seconds after the boundary, because the grace window is checked once per
cache refresh rather than per verification.

**How it was found.** Same harness as finding 2: minted a JWT with a key held
past its declared boundary and confirmed it still verified inside the
60-second window between cache refreshes.

**What it costs.** A narrow but real window where a key Google considers
retired still authenticates a request here — not exploitable by an outsider
(the key material itself is never exposed by this finding), but a correctness
gap between what Google publishes as valid and what this app accepts.

**Disposition.** Slice 4, with finding 2 — same file (`identity/iap.py`),
same trip through the code, no reason to open it twice.

## 5. No CSRF token, no Origin check, no CORS middleware

**Finding.** The app has no CSRF defense of its own. Exploitability rests
entirely on IAP's cookie being `SameSite`, which is Google's choice, is not
configurable from this app, and is documented nowhere in this repository.

**How it was found.** Read the request pipeline looking for exactly this
check while probing the gate for finding 1, and confirmed by cross-origin
request against a running instance behind `dev` identity — the request
succeeded.

**What it costs.** If IAP's own cookie behaviour ever changes, or if a
future deployment path puts something other than IAP in front of this app,
there is no second layer. Today, this is the one item in this table that is
documentation risk more than code risk — the gap is that nobody has written
down the assumption this app's safety currently depends on.

**Disposition.** Slice 4, as a stated assumption in ADR-0013 at minimum.
Documentation, not code — and therefore the one most easily forgotten,
because there is no failing test to remind anyone it is still open.

## 6. `Selection.author`, `Override.author` and `IntentConfirm.confirmed_by` are client-named

**Finding.** Three DTOs still accept a client-supplied actor field and carry
it into the decision graph as `author`/`chosen_by`, the same shape of bug
slice 2 fixed for eleven other routes (see slice 2's checkpoint entry in
`plan/current-status.md`) — but these three were not in the sweep that found
the others. Two sites: `Selection.author` and `Override.author`. A third:
`IntentConfirm.confirmed_by` (`src/fenceai/api/app.py:1032-1035`, the DTO
field; `src/fenceai/api/app.py:1043`, passed unchanged into
`confirm_intent`), which reaches the decision graph the same way —
`src/fenceai/project/intents.py:73` writes it as `author=confirmed_by` on a
materialized `Override`, and `:82` stamps it onto `intent.confirmed_by`.

**How it was found.** The two DTO fields were found by a grep for `author=`
and `chosen_by=` against the DTOs, run specifically because finding 1's
probing raised the question "who else can a client claim to be" — that was
slice 2's review round. The third site, `IntentConfirm.confirmed_by`, was
found later, during slice 3, by `architecture-critic` reading the code
rather than running it — worth saying plainly, since this document opens by
claiming every finding in it was found by running the code, and this one
site was not.

**What it costs.** The same claim-forging risk slice 2 fixed elsewhere: the
decision graph can attribute a selection, an override, or a confirmed
intent to somebody who never made it.

**Disposition.** With finding 1 — same surface, who the actor is.
`tests/api/test_gate.py`'s guard docstring records it rather than pretending
the gate already covers it.

## 7. A binding can never be cleared

**Finding.** `identity/binding.py` binds a `subject` (Google's `sub`) to a
`users` row on first arrival and refuses any other subject arriving on the
same address (`subject_mismatch`, by design — see ADR-0013). But no route
exists to clear that binding, so a Google account that is deleted and
recreated (which mints a new `sub` for the same address) is refused forever,
with no admin action available to fix it.

**How it was found.** Bound an address, simulated the account being deleted
and recreated with a fresh `sub` (the realistic failure mode for
offboarding/reboarding through Google Workspace), and confirmed there is no
route that resets `subject` to admit the new one.

**What it costs.** A real, not hypothetical, offboarding scenario locks a
person out permanently unless someone deletes and recreates the `users` row
directly against the database.

**Disposition.** With finding 1 — an admin-routes change, alongside the
per-capacity work.

## 8. `Principal.subject` is not stripped

**Finding.** `identity/model.py`'s `Principal.email` is stripped and
normalized on construction; `Principal.subject` is not. A `sub` claim with
leading or trailing whitespace binds as a distinct subject from the same
value without the whitespace.

**How it was found.** Constructed a `Principal` with a whitespace-padded
`subject` and watched it bind separately from the unpadded value, rather
than being rejected or normalized.

**What it costs.** Narrow — Google's own `sub` claims do not carry stray
whitespace in practice — but it is an inconsistency with how `email` is
already handled, and a cheap one to close.

**Disposition.** Next slice, quick.

## 9. `POST /api/knowledge` 500s on a `type` outside the Literal

**Finding.** The DTO's `type` field is a bare `str`, not the `Literal` the
rest of the schema implies, so a request naming an unrecognized type reaches
domain code that assumes the Literal's closed set and raises unhandled,
answering 500 instead of 422.

**How it was found.** Submitted a knowledge-authoring request with a
deliberately wrong `type` value and got an unhandled exception traceback
back instead of a validation error.

**What it costs.** A client bug or typo becomes a 500 instead of a normal
validation failure — noisy in logs and a worse error message for whoever
sent it, but not a security or data-integrity issue.

**Disposition.** Next slice, quick.

## 10. `tools/ui_smoke.py`'s `wait_for` lets a CDP evaluation error raise

**Finding.** `wait_for`'s polling loop does not catch an error raised by the
CDP evaluation itself (as opposed to the condition it's testing); a
transient null — the page briefly not having the element the JS expects —
aborts the entire smoke run instead of being retried like any other
not-yet-true condition.

**How it was found.** Watched a real run abort mid-suite on a transient
condition that a retry one poll interval later would have resolved.

**What it costs.** An occasional false-negative full-suite abort, costing
whoever is running the smoke suite a rerun and some confusion about whether
something actually broke.

**Disposition.** Deferred unless it bites during slice 3 — it did not.
Narrow it when done: swallow only the evaluation error and print the last
one in the timeout's own detail, so a genuinely broken selector still times
out loudly with a useful message. A blanket `try/except` around the whole
poll would turn a broken selector into a mute timeout, which is worse than
the bug it fixes.

## 11. People table accessibility

**Finding.** The People admin table has unlabelled `<select>` elements and
buttons (no accessible name beyond visual context) and `<th>` cells with no
`scope` attribute, so the table's structure is not announced correctly to
assistive technology.

**How it was found.** Ran an accessibility pass over the People tab while
building the admin routes for slice 2's capacity work.

**What it costs.** The admin-only People tab is not usable with a screen
reader today. Low usage surface (admins only) but a real gap.

**Disposition.** Next frontend slice.

## 12. `#sign-in-error` is hard-bound to `error.no_identity`

**Finding.** The sign-in error element always renders the `no_identity`
message regardless of which of the gate's actual refusal reasons
(`no_identity`, `no_capacity`, `account_deactivated`, `subject_mismatch`)
fired — so a deactivated or mismatched account sees "you are not signed in,"
the wrong sentence for the one moment it matters most.

**How it was found.** Triggered `account_deactivated` and `subject_mismatch`
against a running frontend and read the message actually shown, rather than
the one the gate returned.

**What it costs.** Confusing, incorrect guidance at exactly the moment a
real access problem needs an accurate explanation — an admin fields a "why
can't I log in" question that the UI itself could have answered correctly.

**Disposition.** Next frontend slice, with finding 11.

---

## Where each finding lives next

| Slice | Findings |
|---|---|
| Slice 3 (this slice) | 3 — done |
| Per-capacity authorization slice (next) | 1 (opens it), 6 (opens it), 7 (opens it) |
| Slice 4 (IAP adapter / ADR-0013) | 2, 4, 5 |
| Next slice (quick) | 8, 9 |
| Next frontend slice | 11, 12 |
| Deferred, contingent | 10 |

Findings 1, 6 and 7 share one surface (per-capacity authorization and who the
actor is) and are grouped as a single future slice rather than three. Findings
2 and 4 share one file (`identity/iap.py`) and one investigation. Finding 5 is
documentation, not code, and is the one most likely to be forgotten precisely
because no test will ever go red for it.
