# Persona lab, run 2 — five roles from the architecture

**Build under test:** `ebd082d` (harness fix `cb8d4cb` landed during refutation).
**Study design:** `docs/superpowers/specs/2026-08-11-persona-lab-run2-addendum.md`.
**Supersedes:** `persona-lab-2026-08-11.md`, whose study was measuring the wrong thing.

Five personas drawn from the *architecture* — not from market research — each doing a real
job twice, on two sites, with real numbers. They perceived only rendered UI: visible labels,
the status bar, warnings, open dialogs. No checklists, no hypotheses, no product vocabulary,
no framing that made quitting a deliverable. They wrote findings in free prose and **never saw
the classification categories**; an independent refuter reproduced each one, then assigned
symptom, surface and severity.

273 recorded steps. 64 raw findings → **31 confirmed in 18 groups, 13 refuted, 3 confirmed
positives.**

---

## 1. Did they get the job done?

| Persona | Actions | Outcome |
|---|---|---|
| **fulfillment** | 62 | **Both jobs finished.** Sent-ready orders, cut plans, quotes saved. Site 2 drawn in six actions. |
| **expert** | 61 | Site 1 finished exactly as they would build it. Site 2 required redoing identical work from scratch. |
| **approver** | 36 | Verified an accepted quote is frozen. Could not produce the delta the site manager asked for. |
| **topology-author** | 59 | Plot 1 partly wrong (slope on the wrong leg). Plot 2 essentially unenterable. |
| **knowledge-owner** | 55 | Neither rule change took effect. Stopped at 55. |

Run 1 reported 0 of 6. That number was an artifact of a study that rewarded quitting, hid the
status bar, and drew blind. **Two personas completed real work here**, and one measured a real
learning curve: `fulfillment` drew site 2 in six actions after fumbling site 1.

---

## 2. What works — verified as carefully as the defects

**Accepted quotes are genuinely immutable.** The approver recorded every line of an accepted
quote, added a gate, regenerated, saved a new one — and the accepted quote came back identical
to the last line, same total, same cut plan, explicitly labelled a frozen document. Accepting
the new version moved the old to superseded immediately. *"את הפחד שהמחיר יזוז לי מתחת לרגליים
המערכת הורידה ממני."*

**Impact preview does its job and is valued.** Confirmed twice from a fresh session: an unsaved
rule regenerates the portfolio, one named row per affected job, span/post/€ deltas,
`מול הצעה מאושרת` on jobs with an accepted quote, and a pre-approval warning that a conflicting
max span would fail generation in all six. (Caveat: unchanged jobs are skipped, so "a row per
job" holds only for jobs the change touches.)

**Cut plans and typed lengths earn their keep.** *"קיבלתי בדיוק את מה שאני צריך — מק"ט, יחידת
אריזה, כמות לרכש, ותוכנית חיתוך שאני יכול להדפיס ולמסור לבחור במסור בלי שיחשב שוב."* Typed
exact lengths were called the best thing on the screen; `6` → 6000 mm, no mouse needed.

---

## 3. Blockers

### B1. The expert-in-the-loop thesis does not function end to end (severity 4, 3 personas)

Four independent mechanisms, each sufficient on its own. This was proved, not inferred.

- **Site facts cannot be recorded.** `ObstaclePayload` and `ExistingFoundationPayload` exist in
  `topology/model.py:43-50`, and S12 assumes a foundation "marked as topology obstacle/feature"
  — but a repo-wide grep finds them only in `model.py` and the docs. No tool authors them, no
  generator or station code branches on them, no test touches them. The expert can express the
  conclusion (`pin_post`) and never the fact. **This is a golden-scenario ⇄ code disagreement**,
  which CLAUDE.md says must never be silently reconciled.
- **Hebrew corrections cannot become candidates.** `StubProposer.propose` filters on the literal
  English substring `"foundation"` (`ai/stub.py:116`). The refuter recorded the rule in Hebrew —
  no candidate; the same rule in English — candidate immediately. CLAUDE.md states the stub
  understands the demo vocabulary in English **and** Hebrew.
- **An approved candidate changes nothing.** The only action a proposal can emit is `AddNote`,
  and `add_note` has zero consumers in the evaluator or generator. Approve, regenerate, and post
  stations are byte-identical.
- **Scoped rules are silently inert** — see B2, which also kills every auto-proposed candidate,
  since the stub proposer defaults to `scope={"project_id": …}`.

Downstream: saving a pin nulls `state.result`, erasing the generated posts — and clicking a
generated post is the only route to the correction comment box. The UI destroys the path to the
loop.

### B2. Rule scope is accepted, stored, and ignored (severity 4)

The model supports it fully — `KnowledgeVersion.scope`, a closed condition AST, and
`K-STEP-SLOPE` ships a real condition. `POST /api/knowledge` accepts both fields. But
`generator.py` builds `ctx["scope"] = {}` at **every** call site (131, 182, 406, 941), so any
non-empty scope makes a rule silently inert: `{"project_id":"p1"}` → ignored, code default used,
no conflict, no warning; `{}` → fires.

Therefore the review queue's **"אישור בתחולה מצומצמת"** produces rules that can never fire, and
every stub-proposed candidate is born dead. Separately, the UI never sends scope at all —
`tabs.js knowledgeBody()` posts only `{object_id, type, title, actions, author}` — while the
on-screen hint promises conditions are editable in Advanced. A false promise over a no-op.

The evaluation context holds only `run.length_mm`, `run.slope_permille`, `post.surface`,
`post.context`. Neither "series X" nor "sandy soil" exists as a dimension, so both of the owner's
rules are unexpressible even at the AST level. `SetParam.value` is typed `int`, so 0.75 bag per
footing cannot be represented either.

### B3. A 3500 mm gate is priced as a 1000 mm kit, silently (severity 4, 2 personas)

`generator.py:431`:

```python
kit = ev.payload.kit_sku or f"GATE-KIT-{ev.payload.width_mm}"
```

Pure passthrough. The only check is `kit not in catalog.products`, which cannot fire because
GATE-KIT-1000 *is* in the catalog. Nothing compares kit width to opening width. The BOM prices
`ערכת שער 1000 מ"מ · €185.00` with the note *"kit includes: 1x GATE-LEAF-1000"* against a 3.5 m
opening. The refuter accepted that quote against a customer.

Three aggravators: the demo catalog holds exactly one gate kit, so a 3.5 m gate **cannot** be
priced correctly at all; the decision graph attributes the SKU to `K-GATE-REINF@v1` when it was
copied verbatim from the payload (`generator.py:623-633`), violating "the decision graph is the
explanation"; and no test covers it — every gate fixture uses `width_mm=1000`.

### B4. Station resolution disagrees with the readout the app prints (severity 4, 2 personas)

Two hit-tests that don't agree, on an L (which `finishDraft()` emits as two runs):

- Status readout (`editor.js` ~L249) loops runs in **array order**, first within
  `HOVER_RUN_MM = 400` → run1, station 6000.
- Click (`editor.js` L136) uses `closest(".run-hit")` — **SVG paint order** — and run2's band is
  painted last.
- `.run-hit { stroke-width: 16; stroke-linecap: round }` at `SCALE = 0.045` makes run2's end-cap
  a **~178 mm disc centred on the corner**, swallowing run1's stations ~5800–6000.

Measured: 220 mm from the corner → `run1 · 5780`; 126 mm → run2. **Station 6000 of run1 is
unreachable by any event tool**, and the ground popover has no station field.

The damage reaches the model: `groundSamplesFor()` falls back to the end node's `z_mm` of 0, so
run1 reads flat 0→0 while run2 starts at 1000. The two legs disagree about the elevation of the
same shared corner, and a 6 m climb is priced as level ground.

### B5. S05 and S06 are backend promises the authoring UI cannot reach (severity 3)

| Fact | Model | UI |
|---|---|---|
| soil→wall at 4.00 m | Yes — S05's test builds `BasePayload(masonry_wall)` over 4000–7000 | **No** — base popover has no station fields, `save()` hardcodes `0..runLength` and deletes any existing base; no split-run command exists |
| three wall-top heights | Yes — `BaseTopPayload.points` | **Buried** — unlabelled side-view, double-click a dashed hint that appears only after the whole run is masonry |
| neighbour ground 45 cm lower | **Absent from the model entirely** | — |
| 1.80 m privacy from neighbour's grade | **Absent as structured data** — `HeightIntentPayload` has no datum | — |

The phone call those scenarios exist to eliminate still has to happen.

### B6. Other blocking findings

- **No version comparison anywhere** (severity 3, approver). Two rows, each opening separately,
  no diff. The approver reconstructed +185 / posts 7→5 / rails 12→4 / net +70.50 by hand with a
  calculator. Comparing what moved since acceptance *is* this role's job.
- **A run cannot be extended to an exact length** (severity 3, 2 personas). The typed field
  exists on the run's length caption (`editor.js:891`) and works perfectly — 3000 → 9000 → 5000
  all applied. It is simply unfindable, and dragging fails for a separate reason: **the strategy
  overlay blocks selection on vertical runs.** `renderHandles` only draws handles for a selected
  run; the overlay draws span lines at `p[1]-8` with `stroke-width: 6`, which for a vertical run
  lands on the run's own hit line. With the overlay on — the default, and the state after every
  ⚙ compute — the click never reaches `.run-hit`.

---

## 4. Serious, not blocking

- **`editor.js:541` — `focus()` without `.select()`** (severity 3, 3 personas). The caret parks
  at position 0, so typing `1000` into the auto-focused ground field yields **`10000` — ten
  metres — silently saveable**. `openLengthInput` 20 lines below does it correctly.
- **The height popover seeds start from the clicked station** (`editor.js:449`), end from run
  length, height hardcoded 1800 — everything looks answered, so a fence half at the wrong height
  saves without a murmur. The base tool two lines up already does the right thing.
- **The height tool can silently shrink a run** (severity 4, not blocking because undo recovers).
  `.run-label` binds `openLengthInput` with `stopPropagation()` and never checks `state.tool`:
  height tool → click label → type 1800 → a 6 m leg became 1.8 m, no confirmation.
- **The rule editor traps you.** Switching the parameter re-renders but never resets `a.value`
  (the sibling action-kind select calls `defaultActionFor()`), so `1800` survived two switches
  into `screws_per_span` — a display-unit length landing in a raw count. Then `tabs.js:93` gates
  "back to rule builder" behind `JSON.parse` of the very text that is broken, with the same alert
  as the save error. Only a page reload escapes.
- **Annotations dead-end at `לא פוענח`** (severity 3, 2 personas) with no clarification prompt,
  no "did you mean", and no way to point at the thing on screen.
- **Remnants are computed, transmitted, and dropped.** `fulfill.py:117` produces
  `projected_remnants`, the API ships them, `material-optimization.md:29` promises they are
  "returned to projected inventory" — **zero hits for `projected_remnants` in the frontend**.
  Inventory is keyed on `project_id` with no warehouse scope, so job 1's offcuts are invisible in
  job 2.
- **`heuristic plan: N bars vs LP lower bound M`** reached a third and fourth persona. The maths
  is right — 1800 mm pieces from 3000 mm stock at kerf 3 give one per bar, so 10 is the proven
  minimum and the bound of 7 is unattainable — but `cutplan.py:122` calls a provably optimal plan
  "heuristic" whenever the relaxation is loose, and prints it, untranslated, into a Hebrew BOM row
  with no `code + params`. It has now caused two competent users to conclude the tool pads orders.
- **The conflicting-constraint failure prints the raw engine string** instead of a `code + params`
  message — a direct violation of the locale contract in CLAUDE.md.
- **Word collision:** the base-surface default option is `קרקע`, the same word as the adjacent
  `⛰️ קרקע` tool that sets elevation.

---

## 5. Refuted — and six harness defects that produced them

13 findings died. Four are worth naming because a reader would otherwise believe them:

- **"Screws come out at half"** — false. `K-SCREWS@v1` is `screws_per_span=8`, titled *"2 לכל
  חיבור קצה מוט"*; with 2 rails there are 4 rail-end connections. The persona's reading matched
  the model exactly; they differ only on their company's practice of 4 per connection. The
  inspector even shows the derivation.
- **"The dropdowns don't respond, so every rule comes out a hard max-span constraint"** — my
  harness. Chrome's native `<select>` popup is an OS widget CDP clicks can highlight but not
  commit. Driven by keyboard, `company_rule`, `default_component` and `rails_per_span` all
  committed.
- **"The decimal point is swallowed"** (`1.80 מ'` → `180`, `0.75 שק` → `075`) — my harness. `.`
  fell through to `ord('.') = 46` = **VK_DELETE**. Same for `"` (34 = VK_NEXT), which turned typed
  JSON into `[{kind:x}]`.
- **"The status bar showed one number and the popover opened on another" (expert)** — a one-pixel
  hover/click difference; one pixel is 23.7 mm and the discrepancy was 2.4 cm. The
  topology-author's much larger version of the same claim is real (B4).

**Harness defects found across both runs: eight, all fixed** — `char`-only typing, missing virtual
key codes, no `scrollIntoView`, wheel aimed at the canvas, unanswered `alert()`, `.`/`"` key
collisions, and a project selection that silently failed. Plus one **known and unfixed**: native
`<select>` needs keyboard driving. Every one would have shipped as a confident finding about the
product.

---

## 6. Ranked backlog

| # | Fix | Cost | Evidence |
|---|---|---|---|
| 1 | `generator.py:431` — validate gate kit against opening width; warn or fail | small | B3: a 3.5 m gate priced as 1 m, accepted against a customer |
| 2 | `editor.js:541` — add `.select()` | one token | 3 personas; `1000` → `10000` reaches the DB |
| 3 | `generator.py` — pass real scope instead of `{}` at all four call sites | small | B2: restricted approval and every auto-candidate are no-ops |
| 4 | Fix the two disagreeing hit-tests; give ground/base popovers a station field | medium | B4: slope recorded on the wrong leg, priced as level |
| 5 | `ai/stub.py:116` — match Hebrew, not the English substring `"foundation"` | small | CLAUDE.md invariant violated in a Hebrew-first product |
| 6 | Author `ObstaclePayload` / `ExistingFoundationPayload` from the UI | medium | B1; S12's precondition is unreachable |
| 7 | Give knowledge actions something beyond `AddNote` that generation consumes | large | B1: approving a candidate cannot change output |
| 8 | Stop printing `heuristic plan … LP lower bound …`; fix the `certified_optimal` label | small | 4 personas; two concluded the tool pads orders |
| 9 | `.run-label` — check `state.tool` before opening the length editor | small | height tool silently shrank a 6 m run |
| 10 | Overlay must not swallow clicks on vertical runs | small | the real cause of "dragging does nothing" |
| 11 | Quote-to-quote comparison | medium | the approver's actual job |
| 12 | Surface `projected_remnants`; scope inventory to a warehouse | medium | computed, shipped, dropped; docs promise otherwise |
| 13 | Base popover station fields + split-run; a datum on `HeightIntentPayload` | large | B5: S05/S06 unreachable from the UI |
| 14 | `tabs.js:93` — never gate the escape hatch on the broken thing; reset `a.value` on param switch | small | rule editor trap, 2 personas |

Items 1, 2, 3 and 5 are small and cover two severity-4 blockers and a stated-invariant violation.

---

## 7. Limits

**Simulated users.** They find dead ends, missing affordances and vocabulary mismatches. They
cannot tell you whether a קבלן would trust these numbers enough to send them to a customer, nor
whether anyone would switch. `fulfillment` finishing both jobs is a good sign, not a measurement
of adoption.

**Two sites is a short learning curve.** "Site 2 was faster" is one data point per persona, not a
trend.

**The harness shaped the findings again** — six defects, caught only because an independent pass
tried to disprove everything. Treat any future run's findings as hypotheses until refuted.

**My setup errors contaminated two runs**: the topology-author's opening (landed on the sample
project) and the approver's brief (named jobs I never seeded). Both are marked NOT-REPRODUCIBLE
above rather than quietly dropped.

**Snapshot** of `ebd082d`, Hebrew locale only. Run 1's English control established that language
is not the blocker, so it was retired.
