### Task 10: Fitness test, docs, ADR, and the smoke suite

**Files:**
- Modify: `tests/architecture/test_fitness.py`, `docs/architecture/04-backend.md:135-160`, `tools/ui_smoke.py`, `.env.example`
- Create: `docs/adr/0013-identity-is-delegated.md`

**Interfaces:**
- Consumes: `EXEMPT_PATHS` (Task 3).
- Produces: nothing new.

- [ ] **Step 1: Write the failing fitness test**

Append to `tests/architecture/test_fitness.py`:

```python
def test_every_api_route_is_gated_by_the_app_itself():
    """Not route by route. Seventy routes were born ungated by omission, and
    the only fix that cannot be forgotten is one dependency on the app."""
    from fastapi import Depends
    from fenceai.api.app import app
    assert app.router.dependencies, "the app carries no gate"


def test_the_exempt_list_is_exactly_what_it_should_be():
    """An exemption is a hole, so adding one is a deliberate edit HERE as well
    as there. Each of these four has a sentence in `api/auth.py` saying why."""
    from fenceai.api.auth import EXEMPT_PATHS
    assert EXEMPT_PATHS == frozenset({
        "/api/health", "/api/session", "/api/dev/identity",
    })


def test_every_exempt_path_is_a_route_that_exists():
    """An exemption for a path nobody serves is a stale hole waiting for a
    route to be added onto it."""
    from fenceai.api.auth import EXEMPT_PATHS
    assert EXEMPT_PATHS <= _route_paths()
```

- [ ] **Step 2: Run the architecture suite**

Run: `uv run pytest tests/architecture -q`
Expected: FAIL on the route count and route table tests (the routes changed), PASS on the three new ones.

- [ ] **Step 3: Update `04-backend.md`**

Change `74 routes.` at line 135 to the number the test reports. Replace the Identity row (line 157) with:

```
| Identity | `GET /api/session`, `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST/DELETE /api/dev/identity` (dev only) | **Google holds the identity; a row here holds the capacity.** There is no password in this app and no session of ours: under `iap` a signed `X-Goog-IAP-JWT-Assertion` names the person before the request arrives, verified against Google's keys with the `aud` checked, because the plain header is spoofable by anything that reaches the service directly. `users` is a capacity assignment table — rows are created BY EMAIL before that person has ever signed in, and `subject` (Google's `sub`) binds on first arrival and is never used to FIND a row. A subject arriving on an address bound to a different one is `subject_mismatch`, refused and audited, because an admin reconciles that and the app must not hand the row to whoever holds the address today. **Every route in this table is gated**: one app-level dependency refuses `no_identity` · `no_capacity` · `account_deactivated` · `subject_mismatch` · `capacity_insufficient`, and the exempt list is four paths pinned by `tests/architecture/test_fitness.py`. `GET /api/session` is the one that answers without a row, because the screen telling somebody to ask an admin has to name them to the admin they are about to ask. Signing out is a redirect to IAP's logout — revoking access is central and for every device at once, which the app could never promise; `active=False` is the local half that still refuses. `FENCEAI_BOOTSTRAP_ADMIN` admits the first admin and self-disables the moment one exists |
```

Update the table count line if the `sessions` table removal changed it.

- [ ] **Step 4: Run the architecture suite again**

Run: `uv run pytest tests/architecture -q`
Expected: PASS.

- [ ] **Step 5: Write ADR-0013**

Create `docs/adr/0013-identity-is-delegated.md` following ADR-0012's shape: context (a local password store and 70 open routes behind a login screen), decision (delegate identity to Google through a port; make `users` a capacity table; default-deny at the app), consequences (signing out stops being ours; `active=False` is the local half; a dev provider keeps the offline property; per-capacity authorization is still a separate slice), and alternatives rejected (mirroring Google accounts locally; auto-creating every IAP arrival as `sales`; gating route by route).

- [ ] **Step 6: Update `.env.example`**

```
# No default. Must be `dev` or `iap`, or the app refuses to boot.
FENCEAI_IDENTITY=dev
# Who a bare `uvicorn` opens as, when no picker cookie has been set.
FENCEAI_DEV_USER=admin@example.com
# IAP only: the backend service the assertion must be addressed to.
FENCEAI_IAP_AUDIENCE=
# Set for the first deploy, removed after. Self-disables once an admin exists.
FENCEAI_BOOTSTRAP_ADMIN=
```

- [ ] **Step 7: Move the smoke suite onto the picker**

In `tools/ui_smoke.py`: launch the server with `FENCEAI_IDENTITY=dev`; replace the two `fetch('/api/session', {method:'POST', ... password ...})` calls (around lines 2673 and 3680) with `fetch('/api/dev/identity', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email:'dana@example.com'})})`; replace the `DELETE /api/session` (line 2690) with `DELETE /api/dev/identity`; and delete the line setting `sign-in-password`.

- [ ] **Step 8: Run the smoke suite**

Run: `uv run --with websocket-client python tools/ui_smoke.py`
Expected: every check passes. A failure here is a real one — this is the only place the picker, the no-access screen and the people panel are exercised in a browser.

- [ ] **Step 9: Run everything**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest -q && uv run pytest tests/scenarios -q && uv run pytest tests/architecture -q`
Expected: all PASS.

- [ ] **Step 10: Verify the offline and zero-setup properties**

Run:
```bash
cd $(mktemp -d) && git clone <repo> fa && cd fa && uv sync && \
  FENCEAI_IDENTITY=dev FENCEAI_DEV_USER=admin@example.com \
  uv run python -c "
from fastapi.testclient import TestClient
from fenceai.api.app import app
with TestClient(app) as c:
    print(c.get('/api/session').json()['status'])"
```
Expected: `ok` — a clean clone, no extras, no Postgres, no Google, and the app resolves the seeded admin.

- [ ] **Step 11: Commit**

```bash
git add tests/architecture/test_fitness.py docs/architecture/04-backend.md \
        docs/adr/0013-identity-is-delegated.md .env.example tools/ui_smoke.py
git commit -m "docs(adr): ADR-0013, the route table, and a smoke suite with no password in it"
```

---

