# Start prompt — agent framework slice 1

Paste the block below into a fresh session in this repo.

---

Implement `docs/superpowers/plans/2026-09-08-agent-framework-slice-1.md`.

**Read first, in this order, before touching any code:**
1. `docs/superpowers/specs/2026-09-08-advisory-agent-design.md` — what the agent is and why, with every decision attributed to the product owner rather than inferred.
2. `docs/superpowers/specs/2026-09-08-agent-framework-design.md` — how it is built. §1, §5 and §6 are the load-bearing ones.
3. The plan itself.
4. `plan/current-status.md`, top section only.

**The design is settled. Do not re-open it.** If you think a decision is wrong, say so in one paragraph and keep building to the spec; a change needs the product owner, not a judgement call mid-task.

**Use `superpowers:subagent-driven-development`** — one fresh subagent per task, review between tasks. The plan is built around one task at a time, and the reason is on the record: on 2026-09-03 a feature landed correctly with every test passing and the verdict was *"we took a bigger task then we could chew."* No concurrent agents inside a slice.

**The three things that make this slice what it is:**
- A task's permission list becomes the model's output schema, so an agent cannot name an action it was not given. It is a grammar, not a checker.
- A claim may only cite what that task run's view handed it — an agent can echo a citation, never invent one.
- `evaluated: false` ("I did not look") is never an empty result ("nothing to report").

**Stop at the checkpoint after task 10.** Do not start slice 2, do not add the Claude adapter, do not extend the action registry. Run the app, and hand the product owner the URL and what to click. Green tests are not the checkpoint.

**Gates before you call any task done:**
```
uv run pytest -q                  # full suite — the fitness tests only run here
uv run pytest tests/scenarios -q  # must NOT move; this slice adds nothing to generate()
```
And once, at the checkpoint: `uv run --with websocket-client python tools/ui_smoke.py`

**Known risks, already written into the plan:** tasks 4, 6, 7 and 9 build fixtures from field names read at planning time — if one is wrong, fix the fixture, never the production model. Task 10 assumes a `run:changed` event in `state.js`; if the real name differs, use it and do not add a new event. Task 8 is a guard rather than a red-green cycle and says so.

**Repo rules that bite:** another session commits here, so stage your own files by name and never `git add -A`. A new route needs `docs/architecture/04-backend.md` updated — both the count and the table. `i18n/he.json` and `en.json` must keep identical key sets.

**Do not touch** `docs/integration-contract/` — the contract is frozen at v1.3 and the thread is at T59. Nothing in this slice crosses the boundary.

**One small unscheduled defect, if you want it after the checkpoint:** `knowledge/parameters.py:964` emits the `uncovered_point_contradicted` dispute *instead of* the coverage gap — it `continue`s past it. Both teams have agreed it should accompany rather than replace (`conversation.md` T55 §7, accepted T59 §1). Small, test-shaped, and independent of the agent work.
