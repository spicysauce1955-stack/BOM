### Task 5: Delete the password machinery

Nothing references it after Task 3. This task is pure subtraction, and a reviewer can accept Task 3 and reject this one.

**Files:**
- Modify: `src/fenceai/identity/model.py` (remove `password_hash`, `set_password`, `verify_password`, the scrypt constants, `hashlib`/`hmac`/`os` imports)
- Delete: `src/fenceai/identity/session.py`
- Modify: `src/fenceai/store/db.py:79-85` and `:952-975`
- Modify: `src/fenceai/api/app.py:2140-2161` (`_seed_demo_accounts`)
- Modify: `tests/identity/test_user.py`, `tests/identity/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a `User` with no credential; a `Store` with no session methods.

- [ ] **Step 1: Write the failing test**

Append to `tests/identity/test_user.py`:

```python
def test_an_account_carries_no_credential_at_all():
    """Not "an empty password" — no field. Google holds the identity; this row
    holds what that identity may do. A credential here would be the second
    password this slice exists to delete."""
    u = User(id="u_dana", name="Dana", email="dana@example.com", capacity="sales")
    assert not hasattr(u, "password_hash")
    assert not hasattr(u, "set_password")
    assert "password" not in u.model_dump()


def test_the_model_module_offers_no_way_to_verify_one():
    import fenceai.identity.model as model
    assert not hasattr(model, "verify_password")


def test_there_is_no_session_module_left():
    import importlib
    import pytest
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fenceai.identity.session")
```

Append to `tests/store/test_dialect.py` (or `tests/identity/test_store.py`):

```python
def test_the_store_no_longer_keeps_sessions():
    """The row WAS the session, and there are no sessions. An existing SQLite
    file keeps its table — dropping it from the baseline does not remove it,
    and per the deployment spec §4 that is not worth a migration — but nothing
    creates or reads one."""
    from fenceai.store import db
    assert "CREATE TABLE IF NOT EXISTS sessions" not in db._SCHEMA
    for name in ("save_session", "session", "delete_session", "delete_sessions_for"):
        assert not hasattr(db.Store, name), name
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/identity tests/store/test_dialect.py -q`
Expected: FAIL on all four new tests.

- [ ] **Step 3: Strip the credential from `User`**

In `src/fenceai/identity/model.py`: delete the `password_hash` field, `set_password`, `verify_password`, `_SCRYPT`, `_SALT_BYTES`, and the now-unused `hashlib`, `hmac` and `os` imports. Update the `User` docstring — it currently says *"`verify_password` refuses it"*, which will name a function that no longer exists:

```python
    """A person with an account.

    **Deactivated, never deleted.** The audit log names people who have left the
    company, so a row has to keep resolving to a name for ever. `active=False`
    is what a company does instead, and `api/auth.py`'s gate refuses it — the
    two halves of that decision belong together or deactivating becomes a label
    somebody still signs in behind.

    **There is no credential here.** Google holds the identity; this row holds
    what that identity may DO. `subject` records which Google account it was
    bound to and is never used to find the row.
    """
```

- [ ] **Step 4: Delete `session.py` and the store's session half**

```bash
git rm src/fenceai/identity/session.py
```

In `src/fenceai/store/db.py`, delete the `sessions` table from `_SCHEMA` (lines 81-85, comment included) and the four session methods (lines 952-975). Rename the section comment at line 928 from `-- accounts and sessions` to `-- capacity assignments`, and add above `save_user`:

```python
    # The `users` table is no longer an account store. Google holds the
    # identity; a row here says what an identity may DO. `sessions` was deleted
    # with the password store — an existing SQLite file keeps the table, which
    # nothing creates or reads.
```

- [ ] **Step 5: Make the demo rows passwordless**

In `src/fenceai/api/app.py`, replace the `DEMO_ACCOUNTS` comment and `_seed_demo_accounts`:

```python
#: One capacity row per capacity, so a fresh database has somebody to be. They
#: carry NO credential, which is what makes them safe to keep: under IAP a row
#: only matters if Google authenticates that address, and `example.com` is
#: IANA-reserved, so nobody ever can. A real deployment grants its own people
#: through `POST /api/users` and these three never resolve.
DEMO_ACCOUNTS = [
    ("u_dana", "Dana", "dana@example.com", "sales"),
    ("u_yossi", "Yossi", "yossi@example.com", "backoffice"),
    ("u_admin", "Admin", "admin@example.com", "admin"),
]


def _seed_demo_accounts() -> None:
    """Only on an empty table. A company that has made its own accounts must
    never find three strangers in the list after an upgrade."""
    if state.store.list_users():
        return
    for uid, name, email, capacity in DEMO_ACCOUNTS:
        state.store.save_user(
            User(id=uid, name=name, email=email, capacity=capacity), actor="seed")
```

Delete `DEMO_PASSWORD`.

- [ ] **Step 6: Purge the remaining references**

Run: `grep -rn "password\|set_password\|verify_password\|DEMO_PASSWORD\|identity.session\|fenceai_session" src/ tests/ tools/`
Expected: only `autocomplete="username"` in `index.html` (Task 8 removes the password input) and the new tests asserting absence. Fix `tests/identity/test_store.py`, `tests/api/test_command_route.py` and `tests/api/test_queue_route.py` by replacing `_account(..., password=...)` + `_sign_in(...)` with a saved `User` and `client.cookies.set(DEV_COOKIE, email)`.

- [ ] **Step 7: Run the full suite**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -u src/fenceai/identity/model.py src/fenceai/store/db.py \
        src/fenceai/api/app.py tests/identity tests/store/test_dialect.py \
        tests/api/test_command_route.py tests/api/test_queue_route.py
git commit -m "refactor(identity): delete the password store, the sessions table and the cookie"
```

---

