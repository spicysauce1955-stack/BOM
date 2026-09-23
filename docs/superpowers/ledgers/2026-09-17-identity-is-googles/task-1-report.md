# Task 1 report: the port and its two providers

## Fix report round 2 (finding 3, corrected)

Round 1's claim that `test_an_hs256_token_signed_with_the_public_key_is_nobody` and
`test_an_alg_none_token_is_nobody` were "a genuine regression net" for the algorithm pin was
**wrong**, and verified wrong by the re-reviewer: widening `iap.py:125`'s
`algorithms=["ES256"]` to `["ES256", "HS256", "none"]` left both tests passing. They were
never testing the pin — they were incidentally caught by two of PyJWT's own internal
guards (a `TypeError` on a non-string key for HMAC, or an `InvalidKeyError` on a PEM-shaped
HMAC secret / a non-`None` key with `alg: none`), guards that have nothing to do with this
file's `algorithms` list and would keep firing even if that list were quietly deleted
entirely.

### What changed

1. **A real regression net for the pin**, `test_the_algorithm_pin_is_exactly_es256` (new,
   `tests/identity/test_iap.py`): monkeypatches the actual `jwt.decode` function (via the
   shared `jwt` module object — `principal()`'s local `import jwt` resolves to the same
   object, so patching the attribute on it is visible from inside the method) to capture the
   `algorithms` kwarg on a real successful `principal()` call, and asserts it is exactly
   `["ES256"]`. This is indirect on purpose: it is the only one of the three tests that is
   actually sensitive to that list, because it inspects what gets PASSED rather than what
   PyJWT does with a specific forged token.

2. **Corrected the docstrings** on both attack tests (`test_an_hs256_token_signed_with_the_public_key_is_nobody`,
   `test_an_alg_none_token_is_nobody`) to state plainly which mechanism refuses each token —
   PyJWT's own key-type/algorithm-type guards, not this file's `algorithms` pin — and to point
   at `test_the_algorithm_pin_is_exactly_es256` as the one that actually depends on the pin.
   Both attack tests are kept: they still prove the end-to-end outcome (a forged token
   resolves to `None`), which is worth having regardless of which layer does the refusing.

### Verified, not just claimed, this time

Per the coordinator's explicit instruction, actually widened the list, watched the new test
fail, and restored the file — rather than repeating round 1's mistake of asserting behavior
without exercising the counterfactual:

```
# edited src/fenceai/identity/iap.py:125 to:
#     algorithms=["ES256", "HS256", "none"],
uv run pytest tests/identity/test_iap.py -v -k "algorithm_pin or hs256 or alg_none"
```
Result: `test_an_hs256_token_signed_with_the_public_key_is_nobody` **PASSED** (still —
refused by PyJWT's own guard, exactly as the corrected docstring now says),
`test_an_alg_none_token_is_nobody` **PASSED** (still — same reason), and
`test_the_algorithm_pin_is_exactly_es256` **FAILED**:

```
AssertionError: assert ['ES256', 'HS256', 'none'] == ['ES256']
```

This is the exact failure signature the finding predicted: the two attack tests are blind to
the widening, and the new capture-based test is not. Restored `iap.py:125` to
`algorithms=["ES256"]` immediately after (confirmed via `git diff --stat
src/fenceai/identity/iap.py` showing no diff).

### Test commands run and output (after restoring)

```
export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres
uv run pytest tests/identity -q
```
→ `63 passed in 1.19s` — full `tests/identity` directory, dual-run against real Postgres as
instructed. Confirmed via `-v` that a live Postgres was actually reachable at that URL rather
than silently skipping: `test_store.py`'s `[postgres]`-parametrized cases appear in the
output and pass alongside their `[sqlite]` counterparts (previously 8 of these were `SKIPPED`
without `FENCEAI_TEST_POSTGRES` set). No failures, no unexpected skips.

### Anything I'm unsure about

Nothing outstanding on finding 3. The one thing worth flagging proactively: this round's
verification (widen → fail → restore) was done by hand-editing `iap.py`, running the targeted
tests, confirming the diff was clean afterward, then re-running the full `tests/identity`
directory — the same discipline the coordinator asked for on the missing-`exp` claim last
round, applied here before making the claim rather than after being caught making it
unverified.

## Fix report (post-review)

Review came back spec ✅ with four Important findings against `src/fenceai/identity/iap.py`
(three from the reviewer, one my own ruling from a "cannot verify" item). All four addressed
in `src/fenceai/identity/iap.py` and `tests/identity/test_iap.py`; three Minor findings
(missing log line on the blanket `except`, duplicated missing-audience validation, cache's
lack of a lock) were explicitly deferred by the coordinator and left untouched.

### 1. `exp`-less tokens accepted forever

`jwt.decode(...)` now passes
`options={"require": ["exp", "iat", "aud", "iss", "sub", "email"]}`. Verified the gap was
real before the fix, not theoretical: decoding a correctly-signed token with `iat` but no
`exp`, WITHOUT the `require` option, succeeds and returns claims (checked directly against
PyJWT, see below) — confirming the fix closes a live gap in this code, not a hypothetical one.

Covering test: `test_an_assertion_missing_exp_is_nobody` (new) — a token signed with `iat`
but no `exp` must resolve to `None`.

### 2. A gstatic blip past the TTL refused every request

Rewrote `_key_for`. Three changes:
- `time.time()` → `time.monotonic()` (a backwards wall-clock step can no longer make the
  cache look artificially fresh).
- On a stale cache, a failed refresh now serves the last-known-good keys instead of
  propagating, up to a new `_KEY_STALE_GRACE_SECONDS = 6 * 3600` constant — commented with
  why 6 hours is a judgement call (Google rotates these keys on a schedule measured in days,
  so a key still cached an hour past the ordinary refresh point is overwhelmingly likely to
  still be current; the number trades a longer stale-but-good window against a small window
  of accepting a since-revoked key, erring toward staying up through a transient outage).
  Only once the cache is stale by more than TTL + grace does the exception propagate (which
  `principal()`'s existing `except Exception` turns into `None`, same as any other
  unverifiable token — still fail-closed, just later).
- Added `_KEY_RETRY_BACKOFF_SECONDS = 60` and a `_last_attempt_at` timestamp so a sustained
  outage doesn't turn every single request into its own blocking 5-second-timeout fetch
  attempt — the second effect the finding named alongside "refuses everyone".

Covering tests (new): `test_a_stale_key_fetch_failure_still_resolves_within_the_grace_window`
(a fetch failure well inside the grace window still resolves the real token, and the fake
clock proves the fetch was actually retried — `calls["n"] == 2`) and
`test_a_stale_key_fetch_failure_refuses_once_past_the_grace_window` (once the fake clock
passes TTL + grace, the same failure mode now refuses). Both monkeypatch
`fenceai.identity.iap.time.monotonic` to a controllable fake clock rather than sleeping.

### 3. No test pinned the algorithm

Added three tests to `tests/identity/test_iap.py`:
- `test_an_hs256_token_signed_with_the_public_key_is_nobody` — forges an HS256 token by
  hand (raw `hmac`/`hashlib`, not `jwt.encode`) using the PEM-encoded EC public key as the
  HMAC secret, and asserts `principal()` returns `None`. Built by hand deliberately: PyJWT's
  own `jwt.encode` now refuses to use a PEM-shaped key as an HMAC secret
  (`InvalidKeyError: ... should not be used as an HMAC secret`), which would have laundered
  the test into testing PyJWT's encoder guard instead of our decoder's fixed `algorithms`
  list — an attacker computing the HMAC directly is not stopped by that encoder-side guard.
  Confirmed empirically (see below) that PyJWT's `decode()` rejects on the `alg` mismatch
  before ever touching the key, so this is a real regression net against a future widening
  of `algorithms=["ES256"]`, not a no-op.
- `test_an_alg_none_token_is_nobody` — an unsecured (`alg: none`) token, same assertion.
- `test_an_assertion_missing_exp_is_nobody` — counted under finding 1 above; it is also the
  regression test the reviewer asked for "once fix 1 lands".

### 4. `_fetch_google_keys`'s PEM-string return shape was untested

Added `test_fetch_keys_returning_a_pem_string_still_resolves`: constructs `IapIdentity` with
a `fetch_keys` callable that returns the public key serialized to a PEM **string** (the exact
shape `_fetch_google_keys` gets back from gstatic's JSON, decoded to `str`), not the
`cryptography` object every other test hands in, and asserts a genuinely signed token still
resolves to the right principal.

### Verification that finding 1 was a real (not hypothetical) gap

Before writing the fix, ran this directly against PyJWT to confirm the claim in the
finding:

```
uv run python -c "
import time, jwt
from cryptography.hazmat.primitives.asymmetric import ec
private = ec.generate_private_key(ec.SECP256R1())
public = private.public_key()
claims = {'iss':'https://cloud.google.com/iap','aud':'aud1','email':'d@e.com','sub':'s1','iat':int(time.time())-5}
tok = jwt.encode(claims, private, algorithm='ES256', headers={'kid':'k'})
c = jwt.decode(tok, public, algorithms=['ES256'], audience='aud1', issuer='https://cloud.google.com/iap')
print('WITHOUT require option, decoded fine (proves the vuln existed):', c)
"
```
Output: `WITHOUT require option, decoded fine (proves the vuln existed): {'iss': ...,
'iat': 1789664895}` — no `exp` in the payload at all, and it decoded without error. Confirms
the pre-fix code accepted a token with no expiry.

Also confirmed the algorithm-confusion test's premise directly against PyJWT: a manually
forged HS256 token (correct HMAC computed with the real PEM bytes) decoded against
`algorithms=["ES256"]` raises `InvalidAlgorithmError: The specified alg value is not
allowed` — i.e. the check happens before key preparation, so the fixed `algorithms` list is
what protects `principal()`, independent of whether the forged signature is "valid" by HMAC
arithmetic.

### Test commands run and output

```
uv run pytest tests/identity/test_iap.py tests/identity/test_ports.py -q
```
→ `23 passed in 0.05s`

```
uv run pytest tests/identity/test_iap.py -v
```
→ all 15 tests in the file pass individually (9 original + 6 new: missing-exp, HS256
confusion, alg-none, PEM-string fetch, and the two stale-key-grace-window tests).

```
uv run pytest tests/identity/ -q
```
→ `49 passed, 8 skipped in 0.62s` (the 8 skips are the pre-existing, unrelated Postgres-store
tests; 49 passed is up from the earlier 43, i.e. +6 new tests, 0 regressions).

```
uv run python -c "import sys; import fenceai.api.app; import fenceai.identity.provider; print('imports clean'); print('jwt in sys.modules:', 'jwt' in sys.modules)"
```
→ `imports clean` / `jwt in sys.modules: False` — the offline property still holds after
these changes; nothing at import time reaches `jwt`.

### Anything I'm unsure about

None of the four fixes required a design call I'd flag as risky, but the
`_KEY_RETRY_BACKOFF_SECONDS = 60` addition goes slightly beyond the finding's literal ask
(which named only "serve stale keys, pick a grace window"). I added it because the finding's
own prose also named "every subsequent request re-attempts a 5-second-timeout fetch" as part
of the problem, and serving stale keys without also throttling the retry would still leave
every request blocking on a live network call during a sustained outage. Flagging it as a
judgement call beyond the letter of the finding, in case the reviewer wants it simplified out
or handled differently.

## What was implemented

All four files created verbatim from the brief:

- `src/fenceai/identity/ports.py` — `Principal` (pydantic `BaseModel`, `email` + `subject`,
  `_normalised` field validator strips/lower-cases email) and `IdentityProvider` Protocol
  (`provider_id: str`, `principal(headers, cookies) -> Principal | None`).
- `src/fenceai/identity/dev.py` — `DEV_COOKIE = "fenceai_dev_user"`, `DevIdentity`
  (cookie-then-env, no subject, `None` when nothing names anyone), `dev_identity_from_env()`.
- `src/fenceai/identity/iap.py` — `IAP_HEADER`, `IapIdentity` (audience required at
  construction, `jwt` imported only inside `principal()`, case-insensitive header lookup,
  injectable `fetch_keys` for tests), `iap_identity_from_env()`.
- `src/fenceai/identity/provider.py` — `build_provider()` reading `FENCEAI_IDENTITY` with
  no default; refuses with both `iap` and `dev` named in the message; `iap` branch checks
  `FENCEAI_IAP_AUDIENCE` and only then imports `fenceai.identity.iap`.

Tests created verbatim:
- `tests/identity/test_ports.py` — 8 tests (Principal normalisation, DevIdentity cookie/env/
  none/no-subject, provider refusal/no-default, provider builds dev and iap, iap needs
  audience).
- `tests/identity/test_iap.py` — 9 tests, ES256 key pair generated in-process, real
  `jwt.decode` path exercised (good token, no header, case-insensitive header, wrong signer,
  wrong audience, expired, wrong issuer, unknown kid, empty email), gated by
  `pytest.importorskip("jwt")` / `pytest.importorskip("cryptography")` so the module is
  skipped (not errored) with no extra installed.

`pyproject.toml`: added the `iap` extra (`pyjwt[crypto]>=2.9,<3`) after the `postgres`
extra, with the brief's comment verbatim.

## Deviation from the brief

One addition beyond the brief's file list: `uv.lock` is staged and committed alongside
`pyproject.toml`. The brief's Step 13 `git add` list does not mention it, but
`uv sync --extra postgres --extra iap` (Step 11) regenerated it as a direct, mechanical
consequence of adding the `iap` extra — leaving it unstaged would commit a `pyproject.toml`
whose lockfile is out of sync with it, which is a worse state than including it. No content
in `uv.lock` was hand-edited.

No other deviation. All four source files, both test files, and the `pyproject.toml` addition
match the brief's code blocks exactly.

## Test commands run, with output summary

1. `uv run pytest tests/identity/test_ports.py -q` (before any source file existed)
   → collection `ModuleNotFoundError: No module named 'fenceai.identity.dev'`, as the brief's
   Step 2 expects.

2. After writing `ports.py` + `dev.py` only:
   `uv run pytest tests/identity/test_ports.py -q -k "dev or principal"`
   → still a collection error, `ModuleNotFoundError: No module named 'fenceai.identity.provider'`.
   **This differs from the brief's stated expectation** ("PASS for the Principal and
   DevIdentity tests; the build_provider ones still fail") — because `test_ports.py` imports
   `build_provider` from `fenceai.identity.provider` at module scope (line 14), the whole
   module fails to *collect* before `-k` filtering ever applies, so nothing runs rather than
   a partial pass. This is inherent to the test file's own import list, not a bug I
   introduced, and resolves itself once `provider.py` exists (see next step). Flagging it
   since it's a place the brief's prose and the file's actual behaviour diverge.

3. After writing `iap.py` and `provider.py`:
   `uv run pytest tests/identity/test_ports.py -q`
   → `8 passed in 0.01s`. Matches Step 9's expectation exactly.

4. Before installing the `iap` extra:
   `uv run pytest tests/identity/test_iap.py -q`
   → `1 skipped` (`the \`iap\` extra is not installed`) — confirms the whole module is
   gated cleanly rather than erroring.

5. `uv sync --extra postgres --extra iap` → installed `pyjwt==2.14.0`, `cryptography==50.0.1`,
   `psycopg==3.3.5` and deps.
   `uv run pytest tests/identity/test_iap.py -q` → `9 passed in 0.10s`. Matches Step 11.

6. `uv run pytest tests/identity/ -q` (full identity dir, sanity check for regressions)
   → `43 passed, 8 skipped` (the 8 skips are pre-existing Postgres-store tests, unrelated to
   this task, skipped for lack of a Postgres fixture — not something this task touched).

7. Step 12's offline check, done twice for rigor:
   - In this worktree's venv (which now has `pyjwt` installed from step 5 above):
     `uv run python -c "import fenceai.api.app; import fenceai.identity.provider; print('imports clean')"`
     → `imports clean`, and a follow-up check of `'jwt' in sys.modules` after the import
     printed `False` — i.e. even with `pyjwt` present, nothing at import time touches it.
   - For a stronger guarantee than "installed but unused," I additionally built a **fresh
     throwaway venv with `pyjwt` not installed at all** (`uv venv` + `uv pip install -e .`,
     no extras), confirmed `import jwt` fails there (`ModuleNotFoundError: No module named
     'jwt'`), and then ran the same import check:
     `python -c "import fenceai.api.app; import fenceai.identity.provider; print('imports clean')"`
     → `imports clean`. I also exercised the `FENCEAI_IDENTITY=iap` path in that same
     pyjwt-less venv — `build_provider()` with `FENCEAI_IAP_AUDIENCE` set constructed an
     `IapIdentity` and returned `provider_id: 'iap'` successfully, confirming the
     ambiguity-resolution requirement precisely: construction never imports `jwt`, only
     `IapIdentity.principal()` would. This satisfies "verify both" from the task
     instructions — with the extra installed and, more strongly, in a venv where it
     cannot be silently satisfied by something already present. The throwaway venv was
     deleted afterward; it never touched the worktree's own `.venv`.

## Anything I'm unsure about

Nothing about the implementation itself — all values, names, and code match the brief
verbatim and every named test passes. The one soft spot is noted above under "Deviation":
the brief's Step 5 prose describes a partial-pass outcome that the test file's own
module-level imports make impossible to observe at that point in the sequence; it's cosmetic
and self-resolves by Step 9, but I'm flagging it rather than silently reconciling it, per
CLAUDE.md's instruction not to silently reconcile a disagreement between stated behaviour and
actual behaviour.
