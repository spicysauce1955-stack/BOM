# UI v2 review response

Architecture-critic verdict: **SOUND-WITH-FIXES** (module split, snapshot discipline,
forward-revision undo, additive backend i18n all confirmed clean). Test-reviewer
verdict: **GAPS**. All findings dispatched; suite 192 pytest + 19/19 smoke after fixes.

## Architecture critic

| # | Finding | Disposition |
|---|---|---|
| 1 (blocker) | Frontend `anchorFor` wrote whole-run anchors; backend re-anchors per segment — events on multi-segment runs silently shift | **Fixed.** `anchorFor` now mirrors backend `make_anchor` (segment-local); new `stationOfAnchor` mirrors `anchor_station` and replaced every raw `offset_mm` read in editor/inspector/profile. Smoke regression: ghost-insert vertex → place event on segment 2 → asserts segment-local anchor. |
| 2 (major) | `refreshProject` reset undo history on every server refresh | **Fixed.** New `reloadProject()` (fetch + emit only); annotation/override flows use it; history resets only on real project switch. |
| 3 (major) | Override removal lacked `pushSnapshot`; event delete used render-time index | **Fixed.** Snapshot before DELETE; events deleted by id with stale-render guard. |
| 4 (major) | Queued undo restores could write cross-project after a switch | **Fixed.** Generation counter + captured projectId; stale queued restores no-op. |
| 5 (minor) | Inspector populated `#ann-target` (annotations-tab DOM) | **Fixed.** Moved to tabs.js (`renderAnnTargets`). |
| 6 (minor) | state.js ↔ history.js import cycle | **Fixed.** `openProject` emits `project-opened`; history subscribes its own reset; state.js no longer imports history. |
| 7 (minor) | Stub hedging change altered English `height_intent` confidence (not purely additive) | **Accepted as deliberate.** The hedging rule ("about/approx/בערך → medium + note") is intentionally language-uniform; behavior change now documented here rather than implied. |
| 8 (minor) | Failed restore PUT lost the snapshot and desynced buttons | **Fixed.** Failure path restores stack bookkeeping per direction and re-emits state. |

## Test reviewer

| # | Finding | Disposition |
|---|---|---|
| 1 (med) | Rare explain-template branches (sliver, conflict, surface-disagreement, wall/step, defeated suffix) untested in either language | **Fixed.** `TEMPLATES` en/he key-parity assert + parametrized branch fixtures rendering every node in both languages. **The new defeated-suffix test caught a real generator bug**: defeated edges cited the winning version instead of the defeated one — fixed at both sites in `generator.py`. |
| 2 (med) | No contract test binding backend warning/critique codes to the locale bundles | **Fixed.** `tests/web/test_locale_bundles.py`: bundle key parity, every emitted code present in both languages, code-list currency via source grep, no empty translations. |
| 3 (med) | Smoke "profile has content" false-passed on empty groups | **Fixed.** Now counts drawn children of `#p-result` and `#p-ground` separately. |
| 4 (low) | Locale toggle asserted only `dir` flip | **Fixed.** Asserts a real string swaps. |
| 5 (low) | Smoke swallowed page exceptions | **Fixed.** CDP exceptions collected; final "no uncaught page errors" gate. |
| 6 (low) | `name_i18n` empty-string fallback unpinned | **Fixed.** Test added. |
| 7 (low) | Hebrew height-word-without-number branch unreached | **Fixed.** Test added. |
