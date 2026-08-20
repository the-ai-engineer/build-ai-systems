# One image, two runtimes.
#
# The webhook and the worker are the same code with different composition
# roots, so they are the same image with different commands. Nothing in here
# knows which one it will become:
#
#   uvicorn support_agent_app.api.main:create_app    --factory --port 8080
#   uvicorn support_agent_app.worker.main:create_app --factory --port 8080
#
# The default command is the webhook. The worker overrides it, and the later
# maintenance jobs will override it too.
#
# Build and push it with scripts/build-and-push.sh.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build

# Compile to bytecode so the first request does not pay for it, copy rather
# than hardlink because the cache mount and the target are different volumes,
# and never reach for a Python that is not already in the base image.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /srv

# Dependencies first, without the application. A change to app/ then reuses
# this layer instead of resolving and downloading 249 packages again.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# --no-editable installs a real copy into the virtual environment, so the
# runtime stage needs the environment and nothing else.
#
# No cache mount here, deliberately. The project version does not change on
# every commit, so a shared uv cache hands back the wheel it built for 0.1.0
# last time and the image ships yesterday's code with today's tag. Building
# this one wheel takes under a second; the dependencies above are the slow part
# and they keep their cache.
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/srv/.venv/bin:${PATH}"

# An unprivileged identity that owns nothing it runs. The environment is
# copied as root, so the application cannot rewrite its own dependencies.
RUN useradd --system --create-home --uid 10001 support

COPY --from=build --chown=root:root /srv/.venv /srv/.venv

# ARCHITECTURE rule 8: fixture adapters are never the production default.
# WORKER_MODEL_SOURCE already defaults to "configured", so this is the second
# lock rather than the first. Deleting them means a deployment cannot answer an
# employee from a canned model even if someone asks for the fixture by mistake.
#
# The second half is the part that matters: if a base image moves to another
# Python version the path changes, the delete quietly removes nothing, and the
# fixtures ship. Then this build fails instead.
RUN rm -rf /srv/.venv/lib/python*/site-packages/support_agent_app/testing \
    && ! python -c "import support_agent_app.testing" 2>/dev/null

# The schema and the approved policy set, for the operator commands only.
# Neither runtime reads them: the webhook and the worker read the database, and
# ARCHITECTURE rule 7 keeps schema out of startup. They are here because
# `apply-migrations` and `seed-policies` run as Cloud Run jobs from this same
# image, and a job cannot apply a migration it does not carry.
#
# A fixed path, not one relative to the installed package. Both commands take
# the directory as an argument, so the path the job passes is the path the
# image holds and nothing resolves it by guesswork.
COPY --chown=root:root migrations /srv/migrations
COPY --chown=root:root policies /srv/policies

WORKDIR /srv
USER support

# Cloud Run's default container port. Both runtimes listen on it; only the
# webhook is reachable from outside.
EXPOSE 8080

CMD ["uvicorn", "support_agent_app.api.main:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8080"]
