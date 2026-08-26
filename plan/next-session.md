# Next session — internal engine work, because the boundary cannot be checked yet

```text
Written:  2026-08-25, closing the implementation session that built items 1-5.
Rewritten: same day, when the Knowledge team's state changed the plan.
Read:     this first, then plan/current-status.md (newest entry first).
State:    Items 1-5 done and pushed. Items 6-7 are OFF the table for now, and
          the reason is the most important thing on this page.
```

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

- **`Gap.would_close` is generated English with no `code`/`params`**, rendered in the UI
  as quoted foreign text with a Hebrew label saying it is written for curators and never
  translated here. The long-term answer is a `close.<code>` registry beside the warning
  registry, with the prose demoted to a fallback the way `message` already is.
  Deliberately NOT invented yet: a code vocabulary the Knowledge team has not agreed to is
  a second vocabulary at the boundary, which is what the freeze exists to stop.
- **`frost_depth_mm` has no `ge=0` bound** on `SiteConditions`, so the browser is the only
  thing refusing a negative depth. `PUT /site` accepts `-500` from anything that is not
  that panel. One-line engine fix.
- **`site.*` does not reach model variant conditions or eligibility predicates**
  (`fencemodel/resolve.py`, `match.py`), so a variant conditioned on `site.hvhz` falls
  through to the default spec silently. Decide it: bind `site` into
  `PanelContext.condition_ctx()`, or have `validate_model` REFUSE such a condition so it
  fails at authoring rather than at the fence.
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
