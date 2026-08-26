# Item 8 — the warning model and the annexe: two reviews, and what each cost

Both project reviewers ran against `37da965` (build-order item 8, contract
obligation 10 and §3.3.5). Verdicts: **SOUND-WITH-FIXES** and **GAPS**. This file
records what they found, what was done about each, and — where a finding was
rejected or deferred — the evidence for that.

The headline: **between them they found the same defect from opposite ends**, and
neither found anything wrong with the annexe itself. Every finding was about what
a reader is told, or about a guard that could not fail.

## What the architecture review settled in the slice's favour

Recorded because a review that only lists faults leaves the next reader
re-deciding what was already decided.

- **The split was already the contract's.** §3.3.4 names platform codes and
  exempts a warning quoted from a document in as many words. So the slice
  implements the contract rather than departing from it, and CLAUDE.md's rewritten
  rule is a restatement, not an invention.
- **No §15 bullet is violated**, determinism holds (input order, `dict` insertion
  order, no float/clock/randomness in `report/annexe.py`), and the freeze is
  respected — `contract.md`/`AMENDING.md` hashes verify, only the un-hashed
  `fixtures/` moved, and the fixture keeps §1.2's `belongs_to` → `source_docs`
  closure.
- **`cites` optional was the right call and the spec correction the right
  disposition.** §1.1 makes `SourceRef.id` opaque and unbuildable; requiring the
  field would have been satisfied by fabricated ids.
- **`Snapshot.warnings` typed and NOT merged into `KnowledgeBase`.** A warning is
  not a rule, nothing defeats one, and keeping it away from the evaluator is what
  preserves "hard constraint ≠ preference ≠ objective ≠ override".
  `warning_defects` ≠ `Gap` is a real distinction, not a hair split.
- **`core/` is the right home** for `DocumentWarning`; no layering violation and
  no cycle beyond the established `fencemodel/preview → report → fencemodel/model`
  pattern.
- **Warnings sit outside `generate()` and outside pricing**, and S19 pins it.
  That is what makes the whole feature safe to ship.
- **`.doc-warning` never `.warning`**, with the deliberate exception for
  `unplaceable`, and **caller-owned element ids**.
- **`procedures` is a seam, not dead code.**

On the §15 question it was asked directly — does `instances` amount to a read
model computing a quantity? — the verdict was that the module's argument **holds
on the letter** (nothing downstream buys anything with it) but that the module
then minted a statement about the source document out of the multiplicity of its
own argument list. That is finding A1 below, and it was the most valuable thing
either review produced.

## Architecture findings, and their dispositions

| # | Finding | Disposition |
|---|---|---|
| A1 | `instances` published a claim no document made: `identity()` maps an absent `cites` to the empty one, so two in-house documents saying one sentence collapse — correctly — and the locale string rendered that as *"the document prints this 2 times"* | **FIXED**, and not the way it first looked. The collapse is right; the *sentence* was wrong. `annexe.instances` now says what the number is: how many times this appears across the documents this fence is built to. Keying on the document would have broken the shared-footnote property that has its own test |
| A2 | a `procedure` warning could render nowhere while the backend reported it placed: no `procedure` term in the frontend's accounting, and `assemblyPlanHtml` returns `""` for a model that states no order (M-LEGACY states none) | **FIXED** both halves — `annexe.elsewhere_procedure`, and the procedure head now survives the absence of the procedure's steps. A "before you begin" warning is not part of a build order |
| A3 | the printed sheet cited surfaces the printout does not contain: `style.css` prints only the canvas and structure tabs, and the sheet said *"shown on the panel sheet"* | **FIXED** — `annexeHtml`'s new `inline` option, used by the structure sheet, draws the step, procedure, product and model buckets there, each labelled with what it attaches to. The sheet that goes to site carries every warning or says so |
| A4 | `step` is a model-local key placed against a document-blind union of step keys | **FIXED** — `PlacedWarning.owner`, per-document vocabularies (`_place_into`), and the model-local buckets keyed by `(owner, ref)` while the annexe still ignores the owner. Found independently as F6 |
| A5 | `_quoted_warnings` skipped an unreadable document in silence | **FIXED** — `WarningPlacement.documents_unreadable`, counted by the route and said out loud on the surface. The review's judgement that skipping beats refusing was accepted with its reasoning: the failure is absence, and taking a working BOM away over a missing annexe is a worse trade |
| A6 | an authored `procedure` ref was unchecked, so a curator's typo surfaced at render as *this engine's* shortcoming | **FIXED** — `validate_model` refuses a named procedure (the ids are the platform's to issue), and the speculative `target.ref in model_set` branch is gone: a model ref is never a procedure id, so it could never have fired on real data |
| A7 | the 83-collapse rests on an unverified assumption — obligation 10's "226 distinct from 1,038 instances" reads as though Knowledge de-duplicates before publishing | **RECORDED as a question for the other team**, not built on. If they publish distinct warnings, `instances` is always 1 and the collapse is exercised only by the fixture written to exercise it. §1.2 pins it either way, so it goes in `planning-asks` territory rather than into a locale string |
| A8 | `Ingested.warning_defects` is a genuine THIRD category — raw English, no code, not verbatim quotation | **RECORDED**. Currently unreachable (`ingest` has no route). CLAUDE.md now names it, and codes wait until the door is wired: a vocabulary invented before there is a caller is the mistake this repo has already made once at this boundary |
| A9 | `by_ref`'s docstring claimed a singularity `preview.py::_ref_parts` contradicts | **FIXED** — the docstring names the other reader and why it cannot share (it owes a refusal code) |
| A10 | S19's doc said "byte-identical" while the test compared node *kinds* | **FIXED by strengthening the test**, not by narrowing the doc. `generate()` is deterministic, so a full `model_dump()` comparison was available and there was no reason to compare less. Also F2 |
| A11 | the annexe reads live document text by `(id, version)`, ignoring the run's stamped `content_hash`, so editing a draft in place changes what a stored run says the manufacturer warned | **DEFERRED, with the reason.** It matches the existing convention — `report/assembly.py` compares refs only — so fixing it here alone would leave two read models disagreeing about how strictly a document is pinned. Recorded in `plan/open-work.md` as one item covering both, and the overclaiming docstring is softened now |
| A12 | `.replace("{ref}", …)` treats `$&` in a publisher's opaque id as a replacement pattern | **FIXED** — a `fill()` helper with a function replacement, used for every interpolation in the module |

## Test findings, and their dispositions

56 mutants, 41 killed, 4 equivalent, **15 surviving**. Where the reviewer said a
guard was design-intent rather than coverage, that judgement was accepted and
written into the test — this repo's convention is that the distinction is stated
where the guard lives.

| # | Finding | Disposition |
|---|---|---|
| F1 | the `ref` component of the dedup key was unguarded: drop it and one sentence on two steps collapses onto one step while the invariant still balances, because the loss becomes an `instances` count | **FIXED** — `test_one_sentence_on_two_steps_stays_two_warnings`, for a step and for a sku. `ref` was the one component of the key with no test |
| F2 | S19's "moves no decision" could not fail: four leaks into payload, edges and `confidence` survived | **FIXED** — whole-object comparison (see A10) |
| F3 | every frontend call site and `PanelPreview.quoted_warnings` had zero pytest coverage, in a repo that already node-tests functions of this shape | **FIXED** — `bomHtml` exported (the `groupedBomHtml`/`assemblyPlanHtml` precedent), eleven new node tests over the call sites, and two pytest tests for the preview placement. Includes the withheld-step wiring, whose mutant put a browser-found defect straight back |
| F4 | the invariant test cannot see *mis*placement, and the annexe's own accounting was unguarded for the `model` bucket | **FIXED** — a `model` entry in the node fixture and the accounting asserted. The structural limit of `carried()` is real and now stated: it is satisfied by construction unless the loop drops or double-counts, which is why F1's test exists beside it |
| F5 | `place_for_plan`'s "you cannot forget a vocabulary" property was tested only for the vocabularies M-VINYL happens to use; `model_refs=[]` survived | **FIXED** — the fixture now carries a model-scoped and a procedure-scoped warning |
| F6 | step keys pooled across documents, with nothing pinning it either way | **FIXED** with A4, and pinned by `test_a_step_key_is_local_to_the_document_that_named_it` |
| F7 | a carried-but-defective warning (document-scoped, naming a line) is reachable in production because `ingest` deliberately carries it, and nothing pinned that the annexe forces its `ref` empty | **FIXED** — `test_a_carried_but_defective_warning_is_still_placed_in_the_annexe` |
| F8 | the "never localizes" grep was satisfiable while the renderer localized, because no fixture used a code with an entry in a bundle | **FIXED** — a fixture whose code (`sliver_span`) is one of OUR platform codes, asserting their words render and ours do not. That is coverage; the grep is not |
| F9 | `test_only_one_module_renders_a_quoted_warning` is an intent guard, and it was the one test that skipped `_code_only` — so any comment explaining the rule failed the build | **FIXED** — reads through `_code_only` like its neighbours, and its docstring now says plainly that it constrains source text and must not be counted as protection |
| F10 | the publisher's-code guard pinned one hardcoded string | **FIXED** — reads every code the fixture carries |
| F11 | the direction guard had no behavioural content | **FIXED** — narrowed to the half that is honestly an intent guard (no translate affordance), with the real property left to the behavioural test that kills a stubbed `dirOf` |
| F12 | the ambient-database trap was closed inside one file's fixture only | **FIXED suite-wide** — `tests/api/conftest.py` pins a per-test database `autouse`. The API tests also got twice as fast, which is the measurement that says the isolation is real: they had been opening 141 MB of accumulated development state |

Smoke review: the `None`-guard is **fixed**; the Hebrew substring coupling is
**accepted** (brittle, never false-passing, and a copy edit turning a gate red is
the cheaper failure); and the per-line-group dedup that the browser could only
catch if the demo panel happens to have two slots sharing a sku is now pinned by
a node fixture that forces the case.

## What both reviews agreed on, and it is the lesson worth keeping

Nothing either reviewer found was in the annexe, the placement table, or the
type. The defects were all one layer out: **a count that published a claim, a
bucket a surface forgot to account for, a sheet that cited a page it does not
contain, and guards that could not fail.** The feature was right and the things
around it were telling the reader something slightly untrue — which is precisely
the failure obligation 10 exists to prevent, arriving from four directions nobody
had looked in.
