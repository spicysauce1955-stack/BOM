# Persona lab — six real-role users try to do their job

**Build under test:** `315bcbd` (harness fixes `5d08262`, `b720a2f` came after, from this run's own findings).
**Method:** six personas drawn from Israeli fence-trade roles drove the live app in headless
Chrome, perceiving only rendered UI — visible labels, opaque handles, no `#ids`, no API, no
DB, no repo access. 145 recorded steps, 64 raw findings. Every finding was then handed to an
independent refuter, prompted to *disprove* it, with repo access and a fresh browser. Only
reproduced findings carry a severity, and the refuter — never the persona — assigned it.

Spec: `docs/superpowers/specs/2026-08-11-persona-lab-design.md`.
Harness: `tools/persona_lab/`. Raw traces and screenshots are in the run scratchpad.

---

## 1. The headline

**Nobody finished. Six roles, six fallbacks to Excel or WhatsApp.**

| Persona | Gave up at | Of budget | What they would do instead |
|---|---|---|---|
| איש מכירות בשטח (sales rep) | step 13 | 30 | טופס הצעת מחיר בוורד |
| מנהל רכש ומחסן (procurement) | step 19 | 30 | טבלת אקסל של המחסן |
| מכין כתבי כמויות (estimator) | step 26 | 30 | אקסל עם סעיפים מהקטלוג |
| מהנדס פרויקט (English control) | step 29 | 30 | Excel + email |
| קבלן גדרות (contractor) | step 30 | 30 | אקסל + וואטסאפ |
| מודד שטח (measurer) | did not quit | 27 used | סקיצה ביד וצילום בטלפון |

The measurer is the only one who did not give up, and their closing verdict is the sharpest
sentence the run produced:

> בניתי פה שרטוט שנראה שלם ואינו שלם — וזה יותר מסוכן מסקיצה ביד, כי סקיצה ביד לפחות נראית כמו סקיצה.
>
> *I built a drawing here that looks complete and isn't — and that is more dangerous than a
> hand sketch, because a hand sketch at least looks like a sketch.*

They could not enter the retaining wall that is half their job, so the plan silently
understates what the next person prices. Not finishing is not the same as failing safely.

**What the run did not test:** whether any of these people would *trust* a number enough to
send it to a paying customer. See §6.

---

## 2. Read this before the findings: five defects were mine

The refuter pass found that the harness itself manufactured findings. All five are now fixed
(`5d08262`, `b720a2f`) and pinned by regression tests, but they invalidated 13 of 64 findings
and they distort what the personas reported:

| Harness defect | What it looked like to a persona |
|---|---|
| `type_text` sent CDP `char` events, never firing `keydown` | "Typed lengths do nothing" (3 personas) |
| `key()` sent no virtual key codes or `commands` | "Ctrl+Z is broken", "Ctrl+A does nothing" (4 personas) |
| `click` used stale coordinates, no `scrollIntoView` | "The button does nothing", "the tab row is dead" |
| `scroll` aimed the wheel at a fixed point on the canvas, which `preventDefault()`s to zoom | "The page is frozen, the side view is clipped" |
| `window.alert` was never answered, blocking the renderer | "The app froze completely and I lost my work" |

The last one deserves emphasis: the most alarming claim in the entire run — a total app freeze
with data loss — **was false**. The persona never clicked the button they described; an inert
Ctrl+Z produced no visible change and the narrative was confabulated around it. A real user
sees a Hebrew dialog and clicks OK.

This is the value of the refuter pass, and the reason findings below are worth reading: the
same discipline that killed those 13 also confirmed the rest against a live browser.

---

## 3. Confirmed findings, by theme

51 findings survived refutation. The collator groups by `(surface, symptom)` and produced 48
groups — it under-merged, because personas named surfaces in their own words. The thematic
grouping below is written, not generated.

### 3.1 Blockers — these alone stop someone finishing

**B1. There is no customer-facing price. (severity 4, 3 personas)**
The BOM is procurement cost. No margin, VAT, discount, deposit, or price-per-metre exists
anywhere in the model. "שמירת הצעת מחיר" freezes an immutable snapshot and renders it through
`bomHtml()` — literally the same function as the live procurement table (`tabs.js:275-292`).
`Quote` carries only `total_cents`. The button is honestly named for what this codebase means
by "quote", which is exactly why it misleads a sales rep. *No customer-facing output exists in
the product.*

**B2. No export of any kind. (severity 4, 3 personas)**
No Excel, CSV, PDF, print stylesheet, or `window.open` anywhere in `web/static` or `api/`. The
procurement manager: *"אני לא מקליד 8 שורות ידנית מהמסך לאימייל."* The estimator cannot get
lines out to fix them by hand either.

**B3. Prices are in euros, hardcoded. (severity 4, 4 personas)**
`€` at `editor.js:426`, `tabs.js:294,591`, and inside **both** locale bundles
(`bom.unit_price`, `bom.line_total`). There is no currency concept anywhere in `src/`. A
municipal tender in Israel is submitted in shekels.

**B4. Number fields prefix instead of replace, and the wrong value reaches the database.
(severity 4, 5 personas — the most-hit defect in the run)**
`editor.js:541` calls `first.focus()` without `.select()`. Chrome parks the caret at offset 0
in a `type=number` field, so typed digits *prefix* the prefilled value. Four sibling call sites
in the same codebase do it correctly (`editor.js:562-563`, `profile.js:779-780`, `:896`,
`:953`). It poisons every field `openEventPopover` builds: `pop-z`, `pop-width`, `pop-height`,
`pop-start`, `pop-end`, `pop-tilt-deg`.

Observed: gate width `1000` + typed `3500` → `35001000`. Height `1800` + `2200` → `18002200`.
Ground level `0` + `-400` → `-4000`.

The last one is the serious one. It **persists**: the session DB holds
`{"kind":"elevation_sample","z_mm":-4000}` — four metres of drop — written without a murmur.
`Mm` is a bare `int` alias (`core/units.py:15`) and `ElevationSamplePayload` carries no bounds,
so nothing validates between the field and the database. `#pop-height` ships `min=""`/`max=""`
while the neighbouring tilt field *is* bounded, so this is an omission, not a policy. Generation
would emit warnings — but per this project's own no-auto-compute rule, a measurer who saves and
walks away gets no signal at all.

**B5. A 42 m fence does not fit on the plan, and zoom is undiscoverable. (severity 3, 2 personas)**
`SCALE = 0.045` px/mm × `DEFAULT_VIEW.w = 900` = exactly 20.0 m of visible plan. Zoom, pan and
fit-view all work correctly (`editor.js:793` fitView, `:147` wheel, `:152` pan) — their entire
discoverability budget is one `title` tooltip on an unlabelled `⤢` glyph. Four of six personas
concluded the app had no zoom. **Undiscoverable is a real defect**, filed as `not-found`, not
dismissed because the feature exists.

**B6. No חגורת בטון, no mesh SKU, posts with no section. (severity 3, 2 personas)**
`BaseSurface = Literal["soil","concrete","masonry_wall"]` (`topology/model.py:82`) is the
surface the fence stands *on* — pre-existing concrete, the opposite of a concrete belt to be
built and priced. The only concrete in the system is CONC-25 at 0.5 bag per post footing;
there is no linear-metre belt anywhere in `demand/derive.py`. The catalog's 11 products carry
no section attribute and no mesh/infill SKU at all (`catalog/demo.py`), so neither the
estimator (matching tender line items) nor the warehouse (matching 60/60 stock) can reconcile
a single line. No frontend code calls `PUT /api/catalog/products`, so they cannot add them
either.

### 3.2 Serious, not blocking

**S1. Developer jargon printed into the deliverable. (severity 3, 4 personas)**
`heuristic plan: 20 bars vs LP lower bound 12` appears verbatim in the הערות column of the
quantities table (`fulfill.py:131` → `tabs.js:306`) and as a heading tag `יוריסטי (חסם LP 10)`.
Also `run3 · תחנה מ"מ 8764`, `kit SKU`, `[node_surface_disagreement]` prefixed to warnings,
`AI: stub` (`app.js:67`, no `t()` call, no key in either bundle).

This one has a sting. The estimator read the bar count as evidence the tool inflates quotes and
abandoned it — see §4, where that reading is refuted. Jargon in a customer deliverable did not
merely look unpolished; it destroyed a competent user's trust in a correct number.

**S2. English purchase units inside the Hebrew table. (severity 3, 4 personas)**
`bag`, `each`, `bar`, `box of 20`, `cut`, `new`, `application` render raw through `esc()` with
no `t()` (`tabs.js:293-317`); the backend supplies them as English prose (`fulfill.py:131,151,188`,
`derive.py:53-64`, `catalog/model.py:32,38`). This violates the project's own code+params rule
in `CLAUDE.md`.

**S3. No metre display unit. (severity 2-3, 5 personas)**
`UNITS = ["mm","cm"]`. Every persona measures in running metres; every one of them complained.
The catalog name `מוט מסילה 3000 מ"מ` never converts either, so after switching to cm the
column headers say cm while the item description still says mm.

**S4. Retaining wall height cannot be expressed. (severity 2-3, measurer)**
A base surface applies to a whole section with no way to say "from here to here", and there is
no split-a-run tool. Wall height *is* representable — set a built surface, and the side view
grows a dashed hint line that double-click turns into a `base_top` with typed height fields —
but nothing signposts it. The whole-section base is a deliberate decision
(`specs/2026-08-10-sections-model-addendum.md` §4); the dead-end it creates in practice is real.

**S5. Ground steps are supported but undocumented. (severity 3, measurer)**
A true vertical step works — click the same pixel twice, both anchors land on one station
(`station.py:157`). Nothing says so, and there is no field anywhere to type the *measured*
station, so a surveyor arriving with tape and laser gets whatever pixel their mouse landed on
(453.6 cm when they measured 450).

**S6. Locale toggle leaves rendered panels stale. (severity 2, English control only)**
`inspector.js:22` — the `locale-changed` handler calls `renderOverrides(); renderRunEvents();
replay();` and omits `renderRunSelectors()`, which the `units-changed` handler on the very next
line does call. It is the only module in the codebase with an asymmetric locale/units handler
pair. One line.

**S7. Enter on a one-dot draft silently discards it. (severity 1-2, 2 personas)**
`editor.js:231` → `finishDraft()` → `:672` requires ≥2 nodes → `cancelDraft()`, with no message
and no undo entry. Small, but it is the residual of what personas *thought* was catastrophic
data loss.

**S8. Concrete is mixed into the steel order. (severity 2, procurement)**
`BomLine` has no supplier or trade field, so CONC-25 sits in the same table and the same total
as posts and rails. Concrete goes to a different contractor entirely.

**S9. Unfiled, found by a refuter:** the inventory tab's Advanced-JSON toggle is labelled
**"חזרה לבונה הכללים"** ("back to the rule builder") — `tabs.js:177` reuses the
`knowledge.builder.back` key on a surface with no rule builder. Also `i18n/he.json:254` has
double-escaped unicode, rendering the literal `“test”`; `en.json:254` is fine.

---

## 4. Refuted — do not act on these

13 findings died. Four are worth stating explicitly because they are the ones a reader would
most likely have believed.

**The app is NOT over-quoting.** The estimator read `heuristic plan: 20 bars vs LP lower bound
12` as 8 surplus bars, ~144 € of padding, and quit over it. It is false. The LP bound is the
fractional material-volume relaxation `ceil(Σ(len+kerf)/(stock+kerf))` (`cutplan.py:119`),
attainable only if offcuts could be welded end to end. Reproduced: 20 pieces of 1730 mm against
3000 mm stock with 3 mm kerf — two pieces need 3466 mm against 3003 mm of capacity, so **one
piece per bar is the true unimprovable optimum**. There is no waste and no cheaper plan being
withheld. The real defect is the label: `cutplan.py:122` sets
`certified_optimal = (new_bars == lp_bound)`, so a provably optimal plan is called "heuristic"
whenever the relaxation is loose.

**The app never froze and no data was lost.** See §2.

**Typed-while-drawing lengths work.** With real key events, typing `21` raises a chip reading
`21 = 21000 מ"מ` and Enter places the dot at exactly 21000 mm. Harness artifact.

**The SKU dropdown does not desync.** Chrome's `<select>` popup highlights without committing,
so `select.value` legitimately still held the old option. Display and model never disagreed.

---

## 5. Ranked backlog

Ordered by whether it blocks a job, then by how many independent roles hit it.

| # | Fix | Cost | Evidence |
|---|---|---|---|
| 1 | `editor.js:541` — add `.select()` beside `.focus()` | one token | 5 personas; wrong values persist to the DB |
| 2 | Bound `z_mm` / `height_mm` / gate width at save time | small | nothing validates between field and DB |
| 3 | Currency: introduce the concept, stop hardcoding `€` | medium | 4 personas; blocks every Israeli sale |
| 4 | Export the BOM (CSV first — it is what Excel users want) | medium | 3 personas; no export exists at all |
| 5 | Add a metre display unit | small | 5 personas |
| 6 | Route `bag`/`each`/`bar`/`cut`/`new` through `t()` | small | 4 personas; violates CLAUDE.md |
| 7 | Stop printing `heuristic plan: … LP lower bound …` to users; fix the "heuristic" mislabel | small | destroyed a correct number's credibility |
| 8 | Label the zoom/fit control, or fit automatically when content exceeds the view | small | 4 personas concluded zoom did not exist |
| 9 | `inspector.js:22` — add `renderRunSelectors()` | one line | English control |
| 10 | Customer-facing quote: margin/VAT/per-metre, and an output that is not the procurement table | large | the sales rep's whole job |
| 11 | Catalog: mesh SKU, post sections, a חגורת בטון line item | large | estimator + procurement, both ends of the workflow |
| 12 | Signpost `base_top` wall height and the two-point ground step | small | measurer |
| 13 | `tabs.js:177` wrong i18n key; `he.json:254` double-escaped unicode | trivial | found by refuters |

Items 1, 2, 9 and 13 are close to free and cover the most-hit defect in the run.

---

## 6. Limits — read this before quoting any of the above

**These are simulated users.** They find mechanical dead ends, missing affordances, and
vocabulary mismatches. They cannot tell you whether a קבלן would *trust* €1296 enough to send
it to a customer, whether the price is credible, whether the cut plan saves real money, or
whether anyone would switch. Every methodology source consulted is explicit on this, and the
strongest signal here — six roles independently falling back to Excel — is a hypothesis about
real behaviour, not a measurement of it.

**The harness shaped the findings.** Five driver defects manufactured 13 false findings, and
they were caught only because an independent pass tried to disprove everything. Findings from
any future run carry the same caveat until refuted.

**Dedupe under-merged.** The collator keys on `(surface, symptom)` and personas name surfaces
freely, so 51 confirmed findings produced 48 groups. §3's grouping is hand-written. A future
run should constrain `surface` to an enum the way `symptom` already is.

**The no-repo-access rule was enforced by prompt and artifact placement, not by a sandbox.** A
project-wide deny-list would have blinded the main session too. No persona reported reading
repository files, and the refuter pass independently re-derived each finding from the UI, so a
finding that could only have come from source would have failed to reproduce. That is the real
control; the prompt rule is not.

**This is a snapshot** of `315bcbd`. The app was exercised through its seeded sample project
and freshly created projects only.
