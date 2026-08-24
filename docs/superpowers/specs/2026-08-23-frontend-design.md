# Frontend — design

```text
Status:   Design, revised 2026-08-24 (second pass) against the Knowledge team's
          audit response. The evidence fixture now exists; the review queue
          gained a hard dependency it did not have; knowledge admin gained a
          warning surface and lost gates.
Owner:    this repo (src/fenceai/web/static/)
Contract: docs/integration/ in fence-rag carries the boundary in full.
          audit-disposition-v0.1.md records what was accepted and why.
Siblings: 2026-08-23-bom-engine-design.md
```

## 0. Why this document is not a formality

Two things here are load-bearing, and neither is a screen.

**The review queue sets the ceiling on the whole system.** The documented way this
class of project dies is reviewer throughput, not extraction accuracy — Google's
Freebase import into Wikidata was largely *accurate* and stalled anyway, because a
person had to adjudicate every candidate and there were always more candidates
than hours. Our own store is already that shape: 1,988 facts, **none reviewed by a
person**, 324 promoted automatically.

**Impact preview should be the spine of every review surface.** `learning/impact.py`
already answers *"what would this change do to my jobs"* — posts added and
removed, cents delta, and the delta against the quote the customer actually
accepted. Every place this design says "review something", the strong version is
to run that rather than show a diff. Most systems in this space never get this
capability; here it is already running, and the frontend is where it becomes
visible.

---

## 1. Constraints inherited from the repo

Non-negotiable, from CLAUDE.md:

- ES modules under `js/`, communicating **only** through `state.js`. No module
  touches another's DOM subtree. No framework, no build step, no CDN.
- Mutation discipline, in this order: `pushSnapshot(label)` → mutate
  `state.project` → `saveTopology()`. Non-user changes never push history; use
  `reloadProject()` after non-topology mutations or the undo stack is wiped.
- Every user-visible string through `t("key")` or `data-i18n`; `he.json` and
  `en.json` keep identical key sets. Logical CSS properties only. The plan canvas
  and profile SVG are **never** mirrored in RTL. SKUs, ids and dimensions get
  `.sku` / `.num` / `<bdi>` isolation.
- Anything interpolated into `innerHTML` goes through `esc()` — and that now
  includes **every string from the Knowledge Platform**: document titles, quoted
  source text, manufacturer names, curator notes. Document content is untrusted
  data by contract.
- Display units are a presentation preference: convert at the field boundary,
  render via `tu()`. Any length from the platform must round-trip losslessly.

---

## 2. Six surfaces

| Surface | Talks to | State |
|---|---|---|
| Map editor | Planning | unchanged |
| **Evidence viewer** | Planning → Knowledge (discovery) | new |
| **Review queue** | Planning → Knowledge (authoring) | new |
| **Impact preview** | Planning | new surface over an existing engine |
| **Knowledge admin** | Planning → Knowledge (authoring) | extends today's rules UI |
| Decision inspection + BOM review | Planning | extended |

The frontend never calls Knowledge directly. Everything proxies through Planning,
which owns authentication and locale. One backend, as today.

---

## 3. The evidence viewer

The earliest visible payoff in the whole system, and it touches no deterministic
path.

- Resolves a `SourceRef` through the discovery API; renders the page image with
  the region outlined and the quoted text beside it.
- **Renders provenance honestly.** A source reference proves *where the system
  looked*. It does not prove the source says what was written down — across
  studies of citation-bearing generated text, a large fraction of citations fail
  to support the claim attached to them. Label the state (`extracted`,
  `checked`, `verified against source`); never let a crop imply verification.
- Degrades properly: a visual reading has no element and no quoted text, only
  pixels. That is normal for scanned approvals and must be a first-class case,
  not an error.
- Deep-linkable, so a decision node's citation is shareable.

**The fixture now exists.** `docs/integration/fixtures/source-ref-examples.json`
in fence-rag carries **seven responses built from real rows** in their store,
covering every kind and every failure mode — including the three with no quoted
text and the one with no document at all. Build the viewer against that file
before the discovery API exists. `source-refs-design.md` beside it is the endpoint
design; nothing is implemented yet, so what we build against the fixture is still
what tells them whether the shape is right.

**Ask for the batch call now, not later.** A queue screen showing 50 rows would
otherwise issue 50 requests. `POST /source-refs:batch` is agreed and changes no
shape in the contract — design the viewer's data layer around a batch resolve from
the first commit rather than retrofitting one.

---

## 4. The review queue

### 4.1 The shape of the work

A reviewer answers one question repeatedly: *does this value, with these
conditions, match what the picture says?* Optimise for that and nothing else.

**Decompose to binary.** Never ask a reviewer to author a claim — ask them to
accept or reject one, with a correction path for nearly-right. Binary throughput
is an order of magnitude above authoring throughput.

**The crop is the primary content — and the crop alone is not enough.** Where the
source policy sets `min_curation = 2` for this task, the image is the largest
element on screen, the accept control stays disabled until it has rendered, and
`saw_crop` is recorded on the review.

But all 1,225 table readings in the store today record row and column labels and
**no cell bounding box in crop pixels**. A reviewer shown a crop and told "check
the value" without the cell outlined is not doing a bounded task; they are doing an
unbounded one, and §0's whole throughput argument collapses with it. The cell box
is what makes the review binary. We have asked the Knowledge team to prioritise it
above crop performance, and until it lands the queue should render the *absence*
of a cell box explicitly rather than showing a bare crop as if it were located.

**The hazard this exists to catch, in one real case.** On one PE-sealed sheet, the
same manufacturer publishes item J as `.875 X 7 X 62.75 TONGUE AND GROOVE PICKET`
in the bill of material and dimensions that same item at **7 3/8"** on the
elevation. Neither is labelled nominal or coverage; the sheet does not reconcile
them. A curator who reads the drawing builds a panel 5% too wide; a curator who
reads the catalogue is right. **Both validate clean.** No schema change closes
that — the queue is the only thing that does, which is the argument for what it
costs.

**Conditions are as reviewable as the value.** `24"` is not the risk; the risk is
`hvhz: unresolved` riding alongside it. Conditions render at the same weight as
the number, and an `unknown` operator is marked, never hidden.

### 4.2 Layout

```text
┌──────────────────────────────┬────────────────────────────┐
│                              │  footing_depth             │
│      the crop, large,        │  ┌──────────────────────┐  │
│      zoomable, with the      │  │  36"                 │  │
│      cell outlined           │  └──────────────────────┘  │
│                              │  exposure_category   C     │
│                              │  hvhz                no    │
│                              │  ⚠ post_size    unknown    │
│                              │  NOA 23-0314.05 · sheet 9  │
│                              │  extracted · unreviewed    │
├──────────────────────────────┴────────────────────────────┤
│  [ Accept ] [ Correct… ] [ Reject ] [ Needs source ]      │
│                                    ← 47 of 312 →          │
└───────────────────────────────────────────────────────────┘
```

Keyboard first. A reviewer working 300 items should never reach for the mouse.

### 4.3 The queue comes from the policy

Which claims a reviewer sees, which sources they may act on, and what bar a value
must clear are rows in the **source policy** — task × source class × role — not
hardcoded here. A structural reviewer and a catalog admin get different queues
from one mechanism, and the operator configures it.

### 4.4 Ordering, and a trap

Ordering by extractor uncertainty is tempting and **poisons your own
measurements**: a corpus assembled by asking about what the model found hard is
not representative, and cannot afterwards support an honest accuracy figure.

Order by value-at-risk — safety class first, then blocking gaps, then volume —
and keep a **randomly sampled holdout** reviewed separately and never promoted
from.

### 4.5 One review, one family

The escape from the throughput ceiling is that a review produces a *pattern*, not
just an approval:

> *This table appears in 12 other approvals with the same structure. Apply this
> reading to all of them?* — with three previewed, the holdout excluded, and the
> pattern revocable afterwards.

### 4.6 Machine proposals

Agent output is marked as such, with its confidence and its reasoning beside the
value, and accept / edit / ignore. Three bands rather than one threshold: confident
enough to apply, uncertain enough to queue, weak enough to discard — plus a floor
below which nothing is shown at all, rather than spending a reviewer's attention.
Structural tasks never auto-apply, whatever the confidence.

---

## 5. Impact preview

A surface over an engine capability that already exists, used from four places:
approving a claim, adopting a snapshot, confirming a `SkuLink`, taking a revised
definition.

```text
┌───────────────────────────────────────────────────────────┐
│  Adopting "Chesterfield 6ft v4" would change 7 of 34 jobs │
├───────────────────────────────────────────────────────────┤
│  Maple St      −5 posts   −14,000 ¢   vs quote  −14,000 ¢ │
│  Harbour Rd    +2 posts    +6,200 ¢   vs quote   +6,200 ¢ │
│  Old Mill      —          — cannot generate (was already) │
└───────────────────────────────────────────────────────────┘
```

Three things the engine already gets right and the UI must not flatten:

- A project that **could not generate before either** is not evidence about the
  change. Show it distinctly, never as breakage.
- The delta is against **the quote the customer accepted**, not a fresh
  calculation.
- Every row is shown, changed or not, so "34 checked, 7 affected" is honest
  rather than a filtered list implying the rest were examined and identical.

---

## 6. Knowledge admin

Extends today's rules UI rather than replacing it.

- **Part types.** Browse the shared spine; author tenant extensions by choosing a
  parent. The parent picker shows the inherited behaviour in plain language,
  because that is what the author is actually choosing.
- **Parts and panels.** Define what a part is and which type it files under; author
  panel specs as slots, infill patterns and fixing rules. Visual.
- **Containment.** A slot can hold a contained part — relation, coverage, post
  roles, and whether a rule requires it. Coverage is an **anchored interval**, not
  a menu of four kinds, so the editor's job is to author two anchors: the corpus
  really does say `POST LENGHT-(DEPTH+7)`, and one anchor points at a footing depth
  that is itself conditional. Show the resulting extent against the host, because
  a contained part that does not fit is not a worse choice, it is unbuildable —
  and one real insert is *longer* than its host, which must read as a visible
  overhang rather than a silent pass. The host's cavity is **derived**
  (`OD − 2 × wall`, since no manufacturer publishes a cavity) and the editor must
  show the derivation, not just the number.
- **Assembly steps.** Order is a **partial** order: steps carry prerequisite
  *edges* with a kind — `after`, `not_before`, `before`, `exclusive_with` — because
  the corpus states negative dependencies (`do not add concrete… until later`) and
  even denies its own print order in places (`Assembly may be continued by
  installing all bottom rails first, or one section at a time`). The editor must
  distinguish *"must follow"* from *"listed after"*. Scope is one of five —
  `panel · bay · post · run · site` — and roughly half of every real installation
  guide is neither panel nor bay. Every slot must be placed by exactly one step,
  and unplaced slots are shown as a defect, not omitted — but **a long `unplaced`
  list is a correct outcome**, not a to-do list. The editor must never nudge an
  author toward inventing a placement to clear it.
- **Warnings are authored separately from steps, and most are not on one.** Only
  19.9% of the corpus's warnings sit inside a step; 68% are document-scoped. The
  editor authors `text_raw` + `lang` + `attaches_to` + the publisher's own severity
  word, with a code as an optional overlay. Three rules the UI has to carry: a
  warning quoted from a document is **verbatim and untranslated** — never offer a
  translate affordance, because translating a manufacturer's liability sentence and
  publishing it as theirs manufactures a claim; `CAUTION` and `WARNING` are not
  interchangeable and the UI must not normalise them; and a document-scoped warning
  previews into the plan's **annexe**, not onto every line, so the author can see
  where it will land.
- **Gates are out of scope, and the UI must say so.** `FenceModel` models no gate.
  If a curator can file a gate as a fence model, they will, and swing direction and
  latch height — the two facts pool-barrier compliance turns on — vanish silently.
  Offer a gate as a `Gap`, never as a model.
- **Rules.** As today, plus the claims a rule was derived from, as evidence links.
- **Conflicts and gaps.** A conflict shows both sides with authority and dates and
  requires a choice *with a reason* — never an automatic winner. A gap shows what
  is missing and what would close it.

---

## 7. Decision inspection and BOM review

- Any node resting on platform knowledge links to its evidence.
- **Warned lines are first-class.** An unfulfilled requirement renders with its
  reason and, where possible, what would fix it. A BOM missing something must
  *look* like it is missing something.
- **Curation level is visible on every value that carries one.** A number nobody
  checked must not look identical to one an engineer confirmed against a drawing.
- Conservative substitutions announce themselves: *"exposure category not set —
  using the strictest documented spacing."*
- *"Why can't the spans be wider?"* returns the minimal set of rules responsible,
  not the whole graph.

---

## 8. Build order

| # | Work | Blocked by |
|---|---|---|
| 1 | Evidence viewer against `fence-rag/docs/integration/fixtures/source-ref-examples.json` — all seven records, including the three with no quote and the one with no document | nothing |
| 2 | Provenance affordance in decision inspection | 1 |
| 3 | Warned BOM lines and curation-level rendering | engine steps 5, 10 |
| 4 | Impact preview surface | engine step 9 |
| 5 | Review queue — binary accept/reject with crop | 1, discovery API |
| 6 | Containment and assembly-step editing | engine steps 3, 4 |
| 7 | Pattern promotion in the queue | 5 |
| 8 | Conflict and gap surfaces | 6 |

Step 1 needs nobody: the fixture is written, the corpus is on disk, and building
against it is what tells the Knowledge team whether their endpoint returns what a
reviewer actually needs — before they implement it.

**One dependency in step 5 that is not the discovery API.** The queue cannot reach
its throughput claim without a cell bounding box on table readings, which does not
exist for any of the 1,225 readings today. That is Knowledge's work, we have asked
for it ahead of crop performance, and it is the single item most likely to decide
whether the queue is a bounded task or an unbounded one.

---

## 9. Open

- **Hebrew-first review.** Source documents are English; the reviewer's UI is
  Hebrew-first RTL. Crops and quoted source text stay LTR inside an RTL page —
  a deliberate bidi treatment, not a default.
- **Throughput is unmeasured.** Watch someone review twenty real claims and time
  it before designing the queue around an assumption. Every number in §0's risk
  argument is borrowed from other fields; ours is unknown and cheap to learn.
- **Who reviews** is a policy question, not a UI one — roles and their admissible
  sources are configured in the source policy. The UI must not hardcode a
  reviewer type.
