# Task 6 Report: CI builds the image

## Summary
Successfully added the `container` CI job to `.github/workflows/tests.yml` as a sibling of the existing `pytest` job. The job builds the Docker image and runs the gated tests with `FENCEAI_TEST_DOCKER=1` set.

## What was done

### Step 1: Added the container job
- Modified `.github/workflows/tests.yml` to append the `container` job with proper YAML indentation matching the existing `pytest` job
- Job configuration:
  - Runs on `ubuntu-latest`
  - Sets `FENCEAI_TEST_DOCKER: "1"` environment variable
  - Uses `actions/checkout@v4` and `astral-sh/setup-uv@v5`
  - Runs `uv sync` with no extras (as specified)
  - Runs `uv run pytest tests/deploy -q`
- All comments from the brief were preserved verbatim, including the explanation for why no extras are installed

### Step 2: Verified YAML syntax
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/tests.yml')); print('yaml ok')"
```
Result: `yaml ok`
- PyYAML was installed, so step was not skipped

### Step 3: Reproduced the job locally
```bash
FENCEAI_TEST_DOCKER=1 uv run pytest tests/deploy -q
```
Result: `.............                                                            [100%]
13 passed in 12.75s`

Real test count: **13 passed** (matches expected: 6 Dockerfile + 3 compose + 4 container)

### Step 4: Committed the changes
```bash
git add .github/workflows/tests.yml
git commit -m "ci: build the image and run it, on every PR

No registry and no deploy — those stay slice 5's. But a container test
that nothing runs proves nothing, which is the ruling slice 1's amendment
already made about the dual-run.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```
Commit: `2a38ae3`

## Deviations from brief
None. The job was added exactly as specified, YAML was verified to parse, the test runs successfully locally with 13 passed, and the commit message follows the specified format with the correct attribution.

## Concerns
None. The workflow is ready for CI.
