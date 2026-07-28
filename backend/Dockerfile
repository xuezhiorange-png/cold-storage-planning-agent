# TASK-012 Slice 2: production-oriented backend image.
#
# This Dockerfile is the single producer of `/opt/cold-storage/build-identity.json`.
# It MUST be the only authority at runtime — see bootstrap.deployment_identity.
# The image runs as a non-root user, installs dependencies from the lockfile
# without updating it, and copies only the runtime source. Build-time secrets
# and tracked `.env` files are excluded.
#
# Build invocation (CI):
#   docker build -f backend/Dockerfile \
#       --build-arg COLD_STORAGE_BUILD_COMMIT_SHA=<sha> \
#       --build-arg COLD_STORAGE_BUILD_VERSION=<version> \
#       -t cold-storage-backend:<sha> \
#       .
#
# Runtime env vars (passed in by docker-compose.production.yml):
#   COLD_STORAGE_BUILD_COMMIT_SHA  (must match the file baked at build time)
#   COLD_STORAGE_BUILD_VERSION     (must match the file baked at build time)
#   COLD_STORAGE_DEPLOYMENT_ID     (deployment-instance identifier)

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install uv once for the builder stage. We pin via a multi-stage layout to
# keep the final image minimal.
RUN pip install --no-cache-dir uv==0.5.11

# Bring in the lockfile first to maximize layer cache and forbid mutation.
COPY backend/uv.lock /build/backend/uv.lock
COPY backend/pyproject.toml /build/backend/pyproject.toml

WORKDIR /build/backend
RUN uv sync --frozen --no-install-project --no-dev

# Copy only the runtime source we need.
COPY backend/src /build/backend/src
COPY backend/alembic /build/backend/alembic
COPY backend/alembic.ini /build/backend/alembic.ini

# Build-time identity is rendered into the immutable authority file. We use
# ARG defaults that the CI provides explicitly so the file is exact and
# reproducible.
ARG COLD_STORAGE_BUILD_COMMIT_SHA=unknown0000000000000000000000000000000000000
ARG COLD_STORAGE_BUILD_VERSION=v0.0.0

# Bake the build-identity file. The builder stage uses a tiny Python one-liner
# that produces deterministic UTF-8 JSON with the exact frozen key set in the
# exact frozen order (D-S2-02.a).
RUN python - <<'PY'
import json, os, pathlib, sys
out = pathlib.Path("/build/backend/build-identity.json")
data = {
    "schema_version": 1,
    "commit_sha": os.environ.get("COLD_STORAGE_BUILD_COMMIT_SHA", "unknown0000000000000000000000000000000000000"),
    "version": os.environ.get("COLD_STORAGE_BUILD_VERSION", "v0.0.0"),
}
out.write_text(json.dumps(data, separators=(", ", ": "), ensure_ascii=False) + "\n", encoding="utf-8")
sys.exit(0)
PY
ENV COLD_STORAGE_BUILD_COMMIT_SHA=${COLD_STORAGE_BUILD_COMMIT_SHA}
ENV COLD_STORAGE_BUILD_VERSION=${COLD_STORAGE_BUILD_VERSION}

# Run the actual install with --no-dev to keep the runtime slim.
RUN uv sync --frozen --no-install-project --no-dev

# --- final stage ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COLD_STORAGE_APP_HOST=0.0.0.0 \
    COLD_STORAGE_APP_PORT=8000

# Required system packages for psycopg2-binary wheels and font fallback used
# by deterministic PDF rendering smoke checks. CJK font is intentionally NOT
# installed here; it is shipped only via CI environment when needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user. The contract requires the image NOT to run as root.
RUN groupadd --system --gid 1001 coldstorage \
    && useradd  --system --uid 1001 --gid coldstorage \
                --home-dir /opt/cold-storage --shell /usr/sbin/nologin \
                coldstorage

# Copy the installed virtualenv and source from the builder.
COPY --from=builder --chown=root:root /build/backend/.venv /opt/cold-storage/.venv
COPY --from=builder --chown=root:root /build/backend/src /opt/cold-storage/src
COPY --from=builder --chown=root:root /build/backend/alembic /opt/cold-storage/alembic
COPY --from=builder --chown=root:root /build/backend/alembic.ini /opt/cold-storage/alembic.ini

# Bake the immutable build-identity file. owner=root, mode=0444.
# This file is the single source of truth for build identity at runtime
# (D-S2-02.a). The in-container application user MUST NOT be able to
# modify it.
COPY --from=builder --chown=root:root --chmod=0444 \
     /build/backend/build-identity.json /opt/cold-storage/build-identity.json

# Ensure the runtime user owns the runtime directories it actually needs.
RUN mkdir -p /opt/cold-storage/artifacts \
    && chown -R coldstorage:coldstorage /opt/cold-storage/artifacts \
    && chmod 0755 /opt/cold-storage/artifacts

ENV PATH="/opt/cold-storage/.venv/bin:${PATH}" \
    PYTHONPATH=/opt/cold-storage/src

USER coldstorage
WORKDIR /opt/cold-storage

# Use the production entrypoint that runs identity cross-checks and probe
# timeout validation before handing off to uvicorn.
ENTRYPOINT ["python", "-m", "cold_storage.bootstrap.production_entrypoint"]
