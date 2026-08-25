# Current status

## Build-order item 11 — step scopes, and `requires` as a partial order (2026-08-25)

**1839 pytest (was 1793) · 203 scenario tests.** Contract obligations 11 and 12,
plus the post/cap/footing gap `report/assembly.py` had recorded since 2026-08-19.

- **`AssemblyStep.scope`** — all five of `panel | bay | post | run | site` from
  the start. The panel sheet renders three and says how many it withheld; `run`
  and `site` are present-and-unrendered, which is the contract's own wording and
  is a promise about a SURFACE, not about the data.
- **`AssemblyStep.requires`** — typed edges (`after | not_before | before |
  exclusive_with`), empty where the document merely prints one step after
  another. `fencemodel/step_order.py` is the single implementation, called by
  `validate_model` (to refuse a contradictory circle at authoring) and by
  `report/assembly.py` (for the sequence it returns).
- **`AssemblyStep.bay_parts`** — `post | cap | footing`. A step can finally name
  what it sets. `assembly_plan(model, panel, bay=...)` is the different input the
  old note said it needed.

**What the read model returns for a partial order, and how it admits it.** One
linearisation, deterministic, ties broken by authored position — plus
`order.stages` (mutually unordered groups), `order.unique`, and `order.basis`
(`authored` vs `requires`). Three states, three sentences on the sheet. The
sequence is a presentation choice and the stage is the fact; a bare sorted list
would have flattened the partial order again with an engine's authority behind
it.

**A `not_before` loop is concurrency, not a contradiction.** Only a loop carrying
a strict edge asserts a step precedes itself. Collapsing the two would have made
"pour both footings, then move on" unauthorable — the same flattening one level
down.

**M-VINYL now exercises all of it**: `set_posts` (post-scoped, bay parts), `cure`
(site-scoped — carried and not drawn), `rails`, `boards` (strict on `rails`,
`not_before` on `cure`), `cap_posts`. Its returned order is NOT its print order,
which is the point.

Details, and five things knowingly left, in `plan/open-work.md` §11.


## The frontend catches up: three slices, built in parallel (2026-08-25)

**1780 pytest · 203 scenario tests · 237/237 browser smoke** (was 202). Three
agents in isolated worktrees, merged one at a time with the suite and the smoke
run between each.

- **Site conditions are enterable** (`js/site.js`). `null` is a control state, not
  an absence: `hvhz` is a three-option select because a checkbox cannot say
  "nobody has stated it", which is the state the evaluator turns into *not
  applicable*. `depthFromField` is a named function so a measured `0` is not
  erased by a falsy check. The whole of engine item 2 was unreachable from the app
  until this.
- **Gaps have a reader** (`js/gaps.js`). `closes_by` GROUPS the panel rather than
  tagging a row — a badge in a mixed list still hands a curator an engineer's
  work, which is the property §1.2.1 says the queue must have. `severity` changes
  a row's weight and never its group: where work goes is not a function of how
  loud it is. Unsuppliable lines are now rows in the priced BOM table with no sku
  and no money, because a table a reader prints and adds up must not look
  complete when it is not.
- **The editor asks what it may offer** (`GET /api/vocabularies`). The hardcoded
  arrays are gone. When the vocabulary cannot be fetched the select is DISABLED
  and says why, rather than offering a stale guess that 422s on save.

**Eight strings that had never been rendered by a browser now are**, and are
asserted: `warning.site_condition_missing`, `structure.site_changed`,
`decisions.stale_site`, and the gap panel's rendering of `uncovered_max_span` and
`no_default_post` in Hebrew from the code rather than the English `message`.

**`would_close` renders as quoted foreign text** — `lang="en" dir="ltr"` inside
the RTL page, with a Hebrew label saying it is written for the knowledge curators
and never translated here. The precedent is the frontend design's own rule for a
manufacturer's warning: translating someone's liability sentence and publishing it
as theirs manufactures a claim. The long-term answer is a `close.<code>` registry
beside the warning registry, deliberately NOT invented here — a code vocabulary
the Knowledge team has not agreed to is a second vocabulary at the boundary.

**Two things the agents found that I had wrong:**

- **S17 only ever passed on leaked state.** It was the one gate file driving the
  API without pinning a database. Two agents reported it failing, I could not
  reproduce it and said so; they were right. The doc's numbers were correct and
  the scenario simply never created the `K-MAXSPAN@v2` the doc names — fixed by
  making it establish its own precondition, not by moving the numbers.
- **Item 3 silently reordered two dropdowns.** `Registry.names()` sorts, which is
  right for an error message and wrong for a select. `declared()` now answers the
  second question, and the editorial order the editor has always shown is pinned.

**Still owed:** `Gap.would_close` wants a code registry (above); `frost_depth_mm`
has no `ge=0` bound on the model, so the browser is the only thing refusing a
negative depth; and nothing calls `ParameterTable.expand()` from a route, so item
5 is still reachable only from tests.

## The gaps the engine produces now have a reader (2026-08-25)

Frontend build-order step 8, the gap half. **1762 pytest · 217/217 smoke.**
`Strategy.gaps` was returned by `/generate` and read by nothing: six gap codes
existed, none had ever been rendered by a browser in either language.

`web/static/js/gaps.js` is the surface — pure, string-returning, no DOM of its
own, the same shape as `warnings.js`, and it calls that module's
`localizedByCode` rather than growing a second code→sentence mapping. The editor
injects it under `#gaps`; the BOM tab injects the same panel above the priced
table.

**The panel groups by `closes_by` rather than chipping it.** That is what the
BINDING clause actually asks for — *"a queue that shows a curator work only an
engineer can perform is a queue whose items are not actionable"* — and a badge
in a mixed list does not deliver it. `severity` changes the weight of a row and
never its group: where the work goes is not a function of how loud it is. An
empty group is not offered; both of today's codes close on the knowledge
platform, so the browser shows one group, and the `planning` side is pinned in
node against a synthetic `unmodellable_entity`.

**`would_close` is on the row, never behind a click** — the other BINDING clause
— and it is the one honest hole in the i18n story: generated English prose with
no code and no params, in a Hebrew-first product. It is rendered as what it is,
quoted, `lang="en" dir="ltr"`, labelled in Hebrew as a note written for the
knowledge curators, exactly as §6 requires for a manufacturer's warning text
(*"verbatim and untranslated — never offer a translate affordance"*). **The
long-term fix is a `close.<code>` registry beside the warning registry** — a
registry addition, which needs no amendment — with the prose demoted to a
fallback. It was not invented here because a code registry the other team has
not agreed to is a second vocabulary at the boundary.

**And the BOM now looks short when it is short** (§7). Unresolved lines were
reported only in the panel above the priced table, so the table a reader prints
and adds up looked complete; they are rows in it now, carrying no money, under a
heading that says the total excludes them.

**Untouched:** the engine. No gap is emitted that was not already emitted, and
`core/gaps.py` is unchanged.

**Pre-existing and not from this work:**
`tests/scenarios/test_s17_section_conversation.py::test_s17_1b` fails on
`b2b8400` itself, with or without a stray `fenceai.db` in the tree.

## Published parameter tables land as ordinary knowledge (2026-08-25)

Item 5, and the last item that needed nothing from the other team. **1751 pytest ·
203 scenario tests, green.**

`ParameterTable` is the contract's §1.3 type, built field-for-field from the
contract rather than from memory — the last boundary type built from memory
invented a `SourceRef` with the wrong fields under the contract's own name, so the
parsing tests come first here and use the contract's shapes verbatim.

**The expansion is the design.** A published table becomes ordinary
`KnowledgeVersion`s, one per row, whose condition reads the namespace that row's
keys are scoped to — so the existing evaluator resolves them beside everything
else, at their own authority, with the same precedence and the same conflict
reporting. No second selection path, no privileged channel into the generator.
That also satisfies obligation 13 without a scheduler: a row conditioned on
`post.role` becomes a rule conditioned on `post.role`, expanded now and selected
when a post exists.

**Every version is built through `from_published`** — the seam recorded as item
5's prerequisite. A loader using the constructor would make published rows look
home-grown, and two that tie and disagree would RAISE: the exact defect `origin`
was added to close, reinstated with nothing failing, because `demo_knowledge()`
holds no published rows to notice.

**Four things the contract is specific about, and why:**

- **`to_mm` rounds, it does not truncate** (§1.1 BINDING). A span limit passes
  through `n = ceil(run_length / max_span)`, so 2463.8 floored rather than rounded
  buys an extra post, footing and pour on a 9.8 m run. Python's `round()` is
  banker's and sends 2500 thousandths to 2, so the half-up form is written out.
- **`value_type` is declared once on the TABLE**, so one column cannot hold both
  `10000 deg_milli` and `not_rackable`. `SetToken` is a separate action rather
  than a union-typed `SetParam.value` for the same reason: a resolver asking for
  a length must not typecheck against a word.
- **`domain_basis` changes what an uncovered point MEANS** — against `measured`
  the table really does not cover it; against `declared` we may not know the
  table's extent. Different facts, different `would_close`, different work.
- **A lapsed row is marked and still expanded.** Dropping it would turn a lapsed
  authority into a coverage hole, and those are different fixes. Judged against
  the run's pinned `as_of`, never a clock (obligation 16): no `as_of` means no
  expiry judgement rather than today's date.

**The frontend gap widened here, and this is the notification.** Three new codes
(`uncovered_parameter_point`, `parameter_authority_lapsed`,
`parameter_value_nonconforming`) are produced and **nothing renders them** — they
are `Gap.code`s, `Strategy.gaps` still has no reader, and the annexe is item 8.
They are in both locale bundles with placeholders verified against the params
actually emitted, so the surface that eventually reads them is not also the change
that has to invent their Hebrew. The locale guard did not catch them, because it
never scanned `knowledge/parameters.py`; that hole is closed.

**Also not wired:** nothing calls `expand()` in a route. There is no snapshot
loader — the contract's payload arrives as a whole `KnowledgeSnapshot` and that
ingestion is not built, so this item delivers the type, the expansion and the
gaps, and stops at the point where a real published snapshot would enter.


## The pricing chain is a declared list, and the API did not move (2026-08-25)

Item 4, the second extension seam, and **steps 1–4 of the build order are done.**
**1725 pytest · 203 scenario tests, green.**

`derive → resolve → fulfil` was three statements in `price_strategy`. It is a
declared tuple in `fulfillment/phases.py` now, because both things the seam exists
for are MIDDLE inserts: kit credit (item 10) and `certify()` for `Combination`
(contract obligation 17, shape agreed, seam named, nothing reads one yet). A
middle insert into a hardcoded chain means reading three statements, working out
what each hands the next, and hoping the mental model matches.

**A phase declares what it reads and what it writes**, which is the "input and
output type" the spec asks for — expressed as field names on a shared state
rather than static types, because the state being ONE object is what lets a new
step add a field without changing the signature of every step around it.
`check_order` then refuses a step placed before its input exists, at import. The
failure that prevents is quiet: `credit_kits` above `resolve_supply` reads
`requirements`, finds the empty list it was initialised with, credits nothing,
and prices a job that looks fine.

**Not a registry, deliberately.** The ORDER is the design, so it is one tuple a
reader sees whole rather than a name→function map assembled by import order — a
pricing chain that depended on what was imported is a job priced differently on
two machines. `price_strategy(phases=…)` takes it as an argument instead of
reading a mutable global.

**The API did not move, and I checked rather than assumed.** `PricedRun` is what
`/bom`, `/structure` and `/quote` all return. A live `/bom` response is
byte-identical across the refactor once per-invocation ids and timestamps are
normalised (26,462 bytes), the compatibility gate's twelve fixtures still match
their committed golden files, and a test pins `PricedRun`'s field set so a later
change to it has to be a deliberate client-facing decision.

**Frontend parity is unchanged by this item and still owed** — four items in
`plan/next-session.md`, the load-bearing one being that site conditions have no UI
at all, which also means three locale strings added for them have never been
rendered by a browser.

**Next:** item 5 — the `ParameterTable` loader. It is the first item that wants
something from the other team (their early publish, to validate against), and the
two prerequisites recorded under it must land first: the `from_published` seam
must be what the loader uses, and conflict surfacing must reach more than three of
the ~13 resolution sites.

## Three vocabularies moved from closed to open (2026-08-25)

Item 3, the first of the four extension seams. **1718 pytest · 203 scenario
tests, green.** The rule the engine spec states, applied:

> A vocabulary is **open** when a general mechanism reads it, and **closed** when
> `if kind == "…"` branches on it somewhere.

Fixing bases, length rules and objective presets were each a `Literal` naming the
members plus a branch that knew what each one meant — so `per_corner` was a type
edit, a branch edit and a release, while adding a part type or a warning code was
a row. Nothing about the concepts made a fixing basis harder to extend. One was
data; the other was a branch.

Each is a `Registry` of named functions over ONE signature now, and the `Literal`
became a `str` validated against the registry. **Validation was moved, not given
up** — and it got better: a typo is refused at parse time with a message naming
what IS registered, which the `Literal` never did.

**The signature is the contract**, which is what keeps this from being a plugin
system. The spec's escalation test decides: a `per_corner` basis is
`(PanelCounts) -> int` like every other and registers; a basis that must see the
neighbouring bay cannot be written that way, and that is the signal it needs a
release rather than a row.

**Three things worth recording:**

- **Registration refuses to overwrite.** Two modules registering `per_member`,
  resolved by import order, is a fence counted by whichever loaded last. Re-adding
  the *same* function is fine — that is an idempotent import, not a conflict.
- **The slope factor stopped being a tail.** It was applied to whatever the
  length if-chain returned, with `panel_height` returning early to dodge it. It
  corrects a HORIZONTAL member for running along the grade, so whether it applies
  is a property of the RULE — it is `along_grade()` for rules to opt into now,
  which is also what makes a new vertical-member rule safe to register.
- **A preset can be a row because it is only a key function.** Every preset ranks
  the same candidates on the same measured facts and differs in what it puts
  first. `_choose` filters infeasible candidates BEFORE any preset runs, so a new
  preset structurally cannot rank an unsuppliable product first — a test asserts
  that ordering, because it is the guarantee that makes the vocabulary safe to
  open.

**The editor is now the closed half, and deliberately visible.**
`js/panel-model.js` still carries hardcoded arrays, and the test asserting
editor/backend equality points at the registries now — so registering `per_corner`
makes it authorable through the API and turns that test RED until the editor names
it too. That failure is the reminder, not a bug. Closing it means serving
`FIXING_BASES.names()` from a route the editor reads; it is not done.

**Next:** item 4 — the declared phase list, which depends on this.

## Site conditions — the prerequisite for anything conditional (2026-08-25)

Item 2. **1704 pytest · 203 scenario tests, green.** The acceptance criterion the
design named is now a test: **one rule on exposure yields two span limits on two
sites** — same fence, same knowledge, `B` gives four 1500 mm bays and `C` gives five
1200 mm ones.

`SiteConditions` sits on `Project` because these are whole-site facts; anything that
varies ALONG a run stays an interval payload on the topology, which is where soil
class will go. `site.*` binds into **every** evaluation context — threaded explicitly
through thirteen functions rather than smuggled inside `scope`, because a hidden
channel is exactly what the item 1 review criticised elsewhere, and because a site
fact that reached the bays and not the posts beside them would be a fence built to
two different sites.

**Three things that were not obvious until they were built:**

- **An unset dimension is OMITTED, not sent as `None`.** That is what makes a rule
  conditioned on it *not applicable* rather than false — the evaluator's existing
  `MissingField` behaviour used as the hook. But the failure mode of getting that
  right is silence: the rule does not fire, the fence is built to whatever
  unconditioned rule was left, and nothing says the deciding fact was never entered.
  So `site_condition_missing` reads the dimensions off the RULES in the snapshot, not
  off a hardcoded list — a base that never mentions exposure does not nag about it,
  and the day one starts publishing exposure rows the warning appears with no code
  change. **Not a `Gap`:** `closes_by` is `knowledge | planning` and this is neither,
  it is a field on the project for a person here to fill in. A gap whose reader
  cannot action it is the one thing §1.2.1 says that queue must not contain.
- **The digest takes the site FACTS, not `site_revision`.** A revision moves when
  somebody saves the form; the facts are what changed the answer. Hashing the counter
  would split the digest between two runs of an identical fence.
  `PLANNING_BEHAVIOR_VERSION` moves to `planning-v3`, because a rule conditioned on
  `site.*` now fires where it could not before — an output change for unchanged
  inputs, which is what that constant exists to record.
- **The 409 is a door the existing guard could not watch.** Site conditions are not
  part of `topology`, so `topology_changed` never fires on them: change a project from
  Exposure B to C and the structure sheet would render the old layout without
  complaint, and that document goes to site.

**Deliberately not built, both stated rather than discovered later:**
`conservative_parameter_used` (§2.3 keys conservative selection on a
`ParameterTable.task` class, and there are no parameter tables until item 5 —
building it now means inventing a task class to switch on, which is the retraction
in the engine spec's §6 all over again); and **no UI** — site conditions are settable
only through the route, so an estimator cannot enter them from the app yet. The
engine reads them, so nothing downstream is blocked.

### Then two reviewers read item 2, and the guard was wrong

**1704 pytest · 203 scenario tests, green.** The compatibility gate is untouched —
only the new fixture's golden file was written, so every existing job still prices
byte-identically.

- **A no-op site save bricked the run, permanently.** The digest hashes the site
  FACTS and the guard compared a REVISION; those agree only if every bump changes
  the facts, and re-saving the same form does not. Regeneration returned the same
  run id, `INSERT OR IGNORE` kept the document carrying the old counter, and every
  derived view answered 409 for ever with no user action able to repair it — while
  the generate response reported the new revision. The run now stamps `site_facts`
  and the guard compares those, so guard and digest agree on what "the site" means.
  It also answers §15: nothing persisted said which site a run was built for, and
  `Project.site` is mutable with no history, so a run's own explanation became
  unreconstructible the moment somebody edited the form.
- **The impact preview was site-blind**, so a rule that relays the whole fence
  previewed as `bom_delta_cents: 0` on the screen the docs call the single
  highest-value review feature. Same class as item 1's dropped conflicts, in a new
  form — and the fix that makes the CLASS loud rather than this instance: the
  evaluator now refuses a context that cannot answer a question a rule asks.
  `facts()` returns `{}` and never absence, so `"site" in ctx` separates "the user
  did not answer" from "the caller forgot to bind".
- **A conditioned rule did not outrank an unconditioned one.** `specificity()`
  counted scope keys only, so *"we say 1500; in Exposure C say 1200"* tied inside
  the hard band and FAILED the run. My own acceptance test carried `authority=0`
  with the comment "beats the unconditioned demo maximum" — that comment was the
  bug, written down and not noticed. Conditions count now, and the test no longer
  tunes precedence by hand.
- **The acceptance test's B arm was a no-op** — B was 1800, the value the demo rule
  already sets, so deleting the B rule left every assertion passing. "Two span
  limits on two sites" was testing one. B, C and the unconditioned baseline are
  three distinct answers now.
- **Four of six binding sites had no test.** Mutating `"site": site` to `"site": {}`
  left 1676 tests green at four of them, including panel safety — a site-conditioned
  HARD limit dropped in silence. There is a test per binding site now, and each one
  fails when its own site breaks.

Also: `/quote` refuses a moved site (a working view stays permissive; an immutable
commercial document must not freeze a stale one), `extra="forbid"` so a misspelled
field fails at the boundary as its docstring always claimed, both locale bundles
carry the sentences the frontend now actually renders, and both version constants
moved — `planning-v4` for the precedence change, `digest-v4` for `site_facts`
joining the digest's inputs.

**Owed and recorded, not silently skipped:** `site.*` does not reach model variant
conditions or eligibility predicates, so a variant conditioned on `site.hvhz` falls
through to the default spec silently. That is a design question — should a MODEL see
the site? — and inventing the answer while shipping something else is how the
retracted entity in the engine spec's §6 happened. It is in `plan/next-session.md`
with the two ways to close it.

**Next:** item 3 — handler registries for fixing bases, length rules and presets.
Then item 4, the declared phase list, which depends on it.

## `Gap` as a return type — the engine moves, and two signed obligations close (2026-08-25)

Item 1 of `plan/next-session.md`, and the first line of `src/` to change since the
contract was ratified. **1658 pytest · 193 scenario tests, green.**

**The audit is the deliverable, and it found one more than the plan named.** All
thirteen `GenerationFailure` sites, verdict and reasoning each, in
`docs/reviews/generation-failure-audit-2026-08-25.md`. Three converted, ten stay:

- `evaluator.resolve()` — a disagreeing hard tie now raises only when **both**
  contenders are `authored`. `KnowledgeVersion.origin: authored | published` is the
  new field, defaulting to `authored` so nothing already in the codebase moves. This
  was the exposure that scaled with adoption: our expansion puts published rows at
  authority 1 or 3, so both branches sat inside the raise band.
- `max_span_mm` uncovered — the declared defect. It laid out no plan at all on the
  single most important parameter in the system; it lays out to
  `FALLBACK_MAX_SPAN_MM` now, warns every bay it touched, and files a `Gap` naming
  the row that would close it.
- **the third, which the plan did not name:** `_resolve_default_post`. Knowledge
  naming no ground-post product was also a run failed over a gap. The post now
  stands with no sku, which demand already reports as an `unresolved` line and
  `/bom` already renders — the channel existed, nothing was reaching it.

**What the audit found by finishing.** After the three conversions the engine has no
refusal left that a curator could close: every one of the remaining ten is either a
fence that must not be built (a violated `hard_constraint`) or an instruction that
cannot be followed (a model id that does not exist). That is the property §3.2.4
actually asks for, and it is stronger than "the two declared defects are fixed".

**Recorded, not fixed.** `DEFAULT_RAILS_PER_SPAN` and `DEFAULT_SCREWS_PER_SPAN` have
been silent fallbacks for unstated quantities since long before this audit — the same
shape as the max-span fallback, minus the warning. Left alone because closing them
moves golden numbers on runs that are currently green.

**One open question, deliberately not settled:** `no_item_covers_part_spec` is the
taxonomy's `unsatisfiable_requirement` almost word for word, and converting the post
default made "a post with no product" representable. It stays a refusal because the
catalog is *our* artefact — *"buy a different post"* is not curator work — and a gap
whose reader cannot action it is the one thing §1.2.1 says a queue must not contain.
What would reopen it: a `closes_by` that names the tenant.

**An invariant reversed, on purpose.**
`test_missing_hard_knowledge_is_generation_failure` asserted the opposite until
today. It is now `..._is_a_gap_not_a_generation_failure`, and the never-block
invariant is written into `docs/scenarios/golden-scenarios.md` rather than living
only in a test. Four tests encoded the retired behaviour; each was rewritten against
what it was actually protecting, not deleted — the API's code-less 422 branch and the
impact report's refs-free failure branch both still have a caller.

**Also changed:** `core/gaps.py` (the contract's `Gap` shape, unrenamed);
`Strategy.gaps`; a `gap` node kind with en/he templates; `warning.uncovered_max_span`
and `warning.no_default_post` in both locale bundles; and the five architecture docs
plus ADR-0005 that asserted the old rule.

### Then four reviewers read it, and two of the three conversions were wrong

Run at the checkpoint CLAUDE.md asks for. **1658 pytest · 193 scenario tests, green.**
Full account in the audit's closing section; the short version:

- **The post conversion moved a refusal rather than removing one.** `sku=""` was not
  the "deleted product" case `resolve_supply` had a branch for, so `/bom`,
  `/structure` and `/quote` answered a **raw 400** carrying a pydantic sentence —
  uncoded, untranslated, worse than the 422 it replaced. Found independently by two
  reviewers. My test stopped one call short of it.
- **The evaluator conversion let the alphabet decide a safety limit.** Two published
  maxima that tie resolved by `object_id`, so 1200 vs 2400 built *2000 mm bays* or
  *1200 mm bays* depending on what the rows were named — exceeding a stated maximum.
  A contradiction is not a gap: §3.2.4 says do not fail over a gap, and §1.2.1 says a
  publish-time `disputed` is not a resolution-time `Conflict`. Not blocking was right;
  picking the looser number was not. It resolves to the most restrictive contender now
  and files `Gap(disputed, on="value")`, so the people who can fix it hear about it.
- **The fallback did not stay in its lane** — the audit's own weakest claim. It was
  consumed by every check that judges against a maximum, so a 2400 mm manufactured
  panel drew an **error** saying it exceeded "the 1800 mm maximum span". A
  manufactured width is authored data and the fallback is not; the fallback yields.
- **`Gap` was emit-only.** It could not parse a published gap: `SourceRef` had been
  redefined against the contract's `{id, belongs_to}` — reintroducing the exact defect
  its BINDING clause closes, under the contract's own type name — and `disputed` had
  lost its `on` discriminator.
- **Two mutations proved the tests did not bite.** Fallback → 5000 (five-metre bays):
  green. A fabricated `governed_by=["K-INVENTED@v1"]` on a gap node: green, because
  the assertion read out-edges and those edges point in. Both fail now, and the
  leave-one-out property test — retire each knowledge object in turn, demand a plan —
  is the executable form of the audit's central claim.

**Held up:** the thirteen-site census. No fourteenth site, no "stays" verdict
overturned, and the non-`GenerationFailure` raises reachable from `generate()`
(`MissingField`) are caught at every call site.

**Deferred, with the trigger recorded** in `plan/next-session.md` under item 5, because
both are inert until a published row can exist: the `from_published` seam must be what
the loader uses, and conflict surfacing must reach more than three of the ~13 resolution
sites. The second is pre-existing — `main` did the same — but item 1 widened its cost.

**Next:** item 2 — `SiteConditions`, `site.*` binding, `site_revision` + the 409
guard. Steps 3 and 4 still need nothing from anybody.

## The boundary contract, ratified — and the engine still unbuilt (2026-08-25)

A full design and negotiation session with the Knowledge Platform team, ending in a
**contract ratified at v1.1 by both sides**. Five review rounds: an audit against their
corpus (29 items), their review of our revision (6 defects), our audit against this
codebase (7, two in code we had published to them), our audit of our own additions (6,
every one in something we invented), and a cold re-read before signature that found
obligation 6 contradicting §1.4 — filed as amendment 001, accepted, cut as v1.1.

**What changed in this repo:** `docs/superpowers/specs/2026-08-25-engine-architecture.md`
(phases vs layers, four extension seams, the open/closed rule, and the retraction of an
entity we proposed and did not need); the engine and frontend designs rewritten against the
measured corpus; `docs/reviews/planning-self-audit-2026-08-24.md`; and
`docs/integration-contract/` — our byte-identical copy of the frozen contract, verified by
hash and governed by `AMENDING.md`.

**What did not change: `src/`.** Not one line. Two obligations are violated in code today
and we signed the contract declaring them:

- `strategy/generator.py:1521` — an uncovered `max_span` raises rather than warning, so an
  uncovered exposure category produces no plan at all.
- `knowledge/evaluator.py:107` — two published rows that tie and disagree raise rather than
  conflicting, and the exposure grows as the other team publishes more.

Both close with `Gap` as a return type, which is also the other team's delta item 1.

**Next:** `plan/next-session.md` carries the build order. Steps 1–4 need nothing from
anybody, and step 1 is the one above.

## A post and a cap are priced choices, and now explained ones (2026-08-21)

`_preferred()` ranks candidates by the company's stated `priority` instead of
`sorted(...)[0]`, and the `place_post` node carries `rejected` / `cap_rejected`
with sentences in both locale bundles. Closes the merge review's biggest open
finding and the last hole in "every BOM line traces through the decision graph".

**The handoff offered two fix directions and the code ruled one out.** Routing
post and cap through `resolve_supply` — the obvious symmetry with rails — would
move the choice to read time. But a post's sku drives GEOMETRY: `preview.py`
reads its face width for the bay's clear width and `report/structure.py` its
declared length for the setting-out sheet, so the drawing would move whenever the
yard moved. That is precisely what ADR-0011 separates. Generation keeps the
choice and was made to explain it instead; `decisions/supply.py`'s docstring now
says which mechanism covers what, having previously claimed coverage it did not
have.

**Nothing existing moved, and that was measured rather than hoped.** `_matched`
returns exactly ONE candidate on every call across every gate fixture
(`{1: 10}`), so preferred-order and alphabetical give the same answer everywhere
today — which is why the gate stayed byte-identical. Both behaviours were shown
failing against mutants first.

**Knowingly left:** when two lines claim one post and their stated orders
CONFLICT the tie breaks alphabetically, and the node does not say that it did. A
`preference_tied` flag would let the sentence admit it. "First claim wins" was
rejected deliberately — it would make which cap gets bought depend on the walk
order, i.e. on the shape of the drawing.

## DesignRun / SupplyRun: one id was answering two questions (2026-08-20)

`docs/superpowers/plans/2026-08-20-design-run-supply-run.md`, eight tasks,
ADR-0011. 1608 pytest · 193 scenario · 200/200 smoke · compatibility gate
byte-identical, which is the evidence that this was an identity change and not a
costing one.

The demonstration, before and after, on a 6 m fence with three posts arriving in
the yard between two reads: 31 700 then 24 200 agorot, `GET /runs/{id}`
byte-identical both times — and now the two BOMs carry different names
(`sup_500f83e5d2f2`, `sup_537b210c0813`), each naming the yard it was priced
against. Before, the `inventory_hash` that explained the difference was computed
on every read and written only to the audit log, entering no identity, no stored
document and no quote.

**Two things the spec had wrong, and the second one is the whole reason Task 5
exists.** `objective_preset` was in the design digest TWICE — by name, and inside
`policy`, which `DEFAULT_POLICY` always populates — so removing the named one
alone would have left the id unmoved and the change inert while looking done.
And once the preset leaves the digest it FREEZES: an unchanged fence regenerates
to the same id, `save_run` is INSERT OR IGNORE, so the stored document is the
first one for ever and its preset with it. Confirmed empirically before the fix —
after regenerating under `honour_priority` the stored run still said
`least_cost`. Six read paths took the preset off that field; they now take it
from the project's live policy. The spec also claimed the digest bump
invalidates the property `test_regenerating_the_same_drawing_keeps_the_conversation`
defends, which it does not: that test generates twice against ONE digest version,
and digest stability is a property within a version.

**The name changed on the way in.** The spec said `MaterialRun`, but `material`
is already a catalog product attribute (vinyl, steel, cedar) that a part's spec
declares as a CONSTRAINT on an item — `item.material == "vinyl"` — and that the
UI renders in a surface called the material drawer. The half this entity names is
the half below the demand boundary, which the codebase already calls supply:
`resolve_supply()`, `ResolvedSupplyLine`, `SupplyDecision`. Hence `SupplyRun`,
`supply_id`, `SUPPLY_BEHAVIOR_VERSION`.

**An existing test caught a real defect the plan had not anticipated.**
`INSERT OR IGNORE` skips the second write, but `get_bom` echoed its own
freshly-stamped object, so two /bom reads of an unchanged fence differed by
`created_at` — breaking `test_editing_a_model_cannot_move_a_stored_runs_bom`,
whose whole job is proving a stored run cannot be repriced, for a reason with
nothing to do with pricing. `save_supply_run` now returns the STORED row, so a
response always equals persistence.

Knowingly not done, in `plan/open-work.md` item 5: the frontend does not yet SHOW
the supply id (`supply` is an additive key no JS reads), no retention policy, the
impact preview still compares designs, and the quote's staleness refusal could
now cite its supply run but would need a new code in both locale bundles.

## The merge review: three reviewers, two blocking defects, one blocking hole (2026-08-20)

Before merging the 40-commit branch: an architecture critic, a test reviewer and
a frontend-contract reviewer over `origin/main...HEAD` plus the uncommitted tree.
Verdicts SOUND-WITH-FIXES, GAPS, and 2 BLOCKS-MERGE. Everything blocking is
fixed; what was left is written up in `plan/open-work.md` with its evidence.

**The two user-visible defects were both mine, and both invisible for the same
reason: every test rendered in millimetres.** `fmt()` is the mm -> display
converter and nothing else, and the grouped BOM and the assembly sheet put every
quantity through it — so the moment a reader switched the app to cm, "8 each"
became **0.8 each** and a step read "fit ×0.3 rails", while the priced table on
the same screen said 8. The second half is worse than the arithmetic: when a
unit genuinely IS `mm` the number must convert AND the label must be swapped for
the reader's, or a converted figure sits under a literal "mm". `bomHtml` has
carried exactly this guard for months; the grouped view copied its number and
not its guard. Both are now one `qtyCells()` with the rule stated once, and five
new node tests render the same payload in BOTH units — the dimension the whole
suite was blind to.

**The blocking test hole: the join everything was renamed for reached no test.**
`decision_id` was made content-derived so the grouped BOM's group, the graph node
`/explain` prints, the section route and a comment's `decision_ref` would all be
one name. But NO fixture in the suite produced a supply decision that reached the
API — the demo models name one product per slot, so `select_supply` never fired
past the wire. Two mutations proved it with 1570 green: deleting the section
route's `with_supply_decisions` enrichment, and renaming the id prefix `s` ->
`sup`. Worse, the test that claimed to defend the join computed its expectation
with `decision_id` itself — it proved `bom_groups` calls that function and
nothing about the graph, which is why the rename survived. There is now one API
test that builds a genuinely deciding fence through the product's own routes (two
catalog products, a published model with two-member eligibilities) and compares
two strings from two different routes; it kills both mutations, and the unit test
now compares against the built graph rather than against the function under test.

**A gate's own section never heard about the gate.** The `gate_event` fact
carried no `run_id`, so `decisions_for_section` could not reach it: a reader saw
two reinforced posts appear at 3000 and 4000 with no stated cause, and the
`gate_event` templates written for that panel were unreachable from it. One line,
plus S17 assertions. The same round found the Hebrew sentence for an END node
read «שבו נפגשים 1 קטעים» — "1 sections meet" — where the common case is one
section stopping; the bundles' existing `_one` convention now covers it.

**And the smaller ones, fixed rather than filed**: `sentence()` (escape the
template, then drop each param in bidi-isolated) existed twice and was about to
be written a third time, so it moved to `units.js` — four call sites that were
interpolating Latin skus and run ids into Hebrew prose and escaping afterwards
now isolate them; the unresolved bucket printed an untranslated `rail` in a cell
that forces ltr; the grouped BOM's product-name cell had lost the `dir="auto"`
the priced table gives the same field; the AI-port fitness test compared two
COUNTS, so a decoy `class StubSomethingElse:` satisfied it — it now checks
protocol conformance per port; and S17's doc caught up with two expectations its
tests had been asserting silently.

**One correction to a reviewer.** The frontend review reported the grouped BOM
rendering "600 mm" for an mm-unit line in cm mode. The bug is real and is fixed,
but no demo product is measured in mm — real units are `application`, `cut` and
`each` — so that reproduction came from a synthetic fixture, not from anything a
user sees today. It is a guard against a shape the catalog permits, not a
shipped defect.

1581 pytest · 193 scenario tests · compatibility gate byte-identical · 200/200
browser checks.

## The seven findings the review left open, closed (2026-08-20)

The 2026-08-20 test review left seven findings open when the session ran out of
room. All seven are closed: **1570 pytest** (+6) and **200 browser checks** (+1,
two rewritten). Every new assertion was shown failing against a mutant first —
including the three browser ones, which cost two full suite runs and were worth
both.

**The two that were testing nothing.** Decision-group ORDER was unobservable:
every fixture that decided anything decided exactly ONE thing, and a one-element
list comes back the same under every comparator — including one keyed on
`chosen`, which is the outcome-derived ordering `bom_groups.py` argues against at
length. The fixture now decides two things that disagree in direction (the rail
takes the LATER sku, the infill the earlier), so a `chosen` key is visibly wrong,
and a second test splits one decision in two so the key's third component
(`sorted(requirement_ids)`) is reachable at all — a stable sort's tie is not an
order, it is whatever the caller happened to pass. `unplaced` had its FIELDS
pinned and not its order, so a `set` rebuild or a tidy-looking `sorted()` was
invisible; it is the panel's own slot order (frame, infill, fixings) because that
is the order a fitter works in.

**The one that was served by nobody.** `grouped.unresolved` was rendered in the
node harness and asserted at no API level, so deleting the fifth argument at
`api/app.py:391` left the suite green while a section missing a part read as
complete. The new route test provokes the gap through the product's own editors —
a catalog product whose stock is shorter than the piece, and a default component
aimed at it — rather than by forcing state.

**The tag lookup, which was the riskiest branch in the module and covered
nowhere.** `groupedBomHtml` resolves three different kinds of id three different
ways (a section's key is a RUN id, a node's names the POST standing there, a
bay's is already an element id). `structure-data.js` had never been loaded in the
node harness, so `tagOf`/`sectionOf` answered null and EVERY group took the
unknown-element fallback. The harness now drives the real tag source over a
structure report, and each branch is asserted by equality against the tag that
element actually has.

**And the browser check that was satisfied by the failure it existed to
prevent.** It asked that a group head "does not look like a raw id" — which
printing `A` on every row of the table satisfies, one name for four bays, the
exact confusion a single tag source exists to prevent. It now re-derives the
mapping from `/api/runs/{id}/structure` the way `structure-data.js` does and
compares per element; the mutant that tags everything `A` fails it and failed
nothing else in the suite, which is the measure of how much the old one was
worth. This also covers the one thing the node harness cannot: its structure
fixture is a hand-written literal, so a backend field rename would leave it green
— the browser check reads the real route.

**Nothing at any level had read a NUMBER out of the grouped table in a browser.**
The checks counted rows and cells, so a renderer printing the CUT LENGTH in the
quantity column passed all of them; it now does not (the mutant reports bays
totalling 5000 against a section's 2500). The property asserted is the one the
view is built on: a bay is a strict subset of its section, so per sku the bays
can never total more, and a bay-only part must total exactly the same in both —
which is what breaks when a `GroupedLine` is shared between two lists and merged
in place.

**One check now asserts the mechanism instead of a word.** "The instructions are
the author's own words" was a single Hebrew word copied out of M-VINYL — which
would equally have matched that sentence rendered under the wrong step, and
would have broken the day an author reworded it. It now reads the model's own
`text_i18n` off the API and requires every authored sentence to appear and the
English of a Hebrew UI not to, which is the actual claim and the one a
`text_i18n[locale] ?? .en` fallback silently breaks.

**Left in the working tree, not committed.** The three browser checks live in
`tools/ui_smoke.py`, which another agent also has uncommitted work in — including
a check that is currently RED because it is unfinished, and the `check(detail=)`
signature these three depend on. Committing the file would land their in-flight
work under this message and a failing check with it; that mistake already has an
archaeology note further down this file. The hunks stay in the tree until their
branch lands.

## The test review, and the bug it found under a heading (2026-08-20)
test-reviewer over the grouped BOM and the assembly steps, 45 mutants, 22 alive.
Verdict GAPS and it was right: the invariants each view is NAMED for were held,
and the numbers those views print were pinned nowhere.

**Three real defects, not test gaps.** `error.model_changed` — a refusal added
that same day — was in neither locale bundle and in no code list, so a user
hitting it got "the action failed (400)". It was invisible to the guard twice
over: `report/` was not among the scanned files, and the code was passed
POSITIONALLY where the guard greps for `code="..."`. `StepPart.sku` was copied
from a field documented "resolved by fulfillment, never here", so it was empty on
every step of every plan — a column that always fell back and a value no test
could pin. And the Panel tab's instruction sheet was headed **"Assembly view —
pick a bay above"** on a tab with no bay list, because two keys were added to
each bundle that the Assembly TAB already owned: `json.load` keeps the LAST
value, so the tab's copy won. Every test in that file reads the bundles through
`json`, which resolves a duplicate silently — the new guard reads the text.

**One correction back to the reviewer.** It reported a shipped double-report, an
unpegged line counted as `unassigned` AND `from_stock`. Not shipped: with a BOM
computed from the same requirements there is no `from_stock` row. My TEST built
the impossible pair — a requirement the BOM had never seen — and then asserted
too weakly to notice what it had manufactured.

**And the standard, missed by me and caught here.** The merge key gained
`length_basis` in the architecture-review round *with no failing test behind it*;
so did the peg de-duplication in the same commit. Both have one now. Nothing
anywhere asserted a single concrete quantity of a group, so one lost
`model_copy` — the same line object appended to a section list and a bay list,
then merged in place — corrupted the first bay into the section's totals with the
whole suite green. `PanelPreview.assembly` could be blanked without a red test,
the feature vanishing from the payload and the tab.

Two vacuous fixtures replaced (a "variant slot" test with no variant, running on
a model `validate_model` rejects; `assert "b" in e`, free because every message
begins "assembly step") and one browser check that asserted the ABSENCE of a
warning, so it passed against the feature deleted.

1564 pytest · 191 scenario tests · 198/199 smoke · gate byte-identical.

## The BOM answers the question an estimator asks (2026-08-19)
`plan/open-work.md` item 4. `Bom.lines` are flat and sorted by sku, which is the
right shape for placing an order and the wrong one for every question asked
before it: what does THIS section need, what is in THIS panel, and which choice
put that product on the list. `report/bom_groups.py` groups the same demand three
ways, recomputing nothing — every number is an `engineering_qty` `resolve_supply`
already settled, re-grouped by the pegs the line already carries.

**It carries no money, and that is the design.** A BOM line is a PURCHASE pooled
per sku across the run — one 3000 mm bar is cut for two bays — so a per-section
price is an apportionment nothing measured, arriving with the authority of a
priced table. The missing concept is not arithmetic: it is a named, versioned
apportionment POLICY, which is an objective in ADR-0007's sense and belongs in an
ADR. An estimator quoting a two-phase job genuinely needs it, and it is now the
most valuable single thing left on the list.

A post shared at a node is named rather than given to a side, and the route
groups by `run_ref` so `/bom` needs no topology and does not inherit
`/structure`'s 409 when the drawing moves on.

## The two review rounds, and what they cost me (2026-08-20)
architecture-critic and test-reviewer over the three slices, per CLAUDE.md. Both
verdicts were SOUND-WITH-FIXES / GAPS and both were worth their cost.

**The finding worth being embarrassed by**: `bom_groups` named a decision group
`role:slot:chosen` — the outcome-derived id `decisions/supply.py` spends a
docstring refusing, and which I had fixed there the same day. One decision, two
names, and the one in the money view changed when the yard restocked.

Three more that would have bitten: an unresolved line was carried by the API and
rendered by nothing, so a section missing a part read as complete — the failure
the BOM tab records having had once already; the grouped panel read the tag
source without awaiting it, the only consumer that neither awaited nor
subscribed; and the merge key had silently diverged from the schedule's while
claiming to be the same one, dropping `length_basis` so slope-cut and width-cut
rails merged.

Twelve mutations survived across the two slices before this round and die now.
Two whole render functions had no test at all, including one I had written an
hour earlier.

**Architecture fitness tests** landed in the same pass (audit §5, "the right
answer to the whole class of drift"). Nine structural assertions — layering, no
AI in deterministic modules, and the backend doc's route and table inventories
counted rather than claimed. They found real drift on their first run and not
mine: the part-library arc had added a table and two routes without touching the
doc. Two of my own rules were wrong first, and both times the TEST was measuring
the wrong thing: importing `ai.records` for a data shape is not reaching for an
AI port, and the doc counts method+path pairs rather than unique paths.

1553 pytest · 191 scenario tests · 198/199 smoke · gate byte-identical.

## A panel can say how it goes together (2026-08-19)
`plan/open-work.md` item 2, roadmap Admin 3 — the one item with **no foundation
at all**: nothing on `FenceModel` carried prose, an ordering, or a step.

The line the plan drew is the one the schema draws. *"An instruction that is only
text is a doc, while an instruction that names slots and an order is data the
assembly film could already drive."* So a step names the slots it fits, and the
consequences follow from that alone: the film can order itself by it, a panel's
parts can be split by it, and a slot no step places is a gap something can
report. An `assembly` step must name parts; an `installation` step need not —
"leave the footings to cure" places nothing and is exactly the second half of
that roadmap line, which is why `kind` exists rather than one flat list.

**The governing property** is the same shape as `Σ(parts) ≡ BOM`: every member of
the panel is placed by exactly one step, or reported as `unplaced`. A sheet that
quietly omits the fixings reads as a finished panel to the person holding it,
which is worse than no sheet at all.

Four calls worth keeping. A model with no steps gets `None` and not an empty
plan, because "says nothing about its order" and "takes no steps" are different
facts and the film needs the difference to know whether to fall back. A step may
name a slot only a VARIANT has — a variant's panel is still this model's panel —
and a bay without it skips rather than inventing a part. Two steps may not fit
one slot: a contradiction, not an ordering. And `text_i18n` follows `name_i18n`,
not the locale bundles: it is expert prose, so it falls back across the languages
the author actually wrote.

M-VINYL carries real instructions because it is the line where order IS the
assembly — nothing is screwed, so a board dropped in before its top rail is a
board that cannot be dropped in at all.

**Not done, and stated rather than implied:** the assembly film still orders
itself by its role heuristic. For every model in the demo the authored order and
the heuristic agree, so rewiring it today would add a second ordering path to a
well-tested feature for no observable difference. The plan is exposed on the
preview, which is what that rewiring needs; a model whose order genuinely
disagrees is what should motivate it.

1530 pytest · 198/199 smoke · gate unmoved.

## A section answers why, and you can argue with it (2026-08-19)
`plan/open-work.md` item 3, roadmap step 5. Two halves, and neither existed.

**Section-scoped decisions.** `/explain/{element}` answers "why is this post
here"; nothing answered "what was decided about this stretch", because a section
is a TOPOLOGY object and the graph indexes by strategy element.
`report/section_decisions.py` renders each node with the same `explain_node` the
element trail uses — a view that returned node kinds and let the client phrase
them would be a second explanation. It is a summary in causal order, not a
deeper trail: one node once, no `←` ancestors, because repeating a rule firing
under every bay it governed buries the sequence it exists to show.

**Commenting was a write with no read.** The inspector posted a `Correction` and
alerted; nothing in the app could ever show it again. `Store.list_corrections`
had exactly one caller, the knowledge proposer. Trying to READ a conversation
found two defects immediately: nothing stamped `created_at`, so a turn had no
place in time, and the list ordered by `id` — `corr_<uuid4 hex>`, a shuffle.
`Correction.decision_ref` is finally populated by something; it had been on the
learning model since it was written with no code setting or reading it.

**The anchor is the part the review changed.** A decision node id is POSITIONAL —
`d0007` is the seventh node emitted, and one new gate event renumbers everything
after it. So `?decision_ref=` without a run mixes comments about different
decisions, and my own golden test was making that call while the route's
docstring warned against it: 422 now, unrepresentable rather than documented.
And after the drawing moves, a comment cannot be matched to a decision in the new
run — offering to "start a conversation" on one two people already had is a false
statement about the record, so the panel counts and names them at the level where
the statement is true. Both halves are pinned: an unchanged drawing regenerates
to the SAME run and keeps its thread; a moved one does not claim the old
comments, which are still kept, because evidence is never destroyed.

**The attribution was quietly incomplete.** A run-level node was found by
descending to its run's `run_geometry` fact — but the builder materialises
evidence BEFORE the node citing it, so nothing emitted earlier could ever be
attributed, and the `topology_node` facts that decided the surface under a
section's own end posts belonged to no section at all. The generator now says
`run_id` outright on the four run-level nodes and the closure walk is gone. Two
exclusions became deliberate and tested: a knowledge object is the SOURCE a
decision cites, and `resolve_demand_products` is one project-wide choice that
would read as several. The guard for the first checked `kind` where the value is
an `action` — dead code, found by the test written to pin it.

**The reviews were worth their cost.** Six mutations survived the suite
(`governed_by`/`defeated`, `units`, the ordinal sort, the run filter, panel
thread keying, direction isolation) and now die; the boundary test compared the
RUN, which would still pass if commenting had quietly run the proposer, and now
compares the knowledge base; and S17 pinned nothing numeric, so it was a slower
copy of the unit tests rather than a release gate. It now pins three 2000 mm
bays, four posts and the layout sentence verbatim, and joins the spine by
asserting the setting-out sheet and the decision trail name the same elements.

Two CLAUDE.md violations in the new module, both real: it read another module's
DOM (`#run-select`, owned by `inspector.js`) and worked only because `app.js`
registers that module first, and it painted after two awaits with no in-flight
guard. Fixed at the source — inspector now SAYS the selection through `state.js`.

1507 pytest · 191 scenario tests · 193/194 smoke · gate byte-identical.

Deferred, both wider than this slice: `select_supply` node ids are positional
over an inventory-dependent sort (`decisions/supply.py`), and the proposer drops
a comment's decision provenance (`ai/stub.py`).

## Note for archaeology: it happened again, two agents, one tree (2026-08-19)
`987e17b` ("test(smoke): the Models tab's slot pane is used, not just opened") is
Task 5 of the part-picker plan and it also carries the **hermetic-profile fix** —
`--user-data-dir`, the `shutil` import, the `rmtree` in `finally` — which belongs
to the diagnosis below and was sitting uncommitted in the shared tree when that
commit staged the file. My own `6004a29`, whose message describes that fix in
full, therefore contains only the 15 lines left over: the readiness wait. Neither
commit is wrong about the CODE; both are wrong about which one holds what.

And in the other direction: `8895c62` carries `docs/architecture/05-frontend.md`'s
"The slot inspector names a part" section, which was the OTHER agent's work,
finished and unstaged, swept in by a `git add docs/`. Its message said the doc
"already describes" that section, which was false — the commit is what added it.
Amended to say so.

Nothing is lost and nothing in the tree is wrong. This is the third time (see the
2026-08-16 note): staging by directory is the same mistake as `git add -A` when
another agent shares the filesystem. `git add <exact paths I edited>`, and read
`git status` before every commit rather than after.

## The browser gate was never flaky — it was not hermetic (2026-08-19)
Closing the part-picker arc meant running the suite, and it came back with 33 red
checks starting at the strategy summary and ending at *"Hebrew RTL is the
default"*. That exact shape had appeared on 2026-08-17, been re-run green, and
been written into `plan/open-work.md` as **flakiness under load**. That diagnosis
was wrong, and the tell was in the evidence at the time: the failing SET was
near-identical across both runs. Load does not fail the same 33 checks twice.

The screenshot settled it in one look — the app was in **English**. Chrome was
launched with no `--user-data-dir`, so it could attach to the developer's own
profile, and `localStorage` for this origin therefore SURVIVED the run.
`fenceai.locale` and `fenceai.units` are persisted preferences (`i18n.js:32`,
`units.js:162`) and this suite ends by toggling to English: the next run opened in
English with every Hebrew assertion red, or in cm with every mm one red. It went
green whenever Chrome fell back to a throwaway profile because the real one was
locked by a running browser — which is the whole of the "under load" story.

The profile is now a temp dir beside the temp DB, dropped in the same `finally`
and for the same reason. Start-up waits for the CDP endpoint and the app to ANSWER
instead of sleeping a fixed three seconds: a fresh profile initialises slower than
a warm one, so the hermetic fix first surfaced as a connection-refused traceback,
and a fixed sleep is what made start-up fragile to begin with.

Proved rather than assumed: the run before the fix ended in English — precisely
the state that produces the 33 failures — and the run after it passed 187/187.

**The lesson worth keeping is about the diagnosis, not the flag.** "Re-run and
see" turned a real defect into a note about the weather, and the note then told
the next reader to do the same thing. A gate whose answer depends on the
developer's browser profile is not a gate, and an identical failure set across two
runs is never flakiness.

## A post is chosen by where it stands (2026-08-18)
Prompted by the user, twice: the canvas was still *"extremely unintuitive and not
comfortable"*, and then *"but what about poles, upper and lower bars, rails,
caps?"* — the question that broke the redesign open. Researched the trade rather
than guessing, and the domain answered three things the schema did not.

**The blocking gap: a post predicate could not see which post it is.** A vinyl
post is routed at the factory and WHICH FACES are cut depends on where it stands
— end (one face), line (two opposite), corner (two adjacent). Manufacturers say
it outright: you must know the layout before ordering. `post_panel_facts` handed
a predicate four facts and position was not among them, so M-VINYL named ONE post
sku for a whole run and every end and corner post was ordered wrong.

The omission was principled but over-broad. It protects a real cycle — a bay's
opening is measured TO the post faces, so a post chosen BY that opening chooses
itself — but a post's KIND comes from the TOPOLOGY, not from the panel, and is
settled before any of it. `post.kind` is now readable
(`POST_PREDICATE_POST_FACTS`, beside the panel set the cycle rule still bounds);
the catalog carries six routed posts (two heights x three positions) keyed on a
`routed_faces` attribute no code knows the name of; M-VINYL maps position to
routing AS DATA in its predicate, kept a separate conjunct so
`sole_excluding_term` can still name which term excluded everybody.

Two calls worth keeping. `gate` takes the single-face post rather than a blank
one: a blank post has no `routed_at_mm`, so the routing conjunct would fail and
every gate on a vinyl run would become a generation failure. `junction` is
deliberately unmapped — three runs meeting needs a three-face post this line does
not make, so it refuses by name rather than standing a two-face post where three
panels land. S16 moved 119 900 -> 119 300 (two terminus posts skip 300c of
routing each); only `vinyl.json` moved in the compatibility gate.

**The parts with no editor at all.** `model.post` and `model.post.cap` were
reachable only through the raw JSON box — and because the panel spans the clear
opening BETWEEN the posts, the two parts with no controls were also the two
literally off the drawing. The elevation now carries them: `x_mm` is NEGATIVE on
the start side, because the post occupies the millimetres before the opening, and
a renderer that clamped it to zero would draw the post over the first board. The
box grows to hold them at ONE scale, so a bay does not resize the moment its
posts appear. They are clickable, and the pane says "chosen by a rule rather than
a list" for a predicate-driven post — or offers to specify one for a model that
says nothing about its posts.

**The inspector: eighteen controls to six.** Describing one board took eighteen,
and the first asked the author to invent an identifier. The trade specifies a
panel with about six; Figma lays out a row of things with four and folds "spread
them out" into `gap: Auto` rather than a matrix. So the `key` field is gone
(elements are auto-named; renaming is a double-click on the chip and still
carries `base_ref`/`top_ref`); `justification` x `excess` collapses into one
Even/Exactly segment with all EIGHT pairs still reachable and a pair no segment
matches saying so; blank-and-zero fields became visible DERIVED readouts with
their reason, which display without ever authoring; and role, cut-to, option
axis, face offset, thickness and the refs sit behind one Advanced disclosure that
badges how many non-default values it holds.

**What the research corrected.** Vinyl picket and semi-privacy DO have gaps —
fixed by where the rail was routed, so derived and read-only rather than absent.
Pre-routed posts are a property of the product LINE, not of vinyl; bracket
systems are common, with a different fit tolerance. The bottom rail's steel
insert is height-conditional. And wood is less free than assumed: board width is
a discrete sku, rail count follows height (2 under 5ft, 3 at 5-7ft, 4 at 8ft).

**Three things found and deliberately not built.**
* **Chain link has no panel object.** Its authored unit is a STRETCH between
  terminal posts, and its BOM is driven by terminal count and hook-ups, not by
  sections. Forcing it into the panel editor would be a larger modelling error
  than the vinyl gap field that started this.
* **A rail cannot carry its companion part.** `FrameSlot` has exactly one
  `requirement`, and a real vinyl bottom rail is the rail PLUS the galvanised
  channel inside it.
* **ISPSC 305.2 couples two rules we model independently.** Rails 45 in apart
  allow a 4 in gap; rails CLOSER than that require 1.75 in. We hold
  `max_clear_gap_mm` and `min_rail_separation_mm` (= 1143 = 45 in) as separate
  refusals, so a compliant pool fence with close rails and tight pickets is
  refused. The error direction is safe; the fix is a knowledge pack under the
  golden-scenarios procedure.

**Four defects the browser found that green suites did not.** Two were patches
of mine landing in the wrong function after an agent rewrote around them — one
put `rename = onRename` inside the AXIS editor, which threw on every model open
while `tests/web` stayed green. Renaming an element dropped the selection (the
first click of a double-click toggles the chip off, so a conditional restore
never fired). And the app seeds the catalog only into an EMPTY database, so a
catalog change never reaches an existing `fenceai.db` — which is why the first
browser check showed no posts at all.

One method note, because it cost time: "assert a laid-out rectangle" catches an
element that was never rendered (the 0x0 basis diagram), but it CANNOT tell a
deferred control from a shown one — Chrome still reports a box for
`content-visibility: hidden`, verified against a control `<details>` built on the
same page. Deferral is asserted structurally instead: the control sits inside the
disclosure, and the disclosure starts shut.

1248 pytest · 180/180 smoke · scenarios updated through the golden-scenarios
procedure, docs moved with the numbers.

## The Models tab is a canvas (2026-08-17)
Spec `docs/superpowers/specs/2026-08-17-panel-canvas-design.md`. The user's complaint, in
their words: *"the whole creating and editing fence panels is really unintuitive
and unnecessarily complex and nerdish."* W4 was not wrong — it was scoped, on the
record, as an expert tool, and it delivered exactly that. What it delivered was
the codebase's internal vocabulary as the only way to say what an expert means:
`basis`, `justification`, `placement.kind`, a `gap_after_mm` whose NEGATIVE value
is what board-on-board IS, and a raw `Expr` AST in a textarea.

**The drawing is now the editor.** Click a rail, a board or a fastener on the
panel and its properties render as sentences in a side inspector; drag a handle
and the authored number moves. The drawing is still entirely the server's —
`renderElevation` paints what `report/elevation.py` placed, and the new
`panel-canvas.js` lays handles over it through a shared `elevationLayout`,
because two copies of a scale is a handle three pixels from the board it moves.

**What a drag writes is pure, and tested in node** (`panel-canvas-geom.js`,
beside `base-top.js`'s precedent). Two rules there are load-bearing and invisible
in a screenshot. A WIDTH is read absolutely and a GAP as a DELTA: `excess=space`
spends the leftover on the gaps, so the drawn gap is not the authored one and
reading it back would make the first pixel of every drag jump by the spread. And
a drag cannot author what the publish gate refuses — `validate_model` bounds the
member's net advance, so the handle stops where the gate would. A `distributed`
slot has no per-member position at all, only two insets, so its interior rails
get NO handle and the inspector says why in a sentence.

**Three decisions taken against the spec, and why.**

*Fasteners are derived on the server.* The spec wanted clickable dots and
promised no backend change; `report/elevation.py` deliberately emitted no fixing
geometry ("screws are counted, not drawn"). Both could not hold. `PanelElevation`
now carries fastener PLACES with a count on each, and the slot's whole `qty` is
apportioned across them — so `sum(place.qty) == slot.qty` by construction, for
every basis and every `qty_per_basis` including the ones that do not divide. A
dot count worked out in JS would eventually say twelve beside a BOM line buying
eight, on the one surface built so an author can see what `per_member_crossing`
means. `ResolvedSlot.basis` carries the rule; a run stored before it draws
nothing rather than a guess.

*Five structures, not five product families.* The spec named privacy
tongue-and-groove, picket, semi-privacy dogear, horizontal slat and ranch rail.
T&G and dogear are board PROFILES — this model does not express them and this
catalog does not supply them, and a starter naming a SKU that does not exist
previews as a gap and is then refused at the publish gate. The gallery ships
vertical slat, picket, board-on-board, horizontal boards and ranch rail, each a
structure over products that exist, each judged in the suite by `validate_model`
AND a real preview with nothing unsupplied. Every card is a real drawing of the
panel it opens, priced through the same route the editor prices with.

*Id, name, grade, the variant picker and the option axes stay a settings strip.*
None of them is a thing you can click on a drawing.

**The vocabularies stayed typed; only the phrasing became data.** Each value now
carries a second, sentence-length locale key beside its label
(`model.basis.sentence.per_member_crossing`), correctable without a release,
while which basis kinds exist at all is still a code change with tests. Both
halves are computed keys, invisible to parity scanning, so the guard shipped with
them. `gap_after_mm`'s sign is gone from the surface — a checkbox and a positive
amount — and no `min` reaches the amount, because the bound that is real is the
net advance and a `min="0"` there deletes two product families.

**Four new modules, and the reason for each split.** `panel-model.js` holds the
vocabulary and the document shapes, because three surfaces read them and
importing them from the editor would make a cycle. `panel-canvas-geom.js` and
`condition-sentence.js` are pure and node-tested. `panel-inspector.js` and
`panel-canvas.js` build detached DOM and report through callbacks — the contract
`renderElevation` already had, and what keeps two modules under `#tab-models`
from being two owners of it.

**The two reviews then found the thing the green suite could not**
(`docs/reviews/panel-canvas-review-response.md`). The fastener invariant was held
by FUDGING: `_fixings` apportioned a slot's whole `qty` across whatever places
the geometry yielded, so `sum == qty` was true by definition of the
apportionment and said nothing about the drawing. Where it bit is
`per_member_crossing`, which `resolve.py` counts arithmetically (members × frame
members) while a drawing can only mark crossings that exist — a panel with
vertical stiles beside vertical slats is counted for 80 and has 42, and the
apportionment put a plausible "×2" on the real ones to absorb 38 that are
nowhere. The apportionment is gone: `qty_per_basis` rides on the slot so a place
holds a DECIDED count, and whatever has no place is REPORTED
(`fixings_unplaced`, surfaced in the inspector) rather than folded in. The
invariant is now `places + unplaced == qty`, by construction.

`PLANNING_BEHAVIOR_VERSION` is `planning-v2`: `Span.panel` is persisted and the
digest is inputs-only, so without the bump an existing project regenerates to
the same run id, `INSERT OR IGNORE` keeps the document that predates the fields,
and its bays draw no fasteners for ever with nothing a user can do about it.

Five tests passed with the behaviour they name deleted — each verified by
mutation, and each now fails: a `writeSentence` that ignored the author's
comparison, two subset-checked vocabularies, three of four placement arms free
to mutate their argument, the drag's floors asserted as constants copied out of
the JS rather than through `validate_model`, and three starters with no
distinguishing number (ranch rail could ship with two rails). `panel-canvas.js`
had no test at all; `valueFor` is pure, so it is exported and node-tested — and
writing that test caught a fixture error of my own within the hour.

Plus nine smaller frontend defects the reviews named: duplicate element keys
reachable from the add buttons, a rail rename orphaning the boards that name it,
the inspector offering `between_frame` on a frame slot, a predicate-driven
eligibility rendering as "no products" beside a button that would author the one
combination the loader refuses, a drag that lost its pointerup freezing the
canvas for the session, and a readout showing the pointer rather than the number
being written.

1222 pytest · 178/178 smoke · scenarios unchanged.

## W3 is finished — the routed vinyl case (2026-08-17)
The three pieces `plan/open-work.md` §1 named, in order, plus the preview gap the
last of them made closable.

**The panel facts reach post matching, and the refusal is deleted in the same
commit** (`288a1d7`). Height at the post's own station, the vertical mode the bay
will be built to, the model id, and the rail positions those settle — no width of
either kind, which is the cycle rule. `rail_positions_mm` is `placement_positions`'
answer over the horizontal frame slots and never a second derivation, and the
count it places is the KNOWLEDGE-resolved one: `_segment_view` is now the single
construction of a model's knowledge view, so a bay and the post beside it cannot
resolve different numbers.

The cap gained what it had always been allowed to ask for — the post it caps.
`test_a_cap_predicate_may_read_the_post_it_caps` had passed *validation* while
`_model_post_skus` matched caps against an empty context, so such a cap matched
nothing and came back None with nobody told.

**One new refusal, where two features meet.** A variant conditioned on the bay's
WIDTH cannot be evaluated at a post's station — a post stands between two bays
that need not be the same width — so a model with one AND a post matched on
`rail_positions_mm` would hand the DEFAULT spec's rails to the predicate. Refused
at authoring; neither feature alone is.

**M-VINYL and S16** (`edeb0d0`). The line that cannot be described without its
post: its rails go THROUGH the post, into holes punched at the factory. Two
routed posts sit in the demo catalog and only the fence's own height separates
them, which is what makes the post an answer rather than a lookup. It buys no
screws at all — a board held in a channel top and bottom is not fixed — and its
60 mm residual goes to the two EDGES rather than into eight 7 mm slots between
boards, which would not be a privacy fence.

Two defects found by building it. `_skus_used` did not record `Post.cap_sku`:
knowledge's `post_cap` rides in `demand_skus` and a MODEL's cap does not, so a run
buying a cap recorded nothing that would make repricing it refuse the stored
answer. And a post's and a cap's predicate are now checked against the namespaces
the generator actually supplies — an unsupplied namespace does not error at
generation, it matches nothing and falls through to the company default.

**Boundary posts intersect** (`0c3472c`). Both models' post specs apply to the one
post between them and the candidate set is their INTERSECTION — not an
arbitration. The three codes spec §8 designed are built, and which term did the
excluding is answered STRUCTURALLY (`match.sole_excluding_term`: drop one conjunct
at a time; if exactly one drop admits somebody, that conjunct is the sole cause).
No code anywhere knows what a routing attribute is called.

**And the preview measures its own model's post** (`e033f01`), which is the gap
this file recorded as closing "in W3, when the model owns its post". The caller
now says only the height and the bay width, and the preview reaches the same
opening, slats and cut lengths as the run.

Mutation-verified twelve ways across the four commits; every mutation kills
exactly the test that claims the behaviour.

1152 pytest · 175 scenario tests · 170/170 smoke · gate byte-identical (one file
ADDED, `vinyl.json`). The browser suite caught two things pytest could not: the
model tool's picker list, which is asserted EXACTLY because a published model it
does not offer is unreachable, and — in the check written for this arc — that the
routed panel fits nine slats across the opening its own post leaves rather than
ten across the centre-to-centre width.

## Note for archaeology: two concurrent agents, one working tree (2026-08-16)
`11d3c99` ("feat(strategy): a model's post and cap reach the fence") also carries
`animate.js`, `assembly.js`, `style.css`, `index.html` and both locale bundles —
the assembly-film slice, swept in by a `git add -A` while a concurrent agent was
mid-edit in the SAME working tree. Nothing was lost and nothing is wrong in the
tree; the message is simply narrower than the diff, and the film's own commit
(`9527509`) carries its browser suite and its reasoning.

The cause is worth writing down because it is not obvious: subagents share the
filesystem, so one agent's `git checkout -b` moves the OTHER agent's branch, and
one agent's `git add -A` stages the other's in-progress files. Two rules for next
time — give each agent its own worktree, or let exactly one agent touch git; and
never `git add -A` while another agent is running, stage by path.

## The panel's layer identity is positional (found by the film, unfixed)
`elevation.js` gives `.elev-member` a `data-order`, but the `.elev-edges` and
`.elev-seats` layers carry nothing tying a shape back to its member — the
correspondence holds only because all three loops walk the same `elevationRects`
array in the same order. Any change to one loop silently mis-pairs outlines and
housed ends with the wrong slat. `assembly.js` defends itself by checking the
layer lengths agree before trusting the reading, and leaves a layer un-animated
rather than fading an outline off the wrong member. The real fix is a `data-order`
on those rects, for whoever is next in that file.

## W3 — a model owns its post and cap (2026-08-16)
Spec §W3, and the §5 reversal the user chose: post selection leaves run-wide
knowledge for any model that declares a `PostSlot`. A model described the panel
BETWEEN two posts and said nothing about the posts, which is right for a company
with one post standard and wrong for a product line — a routed vinyl post is
specific to the panel that seats into it.

**The cap nests inside the post** because a cap exists BECAUSE a post does, and
its predicate reads the post it caps — answerable only because the post is chosen
first. Every relation in this design is one-directional for that reason.

**The cycle rule** (`POST_PREDICATE_PANEL_FACTS`) is why the resolution order is a
DAG: a bay's clear opening is measured TO its posts' faces, so a post chosen BY
that opening would be choosing itself.

    height -> rail positions -> post -> clear width -> infill fit

**Posts are sampled at their OWN station**, not gathered from the bays either
side. A post stands at one place and `fence_model_at` answers for that place with
the half-open convention every other station question uses — so the answer cannot
depend on which neighbouring bay resolved first, and the generator needed no
two-pass restructure.

**Precedence sits BELOW the three situational posts** — forced sku, masonry mount,
gate reinforcement. Those describe a post doing a different JOB, and a line with
no variant for them would otherwise silently replace a post chosen for its
situation.

**And the honest half.** W3a designed the post predicate to read height-derived
panel facts; W3b then resolved posts before any bay exists, so those facts are not
in the matching context. A predicate reading one would match nothing and fall
silently through to the company default — a model quietly not getting the post it
asked for. Refused BY NAME at authoring with the reason and the workaround, the
same rule `_UNSUPPORTED` applies to every designed-not-built field. The constant
stays as the statement of what will be readable when the generator supplies it.

Mutation-verified four ways: cycle rule disabled, post validation skipped, model
post ignored, model cap ignored — each kills tests. One vacuous test avoided
rather than shipped (the cap test named POST-CAP, which is also the company
default, so it passed whether or not the model was consulted).

**Remaining in W3:** supplying the bay facts to post matching, the routed-vinyl
demo model and its golden scenario, and boundary-post intersection across two
models.

1090 pytest · 159/159 smoke · gate byte-identical.

## Typed catalog capabilities, and a migration that says what it did (2026-08-16)
Audit finding §4.2, with its hazard taken head-on. Three facts were read out of the
open `attrs` bag by deterministic code: the post length the length check measures
against, the post face the clear opening is measured to, and the opening a gate
kit fits. `attrs.get("length_mm")` compiles whether or not anything sets it, a typo
is a silent `None`, and by the time it matters the number is on a cut list.

`Product.capabilities` is a typed record of exactly those three. Deliberately flat
rather than a union of capability KINDS: three facts is not a taxonomy, and a union
whose variants each hold one integer is machinery around nothing.

**The rule, drawn precisely.** Data read by CODE is typed; data read by a
PREDICATE or the UI stays in the open bag — material, finish and colour are the
catalog's answer, not the code's. `_item_ctx` merges capabilities INTO the item
namespace so a predicate asks "how wide is its face" without caring where the
catalog keeps the answer; an undeclared capability is OMITTED rather than passed as
None, so it raises `MissingField` and correctly fails to cover a requirement.

**The migration is deliberate and legible.** `catalog_hash` is computed over
`model_dump()`, so adding a field changes every product's hash and every
previously generated run refuses. That refusal is correct — but `catalog_changed`
is the wrong sentence for it: nothing was repriced, the schema moved, and a reader
told the catalog changed goes hunting an edit that never happened. Runs now stamp
`catalog_schema_version`, and a mismatch raises `catalog_schema_changed` with both
versions and its own line in each locale bundle.

**What the browser suite caught, for the fourth time this arc:** two JS readers
still fetching the migrated keys out of `attrs` — the gate picker's declared
opening and the macro view's post faces. Both silently fell back to a nominal, and
1079 passing unit tests saw nothing.

1079 pytest (+6) · 156 golden scenarios · 159/159 smoke · compatibility gate
byte-identical (it carries no catalog hash).

## One line, one lifecycle state (2026-08-16) — W2b, option A
Audit finding §1.7. `RequirementLine` was both states at once: demand emitted it
with `sku=""` and `unit=""`, and `resolve_supply` filled them in by MUTATING the
same object. So the type claimed a product through the whole half of its life
where it had none, and "a blank sku never reaches `fulfill()`" rested on caller
discipline — which `fulfill()`'s own refusal records having been broken at all
three routes by a three-word edit that produced zero test failures.

`DemandLine` (no sku, no unit) and `ResolvedSupplyLine` (both required, non-empty,
set together by `of()` because the unit is a property of the CHOSEN product).
`fulfill()`'s runtime check is gone, and its absence is the point: there is no
longer a value to hand it that it would have to refuse. `ResolvedSupplyLine` lives
in its own `fulfillment/lines.py` for the same reason `fencemodel/selection.py`
exists — `supply.py` needs `fulfill.engineering_unit_for` to build one and
`fulfill.py` consumes one, so the type cannot live in either.

**Option A, chosen deliberately: one path.** A product knowledge already chose —
a post, a cap, concrete, a gate kit — now arrives as a ONE-MEMBER eligibility
instead of an authored `sku`. That deletes the second branch in `resolve_supply`,
the branch that had to re-implement the feasibility gate and did not until a saved
run could be made permanently unreadable through the UI alone.

**One behaviour preserved on purpose.** A lone candidate naming a product the
catalog does not have still resolves, so `fulfill()` gives it its defined answer —
a zero-priced, flagged line — which is how a post pointing at a DELETED product
still shows up on the BOM instead of vanishing into a warnings panel. Narrow by
design: with rivals an unknown sku stays filtered out, because `_candidate_cost`
cannot price what does not exist and a candidate costing nothing would beat every
one that does.

**The gate was regenerated, and the regeneration was proved first.** Before
writing a single file: BOM sections byte-identical in all ten fixtures, the same
set of line ids everywhere, and exactly one field differing per line —
`eligibility`. Line ORDER also changed, and `resolve_supply` now sorts its output
back into demand order, because grouping is an internal optimisation and must not
reorder the answer. The old order was itself an artifact: authored lines were
emitted in a first pass, so gate kits appeared BEFORE panel slots although demand
asks for them last.

**What the browser suite caught that pytest could not**, again: the Panel tab's
parts table read rail/screw/slat and now reads rail/slat/screw — frame, infill,
fixings, the panel's own structure. A user-visible ordering change out of a
backend refactor, invisible to 1073 passing unit tests.

1073 pytest (+6) · 156 golden scenarios · 159/159 smoke · gate regenerated with a
verified diff.

## A part can declare what it needs (2026-08-16) — W2a of the part-specs arc
Spec §W2, first half. `Eligibility.predicate` had been on the schema since phase 1
and refused at load for two stated reasons — nothing evaluated it, nothing froze
it. `fencemodel/match.py` closes both, and the `_UNSUPPORTED` entry is deleted in
the same change that makes it work, which is what that table's own comment asks
for.

**The matcher sits ABOVE the mechanism that already exists.** It produces
`EligibleItem`s — the shape a slot has always carried and a run has always frozen
— so `resolve_supply`, `select_supply`, `fulfill()`, the parts ledger, the drawer
and the decision graph are untouched, and freezing is free. Members come back
sorted by SKU at the default priority and approval, because `resolve_supply`
groups on that signature and grouping decides which product is chosen.

**A `MissingField` is a NO, not a "not applicable".** The knowledge evaluator
reads it the other way because there the question is whether a rule fires; here it
is whether an item COVERS a requirement, and an item that cannot answer has not.

**`item` is what a product IS**, not merely its attrs: `sku` and `consumption` are
reserved keys that always win. Without `consumption` a rail slot is inexpressible
— "bought by the length" is a typed field, and every author would otherwise have
to hand-tag their bar stock. `Product.attrs` widened to hold `list[int]` /
`list[str]`, because a routed post's hole heights are `[150, 1650]` and no scalar
holds that. The bound: data read by CODE should be typed (a magic string key in
Python is the defect the audit named); data read by a PREDICATE is data reading
data, and belongs in the open bag.

**Authoring keeps its guardrail and gains a better sentence.** A predicate no
catalog item covers is refused at authoring — the same rule an empty member list
already got, for the same reason. A predicate that reads `panel.*` is NOT checked
there, because the bay does not exist yet and refusing it for failing a question
nobody asked would be worse than the gap; `field_paths()` (new, in
`knowledge/ast.py`) is how the two are told apart. A slot carrying BOTH a
predicate and members is refused: intersecting the two lists has more than one
defensible reading.

Wired at both call sites — generation and the panel preview — and the mutation
that makes `match_spec` a no-op kills tests in both. The preview one was the only
cover for that path; without it the Panel tab would have shown an empty, free
panel for a model that builds perfectly well.

1064 pytest (+16) · 156 golden scenarios · 159/159 smoke · compatibility gate
byte-identical (every shipped model still authors its members, and a spec with no
predicate is returned as-is rather than deep-copied).

**Still open in W2:** the `DemandLine`/`ResolvedSupplyLine` split, typed catalog
capabilities for the keys Python reads (`length_mm`, `face_width_mm`,
`opening_width_mm`), and engine behaviour versions.

## The clear opening becomes real (2026-08-16) — W1 of the part-specs arc
Spec `docs/superpowers/specs/2026-08-16-part-specs-and-fence-system-design.md` §W1.
`PanelContext.clear_width_mm` had been `= width` since phase 1 behind the comment
"face widths arrive in phase 2", so `clear_between_posts` and `centre_to_centre`
returned the SAME number and `resolve.py`'s infill axis was the centre-to-centre
width. Every slat panel was fitted across an opening that includes half a post at
each end: the demo's 1500 mm bay spread its eleven gaps to 27–28 mm to absorb
80 mm of post, where the model asks for 20 mm — the outer slats overlapped the
posts they were supposed to sit between.

**The blocker was ordering, not arithmetic.** Interior line posts were created
AFTER the bays they bound (two sibling loops inside the segment loop), so at
`resolve_panel` time the posts at a bay's ends did not exist. The two loops are
swapped; the mutant that hides line posts dies with `1460` — one end narrowed and
the other not — which is what pins the swap.

**One calculation for one fact.** `clear_opening_mm(centre, face_start, face_end)`
in `fencemodel/resolve.py` is the single rounding point: the two halves are summed
and divided ONCE, so a pair of odd faces cannot lose a millimetre twice. `Span`
records the result, because the panel preview and the read models re-read a stored
run and must fit to the number the bay was built to — `bay_preview_plan` carries
the face allowance over rather than re-measuring, and a what-if on the width keeps
it, since imagining a wider bay does not change which posts bound it. A product
declaring no `face_width_mm` contributes 0, never a nominal. `Span.clear_width_mm`
is `None` for runs generated before this, which read at centre-to-centre — the
fence that exists, not the one today's generator would build.

**The gate did not move**, against the spec's own prediction. Twelve slats fit at
1500 and at 1420, so no purchased quantity changed; only where the slats sit. The
change is capable of moving it — at 1700 mm the member count does change, which is
how the panel-preview tests caught the drift — the committed widths just do not sit
near a boundary. One gate assertion was over-specific (it required the fixture's
residual to be non-zero, a property of the width rather than of the feature) and
now asserts what the fixture is for: the fitted count is a number the golden file
watches.

**Known gap, deliberately not closed here:** the model-scoped preview (Panel tab)
still fits at the width it is given, because a model with no project has no posts
to measure. It closes in W3, when the model owns its post.

1048 pytest (+4) · 156 golden scenarios · 159/159 smoke · gate byte-identical.

Updated: 2026-08-16 — the two-tier visualizer is in: an Assembly tab with two
synchronized viewports (the run standing up, and one panel assembled), a material
and inventory drawer on every part, a live what-if that never generates, joints
that change the cut list and are drawn in section, and prices in ₪. Five tags,
`v0.6.0-nis` through `v0.9.0-joint-drawing`. Still open from the panel arc:
`excess=trim_last`/`extension_clip`, `InfillSpec.supply=assembly`, and phase 3
arc-flow.

- [x] Research (4 parallel researcher reports, synthesis, ADRs 0001–0010)
- [x] Architecture (docs/architecture/*, golden scenarios S01–S14 defined)
- [x] Slice 0: spike + review cycle (docs/reviews/spike-review-response.md)
- [x] Slices 1–8: core domain — all S01–S14 scenarios passing
- [x] Slice 9: SQLite store + FastAPI API
- [x] Slice 10: SVG topology editor + strategy overlay UI (headless-Chrome verified)
- [x] Slice 11: hardening, V1 docs, fresh-clone verification
- [x] Final review pass: architecture-critic SOUND-WITH-FIXES + test-reviewer GAPS —
      every finding fixed (docs/reviews/final-review-response.md); 153 tests passing

V1 completion definition (docs/input/plan.md §20): satisfied — integrated app runs,
golden scenarios pass, strategy generation + decision provenance + material semantics
+ BOM + cutting/packages/remnants + annotations/interpretations + correction/candidate
workflow all work, architecture docs match implementation, automated tests pass, fresh
developer can run from docs/v1-runbook.md.

Next (V2 candidates): see docs/v1-known-limitations.md triggers — persisted BOM
snapshots, cross-project impact preview, CP-SAT escalation, substitution netting,
Claude proposer/critic adapters, Tier-2 explanation polish, multi-tenant Postgres.

## UI v2 (2026-08-10) — COMPLETE
Spec docs/superpowers/specs/2026-08-10-ui-v2-design.md; plan .../plans/2026-08-10-ui-v2.md.
Delivered by 4 worktree agents + integrator: module scaffold; backend i18n (warning
codes+params, he/en explanation templates, Hebrew stub interpretation, bilingual names);
editor (undo/redo, select/draw grammar, snapping, typed lengths, canvas event popovers
incl. height tool); profile side view (ground/wall editing, synced selection); Hebrew-first
RTL (153-key parity, Noto Sans Hebrew, logical-properties CSS, localized dynamic content).
Verified: 174 pytest + 14/14 tools/ui_smoke.py checks + inspected screenshots.

## Rule impact preview (2026-08-10) — COMPLETE
"This change would affect N of your projects" before approving/saving knowledge —
Research D's highest-value review feature. learning/impact.py (pure regenerate-and-diff),
2 API endpoints, UI in review queue + knowledge editor (he/en). 202 pytest + 21/21 smoke.

## Canvas zoom/pan/fit (2026-08-10) — COMPLETE
Wheel zoom anchored at cursor (0.25x-6x), middle/Ctrl-drag pan (screen-space math),
fit-view button, world-aligned grid re-rendered per view (5 m spacing when zoomed out).
202 pytest + 24/24 smoke.

## Persisted quotes (2026-08-10) — COMPLETE
Immutable BOM snapshots with lifecycle (draft/accepted/superseded, atomic supersede),
quotes panel in the BOM tab (he/en), impact preview reports vs-accepted-quote deltas.
Smoke hardened: aborts if a stale server holds the port. 208 pytest + 26/26 smoke.

## Base top-line editing UI (2026-08-10) — COMPLETE
Side-view editing for the base_top event (backend efc49e7): filled band whose top edge
follows the point profile (vertical jumps at steps, concrete/wall tones), draggable
diamond dots (10 mm z snap; horizontal drag moves pos_permille, snapping onto a
neighbour makes a STEP), dbl-click edge inserts an interpolated point, dbl-click the
dashed hint line gives a bare built base a top line, dot popover types/deletes points,
band popover edits first/last and converts legacy wall_profile into a 2-point base_top.
Inspector lists base_top with a localized point count. 8 he/en keys added.
217 pytest + 26/26 smoke + 28/28 dedicated CDP drive (step -> K-STEP-POST transition
post verified in plan AND profile) + inspected screenshots.

## UI ease-of-use round (2026-08-10) — COMPLETE (#2-#4 of research menu; #1 auto-compute rejected by user)
Type-while-drawing exact lengths (SketchUp mechanic, unit-tolerant, angle-snap on
direction only); gate catalog picker (components excluded); seeded sample project +
getting-started checklist + empty-canvas CTA + labeled toolbar; zero prompt()/JSON
UIs left: inline quote/reject/scope/run forms, sentence-style knowledge rule builder
with Advanced-JSON toggle, inventory table editor. 220 pytest + 27/27 smoke,
272-key he/en parity. Research report menu retained for next rounds (#5-#10:
adaptive UI, wizard spine, dimension pad, spatial warnings, segment table, aerial).

## Persona-lab run 2 batch A: frontend + fulfillment (2026-08-11) — COMPLETE
**One resolver decides which run a pointer means** (`geom.runAtPoint`): hover used array
order, clicks used SVG paint order, and `.run-hit`'s round cap put a 178 mm disc over the
neighbouring leg — the status bar said one station and the click recorded another, so a
climb was authored on the wrong leg and priced level, and the first leg's last 200 mm were
unreachable. Linecap is butt; the strategy overlay can no longer swallow a click. A ground
click at a run end writes the shared node's z, so two legs cannot contradict each other
about one corner. `.run-label` opens the length editor only for the select tool; popover
fields select on focus (`1000` had been reaching the DB as `10000`); the height popover
spans the whole run; the gate picker reads `attrs.opening_width_mm` instead of parsing a SKU.
**Cut plans are certified honestly**: added a counting lower bound, so `lower_bound =
max(lp, counting)` and a provably optimal plan is no longer called "heuristic" — and no
solver vocabulary reaches a BOM line (two S07 assertions had encoded the defect; the doc
never promised the certificate, so the code was wrong). **The rule editor no longer traps
you** — the escape hatch was gated on parsing the broken JSON. Impact failures, api.js
alerts and the inventory back-label now honour `code + params`; projected remnants render.
Documented rather than papered over: package overage is never projected, and inventory has
no warehouse scope, so offcuts cannot reach the next job.
382 pytest + 50/50 smoke.

Note for archaeology: commit `0c100a6` ("bind rule scope") also carries `cutplan.py`,
`test_cutplan.py` and `test_locale_bundles.py` changes from a concurrent agent, swept in by
a `git add -A`. Nothing was lost; the message is just narrower than the diff.

## Persona-lab run 2 backend fixes: B1/B2/B3 (2026-08-11) — COMPLETE
Four defects, TDD, one commit each. **Rule scope now binds** — `bind_scope()` derives
dimensions generically from generation facts (`project_id` run-wide; `surface`/`context`
at the post-level slots), so restricted approvals and stub-proposed candidates can fire and
specificity finally breaks ties; the impact preview binds each case's project. **A gate kit
must fit its opening** — fit is catalog DATA (`Product.attrs["opening_width_mm"]`, like
`length_mm` on posts), never parsed from a SKU: mismatch → `gate_kit_width_mismatch`, no
`kit_sku` → selected from the catalog by declared width, nothing fits → `no_gate_kit` and no
BOM line. **Gate-kit provenance is the gate event**, not K-GATE-REINF (which governs only the
post upgrade); `governed_by` = "this rule decided this value" is now written down.
**The stub proposer reads יסוד as well as "foundation"**, and promotion drops the
"(candidate)" marker in every language.
Refused as hardcoding: nothing — the two blocked dimensions (`series`, soil type) need a
topology-model field, and gate-kit width needed a catalog attribute, which is data, not code.
382 pytest + 49/49 smoke.

## Persona lab RUN 2 (2026-08-11) — COMPLETE, supersedes run 1
Run 1's study was wrong: personas came from market research, not the architecture, so the
central user (the expert correcting proposals, foundation §9) was never simulated and S11–S14
went untested. Run 2 uses five roles from the architecture, each doing a real job twice, with
the status bar visible, a `move` verb, 60 actions (look free), no checklists, no quit framing,
and taxonomy assigned by the refuter instead of the persona.
Report: `docs/reviews/persona-lab-run2-2026-08-11.md`. 31 confirmed / 13 refuted / 3 positives.
**Works, verified:** immutable accepted quotes + supersede; impact preview across the portfolio;
cut plans and typed lengths. `fulfillment` finished both jobs (site 2 in six actions).
**Severity-4 blockers:** gate kit ignores opening width (`generator.py:431` — a 3500 mm gate
priced as GATE-KIT-1000, accepted against a customer, and the decision graph attributes the SKU
to a rule); rule `scope` accepted then dropped (`ctx["scope"] = {}` at generator.py 131/182/406/941
— restricted approval and every stub-proposed candidate are no-ops); the expert loop is inert
end-to-end (obstacle/foundation payloads exist but nothing authors them — S12 ⇄ code disagreement;
`ai/stub.py:116` matches the English "foundation" only; `AddNote` has no consumers); status-bar
station vs click hit-test disagree on an L (`.run-hit` round cap ≈178 mm disc at the corner) so a
6 m climb is priced level. Cheapest real fix: `editor.js:541` needs `.select()` (3 personas,
`1000` → `10000` reaches the DB).
Eight harness defects found and fixed across both runs; one known-unfixed (native `<select>`
needs keyboard driving). 346 pytest + 44/44 smoke.

## Persona lab (2026-08-11) — RUN 1, SUPERSEDED (study design was wrong)
`tools/persona_lab/` — six real-role personas (5 he + 1 en control, from Israeli fence-trade
research) drive the live app over CDP perceiving only rendered UI (visible labels, opaque
handles, no ids/API/DB/repo). Independent refuters reproduce every finding and assign severity.
First run: **0 of 6 completed their job**; 64 raw findings → 51 confirmed, 13 refuted.
Report: `docs/reviews/persona-lab-2026-08-11.md`.
Top blocker: `editor.js:541` focuses popover number fields without `.select()`, so typed digits
prefix the prefilled value (1000+3500 → 35001000) and a bad `z_mm=-4000` persists unvalidated —
hit by 5 of 6 personas. Then: no export, € hardcoded, no customer-facing price, no metre unit.
The run also found 5 defects in the harness itself (all fixed, `5d08262` + `b720a2f`, regression
-tested) which had manufactured 13 false findings — including a fake "app froze, data lost".
302 pytest + 44/44 smoke.

## Display-unit toggle: mm / cm (2026-08-11) — COMPLETE
User-selectable display unit in the header (persisted per browser, Hebrew מ"מ / ס"מ).
New `js/units.js` is the only converter: `toDisplayValue`/`toMm` at every field boundary,
`tu()`/`unitParams()` render `{…_mm} {u}` locale strings (backend warning params convert
by name). Covers canvas labels + cursor readout + typed lengths (a bare number ≥100 now
reads in the active unit), every popover field, the side-view z editors/tooltips/ticks,
inspector events + overrides, BOM cut plans/allocations/engineering demand, inventory
lengths, and `*_mm` rule-builder fields. Storage stays int mm everywhere (ADR-0002
addendum); raw-JSON editors and server-rendered decision prose deliberately stay mm.
244 pytest (incl. node-run round-trip tests for units.js + two bundle guards) +
34/34 smoke (210 cm → 2100 mm verified end-to-end) + screenshot inspected.

## Explanations follow language AND unit; enum words localized (2026-08-11) — COMPLETE
`/api/runs/{id}/explain/{element}` gained a `units` param beside `lang`; explain.py renders
`*_mm` values in the reader's unit with a `{u}` token (same two rules as units.js). Enum
VALUES (post kind, mounting, base surface, vertical mode, post orientation) now render as
words in both the prose (`_ENUM_WORDS`) and the UI (`enum.*` bundle keys + units.enumWord),
so Hebrew no longer carries raw "line"/"soil"/"perpendicular" — this also fixes the
tilted_stepped warning's raw-enum param. inspect() takes key+params and replays the last
inspection on language/unit change. Tests pin: cm rendering without float noise, Hebrew
enum prose, every domain Literal has a Hebrew word, the two lexicons agree, `?units=inch`
is a 422, and reading never mutates the graph. 251 pytest + 37/37 smoke (decision trail
verified in cm with Hebrew enums; screenshot 09).

## Units review round (2026-08-11) — COMPLETE
architecture-critic + test-reviewer on the units work. Three real defects fixed: blank
popover length fields wrote `null` into topology payloads (422 + a zero-length interval at
station 0); the rule builder stored a cm value as mm when the param name was typed into the
free-text box (10x, in persisted rule data); `{u}` rendered literally in the known-params
dropdown. Also removed the cm-mode "bare number < 100 = metres" trap (90 → 90 m) with a
per-unit draw hint. Tests hardened: sub-mm rounding, field steps, both param directions,
the stateful half of units.js (stubbed localStorage/DOM), gershayim-proof unit-literal
guard, inverted call-site guard, and a source guard for the dynamic warning renderer.
Smoke: blank-field refusal, real reload, converted BOM numbers, raw-JSON-stays-mm,
post-generation placeholder sweep, and a freehand `*_mm` rule param driven in cm mode
(mutation-verified: fails against the pre-fix code). The typed-length parser moved from
editor.js into units.js as `parseTypedLength(buf, unit)`, so its unit-dependent boundary
matrix is pinned in node as well as through a canvas keystroke check — both layers
mutation-verified. 260 pytest + 44/44 smoke. Dispositions:
docs/reviews/units-review-response.md.

## Side view: scope switch + base-top actions (2026-08-11) — COMPLETE
User feedback: aligning two sections' bases, changing a base height at all, making one
horizontal and creating steps were all hard, and the whole fence competed for one strip.
The side view now has a SCOPE switch (whole fence | one section, remembered) with a section
picker that keeps the plan selection in step; a focused section fills a taller panel, so the
drag targets are far bigger. New `js/base-top.js` holds the geometry as pure transforms —
`flatPoints` (a height above ground), `levelPoints` (ONE absolute elevation, with a point at
every ground break, since z is stored above local ground), `matchEnds` (meet the neighbour's
top at a shared node), `withStep` (a plateau: everything past the step rises with it) — plus
`topZAt`, moved out of profile.js. A base bar drives them by number instead of by aim, and
says plainly when a section is on soil (base_top only affects BUILT_BASES). 395 pytest
(13 new node-run geometry tests) + 58/58 smoke, incl. two adjacent sections aligned
end-to-end. Level is exact to NUMERIC_TOLERANCE_MM — permille point positions quantize it.

## Base-top segment rules + neighbour elevation (2026-08-11) — COMPLETE
Follow-up to the side-view round. A step is now what the word means on site: a VERTICAL
riser followed by a HORIZONTAL tread. Both are `lock` values on the new
`BaseTopPoint.lock` field (level|step|null, an authoring constraint on the segment that
starts at that point) — `enforceLocks` re-imposes them after every edit (drag, typed z,
height, level, match, step), propagating outward from the point the user actually moved.
Clicking any segment of the top line opens a rule popover (אופקי / אנכי / חופשי); locked
segments render distinctly. "Horizontal" now locks every segment, and a corner match that
would contradict a standing horizontal rule is REFUSED with a note pointing at the new
"≡ גובה השכן" action, which levels the whole section at the neighbour's elevation (the
second reading of "align two sections", per user confirmation). 401 pytest (6 new lock
tests) + 62/62 smoke, incl. lock persistence through the API and the refusal path.

## Map panning, side-view scale, fence-on-base, strategy summary (2026-08-11) — COMPLETE
Four pieces of user feedback. (1) The plan canvas pans by dragging empty space with the
primary button (any tool; grab/grabbing cursors), alongside the existing middle- and
Ctrl-drag; a press that never moves is still a click, so nothing edits by accident.
(2) The side view gained an elevation scale — "nice" 1/2/5 tick steps, labels in the
display unit, and the axis names its unit AND the vertical exaggeration that distorts it.
(3) REAL MODEL FIX: posts on a built base were recorded at ground level while the panels
already rested on the base top, so the post-length check measured through the wall and
charged embedment on top. New `Post.base_z_mm` (the elevation a post stands on; None =
ground) — the check measures exposure from it and only `ground`-mounted posts pay
embedment. The profile draws posts from base_z to the adjacent panel tops. (4) A strategy
summary above the warnings: counts, fence length, span width range, height, panel mode,
post SKUs, note count, a link to the priced BOM and the "click anything to see why" hint.
406 pytest (5 new built-base tests) + 74/74 smoke, screenshots inspected. Follow-up: the
map's `grab` leaked onto everything drawn on it (a CSS rule on the <svg> beats the
elements' presentation attributes) — every cursor role is now spelled out: map=grab,
draw=crosshair, event tools aim (crosshair) at a run, runs=pointer, vertices=move,
ghosts=copy, generated elements=help, and an active pan forces `grabbing` over every
element under the pointer so it never flickers mid-drag.

## Structure & parts: layout and the items it consists of (2026-08-11) — COMPLETE
Researched (fence estimating vendors, contractor spacing guides, permit-drawing rules, AIA
dimensioning) and built in five tasks; spec + plan in docs/superpowers/.
`fenceai/report/structure.py` is a pure read model over a run: sections/posts/bays/gates
tagged (A, P1, B1, G1 — derived, never stored), setting out as running stations with
centre-to-centre spacings, and per-element parts obtained by INVERTING existing pegs
(element → RequirementLine → BomLine, plus cut-piece bar provenance). Its governing property
is Σ(parts) ≡ BOM, with unpegged demand reported as `unassigned`. `RequirementLine.role`
(post|cap|concrete|rail|screw|gate_kit) rides to `Part.role` so the customer sheet can
describe fixings instead of counting them — trade practice, not a guess from SKU strings.
GET /api/runs/{id}/structure serves it; the Structure tab renders both detail levels;
`js/structure-data.js` is the single tag source for the tab AND both drawings; the side view
gained a chained centre-to-centre dimension string with one overall per section and the
CLOSING bay marked; printing yields the site sheet (drawings + schedules, title block, plan
auto-framed). 424 pytest (16 new) + 88/88 smoke.

## Structure & parts review round (2026-08-11) — COMPLETE
architecture-critic + test-reviewer before calling the milestone done; both earned it.
The layout half was sound; the parts half was not. Fixed: a stored run laid out over an
EDITED topology (invented stations — now 409 + "the drawing changed"); the report being a
function of mutable inventory with nothing recording it (inventory_hash + cache
invalidation); Σ(parts) ≡ BOM holding in only one direction (fulfilment emits no line when
stock covers demand → new `from_stock` bucket); `unassigned` summing across units and
printing negatives; a shared corner post carrying TWO tags while the drawing prints one
(tags now unique per element, `A/P1`, totals count elements not rows); the dimension chain
starring a GATE opening as the tolerance-absorbing bay; a stale in-flight fetch labelling
one run's drawing with another's schedule; and a gate clamped past its section end keeping
a kit that cannot fit (new `gate_past_run_end` warning). Tests: four demonstrated mutations
(concrete on the wrong post, screws on the wrong bay, every rail claiming bar #1, a cap
labelled a post) now die; the vacuous `32 + 0 == 32` unassigned test became the real
fitted-vs-bought relationship; browser checks assert identity rather than existence.
440 pytest + 99/99 smoke. Dispositions: docs/reviews/structure-review-response.md.

## Fence models, phase 1 (2026-08-12) — COMPLETE
Spec docs/superpowers/specs/2026-08-12-fence-model-design.md (revised after adversarial
review, 7 blockers / 8 major / 9 minor dispositioned); plan
.../plans/2026-08-12-fence-model-phase1.md. The structure of a fence panel stops being two
integers on `Span`. A new pure module `fenceai/fencemodel/` owns the schema (`model.py`
with load-time `validate_model`), the 1-D pattern fit (`fit.py`), and per-span resolution
(`resolve.py`); `Span.panel` carries a `ResolvedPanel`, `derive_requirements` expands its
slots instead of reading `rail_count`/`screws_count`, and a new
`fenceai/fulfillment/supply.py` resolves each line's ELIGIBILITY to a concrete SKU before
`fulfill()` runs, so the parts ledger keeps keying on `(sku, unit)`. Choosing among eligible
items is an objective coupled to the cut plan, not a lookup — named lexicographic presets
(`least_cost`, `honour_priority`, ADR-0007), with feasibility filtered first. The run-id
digest gains the model snapshot, the catalog hash and the preset, and `/bom`, `/structure`
and `/quote` refuse a run re-read against a moved catalog (409 `catalog_changed`). All of it
lands behind a built-in `M-LEGACY`, whose acceptance gate is that every existing shape
produces identical requirement lines and an identical BOM.

## Fence models phase 1 review round (2026-08-12) — COMPLETE
architecture-critic (SOUND-WITH-FIXES) + whole-branch code review (WITH-FIXES) +
test-reviewer (GAPS), converging on the same defects; all fixed in one wave.
`fit_pattern` HUNG on a non-advancing pattern (`gap_after_mm` may be negative and nothing
bounded it) — guarded in `fit.py` per pattern cycle and rejected per member in
`validate_model`. Demand had guessed the parts-ledger unit three times and was still wrong
(an indivisible product with `attrs.length_mm` legitimately backs a length slot, and is
still bought in eaches — the same six items appeared in `unassigned` AND `from_stock`);
demand now emits no unit at all and `resolve_supply` writes sku and unit together from the
one function `fulfill()` uses. The four copy-pasted `derive → resolve → fulfill` sites
became `fulfillment/pipeline.py`, which closed the divergence that duplication had already
caused: `create_quote` loaded the catalog directly, so the one endpoint freezing an
immutable commercial document was the only one exempt from the staleness check (BOM 409,
structure 409, quote 200). `fulfill()` now REFUSES a blank sku instead of trusting its
callers. All-candidates-infeasible was a silent pick followed by an unhandled 500; it is a
`no_eligible_item` warning plus an `unresolved` line. Features validated at load and then
ignored at resolve (`variants`, `option_axes`, `layout_policy`, `height_support`,
`Eligibility.predicate`, `excess` of trim_last/extension_clip) are now REJECTED by
`validate_model` rather than blessed and dropped — a deferral must not read as a working
feature. The compatibility gate became a committed artifact (per-fixture requirement lines
+ BOM as JSON), and the fixture set gained the RAKED shape the suite entirely lacked: two
mutations that previously left the suite green (deleting the slope-length branch; ignoring
the resolved `demand_skus`) now fail. Two vacuous tests deleted/replaced. 555 pytest
(+46) · 126 golden scenarios (+18) · 101/101 smoke. Dispositions and the fix wave:
docs/reviews/fence-model-phase1-review.md.

## Fence models phase 1 — closing the open findings (2026-08-12) — COMPLETE
The four gaps `docs/reviews/fence-model-phase1-review.md` left open (two "Open", one
"worth knowing", one raised there as a suspicion) are closed on
`fix/fence-model-open-findings`; that document's new "How they were closed" section is the
record. **A saved run could be made permanently unreadable through the UI alone** — an
800 mm rail stock plus a `DefaultComponent` aimed at it, two API calls — after which /bom,
/structure and /quote all returned a raw English 400 from the cut planner and the structure
tab said *"generate a strategy to see how it is laid out"*, which is false. Not fixed by
catching the planner: `resolve_supply` skipped its feasibility gate for a ONE-member group,
so the gate now runs before the candidate count is looked at (and on the authored-sku path
too), and `fulfill()` cannot be handed a piece longer than its stock by any route.
Feasibility became a catalog+geometry predicate instead of a cut plan, so it is free at
group size one. **The gap was then computed, localized and rendered nowhere** —
`Bom.warnings`, `StructureReport.warnings`/`unresolved` were read by no JS at all, so the
200 would have been a BOM silently one line short; `js/warnings.js` now owns the single
`code + params` → sentence path and both money views render it, naming the BAY via the
structure report's tags. `no_feasible_item` splits "candidates were tried and none fits"
from `no_eligible_item`'s "nothing is a candidate". **`InfillSpec.supply` and
`Eligibility.group`** join the rejected-feature table — `group` after verifying both that
nothing reads it and that it would change the chosen SKU (grouping decides which lines are
costed together, and cut planning is not additive). **`validate_model` gained its
production caller**: `generate()` validates the resolved model, `GenerationFailure`/422 if
it fails, 2.1 us against a 0.85 ms four-bay generation, once per topology run — no caching.
That gate found a real hole on its first run (a test catalog missing the rail its panels
were eligible for). Compatibility-gate fixtures untouched.

A second review of that round found five more, all fixed. **One of the new smoke checks was
vacuous** — it read the whole structure body for `A/B1`, which the ordinary bays table
already prints, so it passed with the feature deleted; every assertion is now scoped to the
`.supply-problems` panel and the bay-naming one to the warning rows inside it (re-verified
by deletion). **The Hebrew sentence printed raw English identifiers**: a `role.*` lexicon
and a `roleWord()` beside `enumWord()` — its own namespace, because `concrete` is both a
base surface and a role — plus `{slot_key}` suppressed when it equals `{role}`. **The 422
told the user nothing and also threw**: `GenerationFailure` carries optional `code + params`
like `ReadRefused`, `fence_model_unknown_sku` names the SKU a knowledge rule got wrong,
`api.js` renders any `error.<code>`, and `btn-generate` no longer hands an async function
to `addEventListener`. **The customer sheet was getting an itemised screw count** — the
panel now follows that sheet's own describe-don't-itemise rule. **And the false "generate a
strategy" message's CLASS is closed**, not just this round's cause: an unrecognised refusal
in `structure-data.js` was mapped to "no attempt yet", and is now `"unknown"` naming its
code. 585 pytest (+30) · 126 golden scenarios (unchanged) · 107/107 smoke (+6).

**Phases 2 and 3 remain.** Phase 2: `M-SLAT`, variants, option axes, the pricing union,
the elevation read model, the panel warning codes, and multi-member eligibility selected by
running the FFD planner per candidate — plus the `select_supply` decision node, without
which a multi-member choice has no explanation (docs/v1-known-limitations.md). Phase 3:
arc-flow over multiple stock lengths and sources with remnants, via OR-Tools.

## Panel authoring W1/W2 — the model gets a UI (2026-08-12) — COMPLETE
Spec docs/superpowers/specs/2026-08-12-panel-authoring-design.md. W1 and W2's backend
landed on `feat/panel-authoring-w1` (persisted, versioned models; the `fence_model`
interval event; `POST /api/fence-models/{id}/{v}/preview`); this is the surface, which was
the whole complaint: *"I don't see an option to see the Panel spec and choose a model
before the strategy."* Every clause of it was true of the frontend — `variant` and `preset`
had **zero hits** across `web/static/`, and the only product choice anywhere in the app was
the gate kit picker, so the thing that decides every material, size and structure below it
was unreachable. Three surfaces now: a **Panel tab** between Structure and BOM (`js/panel.js`
— a model picker over the library, height and bay width in the display unit, and one
panel's parts priced from the preview endpoint, which drives the SAME `resolve_panel` →
`derive_requirements` → `resolve_supply` pipeline a real bay does, so the preview cannot
drift from the fence the user then gets); a **model row in the canvas aside**, so "what is
this fence built from" is answerable without leaving the drawing; and a **`fence_model`
event tool** on the rail, authored through the same popover as height intent. Three
decisions worth keeping: `unsupplied` and `warnings` render ABOVE the priced table, because
a panel one part short must not read as complete; `apiSend` grew a `quiet` option, because a
debounced preview firing per keystroke owed the user silence rather than a dialog each time;
and the event tool replaces any `fence_model` event overlapping the stretch it writes,
because `fence_model_at` answers with the FIRST covering event — a stale one left behind
would silently defeat the choice just made, with nothing on screen to see. 671 pytest (+7,
a node suite for the library naming rules the browser cannot reach: a draft-only or retired
model is offered NOT SELECTABLE rather than hidden) · 126 golden scenarios (unchanged) ·
116/116 smoke (+9).

**W3–W6 remain**: variants and option axes (`_unsupported_features`), authoring (edit, add,
duplicate, vary), the elevation drawing beside the slot table, and the `select_supply`
explanation.

## Panel authoring W3/W5/W6 — the model resolves, explains and is checked (2026-08-12) — COMPLETE
Four features stopped being refusals. **Variants** resolve per BAY (a condition reads the
panel's own height, and a level top over a slope gives every bay of one segment a different
one); precedence is authored order, first satisfied wins, and the node records `failed`
(evaluated, not satisfied) separately from `not_reached` (authored after the winner, never
asked) because recording the second as failures would put an unchecked claim in the graph.
No `defeated` edge — a variant is product structure evaluated outside the knowledge
evaluator — and a test asserts the absence so nobody re-adds it for symmetry.
**Option axes** NARROW a slot's eligibility to the member `sku_by_option` names, keeping its
priority and approval, so a colour cannot smuggle in a product the slot disallows.
**`height_support`** aggregates per section, not per bay. **`layout_policy`** contributions
enter the same evaluator scoped `series=<model_id>`, each at ITS OWN authority — lumping a
manufacturer's max span with a nominal width buys either an unbeatable preference or a
beatable safety limit. Two stay refused with stated reasons: `Axis.available_when` (an axis
is answered before a bay exists) and any contribution outside `SERIES_SCOPED_PARAMS`.

**`select_supply` closed the phase-2 blocker** `docs/v1-known-limitations.md` recorded.
`SupplyDecision` carries every candidate's PLANNED cost and waste (infeasible ⇒ `None`, never
zero, which would read as "free"), and `decisions/supply.py` derives the node at READ time —
selection is coupled to the cut plan and runs in fulfillment, which has no graph builder and
does not acquire one. The stored document is never rewritten; two tests pin that. The
sentence names the runner-up and the gap, because "cheaper than the others" is not an
explanation. Mutation-verified.

**Pricing by the running metre** (`LinearPrice`), the way the market quotes bar stock. A rate
AUTHORS the purchase price of a whole bar; per-m² and per-band are absent because `fulfill()`
emits one line per SKU and they need grouping per `(sku, price_basis, size)` first.
`purchase_price_cents()` is the single read and the one rounding point. A rate-priced product
may not also carry a flat price.

**The panel is drawn.** `report/elevation.py` turns a ResolvedPanel into rectangles, on the
preview and on every structure bay. Derived, never stored; computed on the server, not
mirrored in JS. `placement_positions` spreads `distributed` INCLUSIVE of both ends — two
rails is a top rail and a bottom rail — and is the one rounding point for placement. The one
undeclared number (a frame member's face height, product data the catalog lacks) is flagged
`declared=False` rather than passed off as measured.

**Panel safety**: `clear_gap_exceeded` measured against `max(gaps_mm)` — a rounded 23 would
pass a 23 mm limit while several real openings measured 24, the sphere test defeated by a
return type — plus `rail_separation_insufficient` (anti-ladder) and
`pattern_residual_large`. **The tier decides the consequence**: the same check raises
`GenerationFailure` under a `hard_constraint` and warns otherwise, so a jurisdiction pack
stops a job with no code change. The demo seeds them as `company_rule` because every number
in it is US/AU/UK. Codes are written as `code="..."` literals in a record rather than dict
keys, because the locale guard scans for that literal — found while writing it.

**`catalog_hash` narrowed** (second closed limitation): `catalog_skus` records what a run
named — chosen SKUs, every eligibility RIVAL, kit components transitively — so adding an
unrelated product no longer 409s every prior run, while repricing one it bought still does.
Safe only because eligibility is frozen into the run.

**`exact_span_mm`** implemented: a model that ships in one size tiles its section in that
size, reports the odd bay rather than absorbing it, and is still clamped by the hard maximum.

777 pytest · 126 golden scenarios unchanged · 116/116 smoke.

**Remaining:** W4's authoring UI; an SVG renderer for the elevation the backend now serves;
`excess=trim_last` (blocked on the same 2D-cutting non-goal as sheet infill) and
`extension_clip`; `InfillSpec.supply=assembly`; phase 3 arc-flow over multiple stock lengths.
## Panel authoring W4 — the model becomes editable (2026-08-12) — COMPLETE
Spec §W4. The rest of the user's question: *"what if the user wants to edit, change or add a
panel? variant?"* W1–W3 made models persisted, versioned, selectable data with a working
preview and left the **only** way to author one a hand-written JSON POST — so the structure
that decides every material, size and price below it was editable by everyone except the
expert who owns it. A **Models tab** (`js/model-editor.js`, ~1200 lines, owning nothing
outside `#tab-models`) now edits frame slots, infill patterns, fixings, eligibility, option
axes and variants as sentence-style rows over the live document, with the rule builder's
Advanced-JSON escape hatch whose exit is never gated on the JSON being valid.

Lifecycle as the spec demands it: "Edit" on a published version opens a **deep copy** whose
first save lands a draft at the next free version, so an active version — the one an
accepted quote was priced against — is never mutated; publish is the gate, and its 422
renders from `code + params` under a Hebrew heading rather than as the engine's English
authoring text; retire and duplicate sit beside them. **Impact is shown before the change**
(foundation §11): the same `renderImpactReport` the knowledge tab uses, now moved to
`js/impact.js` because a third caller is where two copies start disagreeing.

**It also closed a latent 500 that it made routine.** `Store` holds ONE
`sqlite3.Connection` opened `check_same_thread=False`, and FastAPI serves sync endpoints from
a threadpool — so overlapping requests interleaved statements on one connection. The browser
suite caught it as `GET /inventory` answering 500 while a draft was being saved; reproduced
standalone at **48 failures in ~540 overlapping requests**. The silent half is worse: half of
`Store`'s methods are read-then-write sequences, and another thread's `commit()` landing
inside one commits a transaction nobody finished. `Store` is now `@_serialized` — a
re-entrant lock around every public method, because a per-thread connection would give every
`Store(":memory:")` test its own empty database. Pinned by `tests/store/test_concurrent_access.py`,
which drives real threads and fails on the unguarded class. ADR-0008 records both the fix and
what it does NOT cover: route-level read-then-write is still a TOCTOU window.

**The review caught the design wrong first, and the wrong version was plausible.** The editor
originally debounce-saved every 250 ms, because the only preview route priced a STORED
document — from which it followed that a live preview and a save-on-demand editor could not
both exist. But the model id is a save key: typing "M-SLAT" one character at a time left
`M@v1`, `M-@v1`, `M-S@v1` … behind as permanent library rows (there is no delete route) and
landed the half-built document as a new draft version of the shipped M-SLAT, which is then
what "Edit" opens for everybody. And the constraint was never real — `preview-impact` had
taken an unsaved document in its body since W3, and `preview_panel` was always a pure function
of a `FenceModel` object. So W4 adds `POST /api/fence-models/preview` taking `{model, bay}`:
an edit re-prices and does nothing else, Save and Publish are the only writes, and the id is
refused in the field if the library already holds it. **The lesson worth keeping: when a
client design is justified by "the API only offers X", check whether X is a property of the
system or of one route signature.**

Three more decisions worth keeping.
**`gap_after_mm` has no `min`**: a negative gap is an overlap, and board-on-board and
shadowbox are exactly that; the bound belongs on the member's net advance, where
`validate_model` already puts it. **The selects offer only what the resolver honours** —
`excess` narrowed to `truncate|space`, and `Axis.kind` narrowed to `enum` with a new
`_unsupported_features` entry refusing `numeric`, since nothing reads that field and an
authoring surface is what turns a silently-ignored field into a wrong answer. And the two
catalog caches (`tabs.js` and `editor.js`) became one in `js/builder-ui.js` — they had
different failure behaviour, so one lost request left the gate picker working and every SKU
picker permanently blank. `ModelListing` gained `draft_version`/`versions` so "Edit" reopens
the draft that exists instead of guessing `active + 1`, which is wrong the moment a version
above the active one is retired.

743 pytest (+22: a node suite that builds the documents the "+ Add" buttons build and lets
pydantic and `validate_model` judge them — the discriminator on every eligibility member, a
variant's starting condition as valid `Expr`, a deep draft copy, the swatch pattern, and the
editor's vocabularies pinned against `model.py`'s in BOTH directions, and the id-collision
truth table over all four session kinds — plus four threading tests that fail on the
unguarded store) · 126 golden scenarios (unchanged) · 127/127 smoke (+11), including that
authoring writes NOTHING until asked, that an unsaved model is priced anyway, that the
published model's STORED SPEC carries the rows (an empty model publishes, so listing metadata
alone proves nothing), that the Advanced-JSON box lets go with broken JSON in it, that a
length typed in cm stores millimetres, and that a wider slat gap fits fewer slats.

**W5–W6 remain**: the `select_supply` explanation and multi-member groups, the pricing union,
the elevation drawing beside the slot table, and the phase-2/3 tail.

## Panel authoring — the two review rounds (2026-08-13) — COMPLETE
architecture-critic (SOUND-WITH-FIXES) + test-reviewer (GAPS) over the whole branch.

**Two blockers.** `project_id` was not in the run-id digest, and it is bound as a scope
dimension — so two projects with the same topology and one project-scoped rule collided,
and `INSERT OR IGNORE` dropped the second: its user pressed Generate, saw their own answer,
and every later read served the other project's fence. And the M-LEGACY seam short-circuited
before `library.resolve`, so a published v2 was offered by the picker, priced by the preview
and reported on by the impact preview, then ignored at generation — the id is now reserved
at the route.

**A live 500 no pytest test can see.** `Store` shared one sqlite3 connection across
FastAPI's threadpool with `check_same_thread=False` silencing the guard; two overlapping
fetches interleaved statements and raised `InterfaceError` out of a route. `TestClient`
serialises requests, so the browser smoke suite was the only detector — red here, green on
main. Found independently by both the test review and the W4 agent. Every store method is
serialised now, held for the WHOLE call because several read then write.

**Three wrong answers behind a green suite.** The sphere test measured only the gaps
BETWEEN members, and `center` justification folds the residual into the edge margins and
zeroes it — so two 150 mm holes stood against the posts while every measured gap read 50.
A multi-member pattern drew thirteen slats where seven were bought, running out of the
panel. An exact bay width silently lost to a `min()` against the hard maximum, producing
bays of neither width and reporting the width nobody used — now a conflict citing both.

**And one the new tests found rather than the review**: `per_gap` counted PIECES, not
positions, so a member with `qty=2` (a batten pair at one position) made a 12-position
panel order 17 spacers.

**Coverage.** The infill path was outside the invariant battery and the golden gate
entirely — dropping infill lines from `BomLine.pegs` broke the BOM→requirement→element
traceability invariant with a green suite. Two M-SLAT fixtures join both (the existing
eight gate files are byte-identical, so the compatibility claim still holds), and that
mutation now dies. Nine single-line pass-throughs in `resolve_panel` had no test at all —
`edge_margin_mm`, `justification`, `face_offset_mm`, a member's own `qty`, a VERTICAL frame
slot, `per_end_member`, `per_gap` — all pinned by one panel that uses the non-default value
of every one of them.

845 pytest · 145 golden scenarios · 127/127 smoke.

## The panel, drawn (2026-08-13) — COMPLETE
Spec §"the same slots render the elevation", and the one browser check it names that nothing
had implemented. `report/elevation.py` had computed a `PanelElevation` for every preview and
every structure bay since phase 2 and **no JS read it** — `grep -rn elevation js/` returned
ground profiles only. The headline of the wave was "see the panel" and it shipped as a table
of numbers.

`js/elevation.js` is one renderer with two callers: the Panel tab's preview and the Structure
tab's selected bay. It does not fetch (both callers already hold the rectangles; the bay's
ride along on the `structure-data.js` cache, whose in-flight guard exists precisely so one
run's drawing cannot be labelled with another's schedule) and it computes no geometry. The
ONE transform it owns is the axis flip — the panel frame puts y = 0 at the bottom of the
opening, SVG grows downward — and `tests/web/test_elevation_module.py` checks it against the
coordinates the real `panel_elevation` sends rather than a fixture that could keep passing
after the read model changed its mind.

**The gaps are dimensioned by lookup, never by measurement.** `gaps_mm[i]` is the gap after
placed member `i` and a member carries that `i` as its index, so the figure is the server's.
The wire does not say WHICH slot the fitted list belongs to (a frame slot and an infill slot
are the same shape on the elevation), so the pair has to prove it: a gap is drawn only where
two consecutive members already sit exactly the listed distance apart, and an unconfirmed
pattern gets no dimension line rather than a number invented in the client.

**Hidden edges.** A rail on a slat panel is genuinely behind the slats, so occlusion alone
left a two-rail and a three-rail panel looking identical — the one comparison the drawing
exists to make. Every member's outline is drawn over the infill (outlines only, no fill, and
no extra rectangle to count), and selecting a slot RAISES its members, because SVG has no
z-index and a highlight nobody can see is the same as no highlight.

**Nothing server-authored reaches a colour.** Fill and edge come from the stylesheet keyed by
a role from a closed set — never a sku, never a swatch. A member whose face height is the
nominal the read model invented (`declared=False`) is dashed AND said to be, in both bundles,
or the picture claims a precision the catalog does not have. The elevation joins the plan
canvas and the side view in never being mirrored in RTL, verified in Hebrew by screen
position, not by reading the stylesheet.

854 pytest (+9 node) · 145 golden scenarios (unchanged) · 137/137 smoke (+10), including that
the drawing carries one rectangle per member the priced table says is BOUGHT (screws are
counted, not drawn), that switching the model redraws it and not only the price, that
clicking a drawn slat selects its part row and a part row lights up its members, that the
dimensions follow the display unit, and that the slats run left to right in Hebrew AND in
English — a drawing that happened to be left-to-right because the page was would pass the
RTL check by accident.

**Awkward in the read model, found by drawing it.** (1) A client cannot tell an infill member
from a frame member: `PanelElevation.gaps_mm` belongs to the fitted slot and nothing on the
wire names it, which is why the gap dimension has to confirm itself geometrically. (2)
`placement_positions` spreads distributed rails inclusive of both ends and `_frame` then
clamps them inside the opening, so a two-rail panel draws its rails flush with the top and
bottom edges rather than inset — correct per the spec, and it reads oddly. (3) Fixings have
no extent, so a panel whose model is only fixings draws nothing; the renderer returns null
and the caller says so.

## The panel, drawn (2026-08-13) — COMPLETE
`js/elevation.js` renders the `PanelElevation` the backend has been serving since W2 and
nothing read. One renderer, two callers: the Panel tab above its priced table, and the
Structure tab for the selected bay through the existing `structure-data.js` cache (no
second fetch — a second fetch is exactly the stale-run bug finding A7 closed). It owns no
geometry, only the panel→SVG axis flip; duplicating the fit maths in JS is what the read
model exists to prevent.

Clicking a drawn member selects its part row and clicking a row raises its members — the
browser check the fence-model spec asked for and that had never been implemented, and the
only way to see a rail on a slat panel, since the slats are genuinely in front of it.
Nominal faces (`declared: false` — a rail's face height is product data the catalog does
not carry) draw dashed and say so. Colours key off a closed role set in CSS; no sku,
swatch or server string reaches `fill`. The SVG joins the plan canvas and the profile in
never being mirrored — asserted in Hebrew AND English by screen position, not by
stylesheet.

Two read-model awkwardnesses it found are closed: `slot_kind`/`kind` say whether a member
came from the frame or the infill (a vertical frame slot and a vertical infill slot were
the same shape on the wire, so the renderer had to confirm its gap dimension geometrically
rather than index the list it was handed), and `face_offset_mm` rides along so a shadowbox
can be drawn at its real depth rather than as two layers.

## Authoring gaps closed (2026-08-13) — COMPLETE
The four the authoring round reported rather than patched. A slot with **no eligible
product** published cleanly and then reported `no_eligible_item` on every bay of every job
built to it — refused at authoring, where the author can still say what belongs there. One
**already-broken project** 500'd the whole portfolio impact preview, at the moment a user
most needs an answer; it is now a `baseline_failed` row, not counted as affected because
the change did not break it. **Two drafts** disagreed: `listing()` reported the highest and
the save took the first. And an **abandoned draft stayed for ever** — DELETE discards one,
refused in the STORE for a published version, because an immutable document any route
could delete is not immutable.

The locale guard scanned five files for `code="x"` only, so every code a ROUTE emits was
invisible twice over. It now scans `api/app.py` and both spellings, and immediately caught
four codes shipping untranslated — including two 409s a user meets whenever they edit a
catalog or a drawing.

863 pytest · 145 golden scenarios · 137/137 smoke.

Findings log for the whole arc, with the still-open suggestions in the order I would take
them: `docs/reviews/panel-authoring-session-2026-08-13.md`. The first of them is that
prices still render in €, which the persona lab flagged in run 1 and which the market this
ships into does not use.

## W4 — the embedment reaches the drawing (2026-08-14) — COMPLETE
Wave 4 of `docs/superpowers/specs/2026-08-14-two-tier-visualizer-design.md` §2.5. A macro
elevation has to draw a post's buried portion and its footing, and nothing on the wire said
how deep a post sits: `post_embed_mm` was resolved inside `_check_post_lengths` and written
only into a conflict node's params.

`Post.embed_mm` is now written by that same function, from the same resolved value, so the
drawing and the length check cannot disagree; the conflict node reports the post's own
embedment rather than the resolved default, which on a masonry post had it explaining a sum
it never made. `Station.embed_mm` and `Station.post_length_mm` carry it to
`/api/runs/{id}/structure`, the length read from the post product's catalog `attrs.length_mm`
and `None` when the product declares none — a client then draws no embed dimension rather
than a guessed one. `build_structure` takes the catalog as a fifth GIVEN for that one read.

The coverage question the wave asked: `_check_post_lengths` walks past any post with no
adjacent bay, and one exists in practice — the node post of a run whose first bay is a gate.
Embedment is therefore recorded BEFORE that skip, so 0 stays a fact (masonry) and never
means "not known".

872 pytest · 145 golden scenarios · compatibility gate byte-identical.

## Joint geometry (2026-08-14) — W2 of `specs/2026-08-14-two-tier-visualizer-design.md`
`Member.base_ref`/`top_ref` had been on the schema since phase 1, read by nothing, and
offered as two selects by the model editor since the authoring wave — a field that reads
as honoured and is not, which is the defect `_UNSUPPORTED` exists to catch and the one it
missed. The `between_frame` length rule closes it for the case a joint needs: a member cut
to the opening between two frame members plus the engagements that disappear into them,
with the positions READ off the frame slots the same panel already resolved rather than
placed a second time. Under any other length rule the refs are now refused by name.

`FrameSlot` gains `joint`/`channel_depth_mm`/`insertion_margin_mm` and `Member` gains
`joint`/`base_engagement_mm`/`top_engagement_mm`, so a joint is data the CUT LIST depends
on before it is anything on a drawing. Seven load-time refusals, each about a number that
would otherwise be wrong on every bay and arrive looking measured — a 20 mm seat into a
12 mm channel, a channel inside a member of undeclared depth, a `channel` kind with no
depth and no engagement behind it.

`M-SLAT` gains v2: the same line with its slats seated 15 mm into a 20 mm bottom channel,
cutting 1665 mm where v1 cuts 1800 in the same 1800 mm bay. It is a DRAFT, and the seed
stopped overriding a document's status to make that possible — an active v2 would answer
every unpinned M-SLAT and move existing jobs onto a different cut list with nobody having
published anything.

Every default is zero and no shipped model declared the rule, so the compatibility gate is
byte-identical with no regeneration.

**What the adversarial pass changed, which was the important half.** The refusal set
shipped without the one check that mattered most: a cut length must be POSITIVE. Refs the
wrong way round (−1750 mm) and a knowledge param collapsing a rail set to one position
(−20 mm) both validated clean, reached `plan_cuts`, and came back
`certified_optimal=True` — a wrong number wearing an optimality certificate. Neither is
decidable when the model is authored, so the resolver refuses to answer and the generator
says so: `panel_length_unresolved`, `severity="error"`, one per (model, slot) per section.
Alone among the panel checks it is an error, because every other one describes a fence
built badly and this one describes a part not bought at all.

The elevation was drawing the OPENING and the BOM was buying the MEMBER — 1800 against
1665 on the model whose reason to exist is that 135 mm — while `report/elevation.py` opened
by claiming the picture cannot drift from the numbers. `_between_frame_extent` now returns
where the member starts as well as how long it is cut, one calculation for one fact, and
the rectangle is placed from it. Four more refusals were one relation short (the insertion
margin constrained nothing; a channel deeper than its own rail passed; `bracket`/`overlap`
were unauthorable by accident and belong in the unbuilt table; an engagement under another
length rule was still ignored), and the demo gave one SKU two different face heights — the
channel is a different profile and now has its own product.

903 pytest · 145 golden scenarios · gate unmoved.

## Joint details on the drawing (2026-08-14) — W3 of `specs/2026-08-14-two-tier-visualizer-design.md`
W2 made a joint change the cut list; a joint nothing can DRAW is still a number on a
schedule. `ElevationMember` gains `joint` and `seat_start_mm`/`seat_end_mm` — the
sub-range of the member, in the same panel coordinates as its rectangle, that is inside a
frame member rather than seen — and `PanelElevation` gains `details: list[JointDetail]`,
one per member END worth a section: the two thicknesses, the channel depth, the
engagement, the insertion margin, and whether the thicknesses are measured or nominal.

The seat is read off the same `(start, extent)` the rectangle is drawn from, never
re-derived from the frame positions. That is the rule W2's review round landed on, applied
one layer up: `_between_frame_extent` is one calculation for one fact, and a second
derivation of the extent here is exactly how a hatched band and the piece it hatches end
up a millimetre apart.

The spec's numbers reach the read model on `ResolvedSlot` rather than beside it. It
already carries geometry PARAMETERS for this reason, and the alternative — `panel_elevation`
taking a panel AND the spec it came from — is a read model with two sources that can
disagree, only one of which a stored run keeps. That is also what makes the property below
free.

`details` rides on `PanelElevation`, so the panel preview and a stored run's
`Bay.elevation` carry it by the SAME code path: no second endpoint, and no chance of the
Models tab's detail disagreeing with the bay built to that model. Asserted from both ends
(`tests/fencemodel/test_preview.py`, `tests/report/test_structure.py`).

Two things it refuses to invent: a member naming no frame slot at an end gets no detail,
and neither does a butt landing with no engagement and no channel — a section through two
rectangles touching is what the elevation already draws, so the inset would frame a fact
the panel states better. An empty section drawing is worse than none.

Two narrowings recorded in the limitations rather than half-built: one seated range where
a member can seat at both ends (`details` is per-end and states both), and the design's
`"<member_slot>@<frame_slot>"` key, which repeats when a member names one rail SET at both
ends — `end` disambiguates it.

977 pytest (+12) · 145 golden scenarios · gate byte-identical, no regeneration.

## The two-tier visualizer (2026-08-14/16) — COMPLETE
Spec `docs/superpowers/specs/2026-08-14-two-tier-visualizer-design.md`. Nine waves,
each tested, merged and tagged: `v0.6.0-nis`, `v0.6.1-post-embed`, `v0.7.0-assembly`,
`v0.8.0-joints`, `v0.9.0-joint-drawing`.

**Prices read ₪.** Five hardcoded `€${(cents/100).toFixed(2)}` sites — two of them
copies of one `money` helper — became `units.money()` reading `units.currency`, which is
what lets the bundle test forbid a bare symbol anywhere else. Thousands group and deltas
are signed. Multi-currency is deliberately NOT done: that is a `Money(amount, currency)`
type through the whole cost tier plus a rate source with an as-of date, and a symbol swap
wearing its clothes is worse than one honest currency.

**The Assembly tab: two viewports over one fence.** MACRO (`runview.js`, pure, node
tested) unrolls the structure report into an elevation — posts in their footings, the
embedded length hatched below the ground line, panels drawn as their own members and
bounded by the post faces they dock into, gates with a swing arc, risers where two bays'
bottoms disagree, and the dimension set (total run, bay widths, heights, embedment, step
rise) behind one switch. MICRO is the same `elevation.js` drawing the Panel and Structure
tabs use, for the bay the macro view has selected. Selection is shared in both directions:
a bay picked above is assembled below, and a member picked below lights up every bay that
carries it — the macro question the micro view cannot answer on its own.

`runview.js` PLACES and does not compute: every station, elevation, height, width and
embedment it emits is a field of the report, which is itself forbidden from recomputing a
quantity. It refuses three inventions and says each out loud — a post whose product
declares no `face_width_mm` is a nominal, a gate opening with no neighbouring height gets
no leaf, and above 900 drawn members panels become blocks and the panel says it simplified.

**The material & inventory drawer** joins three documents on one SKU (the slot's own
eligibility, the catalog, this project's stock) and is pure, because each join has a way
of being wrong that looks fine: offering the CATALOG rather than the eligible set, adding
remnants to whole units, or showing a rate-priced product's per-metre figure in a column
of per-unit prices.

**Real time, honestly.** Typing a height or picking a product re-runs the same preview
pipeline the Panel tab uses, at the selected bay's model and version, in 250 ms. It is
labelled a what-if with one button back, and the cost strip names BOTH figures — this
run's BOM and one panel's preview — every time, because two numbers with the same shape
and different meanings are exactly what a silently-switching live figure gets wrong.
Generation stays behind the explicit button and the smoke counts the project's runs across
a dimension change to prove it.

**Joints, at two scales.** `between_frame` honours `base_ref`/`top_ref`, so a slat seated
15 mm into a channel is CUT 15 mm longer: the picture and the price come from one extent.
The elevation hatches the housed end (the one honest thing it can say at 1:8000); the
section inset beside it draws the housing, the clearance, the seated length and the
exposed run, each dimensioned from numbers the read model already spent on the cut list.
A butt landing draws no section at all. The pattern PITCH (member + gap, the figure a slat
fence is specified by) is emitted only when constant — `spread_to_fit` absorbs its
remainder into the gaps, and one pitch over an uneven pattern is wrong by the last bay.

**Not built, deliberately**: no 3D (a different renderer with a different set of lies
available to it, and nothing in the BOM needs it); the Assembly tab is not on the print
sheet (what goes to site is a decision for whoever owns that sheet); and a drawer
selection stays preview-scoped — making one stick is authoring the model or writing an
override, both existing surfaces, neither bypassed by a dropdown.

**What the browser suite caught that pytest could not**, again, three times: a rail
painting black because the macro member carried its role class but not `elev-member`;
selecting a different bay keeping the previous bay's preview, so the cost strip quoted one
panel's price under another's tag (both numbers correct in isolation); and the joint
section rendering inside the panel's own render, so it ran once while nothing was selected
and never again — the box was present and simply empty.

906 pytest · 145 golden scenarios · 155/155 smoke · compatibility gate byte-identical
throughout the arc.

## The review pass (2026-08-16) — COMPLETE
Two adversarial reviews of the visualizer arc: `architecture-critic`
(SOUND-WITH-FIXES, 14 findings) and `test-reviewer` (GAPS, found by mutating the
implementation and watching the suite stay green). Every finding dispositioned;
all fourteen fixed.

**The blocker.** The Assembly tab priced a bay of a STORED run through the
model-scoped preview route, which hardcodes `least_cost`, hardcodes
`length_basis="width"`, reads the live catalog, and knows none of the
company-resolved quantities the bay was laid out with. Under S15 the drawer
marked RAIL-3050 as the chosen product where the run had bought RAIL-3000 and
priced the bay at 51% of what it cost — under a tag that said "as generated".
`POST /api/runs/{id}/bays/{element_id}/panel-preview` reads everything the run
decided off the run (preset, cut basis, rail and screw counts, the STAMPED model
version, and the option answers off the decision graph) and leaves only what a
person is imagining in the body. One `preview_panel`, not a second one.

**Four client-side re-derivations of numbers the server owns**, each removed:
the post top (the length check answers it, with a tilt correction the JS did not
have, and the `insufficient_post_length` warning depends on it); the per-unit
price (a second implementation of the declared single rounding point, on a money
surface); the edge margin (the fit's own figure, and `truncate` leaves the
residual BEYOND it); and the ground line (sampled at posts, so a retaining step
between two posts drew as a smooth chord).

**The graph now explains the length.** A `between_frame` slat is 1665 mm in an
1800 mm opening and no node said the number or the subtraction behind it, while
`report/elevation.py` opened by claiming the picture cannot drift from the
numbers. The `resolve_panel` payload carries each slot's length, its start and
the terms it was measured between; the span-quantity node became a real input
edge rather than a shared scope tag; and embedment got its own quantity node
with `governed_by`, so two knowledge versions of `post_embed_mm` can no longer
draw two different footings with no `defeated` edge anywhere.

**What the mutation pass found.** The drawer's alternatives — the feature's whole
reason to exist — were rendered by no test in any tier: every demo slot names one
eligible product, so `buttons == len(options) - 1` was `0 == 0`, and deleting the
offer button AND hardcoding a zero delta passed eighteen tests. Five `runview.js`
mutants survived simultaneously (footings for everything, the embed dimension
drawn UPWARD, the whole step-dimension branch, the gate branch, the vertical
extent). "One scale for both axes" was the name of two tests and the assertion of
neither. And the second direction of the shared selection — a member picked in
the panel lighting up in every bay that carries it — was checked nowhere.

**One doc/code disagreement settled rather than left.** The spec promised a stale
badge and a Generate button on the macro view during a what-if. The
implementation does neither and should not: the macro view is showing the RUN,
which a hypothetical panel height has not made wrong, and the button would either
do nothing or silently generate the old height. Spec corrected, with the reason.

954 pytest · 155 golden scenarios · 158/158 smoke · compatibility gate
byte-identical across the whole arc, including every fix above.

## Stock netting (2026-08-16) — COMPLETE
The last open finding of the review pass, and the only one where a user read a
figure and got a wrong answer: the drawer's "in stock" column read the project's
inventory alone, so a product whose every bar this run had already been allocated
still reported the shelf count — on the one surface built for "could I switch this
part to that product".

Three facts now, never collapsed: what the yard holds, what this fence has already
been given, and what is left. Units and offcuts stay apart here as everywhere else,
because the planner spends them differently — a remnant allocation takes the WHOLE
offcut as a bin, so half of one is never left over and whatever survives comes back
as a projected remnant, a different item. The allocations ride on the /bom response
the cost strip already fetches, so it costs no request.

Two things the browser check taught, both kept as comments: element ids are
deterministic from the topology, so regenerating the same fence KEEPS the member the
user had selected (right behaviour, and a blind second click toggles it off); and a
smoke step that leaves the project's inventory changed makes every later check depend
on that step having run, so it puts the yard back.

1045 pytest · 155 golden scenarios · 159/159 smoke · gate unmoved.

## The part library, slice 1A (2026-08-18) — COMPLETE
Spec `docs/superpowers/specs/2026-08-18-part-library-design.md`, plan
`docs/superpowers/plans/2026-08-18-part-library-1a-backend.md`, nine tasks executed
serially, the spec ruled binding wherever the plan disagreed with it (twice, both
recorded in the ledger). A part is now a third citizen of the pattern knowledge
objects and fence models already followed — named, versioned, immutable once active,
a run stamps what it resolved — for the one fact that had been living wherever it was
last typed: what a piece **is**. `SLAT-100` backed an infill member in two versions of
one model before this landed, as two separate acts of authoring; it is one part now
(`infill-slat-100`), edited once, and the edit reaches both the next time either
version is drawn from. A `SpecField` reads as a sentence about the item
(`item.width_mm == 38`), compiles to the AST
`match_eligibility` already owned, and a slot names a part by `id`, never by
`id@version` — the same unpinned shape a project already uses for its model choice,
paid for the same way: `GenerationRun.part_snapshot` stamps the exact version (and,
for a still-mutable draft, its content hash) a run actually drew on, so publishing a
part changes what a model builds NEXT, never what an already-generated run meant.

**The bargain, said once, in the one place that has to say it.** An ACTIVE model
version stopped meaning one fixed thing forever the moment the parts beneath it
became shared and mutable-by-publish. That is not a defect smuggled in — it is the
reason the entity is shared rather than copied, the same trade the model library
already made with unpinned projects, and it is why `docs/architecture/02-entities.md`
now says it beside `FenceModel` rather than leaving a reader to infer it from a
docstring.

**Two fields left AUTHORING and neither one left the SYSTEM.** `eligibility` moved
onto the part, which is the whole point. `role` tried to go the same way and could
not fully: `fencemodel/resolve.py` reads it at three call sites to write
`ResolvedSlot.role`, and `demand/derive.py` consumes that role downstream deriving a
requirement line. It came back as a RESOLVED field, filled from the part's `type` at
generation time — the same fact, said once, just no longer said twice by an author
who could disagree with themselves between the slot and the part.

**What the migration refused to do, rather than resolve silently, twice.** Where two
models draw the identical SKU at two different declared widths, migration reports and
stops instead of picking one — a missing field and a stated one are not the same
fact, and merging them would write a number onto a slot that had declared nothing,
changing a drawing rather than a document. And a `suggest_only` eligibility member
cannot be migrated by promoting it to `auto`, because that would let the system
substitute a product a human had said needs sign-off. Neither refusal fired on the
demo catalog — checked by hand, not merely asserted — but both exist as refusals
because "migration resolves it for you" is exactly the silent-narrowing failure mode
the rest of this system spends its whole design refusing to commit.

**Honestly: two slots still name SKUs directly, not a part.** `routed_vinyl_model`'s
post and cap compare an ITEM fact to a BAY fact
(`item.routed_at_mm == panel.rail_positions_mm`), and a `SpecField` only ever compiles
to `item.<key> <agree> <literal>` — there is no field-reference right-hand side for it
to borrow. `legacy_model`'s rail and screw eligibility is rebuilt PER RUN from the
run's resolved `demand_skus`, a knowledge rule reaching the BOM; naming a part there
would let a fixed SKU silently outrank the rule that sources it. Both keep their
authored `Eligibility` and `part_id=""` — a documented meaning, not an oversight, and
`validate_model` refuses a slot that names neither a part nor an eligibility, so the
empty default cannot be a quiet way to author nothing. The proper fix is a `SpecField`
whose right side may be a panel `FieldRef` rather than only a literal; it is scoped
and not built, because building it would have moved a BOM mid-arc and every dispatch
on this branch said a moving BOM means stop.

**The gate that held.** Golden scenarios, BOM, decision graph and resolved geometry
came out byte-identical against the pre-branch baseline — checked by running
`matching_skus`, not by trusting a report of it. The one thing that did NOT hold, by
design and stated plainly rather than discovered later: `RUN_DIGEST_VERSION` became
`digest-v2`, because `part_snapshot` genuinely joined the run id's inputs and a digest
that ignored a real new input would let two runs built from different part versions
collide on one id. A newly generated run gets a new id; a stored run keeps the one it
was given and reads exactly as it did before this branch. The acceptance gate was
narrowed to say so explicitly — byte-identical on the fence, not on its address.

**What the browser suite caught that nothing else could:** nothing. 1A changes no UI
and no rendered surface, and the smoke suite came back 183/183 confirming exactly
that — the one surface this arc had not touched by design stayed untouched in fact,
not merely in intent.

1378 pytest · 183 golden scenarios · 183/183 smoke · gate byte-identical on BOM,
decision graph and resolved geometry — run id moved, by design, on `digest-v2`.

**The fix wave (same day).** Three reviews — architecture-critic, a mutation-based
test review, and a whole-branch read — produced twenty findings, worked in four
commits. The correctness half had one shape repeated six times: a second door into a
state something else was guarding. `Part.status` defaults to `"active"`, so
`save_part` was a door into the state `set_part_status` guards, and the migration tool
walked through it — committing a second active version and only then raising
`active -> active`, aborting AFTER the write on every database that was not fresh.
`set_part_status` was the only multi-statement writer in `db.py` with no rollback, so
a failed activation left the predecessor's retire for the next call to commit and the
id ended with ZERO active versions. Its retirement refusal asked about the VERSION
where a model names the ID, which left every abandoned draft of an in-use part stuck
forever. `validate_part` had no caller but generation, against its own docstring:
authors got a 422 on a job they were pricing instead of a refusal on the part they
were writing. And `_LIST_VALUED` — a constant naming an invariant — was dead, so
`among` with a bare string compiled to `In(['w','h','i','t','e'])` and published clean.

**The one that was hiding in plain sight.** After resolution, "this slot declares a
predicate" is EVERY part-named slot — the normal path, not the rare one — and
`validate_model` `continue`d past four authoring rules on it. `resolve._chosen_option`
cites two of them BY NAME as load-time guarantees, so with them gone it fell through
to `unnarrowed` and a user's option choice was silently ignored. Separately, a slot
naming a part while ALSO authoring `members`/`role`/a dimension validated clean and
was then overwritten by resolution — a `suggest_only` flag a human had insisted on
deleted without a word. Both refusals now sit on the authored document, which is the
only place the two can both be true.

**Performance, measured on the same 120 m run against a 4623-product catalog: 2.92 s
-> 1.53 s.** `_model_post_skus` re-resolved the whole document once per post SIDE with
the dedup on the next line throwing half of them away — 135 resolutions for 68 posts,
now 2. `_item_ctx` was recomputed once per (slot, product) pair, 957 000 times per
run, almost all of it a `model_dump()` of three optional integers; memoised by the
product's IDENTITY rather than its sku, because a catalog is edited by REPLACING a
product and an sku key would answer the new product's question with the old product's
facts. Same run id, same BOM, same decision graph.

**The test net closed where mutations walked through it.** Four gaps were confirmed by
applying the mutation, watching the new test fail, and reverting: the run-pinned bay
preview (dropping `part_snapshot` at the route AND neutering `library_at` both left
the suite green — the drawer-shows-one-thing trap, one level in from where
`bay_preview_plan` closed it); the multi-candidate part, wired to no model, so nothing
drove `compile_spec -> match_spec -> more than one member -> pin`; the snapshot
ordering, asserted on a hand-built list rather than a generated run; and clearing
authored members during resolution. Four locale keys nothing emits were DELETED rather
than left as furniture — slice 1B adds them back with their emitters.

1403 pytest · 183 golden scenarios · compatibility gate untouched.

## The part picker — repairing the Models editor (2026-08-19) — COMPLETE
Spec `docs/superpowers/specs/2026-08-19-part-picker-repair-design.md`, plan
`docs/superpowers/plans/2026-08-19-part-picker-repair.md`. Arc A of three (B is
connections, C is item tolerance). Slice 1A moved a slot's eligibility onto the part
it names and left the editor believing the old shape. The regression it shipped with
was not exotic: `panel-inspector.js` still wrote `req.eligibility.members` and
`req.role`, both fields 1A had made RESOLVED rather than authored, and the validator
it added refuses a document that states both a `part_id` and either one. An expert
opening the Models tab saw every slot claiming no product, and the save that would
have fixed it was refused — with a 422 that named a field the editor never showed
them touching.

**Why 183 green smoke checks did not notice.** The suite has always opened the
Models tab, driven a different tool entirely — choosing a published model for a
span — and left again. Not one of those 183 checks ever clicked into the slot
inspector this arc repairs, so a pane that showed "no product" on every slot and
refused the fix passed clean, run after run, because passing required using a
surface nothing used. A tab that is opened and not exercised is not covered; the
green run was truthful about what it checked and silent about what it did not.

**The repair is a mirror, kept honest by testing both sides of it.**
`eligibility_source` (Python, `PartRequirement`) answers one question — which of
four shapes a slot is — and `panel-model.js`'s `eligibilitySource` answers the same
question in the runtime that has no import path to the first. `part_id` wins ahead
of everything else, because resolution fills a predicate onto a part-named slot and
a resolved document must not then read as rule-authored. The two are the deliberate
duplication CLAUDE.md's reuse rubric does not mean to catch — no shared module runs
in both a FastAPI process and a browser tab — and what keeps them from drifting is a
Python test over the real demo models on one side and a node test over the real
library on the other, not a promise.

**Two fields left authoring, and neither one left the system.** `role` did not move
behind Advanced; it is gone from the pane entirely, because `_part_or_authored`
refuses a part-named slot that also states what the piece is — offering the control
was offering exactly the save the server would refuse. It came back as a RESOLVED
field: `resolve_model_parts` fills it from the part's own type at generation, so
`ResolvedSlot.role` is still required and the BOM still reads it. `width_mm` and
`thickness_mm` are the identical exclusion one level up, on the holder rather than
the requirement (`_refuse_authored_dimensions`), and the sharpest finding of the arc
was that the editor had fixed the picker's own pair while leaving this one live —
`M-SLAT`'s slat names a part and carries `width_mm=0`, and the pane still offered a
width field with `min: 1` until the fix reached it. Naming a part now clears the
holder's own dimension in the same act that writes `part_id`, because hiding the
control alone was not enough — `defaultMember` still wrote a stale 100 mm into a
freshly added member, which is the same 422 through a door the fix had left open.

**A localization bug the pure/DOM split caught rather than shipped.** `specChips`
lives in `panel-model.js`, which is deliberately import-free so node can run it —
that is what makes the four-shape logic testable without a browser, and it is also
why it cannot call `t()`. An early draft phrased chip text as English prose right
there, in the one module with no path to i18n, in a Hebrew-first product. The fix
kept `specChips` returning structured facts — key, agreement, value, unit — and
moved the sentence assembly into `panel-inspector.js`, through the same `model.chip.*`
bundle keys every other user-visible string goes through.

**The preference list survives only where a slot genuinely authors one.**
`authored_members` slots — the two that still name a rebuilt-per-run sku list rather
than a part, because a fixed sku there would let a company rule get silently
outranked — keep the ordered picker under Advanced. A `part` slot cannot show it (the
pair a part-named requirement is refused for), and `authored_predicate` cannot either
(a list with nothing to order). Getting this branch wrong in either direction was the
same defect the arc exists to remove, one field over.

**What the smoke suite had to relearn to close its own gap.** Retargeting it past a
tab-open-and-leave step surfaced staleness the tab-open step had been hiding for two
tasks: `add-eligible` no longer exists on a part-named slot (narrowed correctly, the
check was not); a `role`-in-Advanced assertion still listed a field that had left
authoring, not moved; and a width-field block that looked stale on a first read was
in fact driving a STARTER template's `authored_members` slot, where both controls
still legitimately render — read the block without reading what opened it, the first
time through. Two stalls in the same implementer, same wait-loop pattern, led to an
escalation to a fresh agent on a more capable model with an explicit instruction to
poll the smoke run in the background rather than park on it; the escalated run closed
clean.

**The gate held exactly where it had to.** Nothing in this arc touches resolution or
field generation — no scenario moved, and `tests/scenarios/compatibility_gate/*.json`
is byte-identical to the branch's root. The full suite grew by 29 tests across four
tasks and the smoke suite grew from 183 checks to 187, four of them landing
specifically inside the slot pane this arc exists to repair.

1432 pytest · 183 golden scenarios · 187/187 smoke · compatibility gate unmoved.
