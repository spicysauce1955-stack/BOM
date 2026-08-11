# Persona lab — run 2 study design (addendum)

Amends `2026-08-11-persona-lab-design.md`. The harness (driver, act.py, refuter protocol,
report collation) stands. **What changes is the study**: who is simulated, what they are
asked to do, what they are allowed to be told, and what the app is allowed to show them.

Run 1 produced 51 refuter-confirmed findings and one honest conclusion: the study was
measuring the wrong thing. This addendum records why and what replaces it.

## 1. What run 1 got wrong

**Personas came from market research, not from the architecture.** They were built from "who
works in the Israeli fence trade" and never reconciled with "who is this system for". Those
are different sets. The sales-rep persona graded the product against selling, and S01–S14
contain no scenario about a price, a margin, a customer, or an export. Its blockers are
reclassified as out of scope.

**The product's thesis was never touched.** Foundation §9: *"The expert should be able to work
normally, correcting the proposed construction rather than separately documenting every rule in
advance."* Four of fourteen golden scenarios (S11–S14) exist for that loop. Across 145 recorded
steps, no persona corrected the system, annotated anything, or taught it a rule.

**The prompts led the witness.** Each persona was handed "your central checks" — *does every
line have a catalog code, can you export, is there a חגורת בטון line*. A real user has no
checklist of the product's likely weaknesses. Some headline findings are the prompt reflected
back.

**Quitting was rewarded.** Personas were told to quit when a real person would, given their
quit triggers, and in one case told outright that giving up early was the valuable output. An
agent told that quitting is a deliverable will quit. The unanimous 0/6 is not trustworthy.

**They priced the demo.** A fresh DB opens into the seeded sample project, so several personas
generated and quoted the sample's 15–17 m runs while believing they were working their own job.

**Thirty actions is about three minutes**, with every `look` consuming one. Run 1 measured the
first three minutes of a first-ever session and reported it as "can they do their job". The
question that matters is whether the tool beats the fallback on the *third* project.

**The app's teaching channel was switched off.** The outline enumerates interactive elements
only. `#statusbar` is a `<div>`, so it never appeared — yet the UI v2 spec built it precisely
as the antidote to undiscoverable gestures ("always names the current mode and next gesture").
Every persona drew blind to the one surface designed to tell them what to do next. This alone
plausibly accounts for most of the drawing failures and the "there is no zoom" conclusion.

## 2. Roles, from the architecture

Five roles, each mapped to the scenarios that exist for it. The English control is retired: its
question ("is language the blocker?") was answered — no — and the budget is better spent on the
loop that was never tested.

| Role | Trying to achieve | Success | Scenarios |
|---|---|---|---|
| **Expert** *(central)* | Teach the system the company's way by correcting proposals in context, not by writing rules up front | "It agrees with me by default now, and I documented nothing in advance" | S11, S12, S14 |
| **Knowledge owner** | Change a rule without breaking work already done | "I saw it would hit 7 projects before approving, and scoped it" | S13 |
| **Topology author** | Make the drawing a true description of the site | "What is on screen is what is out there" | S03–S06 |
| **Fulfillment consumer** | Turn engineering demand into the least wasteful purchase | "The cut plan and remnants beat what I do in my head" | S07–S09 |
| **Strategy approver** | Freeze a version and know what changed since | "I can see the delta against what I accepted" | quote lifecycle |

## 3. Protocol changes

- **No checklists.** Persona prompts carry the job and the site data. They carry no list of
  things to inspect, no named product surfaces, and no hypotheses.
- **Findings in free prose.** Personas describe what happened in their own words. The
  `symptom` enum is assigned by the **refuter**, not the persona — naming the categories in
  advance primes the very findings we are counting.
- **Quitting is not a deliverable.** The instruction is to finish the job. If they genuinely
  cannot, they say so plainly. No quit-trigger list, no framing that makes stopping valuable.
- **Budget 60 actions, and `look` is free.** Perception is not an action; real users look
  constantly. This roughly quadruples effective interaction.
- **Two projects, not one.** Every persona does their job twice on different sites. The second
  run is the measurement that matters — the first is training. Report time-on-task for both.
- **Real job tickets.** Each persona receives written site data with actual numbers, the way a
  measurement sheet or a WhatsApp message would arrive, instead of prose to invent from.
- **Clean start.** The harness creates and selects an empty project per persona, so nobody
  quotes the demo. The knowledge-owner and approver roles instead get a **seeded set of several
  realistic projects**, because impact preview and deltas are meaningless against one project.

## 4. Harness changes

Additive; nothing already verified is removed.

- **Feedback regions in the outline.** The status bar, the warnings strip, any open dialog or
  popover text, and the getting-started checklist are rendered as a `screen says:` block above
  the handle list. These are the app's feedback channels; a sighted user reads them
  unavoidably. Static prose generally stays out — this is not licence to dump the DOM.
- **`move x y` verb.** Mouse move without click, so drawing has live rubber-band feedback and
  the cursor readout updates. Drawing is the product's core interaction and run 1 did it one
  frozen frame at a time.
- **`seed.py`** — creates several realistic projects for the roles whose work is cross-project.

## 5. What carries over unchanged

The refuter pass, its adversarial framing, its authority over severity, and the rule that a
feature which exists but cannot be found is `not-found` rather than a refutation. Run 1 proved
that pass is the only thing standing between this technique and confident fiction: it killed 13
findings, including a fabricated app freeze, and traced six defects to the harness itself.

`surface` also becomes a fixed enum alongside `symptom`, because free-text surfaces under-merged
51 confirmed findings into 48 groups.
