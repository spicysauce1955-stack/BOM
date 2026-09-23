# syntax=docker/dockerfile:1

# ---- builder ----------------------------------------------------------------
FROM python:3.12-slim AS builder

# Pinned, not `:latest`: the thing that resolves the dependency tree is itself a
# dependency, and an unpinned one makes the build unreproducible in the one
# place `--frozen` was supposed to guarantee it.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies in their own layer, before any source: they change when uv.lock
# changes, which is rare, while src/ changes every commit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra postgres --extra iap

# Then the project itself. Both extras again — `uv sync` without them would
# PRUNE what the line above installed.
COPY src ./src
RUN uv sync --frozen --extra postgres --extra iap

# ---- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

# `/app` in both stages, and not a coincidence: `uv sync` installs the project
# as an editable pointer to /app/src/fenceai, so the venv copied below only
# resolves if the source sits at the same absolute path it did at build time.
WORKDIR /app

RUN useradd --create-home --uid 10001 fenceai

COPY --from=builder --chown=fenceai:fenceai /app/.venv /app/.venv
COPY --from=builder --chown=fenceai:fenceai /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER fenceai

# Documentation only — Cloud Run ignores it and injects $PORT instead.
EXPOSE 8080

# Three things, each guarding a named failure:
#   exec          — uvicorn becomes PID 1 and receives Cloud Run's SIGTERM
#   0.0.0.0       — Cloud Run routes to the container's external interface;
#                   127.0.0.1 answers the health check and nobody else
#   ${PORT:-8080} — Cloud Run injects $PORT and does not promise 8080
#
# `core/env.py`'s load_dotenv() prefers real environment variables, so it is a
# harmless no-op here and no .env is needed or wanted (spec §6).
CMD ["sh", "-c", "exec uvicorn fenceai.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
