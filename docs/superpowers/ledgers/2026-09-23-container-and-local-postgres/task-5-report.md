# Task 5 report: Point the browser suite at a server it did not start

## Fix round 1 (post-review)

Review approved the seam's design and mechanically verified the comment
freeze (0 lost, 0 paraphrased). Two one-liner findings addressed, both in
`tools/ui_smoke.py`, foreground only:

1. **Module docstring under-described the tool.** Added one line after the
   existing usage paragraph (not touching the frozen `#:` block or the
   frozen preflight comments at what are now lines 28–30, which correctly
   stayed byte-identical): "Set FENCEAI_SMOKE_BASE_URL to point every check
   at a server this script did not start instead — e.g. a container's
   published port — which is how you prove an IMAGE serves this app; a
   uvicorn launched here from source would only prove the opposite."

2. **FATAL echoed a resolved value, not what the user typed.** The
   attached-mode abort at (now) line 4864 printed
   `{_BASE_URL_ENV}={target_base_url()}`, so `FENCEAI_SMOKE_BASE_URL=/`
   (which `rstrip("/")`s to empty and falls back to the default) printed
   `FENCEAI_SMOKE_BASE_URL=http://localhost:8791` — a value never exported.
   Changed to capture `raw = os.environ.get(_BASE_URL_ENV, "")` and print
   both: `FATAL: {_BASE_URL_ENV}={raw!r} resolved to {target_base_url()},
   but nothing answered /api/health there ({exc!r}) — start it first`.

Noted for the record, not redone: the coordinator already found that both
of my earlier smoke runs (unattached, then attached to the container) left
34 tracked `tools/smoke-out/*.png` files modified — last-write-wins, so
they depicted the container's dev-seeded Postgres app rather than the
throwaway-SQLite baseline — and ran `git checkout -- tools/smoke-out`
before I resumed. My original commit (`05c32ee`) was already exactly the
two intended files; this was a pre-commit-hygiene note for future runs
(regenerate `smoke-out/` unattached before any commit that includes it),
not a defect in what I committed.

### Verification (foreground)

```
$ uv run pytest tests/tools tests/web/test_smoke_cases_registered.py -q
98 passed, 12 warnings in 31.45s
```

Hand-exercised both FATAL directions (each aborted at the very first
preflight check in `main()`, before any DB, server, or Chrome would have
been created — confirmed no stray uvicorn on :8791 and no stray CDP
listener on :9333 afterward):

```
$ FENCEAI_SMOKE_BASE_URL=/ uv run --with websocket-client python tools/ui_smoke.py
FATAL: FENCEAI_SMOKE_BASE_URL='/' resolved to http://localhost:8791, but nothing answered /api/health there (URLError(ConnectionRefusedError(111, 'Connection refused'))) — start it first
EXIT:2

$ FENCEAI_SMOKE_BASE_URL=http://localhost:1 uv run --with websocket-client python tools/ui_smoke.py
FATAL: FENCEAI_SMOKE_BASE_URL='http://localhost:1' resolved to http://localhost:1, but nothing answered /api/health there (URLError(ConnectionRefusedError(111, 'Connection refused'))) — start it first
EXIT:2
```

Did **not** re-run the full browser suite — neither change touches a code
path the 646 checks exercise (a docstring line and an error-message
string on an abort path that both smoke runs already proved is otherwise
unreached), and the run costs several minutes.

`git status --short` after the hand-exercises: clean except
`tools/ui_smoke.py` — no `tools/smoke-out` PNG was dirtied (the FATAL
aborts before any screenshot code runs), so no checkout was needed.

Committed `tools/ui_smoke.py` by name (not `git add -A`) as `082fc0d`.
Compose stack on :8080 left running and untouched; `fenceai-test-pg` on
:5432 untouched.

## What was done (original submission)

Followed the brief step by step (TDD), working only in
`/home/user/.superset/projects/BOM/.claude/worktrees/slice3-container-postgres`.

1. **Read `tools/ui_smoke.py` lines 4810–4940 in full before touching anything**,
   as instructed, to internalize the load-bearing comments around `main()`
   (the stale-port abort, the CDP-port abort with its `pkill -f
   'remote-debugging-po[r]t=...'` bracket-typo explanation, the
   `FENCEAI_DEV_USER` exclusion rationale, and the fresh-Chrome-profile
   rationale). All of these comments are preserved verbatim in the diff.

2. **Step 1** — wrote `tests/tools/test_ui_smoke_target.py` exactly as given
   in the brief (4 tests: default target/attached, attach via env var,
   trailing-slash normalization, blank-value-is-not-an-attachment).

3. **Step 2** — ran it, got the expected 4 failures
   (`AttributeError: module 'ui_smoke' has no attribute 'target_base_url'`).

4. **Step 3** — added `_BASE_URL_ENV`, `target_base_url()`, and `attached()`
   directly below the `PORT` / `CDP_PORT` constants (now at lines 31–32 of
   `tools/ui_smoke.py`, unchanged from before my edit), before the `OUT =`
   line — exact text from the brief.

5. **Step 4** — ran the test again: 4 passed.

6. **Step 5** — replaced the five URL-construction sites with
   `target_base_url()`. Found them **by content** (`grep -n
   'localhost:{PORT}'`), confirming five hits before editing and two left
   afterward (the intentional ones: inside `target_base_url()`'s own
   fallback, and the "already listening on our own port" abort branch in the
   non-attached leg of `main()`):

   | Site | What it was | What it is now |
   |---|---|---|
   | line 420 (was 420, unshifted — above the inserted functions) | `c.cmd("Page.navigate", url=f"http://localhost:{PORT}/")` | `url=target_base_url() + "/"` |
   | readiness-loop tuple entry (was 4899, now inside the restructured `_wait_urls` list) | `f"http://localhost:{PORT}/api/health"` | `target_base_url() + "/api/health"`, appended only `if not attached()` |
   | `Cdp(...)` construction (was 4909) | `Cdp(f"http://localhost:{PORT}/", cdp_port=CDP_PORT, out_dir=OUT)` | `Cdp(target_base_url() + "/", cdp_port=CDP_PORT, out_dir=OUT)` |
   | mid-suite reload (was 6917) | `c.cmd("Page.navigate", url=f"http://localhost:{PORT}/")` | `url=target_base_url() + "/"` |
   | deep-link case (was 9066) | `f"http://localhost:{PORT}/#evidence="` | `target_base_url() + "/#evidence="` |

   `CDP_PORT` URLs (the two `/json/version` checks) were left untouched, per
   the brief: Chrome is always ours, wherever the app runs.

7. **Step 6** — branched `main()`:
   - The app-side "something is already listening" abort is now `if
     attached(): ... else: <original abort, byte-identical>`. The attached
     branch does a 5 s `urlopen` on `{target_base_url()}/api/health` and
     fails loudly by name if nothing answers, exactly as specified.
   - The CDP-port abort block immediately below is untouched, including
     every comment (verified with `git diff` — zero changes in that
     hunk).
   - `server = None; db = None` up front; the temp-DB creation, the
     `FENCEAI_DEV_USER`-exclusion comment block, and the `Popen` are now
     inside `if not attached():` — comment block preserved verbatim.
   - The Chrome/profile launch is unconditional (always ours).
   - The readiness loop: `_wait_urls` always includes the CDP URL; the app
     health URL is appended only `if not attached()`. I added one short new
     comment line explaining why (`# (When attached, the app side of this
     was already proven above; ...)`) directly under the existing "Wait for
     BOTH..." comment, which itself is untouched.
   - Teardown (`finally`): `for proc in (server, chrome): if proc is None:
     continue; ...` and `if db is not None and os.path.exists(db): ...` —
     both guards added per the brief ("only kill `server` when it is not
     `None`").
   - Confirmed via `python3 -c "import ast; ast.parse(...)"` that the file
     still parses.

8. **Step 7 — the regression that matters most.** Ran, in the foreground,
   with no `FENCEAI_SMOKE_BASE_URL` set:

   ```
   uv run --with websocket-client python tools/ui_smoke.py
   ```

   Result: **646/646 checks passed**, exit code 0. The seam is invisible
   when unused.

9. **Attached sanity check**, per the brief's explicit ask, against the
   already-running compose stack (`slice3-container-postgres-app-1` on host
   port 8080, `FENCEAI_IDENTITY=dev`, no `FENCEAI_DEV_USER`):

   ```
   FENCEAI_SMOKE_BASE_URL=http://localhost:8080 uv run --with websocket-client python tools/ui_smoke.py
   ```

   Result: **646/646 checks passed**, exit code 0. Verified afterward that
   the compose containers were untouched (`docker ps` still shows
   `slice3-container-postgres-app-1`/`-db-1` "Up ... (healthy)"), nothing
   was listening on :8791 (the suite's own port, confirming it never started
   its own server), and `http://localhost:8080/api/health` still answered
   200 after the run. No `docker compose down` was run, no server I didn't
   start was killed, and no throwaway SQLite file was created (the `db`
   variable stayed `None` on the attached path, so the teardown's `if db is
   not None` guard never fired).

10. **Step 8** — guard tests:

    ```
    uv run pytest tests/web/test_smoke_cases_registered.py tests/tools -q
    ```

    Result: **98 passed**, 12 pre-existing `SyntaxWarning`s from raw `\d`,
    `\w`, `\{` escapes inside JS-string literals elsewhere in the file
    (unrelated to this change, present before my edit too — confirmed by
    the fact they appear at line numbers unrelated to any hunk I touched).
    `test_smoke_cases_registered.py` (which parses `_CHOICE_CASES` via
    `ast` and asserts single assignment + full registration) is green, and
    `tests/tools/test_cdp_move.py` (which reads the file as text) is green.

11. **Step 9** — staged only `tools/ui_smoke.py` and
    `tests/tools/test_ui_smoke_target.py` by name (never `git add -A` —
    the smoke run regenerated 33 tracked PNGs under `tools/smoke-out/`,
    left untouched/unstaged per the "stage your own files by name" rule).
    Committed as `05c32ee`. Attribution line used
    `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` — this
    session's system reminder for attribution supersedes the brief's
    `Claude Opus 5 (1M context)` line, per that reminder's own precedence
    rule.

## Deviations from the brief, and why

- **Readiness-loop restructuring wasn't literally given as code** in the
  brief (only described in prose: "only wait on the app's health when we
  started it"). I built it as a small mutable list (`_wait_urls`) with a
  conditional `.append(...)`, keeping the existing `for url in ...:` /
  `for _ in range(120): ... else: FATAL` structure completely intact. I
  added one new short comment line under the existing "Wait for BOTH..."
  comment to explain why the loop is no longer always "both" when attached;
  the original four-line comment itself was not altered or reworded.
- Everything else matches the brief's exact code samples.

## Facts asked to be double-checked

- **Five URL-construction sites, found by content**: confirmed — exactly
  five `localhost:{PORT}` interpolations existed pre-edit (`grep -n
  'localhost:{PORT}' tools/ui_smoke.py` before editing showed lines 420,
  4828, 4899, 4909, 6917, 9066 — six hits total, but 4828 is the
  "already listening on our own port" abort check, which is correctly
  *not* one of the five call sites the brief tabulates, since it must stay
  pointed at literal `PORT` even in the attached world — it's the
  non-attached branch's own-port guard). This matches the brief's table of
  five (420, 4899, 4909, 6917, 9066) exactly.
- **`ui_smoke` imports cleanly, no import-time side effects**: confirmed
  implicitly — `tests/tools/test_ui_smoke_target.py` imports it inside each
  test function per the established pattern and all 4 tests pass cleanly
  with no server/browser ever touched.
- Both stated facts held; nothing found false.

## Files touched

- `tools/ui_smoke.py` — the seam, five call sites, and `main()` branching.
- `tests/tools/test_ui_smoke_target.py` — new, per brief Step 1 verbatim.

## Commands run (full list, in order)

```
uv run pytest tests/tools/test_ui_smoke_target.py -q          # 4 failed (expected)
uv run pytest tests/tools/test_ui_smoke_target.py -q          # 4 passed
uv run pytest tests/web/test_smoke_cases_registered.py tests/tools -q   # 98 passed
uv run --with websocket-client python tools/ui_smoke.py       # 646/646 passed
FENCEAI_SMOKE_BASE_URL=http://localhost:8080 uv run --with websocket-client python tools/ui_smoke.py   # 646/646 passed
git add tools/ui_smoke.py tests/tools/test_ui_smoke_target.py
git commit -F <scratchpad file>
```
