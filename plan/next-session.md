# Next session — pending commits, two live design threads, silence owed to no one

```text
Written:  2026-08-25, closing the implementation session that built items 1-5.
Rewritten: same day, when the Knowledge team's state changed the plan.
Rewritten again: 2026-08-27 — the Knowledge team reviewed item A's fixture,
          which cascaded into a real fix and a five-turn negotiation. See the
          two sections right under this box, newest first.
Rewritten again: 2026-09-08 — closed T49's five "Ours, open" ledger items, then
          two design threads (Knowledge tab, a new standalone Connections
          view) grew out of a UI complaint into an approved mockup and a
          committed spec. NOTHING from this session is committed except two
          narrow, docs-only spec commits — ~25 files sit uncommitted,
          including four shared with the concurrent session, tangled
          together. Read this section's FIRST paragraph before touching git.
Rewritten again: 2026-09-07 — the eight-step road shipped, and the road turned
          out never to have shown a state at all. READ ITS FIRST PARAGRAPH: a
          second session commits into this repo concurrently, so never
          `git add -A` here.
Rewritten again: 2026-08-30 — the Knowledge team published real
          curation-level-2 ParameterTable data for the first time
          (conversation.md T12). Item 6 is unblocked and its mechanism is
          built; item 7 is unblocked and not yet started. See "2026-08-30 —
          real data landed" below.
Read:     this first, then plan/current-status.md (newest entry first).
State:    Items 1-11 done and pushed. Item 6's mechanism (SourcePolicy,
          admit()/resolve()) is built and tested against real published
          provenance — NOT YET wired into expand()/generator.py; that
          integration (recording admitted_by on a run, rendering it in the
          decision graph, warning below min_curation) is the next concrete
          step. Item 7 (Provenance on SpecField, the source_docs join) is
          DONE — 2026-09-03, see its row below. Full end-to-end real-snapshot
          ingestion was separately blocked on a Knowledge-side defect
          (Gap.subject not yet structured) — reported as conversation.md T14,
          fixed on their side by amendment 004 and now passing.
```

## 2026-09-08 — T49 closed, and two design threads in flight, nothing committed

### Read this first: git state

**Another session works this repo at the same time — same rule as below, sharper this
time.** `git status` shows ~25 modified files plus a handful this session's own concurrent
sibling created (`api/app.py`, `knowledge/parts.py`, `test_snapshot_routes.py`,
`plan/current-status.md`, `docs/architecture/published-part-inspection.md`,
`js/published-parts.js`, `tests/web/test_published_parts_module.py` — **do not touch these,
they are not this session's**). **Nothing from this session is committed** except two narrow
spec-doc commits (`docs/superpowers/specs/2026-09-07-connections-view-design.md`, written then
amended). The user has not asked for the rest to be committed, so it wasn't — per this
project's own rule, commits happen only when asked.

Four files carry **both** sessions' changes interleaved in one working-tree diff:
`app.js`, `i18n/en.json`, `i18n/he.json`, `index.html`. Before anyone commits any of this
session's pieces, the same surgery the 2026-09-07 section below describes (`git checkout HEAD`,
reapply only this session's lines, commit, restore the combined file) has to happen on all
four — and there's more tangled in each of them now than there was last time.

### Thread 1 — the three open items from 2026-09-07, closed

1. **The clear-drawing smoke ran for the first time and found a real bug.** `clearDrawing()`
   (`editor.js`) cleared landmarks locally, then `saveTopology()` replaced the WHOLE
   `state.project` with the server's response — which still carried the pre-clear landmarks,
   since that route never touches context — clobbering the local clear before `saveContext()`
   ever ran. Fixed: re-set `landmarks = []` again after `saveTopology()` returns. A second,
   independent bug in the same test: the "drawing doesn't touch topology revision" check was
   asserting AFTER the Clear+Undo sequence, which are supposed to bump revision by design —
   moved the assertion to where it actually belongs, right after the landmark drags.
2. **Three step-1 leftovers, removed.** `checklist.js` deleted outright (per the 09-06 spec's
   own invariant — "deleted, not left dormant"); the Generate/Fit toolbar and the "This
   stretch" segment panel are now properly scoped out of step 1 via `step-surfaces.js`
   (`#generate-toolbar`, `#run-editing-panel` ids added, both tables + their CSS mirror
   updated).
3. **The lingering pencil CTA turned out to be the same bug as #2**, not the suspected
   `getScreenCTM`-on-a-hidden-SVG theory (which was checked and is a red herring — closed for
   free by the checklist deletion). Separately, **the whole empty-canvas CTA (`editor.empty_cta`,
   the arrow-pointing-at-the-pencil feature) was removed entirely**, on direct instruction —
   `renderCta()`, its four call sites, the `g-cta` layer, and the locale keys are gone.

**369/369 browser smoke, full suite green** after this thread (before thread 2 added more).

**Still open from that list, untouched:** item 4 (`road.state.blocked` dead string), item 5
(the 2-4 map variant, named as a seam), item 6 (**the whole-branch review still hasn't run** —
now covering thread 2 below as well, which makes it more overdue, not less).

### Thread 2 — `conversation.md` T49's five "Ours, open" items, all closed

Read `conversation.md` T49 (both repos, byte-identical) before touching any of this — it's
the actual negotiation record, this is just the punch list.

| Item | What shipped |
|---|---|
| `fit_pattern` rounding conformance | New `fit_pattern_milli()` in `fencemodel/fit.py` — same exact algorithm, fed true thousandths instead of pre-rounded mm, rounding only the aggregate slack and each distinct gap value once. Wired into the one real caller (`resolve.py:701`), proven an EXACT no-op on today's whole-mm data (281/281 golden scenarios unmoved). Test reproduces the negotiation's own worked example: naive engine gave a false-PASS 91.0mm opening against a 100mm limit; the fix gives 121mm, correctly FAILing — the sphere-test-flip defect, closed. |
| Uncovered-point cross-check | New gap code `uncovered_point_contradicted` (`knowledge/parameters.py`) fires when a table's own row (via an omitted-dimension match) actually covers a point the publisher claimed was uncovered — the exact mechanism that would have caught their 16-false-uncovered-points bug automatically. Locale keys in both bundles, `test_locale_bundles.py` guard extended. |
| Agreement-recorded-as-defeat | New `corroborated_by` field/edge (`evaluator.py`, `decisions/graph.py`, `decisions/explain.py`, both locales) so N agreeing sources render as corroboration, not a suppressed contest. The other half of the ask (`Resolution.admitted` in `parameters.py:541-543`) was correctly DECLINED mid-flight — that's a different, unrelated `Resolution` type (source-policy citation admission, not evaluator rule-precedence) with no current consumer; building it now would be speculative. |
| Vendored real-snapshot fixtures | Three pinned snapshots copied into `tests/knowledge/fixtures/real_snapshots/`; `test_real_snapshot.py` no longer loads by absolute path into the sibling repo and no longer skips silently — verified by actually renaming the sibling repo away and re-running (17/17 passed). |
| Stale claims + dead keys + candidate filing | Four "Knowledge team has published nothing" claims corrected (`snapshot.py`, `core/warnings.py`, a spec doc, a fixtures README). Five dead `knowledge.snapshot.*` locale keys removed (nothing ever rendered them). Candidate **C17** filed in `CANDIDATES.md` (rounding a published LIMIT the same as a MEASUREMENT admits values the publisher excluded — trigger D, non-blocking). |

**Full suite green after all five landed and after a deliberate cross-fork damage check**
(four background agents shared this live working tree, not isolated worktrees — the transient
failures they individually hit mid-flight were resource contention, resolved once everything
landed; verified via a clean full run, not assumed).

**Nothing was sent back to fence-rag.** T49 (ours) is still the last turn in the thread. These
five fixes answer things T49 itself flagged as ours to do, not things they're waiting to hear
about — but if a T50 ever goes out, it should mention this batch landed.

### Thread 3 — Knowledge tab redesign: approved design, zero implementation

Started as "the Knowledge tab gives me a headache." Real bug found along the way: the rules
list renders **533 cards unconditionally** — 486 of them `status: proposed` candidates that
the Review tab already owns via a separate, filtered endpoint; only 47 are real established
rules. Approved design: sub-navigation (Published / Author / Rules) instead of one stacked
page; the Rules pane excludes candidates by default, collapses retired rules, and renders
`scope` as chips and `actions` as the same sentence-style text the rule builder already
writes, instead of two `JSON.stringify(...)` dumps per card.

**Mockup, approved, not yet built:** https://claude.ai/code/artifact/1e114f41-364e-4feb-ab6d-242e809c149a
No spec file written for this one (it stayed "bounded" — reorganizing an existing tab, not new
architecture) and no implementation plan exists yet either.

### Thread 4 — the Connections view: escalated to architectural, spec committed, zero implementation

The same complaint ("no visualization for structured data we understand") escalated once it
became clear the real ask — see what references what across rules/parts/models/products, and
find orphans/dangling references — has no existing flow to reorganize and touches no library
this frontend is allowed to load (no framework, no CDN, per `CLAUDE.md`).

Two real, previously-invisible findings justified building it: a published Part has **no link
to a catalog Product anywhere** (`knowledge/parts.py:26-29`, a named permanent gap, 212 parts
affected), and **nothing checks the reverse direction of any reference at any layer** — only
the forward direction (`Snapshot.dangling_refs()`) is checked, and it's real, tested, and
clean (0 dangling).

Design chosen after researching real precedent (Notion/Obsidian backlinks panels, Knip-style
orphan lists — NOT a global force-directed graph, which no surveyed tool hand-rolls without a
layout library): pick one entity, see a radial diagram of its direct references/referenced-by
plus a separate, always-distinct, filterable orphans list. Shape encodes entity kind
(hexagon=Rule, square=Product, diamond=Model, circle=Part, page=SourceDoc, **triangle=Warning,
added in a same-day spec revision**); color encodes relationship type.

**Spec:** `docs/superpowers/specs/2026-09-07-connections-view-design.md`, committed, then
amended same day after the user pushed on completeness ("what about assemblies, what other
data models don't we see here"). That pass **investigated rather than guessed**:
`AssemblyStep` (`report/assembly.py`, `model.py:634`) turned out to reference only its own
Model's slots — not a new graphable node at all, folds into Model. `Warning`
(`DocumentWarning.cites`) has the identical citation shape Part/Rule/Gap already use — added
as a sixth entity. `Project`/`Override` are real (`fence_model` → Model, `ForcePostSku.sku` →
Product) but explicitly named as a deliberately separate layer (operational job data, a
different audience) rather than silently absent. One real inconsistency the Warning addition
exposed and fixed: `Gap` stays out of v1 as a lookup-able entity, but its citations still have
to count toward the Unreferenced-SourceDoc check, or that check would report false orphans.

**Three published artifacts, all still just previews — nothing behind any of them is real:**
- Interactive mockup (pick an entity, radial diagram + lists update): https://claude.ai/code/artifact/a0380b52-2778-4668-b6ab-5e3b0532327a
- Design map (entity shapes, the reference diagram, the rejected-vs-chosen UI comparison, both workflows): https://claude.ai/code/artifact/60021d4a-1a2b-491b-85de-d9316754d5ee

**Open at handoff, asked and not yet answered:** whether to update those two artifacts to add
the sixth entity (Warning) the spec amendment introduced — offered, not done. Next concrete
step once that's settled: invoke `writing-plans` for an actual implementation plan — nothing
has been built, this is 100% still the design phase for both thread 3 and thread 4.

### A trap worth naming for whoever picks up `fit_pattern_milli`

The first instinct for "round the milli-precision result once at the end" was WRONG, not just
imprecise: rounding each of `_spread()`'s already-distributed gap values independently (rather
than rounding the aggregate slack once, THEN spreading it at mm precision) can make a real,
non-zero slack vanish to zero across every gap — `_spread(3000, 7)` distributes as four 429s
and three 428s milli, every one of which rounds to 0mm alone. Caught by tracing concrete
numbers before trusting the intuition, not by a test that happened to fail. The fix and the
reasoning are in the function's own docstring in `fit.py` — read it before changing that code.

## 2026-09-07 — the eight-step road shipped, and the road had never once shown a state

**Read this first: another session works this repo at the same time.** It
committed into the middle of this session's sequence (`22df48d`, `e6b289a`) and
was still writing when this closed — `plan/current-status.md`, `api/app.py`,
`knowledge/parts.py`, `app.js`, `index.html`, both locale bundles, and a new
`published-parts` surface. Nothing was lost and no history was rewritten, but
**never `git add -A` in this repo.** Stage your own files by name. Where a file
is shared — `index.html`, `i18n/*.json` — check out HEAD, reapply only your
lines, commit, then restore the combined file. That was done three times today
and each time the diff shrank from ~13 lines to the 1-2 that were actually mine.

### The find that matters most

**The road had been completely stateless since the day it shipped.** `road.js`
has listened for `handover-changed` since the six-step road landed, and nothing
in the codebase ever emitted it or set `state.handover`:

```
git grep "state.handover *=" eab8d43 -- src/fenceai/web/static/   ->  nothing
```

So `road()` received `null` on every render and returned all-`unknown` by
design — no badges, ever. Not the 3-of-6 check-mapping gap the eight-step spec
was written about; the payload simply never arrived. Six lines in
`handover.js` (commit `61097b7`) fixed it, and the road showed a state for the
first time. **The lesson is the shape of the failure, not the fix:** the unit
suite was green throughout, the browser smoke was 348/348, and neither could
see it because no test in the release gate boots the real ES-module app.

### What shipped

| | |
|---|---|
| `9808083` | `Stated` on `Project` — named facts, unrevisioned |
| `a8df0ba` | `gates_contradicted` / `promises_contradicted`, both bundles |
| `fd8024b` | `PUT /projects/{id}/stated` |
| `a7945e8` `0edde86` | the road engine over `(roadDef, gaps, stated)`, `roads.js` as data |
| `eab8d43` | eight steps rendered; `road.details` retired |
| `61097b7` | the skip control — and the handover finally published |
| `44894a9` | the map scoped to steps 2-6 |
| `245df1e` | a done control on every step; date defaults to today; the landmark-draft leak |
| `88adbf7` | Clear takes the whole drawing |

Spec `docs/superpowers/specs/2026-09-07-eight-step-road-design.md`, plan
`docs/superpowers/plans/2026-09-07-eight-step-road.md`, SDD ledger
`.superpowers/sdd/2026-09-07-eight-step-road/progress.md` (every ruling is in it).

### Traps this session walked into, so the next one does not

- **`pytest -q` runs two architecture fitness tests that the release gate does
  not.** Task 3 added a route and the plan never said to update
  `docs/architecture/04-backend.md`'s route table; it went unnoticed for three
  tasks because per-task verification was `tests/scenarios` plus the task's own
  tests. **Adding a route or a store table means running the FULL suite.**
- **`str.replace` with no match is a silent no-op.** A self-review edit
  anchored on "A road absent" where the text said "A ROLE absent" quietly did
  nothing, and the plan ended up removing `roadFor` from one file and never
  adding it to the other. Every patch script since asserts its anchor first. Do
  that.
- **`test_road_render.py` parses `road.js` as TEXT.** It finds the first
  click-listener registration to check the skip control's invariants
  (stopPropagation, snapshot-before-mutate). Registering a listener above it
  steals the anchor and leaves both unchecked — and a COMMENT containing the
  literal call string does too. Both happened today.
- **Killing a browser smoke leaves an orphaned server on 8791 and Chrome on
  9333.** The harness then refuses to start, correctly. Clear both ports.
- **A stalled subagent with a Monitor relaunches what you kill.** Three smoke
  runs in sequence, each rewriting tracked screenshots. `TaskStop` the agent,
  not the process.

### Open, and each one deliberate

1. **The clear-drawing smoke never ran** (`88adbf7` says so in its own message).
   Four checks are added and UNRUN. Run `tools/ui_smoke.py` first thing.
2. **Three step-1 leftovers**, all visible in `tools/smoke-out/` and all
   controls for work that is not that step's: the "how to start" checklist tells
   you to click a map the step no longer has (the 09-06 spec already says
   `checklist.js` should be DELETED, not left dormant); the Generate/Fit toolbar
   floats above empty space; the segment picker offers `run1` while you type an
   address. My read: all three belong in `step-surfaces.js`'s scoped list. The
   user has been deciding these, so ask.
3. **The pencil CTA lingering** — reported, not reproduced. Two strings carry a
   pencil: `checklist.draw` (refreshes on `topology-changed`, fine) and
   `editor.empty_cta`. One concrete suspicion: `renderCta` appends its text and
   THEN calls `svg.getScreenCTM()`, which returns null on a `display:none` SVG
   — newly reachable now the canvas is hidden on steps 1/7/8. That would drop
   the arrow, not make text linger, so it may be a different bug. Needs a "when".
4. **`road.state.blocked` is a dead string.** The badge order is
   `unknown -> skipped -> gaps.length -> state`, and a blocked step always has a
   blocking gap, so the count always wins. Same shape as the five dead
   `knowledge.snapshot.*` keys.
5. **The 2-4 map variant** — only arises if placing a gate and choosing its
   model split into separate steps. A nine-step restructure; named as a seam,
   not built.
6. **The final whole-branch review never ran.** The SDD plan reached task 6 and
   stopped for a human question. It should cover the concurrent session's
   `step-surfaces.js` too, not this session's commits in isolation.

### The knowledge boundary, separately

T49 was sent (`e8cde15`) answering T46-T48's seven asks; both copies of
`conversation.md` are byte-identical and now mirrored into this repo
(`4362dff`). Their move: store a cut carrying G89, tell us its hash, leave
`762967d3` and `b2f2fe45` live, tombstone the other three, and answer which
vocabulary G75's fix will emit — `version_status: "current"` fails our loader
outright, so a relabelling breaks us on the first document it corrects.



## 2026-08-30 — real curation-level-2 data landed; items 6 and 7 unblocked

The Knowledge team published `3ae88642…json` (`conversation.md` T12): four
real `ParameterTable`s (`footing_depth_mm`, `footing_diameter_mm`, two
manufacturer scopes each), `curation_level: 2`, real citations. First real
data either side has ever built against.

**Loaded it through our own parser and `expand()` directly, not through their
summary.** Found and fixed three defects in `knowledge/parameters.py`, all
latent until now because every prior caller was a test writing the shapes we
expected:

- `ParameterTable.scope: dict[str, str]` rejected the real `EntityRef`'s
  `tenant: null` outright. Widened to `dict[str, str | None]` — `tenant` was
  never read here anyway.
- `_ENTITY_DIMENSION` had no entry for `kind: "fence_model"` — the real
  publish's actual scope kind, versus the `product_line`/`model` guesses made
  before either side had data to check them against. Every row in all four
  tables was expanding to zero applicable knowledge before this.
- `valid_until: "04/04/2028"` (their `MM/DD/YYYY`) compared lexicographically
  against an ISO `as_of` reported a row valid four more years as **LAPSED**.
  The live version of their candidate amendment C6 (no `Date` type in the
  contract), confirmed in our own code rather than theoretical. Guarded the
  comparison to ISO-looking dates on both sides rather than guessing a parse.

2195 pytest after the fixes (`82d47f2`).

**Then built item 6's mechanism** — `knowledge/source_policy.py`:
`SourcePolicy`, the shipped default table verbatim from contract §1.4,
`admit()`/`resolve()` with the rank → curation_level → source_class tie-break
the BINDING clause specifies (issue_date deliberately skipped — no `Date`
type exists, matching the restraint asked of the other team in
`conversation.md` T13). The shipped default table itself contains two rank
ties (`component_dimension`, `installation_step`), exercised directly by
tests. Verified against the real snapshot's own provenance: admits at rank 1
for `structural_parameter`, matching the shipped table without adjustment.
2206 pytest (`69b014f`). **Not wired into `expand()`/generator.py** — see the
build-order table's item 6 row for exactly what's left.

**Two defects reported back** (`conversation.md` T14, not blocking either
item): `Gap.subject` is still a bare string across all 81 gaps in the real
snapshot, not the structured shape contract §1.2.1 requires — blocks full
`Snapshot` ingestion (item A's ingestion path), though `ParameterTable` alone
parses fine. And the snapshot's 16 `condition_point_uncovered` gaps duplicate
`table.uncovered` point for point — our own `expand()` independently derives
the same 16 from `uncovered` alone, so ingesting today double-counts every
one.

## 2026-08-27 — the Knowledge team's first fixture review landed, and it found a bug in this repo too

`knowledge-asks.md` v0.2 (fence-rag) reviewed
`docs/integration-contract/fixtures/snapshot-example.json` and returned eleven
defects. Fixing the fixture correctly required more than editing JSON: this
repo's own `Gap`, `GapSubject` and `DocumentWarning` types were **already
non-conformant with the frozen contract**, independent of anything the other
team found — `Gap` carried flat `code`/`params`/`message` where the contract
has always specified `because{code,params}` with no `message` field at all, and
`GapSubject` carried a bare `ref` where the contract's `EntityRef` is
`{kind, id, tenant}`. Fixed now:

- `core/gaps.py` — `Gap.because: Because` replaces flat `code`/`params`; `message`
  removed (a `Gap` has no `text_raw` and now no English side-channel either —
  `StrategyWarning.message` is unaffected and still legitimate). `GapSubject.id`
  + `.tenant` replace `.ref`.
- `core/warnings.py` — `DocumentWarning.cites` is now `list[SourceRef]` (a
  warning can cite more than one document); added `lang_basis`;
  `severity_lexeme` is `str | None` (absent and empty are different facts).
- `knowledge/parameters.py` — added `Token{key, value_raw}`; a token-valued
  published row carries the document's own lexeme instead of a bare string.
- Every call site (`knowledge/parameters.py`, `strategy/generator.py`,
  `fencemodel/demo.py`, `web/static/js/gaps.js`, `web/static/js/doc-warnings.js`)
  and every test that touched the old shapes updated. `architecture-critic`
  (SOUND, one minor finding — a gap code with no locale entry rendered as an
  unmarked fallback, now fixed: `gaps.js` marks it `lang="en" dir="ltr"`) and
  `test-reviewer` (GAPS — `GapSubject.tenant` was wired but never actually
  read in `expand()`, and `cites` as a list was untested past one element; both
  fixed, plus a `because`-required test and a `Token`/`Quantity` cross-type
  test) both ran and their findings are closed. **2139 pytest, 280 scenario
  tests, unmoved.**

The fixture itself: all eleven defects fixed, plus `curation_level` dropped to 1
on the structural rows (their corpus has no level-2 population) and
`(exposure_category=B, hvhz=true)` added to `uncovered` — a stand-in, not a
fix, since that point is really a REFUSAL, not a coverage hole (see below).

**Deliberately NOT fixed in the fixture:** `max_span_mm` still models a
condition → value lookup. The Knowledge team's own adversarial review of their
draft found the real table is `(footing depth, max span)` design points, two
per exposure — a shape `value_type` cannot express today. Recording that as a
bug matching the real bug, rather than guessing at a fix, was the deliberate
choice.

**Sent back:** `planning-asks.md` §9 (fence-rag) answers their five questions —
no objection on `curation_level` 0/1 (nothing on our side enforces it yet);
slot-structure-as-a-value is non-blocking since we don't consume
`models`/`parts`/`combinations` from a snapshot at all yet; a **new `GapKind`**
is needed for "checked and refused" vs. "may not cover" (logged as candidate
amendment **C4**); the paired-value table should be solved by adding
`footing_depth_mm` as a domain dimension — a free registry addition, no
amendment — rather than reshaping `value_type` (logged as **C5**), though that
still means Planning has to build a real footing-depth CHOICE in the generator,
which does not exist today; `TaskCode` spellings confirmed.

**What this means for build order below:** nothing here changes items 9-11 —
they were already independent of the boundary. It DOES mean C4 and C5 are now
real, if non-blocking, entries against this repo's own `Gap`/`ParameterTable`
types, worth remembering the next time either is touched.

### 2026-08-27, later the same day — the negotiation, and what it corrects above

Four more turns in `conversation.md` (fence-rag), T1–T4. The two things above
that are now **wrong as written** and superseded by the turns:

- **C4 does NOT need a new `GapKind`, and none was added.** Knowledge's T1
  showed `kind: uncovered_condition` + `domain_basis: measured` already means
  "checked, not a guess" — the missing piece was only *why*, and a new
  `because.code` carries that for free (registry addition, no amendment). We
  conceded in T2 after checking our own `GapKind`'s cost to extend (a closed
  8-member `Literal`, three changes) against a new code's cost (one). **C4 is
  struck.** Implemented: `parameter_condition_excluded` is in both locale
  bundles (`web/static/i18n/{en,he}.json`), guarded by
  `test_locale_bundles.py`'s new `PUBLISHED_GAP_CODES` list (codes this engine
  renders but never emits itself — the source-scan guard would never find
  them). The fixture's `(exposure_category=B, hvhz=true)` case moved out of
  `uncovered` entirely and is now a directly-published `Gap`
  (`FIXTURE-gap-excluded-1`) — only the publisher knows *why* a point is
  excluded, so this loader was never the right place to synthesise that fact.
- **C5's own preferred disposition flipped.** Knowledge's T1 measured the
  domain-dimension option we'd proposed and found it manufactures 8 of 18
  cross-product artifacts (several actively misleading — a footing depth
  *below* the certified minimum reading as an ordinary coverage hole). More to
  the point: footing depth is a design CHOICE, not a site fact `domain` binds
  at run time — the same category as picking between two admissible SKUs, and
  our own `strategy/generator.py:975-976` already ranks admissible candidates
  that way. **C5 now prefers option (1), a paired/compound `value_type`** —
  still the one live amendment candidate left standing, still ours to
  co-author whenever a batch is ready.
- **C1 is closing as answered, not batching with anything.** Our own §9.1
  answer ("publish against your reading, we'll enforce later") was always
  C1's own cheapest listed disposition. Knowledge owes a written 0/1/2 mapping
  in their docs; no amendment. C5 batches with **C2** instead
  (`Warning.attaches_to.ref` never typed) if either needs a version cut.

Net: of five original candidates, **one** (C5) is a live amendment. Worth
remembering next time `ParameterTable.value_type` or `Gap`'s registries come
up — this is now the settled record, not `next-session.md`'s first pass above.

## The fact that reorders everything

**The Knowledge Platform team is still in DESIGN.** They have published nothing, and the
two early publishes the old plan waited on are not coming soon.

The contract is still ratified at v1.1 and still binding — that has not changed. What
changed is that there is no counterparty data to check an implementation against, and
this repo has already learned what that costs. From the ratification's own record:

> An addition made at the boundary has no substance on either side to check it against
> until someone holds it up to one. That is why `continuity` and obligation 13 were both
> wrong — sound against our engine, which was the only substance we had.

So the rule for this session is narrower than the last one's:

- **Build what this repo can verify end to end.** Internal design, read models, the
  engine's own arithmetic, the frontend.
- **Do not build binding boundary behaviour against the spec alone.** Item 6 (source
  policy) is the clearest case: BINDING, zero lines, re-ranked twice, and unverifiable
  until somebody publishes a row with a real `source_class` on it.
- **Do produce evidence for their design.** That is not the same thing — see "the one
  boundary item worth doing" below.

---

## What is done

| # | Item | State |
|---|---|---|
| 1 | `Gap` as a return type — a run is never failed over a gap | done (`622551a`, fixed in `00a8387`) |
| 2 | `SiteConditions`, `site.*` binding, the 409 guard | done (`b60e7e2`, fixed in `00a8387`) |
| 3 | Handler registries — bases, length rules, presets | done (`a2f7db4`) |
| 4 | The declared pricing phase list | done (`360639c`) |
| 5 | `ParameterTable` loader | **built, never validated** (`b2b8400`) |

Plus a frontend round (three agents, merged): site conditions are enterable, gaps have a
reader, the editor asks `GET /api/vocabularies` instead of keeping its own copy.
**1780 pytest · 203 scenario tests · 237/237 browser smoke.**

Both prerequisites recorded for item 5 are closed: `KnowledgeVersion.from_published` is
the seam the loader uses, and a `ConflictSink` means a `Conflict` can no longer be
silently dropped at ten of thirteen resolution sites.

### Item 5 is the largest piece of unverified work in the repo

Say it plainly to whoever picks this up. `ParameterTable` was built field-for-field from
contract §1.3, is tested hard, and **has never seen a table anyone actually published**.
Nothing calls `expand()` from a route. Treat its shape as a hypothesis with good tests,
not as settled.

---

## Build order from here

| # | Work | Blocked by | Ours to verify? |
|---|---|---|---|
| **A** | **The conforming fixture + ingestion** — see below | nothing | yes |
| ~~9~~ | ~~`stock_length` consumed; continuity **derived** against resolved spacing~~ | — | **done** — `strategy/continuity.py`, S18, gate unmoved |
| **10** | Containment → demand: flatten `ContainedSlot` into the panel's slot list under a path key, and the kit-credit rule, which has no home in a demand line today | nothing | yes |
| **11** | `report/assembly.py` — bay and post scopes, `requires` edges as a partial order | 10 | yes |
| ~~8~~ | ~~Warning model — `attaches_to`, the registry split, the **annexe**~~ | — | **done** 2026-08-26 — `core/warnings.py`, `report/annexe.py`, S19 |
| **6** | Source policy — mechanism built (`knowledge/source_policy.py`), **not wired** into `expand()`/generator: `admitted_by` on a real run, decision-graph rendering, below-`min_curation` warning | nothing | yes |
| ~~7~~ | ~~`Provenance` on `SpecField`, the `source_docs` join~~ | — | **done** 2026-09-03 — `knowledge/parts.py`, `specs/2026-09-03-spec-field-provenance-design.md`. Built against `f4d40fb8…`, the first cut publishing real spec values. What it deliberately did NOT build: the link from a published `Part` to a catalog product — see that spec's §7 |

**9, 10 and 11 are genuinely parallel** — different modules, different read models — which
items 6-11 never were as a chain. They are the right shape for concurrent agents.

### 9, 10 and 11, and why each is ours

- **9.** `stock_length_mm` already exists on catalog products and `parts/compile.py`
  already reads it. Obligation 14's real content is that continuity is **derived, not
  authored**: the same rail is continuous in 16 ft White and per-bay in 12 ft Blend at a
  97″ maximum spacing, and a rail cut for rolling terrain is per-bay on the graded bays
  only. `Member.continuity` survives as an authored OVERRIDE for the case where a guide
  states the behaviour and gives no length. All of that is our engine deciding from data
  we hold.
- **10.** `ContainedSlot` does not exist yet — greenfield, no boundary surface at all.
  The kit-credit rule is the interesting half: a gate kit that ships its own hinges must
  credit them against the hinges the panel would otherwise buy, and there is nowhere in a
  demand line to say so today.
- **11.** `AssemblyStep` and `report/assembly.py` exist. This closes something already
  recorded as knowingly-not-done in `plan/open-work.md`: the placeable vocabulary is the
  PANEL's slots, so no step can name a post, its cap or its footing — an installation
  instruction about posts is prose today. Closing it means giving the read model the
  bay's posts, which is a different input.

### The one boundary item worth doing: item A

Write a **conforming fixture** — a hand-authored snapshot with a real `ParameterTable`
matching §1.3, including a `declared` domain, an `uncovered` point and a lapsed row — and
wire the ingestion path that loads it.

Three things it buys, and the third is the point:

1. It exercises item 5 against a whole document instead of unit fixtures.
2. It makes item 5 REACHABLE, so `uncovered_parameter_point`,
   `parameter_authority_lapsed` and `parameter_value_nonconforming` stop being strings
   nothing renders.
3. **It is evidence for the Knowledge team while they are still designing.** This is not
   speculative boundary work, it is the opposite: the frontend design already makes the
   argument for its own step 1 — *"building against it is what tells the Knowledge team
   whether their endpoint returns what a reviewer actually needs — before they implement
   it."* A team in design phase is when that is worth most.

Keep the fixture obviously a fixture. It is what we expect to receive, not something
anyone published, and a file that could be mistaken for real published data is how a
hypothesis becomes a fact nobody checked.

---

## Still owed, and small

- ~~**`Gap.would_close` is generated English with no `code`/`params`**~~ — **DECIDED
  2026-08-27, quoted-and-untranslated STAYS, no `close.<code>` registry for now.**
  Rendered in the UI as quoted foreign text with a Hebrew label saying it is
  written for curators, same treatment as a `DocumentWarning.text_raw` — and on
  reflection that's the same reason: `would_close` is meant to be a specific,
  situational sentence (*"a Bufftech HVHZ approval at exposure B, or
  confirmation that the FBC does not permit exposure B in the HVHZ"*), and a
  closed vocabulary would flatten exactly the specificity that makes it useful,
  same failure shape as translating a manufacturer's liability sentence. The
  Knowledge team hit the identical field on their own side (`conversation.md`
  T6, their G40) and fixed it by making the free text MORE specific, not by
  building a shared code system — evidence the free-text design is right, not
  a stopgap. Revisit only if a real need for it resurfaces; not worth building
  speculatively.
- ~~**`frost_depth_mm` has no `ge=0` bound**~~ — **DONE 2026-08-26.** Bounded on the
  engine side. No upper bound: permafrost is metres deep and the figure a jurisdiction
  publishes is not ours to cap. The sibling audit found no second hole (`revision` is
  overwritten by the route).
- ~~**`site.*` does not reach model variant conditions or eligibility predicates**~~ —
  **DONE 2026-08-26, decided BIND.** Refusing the condition would have left the capability
  missing while looking principled: site conditions exist so that a fence can be
  conditioned on the site. `site` is bound into `PanelContext.condition_ctx()`,
  `match.panel_facts` and `match.post_panel_facts`; `_PostFacts.at` supplies the SAME site
  at a post's station, so a site-conditioned variant is admissible beside a routed post and
  the spec the post is matched against is the spec its bay is built to. Where the project
  did not answer, the existing `site_condition_missing` reports it — one warning covering
  both askers, with a hard constraint's severity preserved. A `site.` key that is not a
  `SiteConditions` field is an authoring error, because a typo would reinstate the exact
  silence the binding removes. **No golden number moved.**
- ~~**`DEFAULT_RAILS_PER_SPAN` and `DEFAULT_SCREWS_PER_SPAN`** are silent fallbacks of
  exactly the shape `FALLBACK_MAX_SPAN_MM` has, minus the warning.~~ **Done
  2026-08-26**: values kept (2 and 8), report added — `uncovered_rails_per_span` /
  `uncovered_screws_per_span`, one gap + one warning per section and model line. The
  golden numbers it was expected to move moved none: the demo base states both counts,
  so no green run emits either gap, and the scenario gate held at 268.

---

## Two habits this session earned the hard way

**A subagent gets its own worktree, cut from the RIGHT commit.** Two of three agents were
branched from `main` rather than the working branch and one of them built an entire
backend that had to be deleted. Check `git worktree list` before briefing anyone. And
never edit the shared tree while an agent is running mutation tests in it — a reviewer's
`git checkout` silently wiped uncommitted work three times before the cause was spotted.

**A gate that only goes green on state another test left behind is not testing what it
claims.** `test_s17_1b` passed for months because it was the one gate file driving the API
without pinning its own database; two agents reported it failing and were told it passed.
Its red was not evidence, and neither was its green.
