# Frontend — design against the Knowledge Platform contract

```text
Status:   Design proposal, for review
Owner:    this repo (src/fenceai/web/static/)
Contract: see "The Seam" — system overview and contract v0.1
Siblings: 2026-08-23-bom-engine-design.md · fence-rag owns the Knowledge Platform
```

## 0. Why this document is not a formality

The review queue is the highest-risk component in the whole system.

The documented way this class of project dies is not extraction accuracy — it is reviewer
throughput. Google's Freebase import into Wikidata was largely *accurate* and stalled
anyway, because a person had to adjudicate every candidate and there were always more
candidates than hours. Our own store is already the same shape: 1,988 facts, **none
reviewed by a person**, 324 promoted automatically.

So how fast someone can accept a claim while looking at a crop is not a UI detail. It sets
the ceiling on how fast the entire system can learn. This screen deserves as much design
effort as the map editor.

---

## 1. Constraints inherited from the repo

Non-negotiable, from CLAUDE.md, and they shape everything below:

- ES modules under `js/`, communicating **only** through `state.js`. No module touches
  another's DOM subtree. No framework, no build step, no CDN.
- Mutation discipline, always in this order: `pushSnapshot(label)` → mutate
  `state.project` → `saveTopology()`. Non-user changes never push history; use
  `reloadProject()` after non-topology mutations or you wipe the user's undo stack.
- Every user-visible string through `t("key")` or `data-i18n`; `he.json` and `en.json`
  keep identical key sets. CSS uses logical properties only. The plan canvas and profile
  SVG are **never** mirrored in RTL. SKUs, ids and dimensions get `.sku` / `.num` /
  `<bdi>` isolation.
- Any user or expert text interpolated into `innerHTML` goes through `esc()`. This now
  includes **every string arriving from the Knowledge Platform** — document titles,
  quoted source text, manufacturer names, reviewer notes. Document content is untrusted
  data by contract; treat it as hostile.
- Display units are a presentation preference: convert at the field boundary with
  `toDisplayValue`/`toMm`, render via `tu()`. Anything showing a length from the platform
  must round-trip losslessly.

---

## 2. Five surfaces

| Surface | Talks to | New? |
|---|---|---|
| Map editor | Planning | unchanged |
| **Review queue** | Planning → Knowledge (authoring) | new |
| **Evidence viewer** | Planning → Knowledge (discovery) | new |
| **Knowledge admin** | Planning → Knowledge (authoring) | extends today's rules UI |
| Decision inspection + BOM review | Planning | extended with provenance |

The frontend never calls Knowledge directly. Everything is proxied through Planning, which
owns authentication and locale. One backend, as today.

---

## 3. The review queue

### 3.1 The shape of the work

A reviewer is answering one question repeatedly: *does this value, with these conditions,
match what the picture says?* Optimise for that and nothing else.

**Decompose to binary.** Never ask a reviewer to author a claim. Ask them to accept or
reject one, with a correction path for the case where the value is nearly right. Review
throughput on binary decisions is an order of magnitude above authoring throughput.

**The crop is the primary content, not a detail pane.** Where the source policy sets
`min_curation = 2` for this task, the image is the largest element on screen, the accept
control stays disabled until the crop has rendered, and `saw_crop` is recorded on the
review. A reviewer who accepts a footing depth without the crop visible is the exact
failure this system exists to prevent.

**The queue itself comes from the policy.** Which claims a reviewer sees, which sources
they are permitted to act on, and what bar a value must clear are all rows in the source
policy — not hardcoded here. A structural reviewer and a catalog admin get different
queues from the same mechanism, and the operator configures it.

**Conditions are as reviewable as the value.** The value `24"` is not the risk; the risk is
`hvhz: unresolved` riding alongside it. Conditions render at the same visual weight as the
number, and a condition with operator `unknown` is marked, not hidden.

### 3.2 Layout

```text
┌──────────────────────────────┬────────────────────────────┐
│                              │  footing_depth             │
│                              │  ┌──────────────────────┐  │
│      the crop, large,        │  │  36"                 │  │
│      zoomable, with the      │  └──────────────────────┘  │
│      cell outlined           │                            │
│                              │  exposure_category   C     │
│                              │  hvhz                no    │
│                              │  fence_height        6 ft  │
│                              │  ⚠ post_size    unknown    │
│                              │                            │
│                              │  NOA 23-0314.05 · sheet 9  │
│                              │  extracted · unreviewed    │
├──────────────────────────────┴────────────────────────────┤
│  [ Accept ]  [ Correct… ]  [ Reject ]  [ Needs source ]   │
│                                      ← 47 of 312 →        │
└───────────────────────────────────────────────────────────┘
```

Keyboard first: accept, reject, next, previous, zoom. A reviewer working a queue of 300
should never reach for the mouse.

### 3.3 Queue ordering, and a trap

Ordering by extractor uncertainty is tempting and it **poisons your own measurements**: a
corpus assembled by asking about what the model found hard is not a representative sample,
and cannot afterwards support an honest accuracy figure.

So: order by value-at-risk (safety class first, then blocking gaps, then volume), and keep
a **randomly sampled holdout** reviewed separately and never promoted from. The holdout is
how anyone ever answers "how good is the extraction."

### 3.4 One review, one family

The escape from the throughput ceiling is that a review produces a *pattern*, not just an
approval. After accepting a reading from a templated table, the reviewer is offered:

> *This table appears in 12 other approvals with the same structure. Apply this reading
> pattern to all of them?* — with a preview of three, and the holdout excluded.

That single interaction is the difference between reviewing cells and reviewing document
families. It needs to feel safe: show what will be promoted, allow per-document exclusion,
and make the pattern revocable afterwards.

---

## 4. The evidence viewer

Used from the review queue, from decision inspection, and from BOM lines.

- Resolves a `SourceRef` through the discovery API; renders the page image with the bbox
  outlined and the quoted text beside it.
- **Renders provenance honestly.** A source ref proves where the system looked. It does
  *not* prove the source says what was written down. The UI must never present a crop as
  verification — label the state (`extracted`, `checked`, `verified against source`)
  rather than implying it.
- Degrades: a `visual_reading` has no element and no quoted text, only pixels. That is
  normal for scanned approvals and must render as a first-class case, not an error.
- Deep-linkable, so a decision node's citation is shareable.

---

## 5. Knowledge admin

Extends today's rules UI rather than replacing it.

- **Roles.** Browse the spine; author tenant extension roles by choosing a parent. The
  parent picker shows the inherited counting rule in plain language — *"counted once per
  connection"* — because that is what the author is actually choosing.
- **Products and assemblies.** Define what a product is and which roles it fulfils; author
  assembly definitions as slots accepting roles. Visual, per the product brief.
- **Rules.** As today, plus the citation: which claims a rule was derived from, rendered as
  evidence links.
- **Conflicts and gaps.** A conflict shows both sides with their authority and dates and
  requires a choice with a reason — never an automatic winner. A gap shows what is missing
  and what would close it.

Every write goes through Planning to Knowledge. The frontend holds no knowledge state.

---

## 6. Decision inspection and BOM review

- The decision graph gains a provenance affordance: any node resting on platform knowledge
  links to its evidence.
- **Warned lines are first-class.** An unfulfilled requirement renders in the BOM with its
  reason and, where possible, what would fix it — not as an omission. A BOM that is missing
  something must *look* like it is missing something.
- **Curation level is visible on every value that carries one.** A number nobody has checked
  must not look identical to one an engineer confirmed against a drawing.
- Conservative-parameter substitutions announce themselves: *"exposure category not set —
  using the strictest documented spacing."*

---

## 7. Build order

| # | Work | Blocked by |
|---|---|---|
| 1 | Evidence viewer against the discovery API | Knowledge shipping `GET /source-refs/{id}` |
| 2 | Provenance affordance in decision inspection | 1 |
| 3 | Review queue — single-claim accept/reject with crop | 1 |
| 4 | Warned BOM lines and curation-level rendering | engine steps 3 and 7 |
| 5 | Pattern promotion in the review queue | 3, Knowledge shipping promotion rules |
| 6 | Knowledge admin: roles, products, assemblies | contract v0.1 agreed |
| 7 | Conflict and gap surfaces | 6 |

Step 1 is the earliest visible payoff in the entire system — a BOM line that opens the
sealed drawing sheet it rests on — and it touches no deterministic path.

---

## 8. Open questions

- **Hebrew-first review.** Source documents are English; the reviewer's UI is Hebrew-first
  RTL. The crop and quoted source text stay LTR inside an RTL page — needs a deliberate
  bidi treatment, not a default.
- **Throughput is unmeasured.** Before designing the queue in detail, watch someone review
  20 real claims and time it. Every number in this document's risk argument is borrowed
  from other fields; ours is unknown and knowable cheaply.
