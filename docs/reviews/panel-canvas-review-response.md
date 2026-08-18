# Panel canvas — review response (2026-08-17)

Two reviews of the `panel-canvas` branch: `architecture-critic` against foundation
§15 and the CLAUDE.md frontend contracts, `test-reviewer` against the suites the
branch added. Both were run after the branch was green (1202 pytest, 178/178
smoke), which is the point — everything below is a defect a passing suite did not
see.

The test review's findings were each verified by applying the mutation and
re-running; every fix below was verified the same way, by confirming the mutation
now fails. That is recorded per item rather than claimed once.

## Accepted and fixed

### 1. The fastener invariant was held by fudging, not by construction (major)

`_fixings` apportioned a fixing slot's whole `qty` across whatever places the
geometry happened to yield, so `sum(place.qty) == slot.qty` was true *by
definition of the apportionment* and said nothing about the drawing.

Where it bit: `resolve.py` counts `per_member_crossing` ARITHMETICALLY (members ×
frame members) while the drawing can only mark crossings that exist. A panel with
vertical stiles beside vertical slats is counted for 80 crossings and has 42;
apportionment put a plausible "×2" on the real ones to absorb 38 that are
nowhere — a number nothing decided, on the surface built to explain what the
basis means. Confirmed by fixture before changing anything.

Fixed by removing the apportionment entirely. `ResolvedSlot` now carries
`qty_per_basis` beside `basis`, so a place can hold a DECIDED count —
`qty_per_basis` times the parts that place stands for — and whatever has no place
is reported on `PanelElevation.fixings_unplaced` instead of being folded in. The
invariant is now `sum(places) + unplaced == qty`, true by construction for every
basis and every geometry, and the inspector says the leftover out loud
("N of these are counted where two members do not actually meet").

The related sub-findings went with it: the remainder line that was dead code
(there is no remainder now), and `qty=0` places (skipped explicitly).

Mutation-verified: swapping the `per_member`/`per_frame_member` place sets, and
`<` → `<=` in the crossing test, and dropping the one-member-is-one-end case, now
each fail a named test. They all passed before.

### 2. `PLANNING_BEHAVIOR_VERSION` was not bumped (major)

`Span.panel` is persisted and the run digest is inputs-only, so adding fields to
a resolved slot changes generation's output for unchanged inputs — which is
exactly what the constant's own doctrine says to bump for ("a different panel
resolution"). Without it, an existing project regenerates to the same run id,
`save_run`'s `INSERT OR IGNORE` keeps the old document, and its bays draw no
fasteners for ever with no user action able to repair it. Now `planning-v2`.

### 3. Tests that passed with the behaviour deleted

Each verified by mutation, before and after.

- **`writeSentence` could ignore the author's comparison.** The test asserted
  only that the result evaluated to a bool. Every variant an author wrote would
  have become `>=`, silently, with the select still showing what they picked.
  Now asserted per comparison.
- **Both offered vocabularies were subset-checked**, so narrowing
  `CONDITION_CMPS` to one value passed. Now equality against `Cmp`'s own
  `Literal`, in both directions — the same rule the other closed vocabularies
  are already held to.
- **Only one of four placement arms was checked for non-mutation.** The module
  header calls this load-bearing for undo/redo; three arms could have written
  through their argument. All four now.
- **The drag's floors were asserted as constants copied out of the JS** (121,
  −99), so the gate's rule and the handle's limit were joined only by a comment.
  Now the drag's own output goes through `validate_model`: at the floor it must
  publish, one millimetre past it must be refused.
- **Three of five starters had no distinguishing number**, so "ranch rail" could
  ship with two rails and "picket" as a duplicate of the slat card.

### 4. `panel-canvas.js` had no test at all

The wiring is where the two pure rules meet the document: which authored field
each handle kind writes, and that a WIDTH reads the pointer absolutely while a
GAP and a MARGIN read the distance moved. `valueFor` is pure, so it is exported
and tested in node (`tests/web/test_panel_canvas_module.py`), together with
`selectionForSlot`. Writing it immediately caught a fixture error of my own — a
two-rail elevation's index 1 IS the last rail — which is the kind of thing the
test exists to find.

### 5. Frontend defects the reviews found

- **Duplicate element keys were reachable**: keys were minted from the list's
  length, so add-three-remove-one-add-again collides, and before the gate refuses
  it, everything addressing an element by key silently targets the first of the
  two. Now minted through `freeId`, the rule already used for model ids.
- **Renaming a rail orphaned the boards that name it**: `base_ref`/`top_ref` kept
  the old key and the gate refused with English authoring text, for an edit that
  looked like a rename. The references now move with it.
- **The inspector offered what the gate refuses**: `between_frame` on a frame
  slot (which has no refs), and `base_ref`/`top_ref` under every length rule
  rather than the one that reads them. Both narrowed — the same principle the
  `excess` list was narrowed under.
- **A predicate-driven eligibility rendered as "no products"**, and "+ Add
  product" then authored the one combination the loader refuses (a predicate AND
  members). It now says what it is, and the button is disabled.
- **A drag that never received its pointerup froze the canvas for the session**:
  `isDragging()` stayed true and the caller stopped repainting. Reset on render.
- **The drag readout showed the pointer, not the number being written** — for
  `from_top` and `fraction` those differ, so the readout disagreed with the field
  it was about to fill.
- **`notify`/`rename` were module singletons** set by one entry point and read by
  another; both now set both.
- **The swatch scan covered one of two style sinks.** The branch added a second
  (the product chip), and the scan aimed at one function by name could not see
  it. Now scanned across the module, requiring at least two.
- **The sentence phrasings had no test that anything RENDERS them.** Two families
  are built from literals rather than const arrays and were invisible to the
  guard; and `sentenceChoice` falling back to the label key would have removed
  the whole feature with a green suite. Both pinned.

## Not changed, and why

- **`per_member_crossing`'s two counts remain two implementations.** The
  architecture review's preferred fix was to make one authoritative. That is a
  change to what a fence COSTS — the arithmetic count is what every existing run
  bought — and it belongs behind the golden-scenarios procedure with its own
  decision, not inside a UI branch. What this branch owes is that the drawing
  never states a number the BOM does not, and `fixings_unplaced` discharges that
  without moving a single price.
- **The smoke drag asserts a positive inset rather than the exact millimetres for
  70 pixels.** The reviewer is right that the scale could be wrong and the check
  would pass. The node suite now pins the whole chain except `getScreenCTM`,
  which is the browser's own; asserting a pixel-derived millimetre in the smoke
  suite trades a real check for one that fails on a viewport change.
- **The gallery check does not tie each card's drawing to its own template.**
  `test_the_five_starters_are_five_different_panels` and
  `test_each_starter_is_the_fence_its_card_names` hold that server-side, where it
  is exact.
- **`basisDiagram` is not tied to `_places`.** It is an illustration of the
  vocabulary, deliberately a fixed three-board sketch rather than of this panel;
  tying it to the placement algorithm would make it the second implementation
  that the rest of this response is about avoiding.
