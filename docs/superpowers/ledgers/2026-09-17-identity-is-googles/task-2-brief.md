### Task 2: `subject`, and the decision to bind it

Still pure domain. `User` gains a field and loses nothing yet — the password machinery is still referenced by `app.py` and comes out in Task 5.

**Files:**
- Modify: `src/fenceai/identity/model.py:56-100`
- Create: `src/fenceai/identity/binding.py`
- Test: `tests/identity/test_binding.py`

**Interfaces:**
- Consumes: `Principal` from Task 1.
- Produces: `User.subject: str`; `bind(user: User, principal: Principal) -> Literal["ok", "bound", "mismatch"]`, which MUTATES `user.subject` only on `"bound"`.

- [ ] **Step 1: Write the failing test**

Create `tests/identity/test_binding.py`:

```python
"""Binding Google's `sub` to a row that was created by email.

Rows are found by EMAIL, because an admin grants Dana her capacity on Monday and
Dana arrives on Tuesday. `subject` is therefore verification and not a key — it
answers "is this still the same Google account?" and nothing else.
"""

from __future__ import annotations

from fenceai.identity.binding import bind
from fenceai.identity.model import User
from fenceai.identity.ports import Principal


def _row(**kw) -> User:
    return User(id="u_dana", name="Dana", email="dana@example.com",
                capacity="sales", **kw)


def test_an_empty_subject_binds_on_first_arrival():
    user = _row()
    assert bind(user, Principal(email="dana@example.com", subject="sub-1")) == "bound"
    assert user.subject == "sub-1"


def test_the_same_subject_arriving_again_changes_nothing():
    user = _row(subject="sub-1")
    assert bind(user, Principal(email="dana@example.com", subject="sub-1")) == "ok"
    assert user.subject == "sub-1"


def test_a_different_subject_on_the_same_address_is_refused():
    """The address belonged to one Google account and now presents another —
    a deleted-and-recreated Workspace account, or something worth a person
    looking at. An admin reconciles it; the app never does, because silently
    rebinding would hand the row to whoever holds the address today."""
    user = _row(subject="sub-1")
    assert bind(user, Principal(email="dana@example.com", subject="sub-2")) == "mismatch"
    assert user.subject == "sub-1", "a refused binding must not have written"


def test_a_principal_with_no_subject_binds_nothing_and_refuses_nothing():
    """`DevIdentity` carries no subject. It must neither bind an empty string
    (which would then mismatch the real `sub` for ever) nor be refused against
    a row a real sign-in has already bound."""
    fresh = _row()
    assert bind(fresh, Principal(email="dana@example.com", subject="")) == "ok"
    assert fresh.subject == ""

    bound = _row(subject="sub-1")
    assert bind(bound, Principal(email="dana@example.com", subject="")) == "ok"
    assert bound.subject == "sub-1"


def test_subject_defaults_to_empty_on_a_row_nobody_has_signed_in_as():
    assert _row().subject == ""
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/identity/test_binding.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fenceai.identity.binding'`

- [ ] **Step 3: Add `subject` to `User`**

In `src/fenceai/identity/model.py`, immediately after the `capacity` field and before `active`:

```python
    #: Google's stable `sub` claim, bound on this person's first arrival and
    #: never used to FIND them. Rows are created by email, because an admin
    #: grants Dana her capacity before Dana has ever signed in. This is the
    #: field that then answers "is this still the same Google account?" —
    #: see `identity/binding.py`. Empty means nobody has arrived yet.
    subject: str = ""
```

- [ ] **Step 4: Write `binding.py`**

```python
"""Is this arrival the same Google account the row was bound to?

One pure function with three answers, kept out of the gate so the decision can
be read and tested without a request. The gate turns `"mismatch"` into a 403 and
persists the row on `"bound"`.
"""

from __future__ import annotations

from typing import Literal

from fenceai.identity.model import User
from fenceai.identity.ports import Principal

Outcome = Literal["ok", "bound", "mismatch"]


def bind(user: User, principal: Principal) -> Outcome:
    """`"bound"` means the caller must SAVE the row; `"ok"` means it must not.

    A principal with no subject binds nothing. `DevIdentity` has no Google
    behind it, and writing its empty string as a subject would make the real
    person's first arrival a `mismatch` against a value nobody set.
    """
    if not principal.subject:
        return "ok"
    if not user.subject:
        user.subject = principal.subject
        return "bound"
    return "ok" if user.subject == principal.subject else "mismatch"
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/identity/test_binding.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the identity suite and the API suite**

Run: `uv run pytest tests/identity tests/api -q`
Expected: PASS — `subject` has a default, so every existing row still validates.

- [ ] **Step 7: Commit**

```bash
git add src/fenceai/identity/model.py src/fenceai/identity/binding.py \
        tests/identity/test_binding.py
git commit -m "feat(identity): User.subject, bound on first arrival and never used to find a row"
```

---

