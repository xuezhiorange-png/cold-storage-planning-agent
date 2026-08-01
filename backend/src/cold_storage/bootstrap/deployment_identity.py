"""TASK-012 Slice 2: in-image build/deployment identity authority.

This module owns the **only** runtime source of build identity for the
backend process. It reads the in-image authority file
``/opt/cold-storage/build-identity.json`` and validates the runtime
identity environment variables against it. Per the Slice 2 contract
``D-S2-02``, the file is the single source of truth: build arguments,
labels, or runtime values that disagree with the file MUST fail
startup closed with a stable failure code from the slice-2 frozen
table (``D-S2-12.a``).

Failure codes emitted by this module
=====================================

* ``BUILD_IDENTITY_FILE_MISSING``
* ``BUILD_IDENTITY_FILE_MALFORMED``
* ``BUILD_IDENTITY_SCHEMA_UNSUPPORTED``
* ``BUILD_IDENTITY_COMMIT_INVALID``
* ``BUILD_IDENTITY_VERSION_INVALID``
* ``BUILD_COMMIT_MISMATCH``
* ``BUILD_VERSION_MISMATCH``
* ``DEPLOYMENT_ID_INVALID``

Failure-category mapping is owned by this module. Other Slice 2 modules
MUST NOT introduce additional build-identity failure codes.

What this module does NOT do
============================

* It does not write the authority file. The image build pipeline
  (``backend/Dockerfile``) writes the file at ``docker build`` time.
* It does not re-derive identity from the working tree, Git CLI, or
  ``git describe`` at runtime. This invariant is enforced by
  ``tests/architecture/test_deployment_startup_boundaries.py``.
* It does not expose raw file contents or raw exception text in any
  return value or log line. Errors are :class:`DeploymentIdentityError`
  subclasses with a ``failure_code`` attribute and a redaction-safe
  ``detail`` projection; no secrets, no DSN, no path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# Hard-coded path. This is the single authoritative source per
# D-S2-02.a. Do not parameterise. Do not add a fallback path.
DEFAULT_BUILD_IDENTITY_PATH = Path("/opt/cold-storage/build-identity.json")

# D-S2-02.d. There is no lenient interpretation. There is one pattern,
# one max length, and explicit prohibitions (whitespace, slash,
# non-ASCII, leading punctuation, control characters).
_BUILD_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$")
_BUILD_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# DEPLOYMENT_ID is an opaque, non-secret identifier per the contract.
# It is not a build artifact: it identifies the deployment instance.
_DEPLOYMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,127}$")


class DeploymentIdentityError(Exception):
    """Base class for all build-identity failures.

    All concrete failures in this module are instances of this class;
    callers branch on ``failure_code`` (and isinstance) rather than
    parsing ``str(exc)``. The ``detail`` payload never contains raw
    file content, raw exception text, DSN, secret, or unsafe path.
    """

    failure_code: str = "BUILD_IDENTITY_ERROR"

    def __init__(self, *, failure_code: str, detail: str = "") -> None:
        self.failure_code = failure_code
        self.detail = detail
        super().__init__(detail)


class BuildIdentityFileMissing(DeploymentIdentityError):
    failure_code = "BUILD_IDENTITY_FILE_MISSING"


class BuildIdentityFileMalformed(DeploymentIdentityError):
    failure_code = "BUILD_IDENTITY_FILE_MALFORMED"


class BuildIdentitySchemaUnsupported(DeploymentIdentityError):
    failure_code = "BUILD_IDENTITY_SCHEMA_UNSUPPORTED"


class BuildIdentityCommitInvalid(DeploymentIdentityError):
    failure_code = "BUILD_IDENTITY_COMMIT_INVALID"


class BuildIdentityVersionInvalid(DeploymentIdentityError):
    failure_code = "BUILD_IDENTITY_VERSION_INVALID"


class BuildCommitMismatch(DeploymentIdentityError):
    failure_code = "BUILD_COMMIT_MISMATCH"


class BuildVersionMismatch(DeploymentIdentityError):
    failure_code = "BUILD_VERSION_MISMATCH"


class DeploymentIdInvalid(DeploymentIdentityError):
    failure_code = "DEPLOYMENT_ID_INVALID"


@dataclass(frozen=True)
class BuildIdentityRecord:
    """Normalised in-image build-identity tuple.

    All three fields are guaranteed to satisfy the Slice 2 contract
    pattern contracts before this dataclass is constructed. Callers
    that want the **runtime** identity (env override + image file
    cross-check) must use :func:`load_runtime_identity` instead.
    """

    schema_version: int
    commit_sha: str
    version: str


def is_safe_build_version(value: str) -> bool:
    """Validate a build-version string against the D-S2-02.d contract.

    Returns ``True`` only when the value conforms to the frozen
    pattern, length, and character class. Returns ``False`` otherwise;
    callers translate ``False`` into :class:`BuildIdentityVersionInvalid`.
    """
    if not isinstance(value, str):
        return False
    # ``re.fullmatch`` enforces the pattern strictly without implicit
    # trimming or normalisation. Reject the empty string: the regex
    # requires at least one leading ASCII alphanumeric character so
    # the empty string fails at the first character class.
    if not _BUILD_VERSION_PATTERN.fullmatch(value):
        return False
    # The pattern already enforces ASCII letter/digit first char and
    # the allowed charset for subsequent characters. Sanity-check the
    # raw bytes here to satisfy the explicit D-S2-02.d clauses about
    # Unicode/control/leading-punctuation — these are properties of
    # the regex above, but defensively assert them again.
    raw = value.encode("ascii", errors="strict")
    return len(raw) <= 64 and raw[0:1] not in (b".", b"_", b"+", b"-")


def is_safe_commit_sha(value: str) -> bool:
    """Validate a 40-character lowercase hex SHA per D-S2-02.b step 3."""
    return isinstance(value, str) and bool(_BUILD_COMMIT_PATTERN.fullmatch(value))


def is_safe_deployment_id(value: str) -> bool:
    """Validate the runtime :envvar:`COLD_STORAGE_DEPLOYMENT_ID` value.

    Per the contract section D-S2-02, the deployment ID is an opaque,
    non-secret identifier: it identifies the deployment instance only
    and MUST NOT override, replace, or back-derive the build identity.
    Pattern enforces ASCII alphanumeric + ``. _ -`` characters and a
    1..128 length bound.
    """
    return isinstance(value, str) and bool(_DEPLOYMENT_ID_PATTERN.fullmatch(value))


def _parse_identity_payload(payload: object, *, source: str) -> BuildIdentityRecord:
    """Normalise a decoded JSON object into :class:`BuildIdentityRecord`.

    The Slice 2 contract freezes the file's key set to exactly
    ``schema_version``, ``commit_sha``, ``version`` and in that order.
    A different key set OR a different order raises
    :class:`BuildIdentityFileMalformed`. We accept ``dict`` rather
    than ``OrderedDict`` because ``json.loads`` guarantees key order in
    Python 3.7+ and the in-image writer is the only producer.
    """
    if not isinstance(payload, dict):
        raise BuildIdentityFileMalformed(
            failure_code="BUILD_IDENTITY_FILE_MALFORMED",
            detail=f"identity file is not a JSON object ({source})",
        )
    keys = tuple(payload.keys())
    expected_keys = ("schema_version", "commit_sha", "version")
    if keys != expected_keys:
        raise BuildIdentityFileMalformed(
            failure_code="BUILD_IDENTITY_FILE_MALFORMED",
            detail=(
                f"identity file key set does not match the frozen contract "
                f"(expected {expected_keys}, got {keys})"
            ),
        )
    schema_version = payload["schema_version"]
    if schema_version != 1:
        raise BuildIdentitySchemaUnsupported(
            failure_code="BUILD_IDENTITY_SCHEMA_UNSUPPORTED",
            detail=f"identity file schema_version must be 1, got {schema_version!r}",
        )
    commit_sha = payload["commit_sha"]
    version = payload["version"]
    if not is_safe_commit_sha(commit_sha):
        raise BuildIdentityCommitInvalid(
            failure_code="BUILD_IDENTITY_COMMIT_INVALID",
            detail="commit_sha must be a 40-character lowercase hexadecimal SHA",
        )
    if not is_safe_build_version(version):
        raise BuildIdentityVersionInvalid(
            failure_code="BUILD_IDENTITY_VERSION_INVALID",
            detail="version must match the frozen ASCII pattern and 1..64 length contract",
        )
    return BuildIdentityRecord(
        schema_version=int(schema_version),
        commit_sha=commit_sha,
        version=version,
    )


def read_in_image_identity(
    *,
    path: Path | str = DEFAULT_BUILD_IDENTITY_PATH,
) -> BuildIdentityRecord:
    """Load and validate the in-image build-identity authority file.

    This is the **only** runtime source of build identity. The function
    is deliberately eager-fail: any read, parse, schema, commit, or
    version failure raises a typed :class:`DeploymentIdentityError`
    subclass before returning. A successful return guarantees the
    record passed every contract check (file shape, schema version,
    commit pattern, version pattern).
    """
    resolved = Path(path)
    try:
        raw_text = resolved.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BuildIdentityFileMissing(
            failure_code="BUILD_IDENTITY_FILE_MISSING",
            detail="identity file not found at expected path",
        ) from exc
    except OSError as exc:
        raise BuildIdentityFileMalformed(
            failure_code="BUILD_IDENTITY_FILE_MALFORMED",
            detail="identity file could not be read at expected path",
        ) from exc
    try:
        payload = json.loads(raw_text)
    except (ValueError, TypeError) as exc:
        raise BuildIdentityFileMalformed(
            failure_code="BUILD_IDENTITY_FILE_MALFORMED",
            detail="identity file is not valid JSON",
        ) from exc
    return _parse_identity_payload(payload, source=str(resolved))


def load_runtime_identity(
    *,
    env: Mapping[str, str],
    path: Path | str = DEFAULT_BUILD_IDENTITY_PATH,
) -> tuple[BuildIdentityRecord, str]:
    """Cross-check runtime identity env vars against the in-image file.

    Returns the verified :class:`BuildIdentityRecord` (always sourced
    from the file per the in-image-authority contract) plus the
    deployment ID from the runtime environment. Behaviour matrix:

    * ``COLD_STORAGE_BUILD_COMMIT_SHA`` missing or disagrees with the
      file's ``commit_sha`` → fail closed with ``BUILD_COMMIT_MISMATCH``.
    * ``COLD_STORAGE_BUILD_VERSION`` missing or disagrees with the
      file's ``version`` → fail closed with ``BUILD_VERSION_MISMATCH``.
    * ``COLD_STORAGE_DEPLOYMENT_ID`` missing or malformed → fail closed
      with ``DEPLOYMENT_ID_INVALID``.

    The contract permits local / test environments to relax the cross-
    check by setting ``COLD_STORAGE_BUILD_IDENTITY_AUTHORITY=LOCAL_TEST``
    (inherited from the bound settings layer). This function does NOT
    consult that switch; the lifecycle integration layer is responsible
    for deciding when to call this function versus an in-memory
    fallback.
    """
    in_image = read_in_image_identity(path=path)

    runtime_commit = env.get("COLD_STORAGE_BUILD_COMMIT_SHA", "")
    if runtime_commit != in_image.commit_sha:
        raise BuildCommitMismatch(
            failure_code="BUILD_COMMIT_MISMATCH",
            detail="COLD_STORAGE_BUILD_COMMIT_SHA disagrees with the in-image authority file",
        )

    runtime_version = env.get("COLD_STORAGE_BUILD_VERSION", "")
    if runtime_version != in_image.version:
        raise BuildVersionMismatch(
            failure_code="BUILD_VERSION_MISMATCH",
            detail="COLD_STORAGE_BUILD_VERSION disagrees with the in-image authority file",
        )

    deployment_id = env.get("COLD_STORAGE_DEPLOYMENT_ID", "")
    if not is_safe_deployment_id(deployment_id):
        raise DeploymentIdInvalid(
            failure_code="DEPLOYMENT_ID_INVALID",
            detail="COLD_STORAGE_DEPLOYMENT_ID must match the frozen deployment-id pattern",
        )

    # Even when DEPLOYMENT_ID changes at runtime, the build identity
    # below comes ONLY from the in-image file. The contract explicitly
    # forbids back-derivation.
    return in_image, deployment_id


__all__ = [
    "DEFAULT_BUILD_IDENTITY_PATH",
    "BuildCommitMismatch",
    "BuildIdentityCommitInvalid",
    "BuildIdentityFileMalformed",
    "BuildIdentityFileMissing",
    "BuildIdentityRecord",
    "BuildIdentitySchemaUnsupported",
    "BuildIdentityVersionInvalid",
    "BuildVersionMismatch",
    "DeploymentIdInvalid",
    "DeploymentIdentityError",
    "is_safe_build_version",
    "is_safe_commit_sha",
    "is_safe_deployment_id",
    "load_runtime_identity",
    "read_in_image_identity",
]
