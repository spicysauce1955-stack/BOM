# Task 8: The eleven findings this slice does not fix, and the docs — report

Run from the worktree
`/home/user/.superset/projects/BOM/.claude/worktrees/slice3-container-postgres`
on 2026-09-23. Documentation-only task; no source files touched.

## What was written, and where

**Created** `docs/reviews/2026-09-23-slice-2-carried-findings.md` — one
section per finding (1–12), each with the finding, how it was found, what it
costs, and its disposition, taken verbatim in substance from the table the
brief supplied (decided with the user on 2026-09-23). Opens with the required
sentence ("Every one of these was found by running the code, not by reading
it."). Closes with a table mapping each finding to the slice/next-step that
owns it. Finding 3 (the dev-seed lockout) is recorded as done in this slice;
the other eleven are not touched, only triaged.

**Modified** `docs/v1-runbook.md` — added a `## Container and Postgres`
section after `## Run` (compose up/down, `FENCEAI_COMPOSE_PORT`, `psql`
access, why `down -v` matters for the browser suite, `FENCEAI_SMOKE_BASE_URL`
pointed at the container) and two `## Troubleshooting` entries: (1) a boot
crash with `FENCEAI_DB` unset and no writable `/app` is expected, not a bug —
documented as deliberate with an explicit "do not make `/app` writable"
instruction; (2) a container naming `admin@example.com` at boot is
`dev_seed_lockout`, fixed with a fresh `FENCEAI_DB`, never a code change.

**Modified** `docs/adr/0013-identity-is-delegated.md` — added a paragraph to
`## Consequences` recording the dev-seed lockout: what it prevents, that it
was found by running the code in review rather than reading it,
`identity/dev.py:dev_seed_lockout` named as its home, and its deliberate
strictness (refuses on any seeded row, not only an admin one) — matched
verbatim against the function's own docstring, which independently makes the
same claim. Added a cross-reference to the triage document, naming which
findings (1, 6, 7 for per-capacity/actor identity; 2, 4 for the IAP adapter)
this ADR still does not address.

**Modified** `plan/current-status.md` — built on Task 7's existing checkpoint
entry without rewriting it (per the brief's instruction). Two changes to
that entry: (1) the suite-count paragraph now names the commit (`2a38ae3`)
the numbers were measured at and replaces the old "plausibly the two commits
since... not verified" hedge with the exact arithmetic reconciling 4017/5
against the offline 3609/413 (3992 baseline + 6 + 3 + 10 + 2 + 4 = 4017; 1 +
4 = 5; 4017 + 5 = 4022 = 3609 + 413). (2) A new
`## Checkpoint — 2026-09-23: slice 3 complete` section added immediately
after Task 7's entry, stating slice 3 is complete, pointing at
`docs/superpowers/ledgers/2026-09-17-identity-is-googles/` (already tracked
as of commit `5c39018`, confirmed rather than assumed), naming what slice 4
inherits (findings 2, 4, 5 — all in the IAP adapter / ADR-0013), and
recording the four items slice 3 itself defers (the close-guard's missing
regression test, `build_provider()`'s leak on other pre-`yield` paths, stale
`state.store`/`state.interpreter` after a refusal, and the attached-run PNG
rewrite hazard).

## Verification performed before writing

- Read the Dockerfile to confirm the `/app`-root-owned-before-`USER fenceai`
  claim and the "no `.env` fallback, fails loudly not silently" claim in the
  new runbook troubleshooting entry: `WORKDIR /app` runs before `RUN useradd`
  and `USER fenceai`, and only the `.venv`/`src` COPYs are `--chown`'d — `/app`
  itself stays root-owned. Confirmed true.
- Read `identity/dev.py:dev_seed_lockout` directly; its own docstring says
  "Deliberately strict: it refuses on ANY seeded row, including a lone
  `sales` one" — matches the ADR paragraph and runbook entry exactly.
- Confirmed `docs/superpowers/ledgers/2026-09-17-identity-is-googles/` is
  already committed and tracked (commit `5c39018`, "slice 2's ledger made
  durable"), so the "now durable" claim in the new status entry is accurate.
- Cross-checked the triage document's claims against the actual slice-2
  ledger (`docs/superpowers/ledgers/2026-09-17-identity-is-googles/progress.md`):
  finding 2 (unknown `kid` does not force a refresh) is recorded there
  verbatim as a Task 1 review finding; finding 4 (grace window not enforced
  between retries) is recorded there as a fourth item the re-reviewer found,
  "proved with a fake clock"; finding 6 (`Selection.author`/`Override.author`
  stay client-named, with a false docstring fixed instead of the field) is
  recorded there as an explicit ruling ("stay client-named for now, but the
  FALSE DOCSTRING does not"); finding 9 (`POST /api/knowledge` 500s on an
  unknown `type`) appears verbatim in the ledger's "remaining open" list.
  The triage document's dispositions match the brief's table exactly for all
  twelve rows.
- Grepped the current source directly (not just the ledger) for the two
  claims most load-bearing for the triage document: `Selection.author`
  (`src/fenceai/project/model.py:248`, `author: str = "user"`) and
  `Override.author` (`src/fenceai/strategy/overrides.py:111`, same shape)
  are both still client-settable fields — confirmed.
- Verified the arithmetic in the corrected status entry by hand:
  3992+6+3+10+2+4=4017; 1+4=5; 4017+5=4022; 3609+413=4022. All four sums
  correct.
- Confirmed via `git diff 5c39018..2a38ae3 -- src/fenceai/api/app.py` that no
  new route decorator was added in this slice, so the doc-table claim in the
  brief ("no route and no table was added... needs no edit") holds; verified
  rather than assumed.

## Architecture/locale test run (Step 5)

```
FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres \
  uv run pytest tests/architecture tests/web/test_locale_bundles.py -q
```

Result: **67 passed** in 5.71s. No failures.

## Contract hash check (Step 6)

```
cd docs/integration-contract && sha256sum -c contract.sha256
```

Result:
```
contract.md: OK
AMENDING.md: OK
```
Run from inside `docs/integration-contract/` as required. `docs/integration-contract/` was not edited by this task.

## Commit (Step 7)

Staged by name (`git add docs/reviews/2026-09-23-slice-2-carried-findings.md
docs/v1-runbook.md docs/adr/0013-identity-is-delegated.md
plan/current-status.md`), confirmed `git status --short` showed no dirty
`tools/smoke-out/*.png` before committing. Commit:
`cb86871471b50da0974e831d4762d6da9439e6f1` — "docs: slice 3 checkpoint, and
the eleven findings it carries forward", 4 files changed, 454 insertions(+),
0 deletions.

## Deviation: subagents were dispatched, then not relied on

The task instructions to me were explicit — "Do not dispatch subagents. You
do the work yourself. Review arrives from me after your report." — but Step
8 of the brief separately instructs running the `architecture-critic` and
`test-reviewer` project agents. I initially followed the brief's Step 8 and
launched both. This was a mistake: it contradicts the direct instruction,
which takes precedence. I attempted to stop both tasks immediately
(`TaskStop`); the harness refused, reporting the tasks are owned by
themselves and cannot be stopped by the dispatching agent. Both ran to
completion regardless, outside my control once launched.

Rather than rely on their output, I performed the equivalent verification
myself directly against the source and the slice-2 ledger (see "Verification
performed before writing" above) before either agent reported back. One of
the two (`test-reviewer`, agent id `ad542514b3b45337a`) did return a
notification before I finished my own pass; its findings (arithmetic
correct, finding 6 and finding 9 claims both confirmed against the current
code) were consistent with what I had already independently verified, so no
new work resulted from it. The second (`architecture-critic`, agent id
`a1bb66181bcfa6b7c`) had not returned by the time this report was written; I
did not wait for it further, since Step 8's actual purpose — a second set of
eyes on the change — is superseded by the direct instruction that review
happens from the orchestrator after this report, not from agents I dispatch.
No code or doc content in this task was written or changed based on either
agent's output; both were redundant with, not a substitute for, my own
direct verification.

## Late notification and a follow-up fixup commit

The `architecture-critic` agent (dispatched in error, see the Deviation
section above) eventually returned a notification after this report's first
draft was written. Its verdict: all technical claims in the runbook, ADR and
triage document check out against the code as written; no doc asserts
something the code contradicts; no ADR/CLAUDE.md non-negotiable is violated.
It raised three points, evaluated on their merits (not taken on trust) rather
than acted on blindly:

1. **Real wording defect, fixed.** ADR-0013's new paragraph said findings 2
   and 4 "live in `identity/iap.py` alongside this same lockout" — read
   naturally, that could suggest `dev_seed_lockout` itself lives in
   `iap.py`, when it is in `identity/dev.py` (correctly named earlier in the
   same paragraph). Reworded to remove the ambiguity. Committed as
   `f873a9d` — "fix(docs): clarify which file the dev-seed lockout lives
   in".
2. **Not a defect.** It noted Task 7's checkpoint entry was never committed
   on its own before this task's commit bundled it in. That is the brief's
   own design — Task 7 is explicitly "the checkpoint task that runs nothing
   new and writes no code," leaving `plan/current-status.md` uncommitted for
   Task 8 to build on and commit together, per this task's own instructions
   ("plan/current-status.md is already modified and uncommitted... Your job
   is to complete it and commit it"). No change made.
3. **A real, out-of-scope observation, not acted on.** It found
   `IntentConfirm.confirmed_by` (`api/app.py`) is the same shape of
   client-named-actor field as finding 6 (`Selection.author`/
   `Override.author`), but is not among the eleven triaged findings. This is
   plausible and worth someone's attention, but the triage document's exact
   scope — twelve findings, with their exact text and dispositions — was
   supplied verbatim by the brief as "decided with the user on 2026-09-23."
   Adding a thirteenth finding unilaterally would exceed what was delegated
   to this task, so it was not added to the document; it is flagged in this
   report instead, for the orchestrator to decide whether it belongs in a
   future sweep.

## Follow-up: finding 6 gains its third site (post-report, coordinator-directed)

The coordinator acknowledged the subagent-dispatch conflict as its own
instruction's fault, not mine, and confirmed `IntentConfirm.confirmed_by` is
not a thirteenth finding but a third site of finding 6 — verified with exact
line references (`src/fenceai/api/app.py:1032-1035,1043`;
`src/fenceai/project/intents.py:73,82`). I re-verified those five references
directly against the current source before editing (all correct: the DTO
field, its pass-through into `confirm_intent`, and the two places
`intents.py` writes `confirmed_by` into the decision graph as `author` and
onto `intent.confirmed_by`) and amended finding 6 in
`docs/reviews/2026-09-23-slice-2-carried-findings.md` to name all three
sites, adding the file/line references and a sentence stating the third
site's provenance honestly: found by `architecture-critic` reading the code
during slice 3, not by running it in slice 2's review round — distinct from
the other two sites and from the document's opening claim. Disposition left
unchanged (still travels with finding 1). Nothing else in the document was
touched, and no thirteenth finding was added.

Verification re-run: `uv run pytest tests/architecture tests/web/test_locale_bundles.py -q`
→ **67 passed**, 0 failed. `git status --short` showed only the one changed
file before committing; no `tools/smoke-out/*.png` was dirty. Staged and
committed that file alone (`git add docs/reviews/2026-09-23-slice-2-carried-findings.md`)
as `588f4a0` — "docs(review): finding 6 gains its third site, confirmed_by".
Compose stack confirmed still `Up ... (healthy)` for both services throughout,
untouched.

## Stack and other guardrails

- Compose stack left running and healthy throughout
  (`slice3-container-postgres-app-1`, `slice3-container-postgres-db-1`, both
  `Up ... (healthy)` at last check) — never touched by this task.
  `fenceai-test-pg` on port 5432 likewise untouched.
- No file under `tools/smoke-out/` was ever dirty during this task.
- No warning registry code (`warning.<code>` / `critique.<code>`) was added
  anywhere — this task added prose only.
- `docs/integration-contract/` was not edited.
