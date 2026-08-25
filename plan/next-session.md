# Next session — build the engine against a ratified contract

```text
Written:  2026-08-25, closing the design/negotiation session.
Read:     this first, then plan/current-status.md for where the code is.
State:    The boundary is DONE. The engine is not. Nothing below needs another
          design round — every shape it names is agreed and signed.
```

## Where things actually are

**The contract is ratified at v1.1 by both teams** (`fence-rag/docs/integration/audit/11`).
Eighteen binding obligations, one amendment filed and accepted, zero open. Both repos hold
byte-identical copies; verify with `sha256sum -c docs/integration-contract/contract.sha256`
before relying on it, and **never edit it** — `AMENDING.md` carries the procedure.

**The engine has not moved this whole session.** Roughly six thousand lines of design
across two repos, zero lines of `src/`. Two obligations are violated in code today and we
signed the contract declaring them, which is on the record in `audit/11` §2.

## The rule for the next session, from the ratification itself

> Each component designs and implements **its own internals**, and preserves the
> **integration points** with the others.

Concretely, for this repo:

- **Free to change without asking anyone:** pipeline phases, fact-space layers, extension
  seams, registries, read models, storage, resolution order, the decision graph's internals.
  `docs/superpowers/specs/2026-08-25-engine-architecture.md` is the design and it binds
  nobody outside this repo.
- **Cannot change without an amendment:** anything in the 18 obligations — the snapshot
  payload, `Gap`, `Provenance`, `ParameterTable`, `condition_scope`, `stock_length`,
  `as_of`, the never-block rule.
- **The test:** if it changes what crosses the boundary, it is an amendment. If it changes
  how we compute, it is ours.

---

## Build order

Item 1 first, and not for tidiness: it is simultaneously a live defect, a violation of an
obligation we just signed, a prerequisite for the seams, and the Knowledge team's delta
item 1. One change, four payoffs.

| # | Work | Blocked by | Obligation |
|---|---|---|---|
| ~~**1**~~ | ~~**`Gap` as a return type.**~~ **DONE 2026-08-25.** Three sites converted, not two — `_resolve_default_post` was a third. `docs/reviews/generation-failure-audit-2026-08-25.md` | — | §3.2.4, and delta item 1 |
| ~~2~~ | ~~`SiteConditions`…~~ **DONE 2026-08-25.** `conservative_parameter_used` deferred to item 5 (it keys on a `ParameterTable.task` class that does not exist yet); no UI — settable only via `PUT /projects/{id}/site` | — | 13's site scope |
| 3 | Handler registries — fixing bases, length rules, presets. Turn `if kind == …` branches into registrations | nothing | none (internal) |
| 4 | The declared phase list, so inserting a step is a row rather than a chain edit | 3 | none (internal) |
| 5 | `ParameterTable` loader — `value_type`, `domain_basis`, `condition_basis`, validity fields, `condition_scope` binding, and a `SetToken` action so a token-valued param has somewhere to land. **Read the two prerequisites above first** | 2 | 13, 15 |
| 6 | Source policy — **currently zero lines** despite being binding and re-ranked twice. `version_status` is an axis | 5 | 6, §1.4 |
| 7 | `Provenance` on `SpecField`, and the snapshot-level `source_docs` join with invariant 12's closure check | 5 | 6, 8 |
| 8 | Warning model — `attaches_to`, the platform/source registry split, and the **annexe** in the structure sheet, which does not exist | 5 | 10 |
| 9 | `stock_length` consumed; continuity derived against resolved spacing | 5 | 14 |
| 10 | Containment → demand: flatten `ContainedSlot` into the panel's slot list under a path key, and the kit-credit rule, which has no home in a demand line today | 5 | — |
| 11 | `report/assembly.py` — bay and post scopes, `requires` edges as a partial order | 10 | 11, 12 |

**Steps 1–4 need nothing from anybody.** Steps 1 and 2 are done; start at step 3.

### Owed from item 2's review, and NOT done

1. **`site.*` does not reach model variant conditions or eligibility predicates.**
   `fencemodel/resolve.py` and `match.py` evaluate against contexts with no `site`
   namespace, so a variant conditioned on `site.hvhz` silently falls through to the
   default spec — the silent-wrong-answer shape, and an HVHZ panel build-up is
   exactly what a variant is for. Decide it rather than inherit it: either bind
   `site` into `PanelContext.condition_ctx()` and extend the missing-dimension scan
   to model conditions, or have `validate_model` REFUSE a variant condition reading
   `site.*` so it fails at authoring instead of at the fence.
2. **No UI.** Site conditions are settable only through `PUT /projects/{id}/site`,
   so an estimator cannot enter them. `error.site_conditions_changed` and
   `structure.site_changed` are therefore strings no browser has ever rendered.
3. **`conservative_parameter_used`** — deferred to item 5 on purpose; it keys on a
   `ParameterTable.task` class that does not exist yet.

### Two things item 5 must do BEFORE it loads a published row

Both fell out of the reviews of item 1. Both are inert today for the same reason —
nothing in `src/` can produce `origin="published"` yet — and both go live the moment
item 5's loader can.

1. **Build every row through `KnowledgeVersion.from_published(...)`**, never the bare
   constructor. `origin` defaults to `authored`, which is the safe direction for a
   field nobody sets, and therefore exactly the trap: a loader that forgets it makes
   a snapshot look home-grown, two published rows tie and disagree, and generation
   RAISES — the declared defect reinstated with no test failing, because
   `demo_knowledge()` holds no published rows to notice. The seam refuses an explicit
   `origin` argument so it cannot degrade into a suggestion.

2. **Surface conflicts at every resolution site, not three of them.** Only
   `max_span_mm`, the vertical mode and the layout preference call
   `_surface_conflicts`. `_resolve_mounting`, `_resolve_reinforcement`,
   `_resolve_default_post`, `_resolve_demand_skus`, `_resolve_quantity` and the panel
   limits all discard `Resolution.conflicts`. This is **pre-existing** — `main` did
   the same — but item 1 widened what it costs: a hard-band tie touching a published
   row is no longer a raise, so a published `require_mounting` disagreeing with an
   authored one now picks a winner by tie-break and reports nothing at all. Ground
   versus masonry, decided silently, on a run nobody warned. The three wired sites
   file a `Gap(disputed)`; the others cannot, because they have no `strategy` to file
   it on. Either thread it, or move surfacing into a wrapper so a new call site
   cannot opt out by omission.

## Known defects, with file and line

Both were declared at ratification rather than discovered, and both close with item 1:

| Where | What |
|---|---|
| `strategy/generator.py:1521` | `resolve_param` returns no winner → `raise GenerationFailure`. An uncovered exposure category produces **no plan at all**, on the single most important parameter in the system |
| `knowledge/evaluator.py:107` | Two contenders tie, disagree, both at authority ≤ `HARD_AUTHORITY_MAX = 3` → raise. Our expansion puts published rows at authority 1 or 3, so **both branches are inside the raise band** and the exposure grows as the other team publishes |

## Five mechanisms specified with no implementation

From the second self-audit pass. Each is designed and none is built:

1. A token-valued parameter has no `Action` that can carry it — `SetParam.value: int`.
2. There is no annexe in `report/`, so the 68% of warnings that are document-scoped have
   nowhere to render.
3. The source policy has zero lines.
4. `Provenance` has no field to attach to on `SpecField`.
5. The `Param` coverage anchor cannot resolve — `PanelContext.params` is a hardcoded
   two-key dict, and footing depth resolves on a different pass.

## What the other team is doing, so we do not duplicate it

Their four, from `audit/11` §3: the cell bounding box, the eleven-warning starter list,
the two early publishes (one `ParameterTable` with a `declared` domain, one definition
carrying a superseded `contributing_source`), and `also_filed_as`.

**We need none of it for steps 1–4.** Step 5 wants the first early publish to validate
against; step 6 wants the second.

## Parked, with what would reopen each

Gates (target `GateModel` shape recorded, publish as a `Gap`); `Combination` (pinned but
inert, `certify()` seam named); concrete and gravel (`site_material` reserved); stock
length constraining layout (publish now, consume later); `soil_class` (belongs in the
topology). Full list with reopen conditions: `fence-rag/docs/integration/where-we-stand.md`.

## Two habits worth carrying in

**Check against a substance, not against the design.** Five rounds each found what the
previous could not, because each checked against something different — their corpus, a
second reader, our codebase, our own additions, then a cold re-read before signature. After
round two the design was internally consistent and unimplementable. Coherence was never the
test.

**Anything invented at the boundary goes to the other side to be measured before it is
binding.** Their formulation, better than ours: an addition made at the boundary has no
substance on either side to check it against until someone holds it up to one. That is why
`continuity` and obligation 13 were both wrong — sound against our engine, which was the
only substance we had.

## Definition of done for the next session

Not "the design is agreed" — that is done. **Item 1 merged with the scenario suite green**,
and `plan/current-status.md` carrying an entry that says so.
