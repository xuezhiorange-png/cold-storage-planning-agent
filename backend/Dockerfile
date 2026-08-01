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
# ARG without defaults so CI MUST pass explicit values; the builder stage
# fails closed if either identity key is empty or malformed, never silently
# writing a placeholder into the in-image authority (D-S2-02 + F-S2-REVIEW-007).
ARG COLD_STORAGE_BUILD_COMMIT_SHA
ARG COLD_STORAGE_BUILD_VERSION

# F-PR76-HIGH-04: the build-version regex MUST match the frozen
# Slice 2 contract D-S2-02.d exactly. It is byte-equivalent to
# ``bootstrap.deployment_identity._BUILD_VERSION_PATTERN`` so the
# Dockerfile and the runtime authority agree on a single source of
# truth. Any character class or length divergence from the runtime
# pattern is a contract violation.
#
# Contract surface (D-S2-02.d):
#   * pattern: ^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$
#   * ASCII_ONLY=true
#   * MIN_BYTES=1, MAX_BYTES=64
#   * NORMALIZATION=NONE  (no trim, no lower-case, no separator swap)
#
# The runtime authority implements the exact same pattern via
# :func:`bootstrap.deployment_identity.is_safe_build_version`. CI
# tests assert equivalence by importing the runtime validator and
# running it against every positive / negative example the
# contract freezes.
RUN python - <<'PY'
import json, os, pathlib, re, sys

# F-PR76-HIGH-04: keep the Dockerfile regex identical to the frozen
# runtime contract. Any drift breaks the build-version authority.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_VER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$")

commit_sha = os.environ.get("COLD_STORAGE_BUILD_COMMIT_SHA", "")
version = os.environ.get("COLD_STORAGE_BUILD_VERSION", "")

if not commit_sha:
    sys.stderr.write(
        "build error: COLD_STORAGE_BUILD_COMMIT_SHA is empty; "
        "DOCKER BUILD IDENTITY MUST BE PASSED EXPLICITLY (F-S2-REVIEW-007)\n"
    )
    sys.exit(1)
if not _SHA_RE.match(commit_sha):
    sys.stderr.write(
        f"build error: COLD_STORAGE_BUILD_COMMIT_SHA={commit_sha!r} "
        "is not a 40-char lowercase hex SHA\n"
    )
    sys.exit(1)

if not version:
    sys.stderr.write(
        "build error: COLD_STORAGE_BUILD_VERSION is empty; "
        "DOCKER BUILD IDENTITY MUST BE PASSED EXPLICITLY (F-S2-REVIEW-007)\n"
    )
    sys.exit(1)
# Strict contract validation: ASCII-only, 1..64 bytes, no
# normalisation, leading character is ASCII alphanumeric.
try:
    raw_version = version.encode("ascii", errors="strict")
except UnicodeEncodeError:
    sys.stderr.write(
        f"build error: COLD_STORAGE_BUILD_VERSION={version!r} "
        "contains non-ASCII bytes (F-PR76-HIGH-04)\n"
    )
    sys.exit(1)
if not _VER_RE.match(version):
    sys.stderr.write(
        f"build error: COLD_STORAGE_BUILD_VERSION={version!r} "
        "does not match the frozen D-S2-02.d ASCII pattern\n"
    )
    sys.exit(1)
if raw_version[0:1] in (b".", b"_", b"+", b"-"):
    sys.stderr.write(
        f"build error: COLD_STORAGE_BUILD_VERSION={version!r} "
        "has a forbidden leading punctuation byte\n"
    )
    sys.exit(1)

out = pathlib.Path("/build/backend/build-identity.json")
data = {
    "schema_version": 1,
    "commit_sha": commit_sha,
    "version": version,
}
out.write_text(
    json.dumps(data, separators=(", ", ": "), ensure_ascii=False) + "\n",
    encoding="utf-8",
)
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
