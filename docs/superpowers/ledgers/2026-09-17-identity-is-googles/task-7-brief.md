### Task 7: The eleven `?author=` parameters

**Files:**
- Modify: `src/fenceai/api/app.py` — lines 914, 1215, 1292, 1387, 1626, 1697, 1763, 1783, 1818, 1841, 1860
- Modify: any test passing `?author=`

**Interfaces:**
- Consumes: `_actor` (Task 3).
- Produces: eleven routes whose actor is the caller and nothing else.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_gate.py`:

```python
def test_no_route_still_lets_a_caller_name_the_actor():
    """`_actor`'s docstring called it: "an actor a client can NAME is not an
    audit trail". The parameter survived only as the fallback for the
    unsigned-in case, and default-deny deleted that case."""
    import inspect
    from fenceai.api import app as app_module
    offenders = []
    for route in app_module.app.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None:
            continue
        if "author" in inspect.signature(fn).parameters:
            offenders.append(f"{route.path} ({fn.__name__})")
    assert not offenders, offenders
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/api/test_gate.py::test_no_route_still_lets_a_caller_name_the_actor -q`
Expected: FAIL listing eleven routes.

- [ ] **Step 3: Remove them one file-scan at a time**

For each of the eleven sites, delete the `author: str = "user"` (or `"expert"`) parameter and replace every use of `author` in the body with `_actor(request)`. Add `request: Request` to any handler that does not already take one. Example, at line 1292:

```python
# before
def accept_quote(request: Request, quote_id: str, author: str = "user") -> Quote:
    ...
    state.store.save_quote(q, actor=_actor(request, author))

# after
def accept_quote(request: Request, quote_id: str) -> Quote:
    ...
    state.store.save_quote(q, actor=_actor(request))
```

- [ ] **Step 4: Run it again**

Run: `uv run pytest tests/api/test_gate.py::test_no_route_still_lets_a_caller_name_the_actor -q`
Expected: PASS.

- [ ] **Step 5: Fix the callers**

Run: `grep -rn "author=" tests/ tools/ src/fenceai/web/`
Expected: every hit is a test or a frontend `fetch` passing the query. Delete the parameter from each; the actor is now the caller.

- [ ] **Step 6: Run the full suite**

Run: `export FENCEAI_TEST_POSTGRES=postgresql://postgres:test@localhost:5432/postgres && uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -u src/fenceai/api/app.py src/fenceai/web/static tests/
git commit -m "refactor(api): the actor is the caller, at all eleven sites that let it be named"
```

---

