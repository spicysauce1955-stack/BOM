### Task 11: Review and checkpoint

- [ ] **Step 1: Run both project reviewers**

Per CLAUDE.md, this slice touches domain abstractions and the frontend contracts, so both are required before declaring it done:

```
architecture-critic: review this slice against docs/product/architecture-foundation-v0.1.md §15
and docs/superpowers/specs/2026-09-17-identity-is-googles-design.md
test-reviewer: review the tests added in this slice for weak assertions and missing invariants
```

They mutate the code. Re-run the full suite after each, and do not treat green at the previous count as evidence that nothing moved.

- [ ] **Step 2: Update `plan/current-status.md`** with the slice-2 checkpoint.

- [ ] **Step 3: The checkpoint is a person watching it work.** Green tests are not the checkpoint. Run the app, sign in as Dana through the picker, confirm she lands on the sales view; become a stranger and confirm the no-access screen names them; become the admin, grant the stranger `sales`, and confirm they get in.

```bash
FENCEAI_IDENTITY=dev FENCEAI_DEV_USER=admin@example.com \
  uv run uvicorn fenceai.api.app:app --reload
```

- [ ] **Step 4: Open the PR** once the product owner has seen it run.

---

## Self-Review

**Spec coverage.** §2 the port → Task 1. §2.1 `IapIdentity` in this slice → Task 1 Steps 6, 10-11. §3 what leaves → Task 5 (with the passwordless seed and the left-behind `sessions` table both stated). §4 default-deny, the five codes, the exempt list, the fitness test → Tasks 3 and 10. §5 the laptop, the cookie, the picker, sign-out as a redirect → Tasks 3, 4 and 8. §6 granting, the two routes, the panel, the bootstrap admin's three conditions → Tasks 3 (`_bootstrap`) and 6 and 9. §7 binding and the three outcomes → Task 2. §8 `?author=` → Task 7. §9 testing — conftest, every refusal deliberately, offline IAP tests, dev precedence, the route's absence under `iap`, the fitness test, node tests, the smoke, both bundles → Tasks 1-10. §10 what this does not do → nothing to build. §11 the contract → untouched, and no task edits it.

**Two claims in the first draft were wrong and are corrected in place.** There is no `/api/i18n/{lang}` route — `_locale_bundle` is an internal helper and the browser loads `i18n/<lang>.json` off the static mount, so the exempt list is three paths and the refusal screen renders in Hebrew because the mount was never gated. And there is no shared `run_node` test helper: every node test in `tests/web/` builds its own module-scoped `SCRIPT` and runs `node --input-type=module -e` with `cwd=STATIC`. Both were checked against the tree rather than assumed, which is the only reason they are not in the plan an implementer would have followed.

**Known gaps, stated rather than hidden.** Task 9's `people.js` is given as a skeleton with its pure half complete and its rendering half described — the panel's exact markup depends on the table styling in `style.css`, and inventing it here would be a fixture written blind. Task 10 Step 3's route count is deliberately not a number: the test reports it, and writing a guess into a plan is how the doc came to claim 47 routes over a 51-route app in the first place.

**Type consistency.** `Principal(email, subject)` is constructed in Tasks 1, 2 and 3 with the same two fields. `bind(user, principal) -> "ok" | "bound" | "mismatch"` is defined in Task 2 and consumed in Task 3's `resolve` only. `resolve(store, principal) -> (User | None, str)` is defined in Task 3's `auth.py` and imported into `app.py` as `auth_resolve` in the same task. `DEV_COOKIE` is defined once in Task 1 and imported by Tasks 3, 4, 6 and the tests. `sessionState(body)` is exported in Task 8 and tested in Task 8. `peopleRows(users)` is exported in Task 9 and tested in Task 9. `current_user` / `require_admin` are defined in Task 3 and used in Tasks 3, 6 and 7.
