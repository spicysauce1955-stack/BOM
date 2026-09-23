# Task 2 report — the image, actually built and actually run

Worktree: `/home/user/.superset/projects/BOM/.claude/worktrees/slice3-container-postgres`

## What was done

Created `tests/deploy/test_container.py`, verbatim from the brief, with the one
correction specified in the task instructions applied: the `image` fixture takes
`_require_docker` as an explicit parameter —

```python
@pytest.fixture(scope="module")
def image(_require_docker) -> str:
```

— rather than relying on pytest's autouse-first ordering to run the gate before the
multi-minute docker build. Everything else in the file is the brief's text unchanged:
the asymmetric gate (`_require_docker`), the module-scoped `image` build fixture, the
`_Container` helper, the `run_container` fixture that always removes what it started,
`_wait_healthy` (condition-based, prints container logs on timeout), and the four tests
(both extras present, `$PORT` + `0.0.0.0` bind, boots under `iap` against a fresh DB,
runs as uid 10001 not root).

`tests/deploy/__init__.py` and `tests/deploy/test_dockerfile.py` were not touched.

## Commands run, and their output

### Step 2 — ungated: must skip

```
$ uv run pytest tests/deploy/test_container.py -q
ssss                                                                     [100%]
=========================== short test summary info ============================
SKIPPED [1] tests/deploy/test_container.py:123: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:131: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:139: set FENCEAI_TEST_DOCKER=1 to build and run the image
SKIPPED [1] tests/deploy/test_container.py:152: set FENCEAI_TEST_DOCKER=1 to build and run the image
4 skipped in 0.02s
```

### Step 3 — gated: must build and pass

```
$ FENCEAI_TEST_DOCKER=1 uv run pytest tests/deploy/test_container.py -q
....                                                                     [100%]
4 passed in 3.45s
```

3.45s, not "a few minutes" — because Task 1's manual build already produced
`fenceai:slice3` from the same Dockerfile and build context, and Docker's build cache
is content-addressed rather than tag-addressed. `docker images` confirms
`fenceai-test:slice3` and `fenceai:slice3` share image ID `2b55a5d9e943`: a full
layer-cache hit, not a skipped build. Re-ran it a second time afterward (see below) and
it stayed at ~3.5s and 4 passed, confirming this isn't a one-off fluke.

`docker ps -a` after this run showed only the pre-existing `fenceai-test-pg` container
and two unrelated long-stopped containers from other work — every container the test
started was removed by `run_container`'s teardown.

### Step 4 — asymmetric gate: must FAIL, not skip

`PATH=/nonexistent` alone breaks `uv` itself (it's resolved via PATH), so the brief's
literal command needed `uv` invoked by absolute path to isolate the failure to the
`docker` subprocess call inside the test rather than to launching pytest at all:

```
$ FENCEAI_TEST_DOCKER=1 PATH=/nonexistent /home/user/.local/bin/uv run pytest tests/deploy/test_container.py -q
...
E                   FileNotFoundError: [Errno 2] No such file or directory: 'docker'
...
E           Failed: FENCEAI_TEST_DOCKER is set but the Docker daemon did not answer
            (FileNotFoundError(2, 'No such file or directory')) — a container job that
            skips its own tests passes while proving nothing

tests/deploy/test_container.py:46: Failed
=========================== short test summary info ============================
ERROR tests/deploy/test_container.py::test_the_image_carries_both_extras - Fa...
ERROR tests/deploy/test_container.py::test_the_server_answers_on_the_port_it_was_given
ERROR tests/deploy/test_container.py::test_it_boots_under_iap_on_a_database_with_no_dev_seed
ERROR tests/deploy/test_container.py::test_the_container_does_not_run_as_root
4 errors in 0.13s
```

FAILED (surfaced as pytest ERRORs from the failing module-scoped fixture, not exit-0
skips) with exactly the message the brief names: "the Docker daemon did not answer".
This is the property the brief calls out as mattering more than the rest, and it fires.

### Final cleanup check

```
$ docker ps -a
CONTAINER ID   IMAGE          ...   NAMES
38324f47bcf2   postgres:16    ...   fenceai-test-pg          (pre-existing, untouched)
77f39b742a98   barak-test-img ...   barak-test-6fcf1fb2       (pre-existing, unrelated)
8d51a3d5d6fb   gcr.io/... kicbase ...   minikube              (pre-existing, unrelated)
```

Nothing left behind by this task's tests.

## Surprises

- The gated run (Step 3) completing in 3.45s instead of "a few minutes" surprised me
  until `docker images` explained it: the image tag is different from Task 1's
  (`fenceai-test:slice3` vs `fenceai:slice3`) but the Dockerfile and build context are
  byte-identical, so every layer was already cached from Task 1's manual build. This is
  consistent with the brief's own comment on the `image` fixture ("The image is left
  behind deliberately: it is layer-cached") — it just meant it was reused across a
  differently-tagged build in the same worktree, not only across repeated test runs
  with the same tag.
- `PATH=/nonexistent` on its own breaks `uv` before it ever reaches the test, since `uv`
  itself is resolved via `$PATH`. Ran `uv` by its absolute path
  (`/home/user/.local/bin/uv`, confirmed via `which uv`) so that the broken `PATH` only
  reached the `docker` subprocess call inside `_require_docker`, which is the actual
  target of Step 4's proof.

## Changes relative to the brief

- Only the one correction specified in the task instructions: `image(_require_docker)`
  instead of `image()`, for the reason given there (make the gate-before-build edge
  explicit rather than relying on fixture ordering).

## Full-suite count (not run here, per instructions)

Per the task instructions, the full suite was not run (another agent may need the
ports this repo's tests bind). Expected effect, per the baseline given: 3998 passed
stays 3998 passed; skips move from 1 to 5 (this file's 4 skips, ungated).
