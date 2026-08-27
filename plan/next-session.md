# Next session — internal engine work, because the boundary cannot be checked yet

```text
Written:  2026-08-25, closing the implementation session that built items 1-5.
Rewritten: same day, when the Knowledge team's state changed the plan.
Rewritten again: 2026-08-27 — the Knowledge team reviewed item A's fixture,
          which cascaded into a real fix and a five-turn negotiation. See the
          two sections right under this box, newest first.
Read:     this first, then plan/current-status.md (newest entry first).
State:    THE BACKLOG IS CLEAR. Items 1-11 done and pushed. Items 6-7 remain
          OFF the table, not pending any question — pending the Knowledge
          team having real curated data to build against, which no amount of
          talking here changes. Nothing else is outstanding on either side.
          Next session starts from a genuinely empty queue, not a stale one:
          confirm this box is still true before trusting it, the way every
          "State:" line in this repo asks to be read.
```

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
| ~~6~~ | ~~Source policy~~ | **the other team** | **no — do not start** |
| ~~7~~ | ~~`Provenance` on `SpecField`, the `source_docs` join~~ | **the other team** | **no — do not start** |

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
