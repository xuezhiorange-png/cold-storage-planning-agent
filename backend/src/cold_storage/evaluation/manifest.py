"""Manifest loader (TASK-011C V1 — D6, with D5/D7/D8 integration).

This module is the **single, authoritative** entry point for
loading and validating a TASK-011C V1 manifest.

Per Charles D6:

  MANIFEST_LOADER_MODULE = backend/src/cold_storage/evaluation/manifest.py
  MANIFEST_LOADER_FUNCTION = load_and_validate_manifest
  LOADER_LOADS_FROM = D8 resource-loading mechanism
  LOADER_RAISES_ON = ManifestSchemaVersionError | ManifestUnsupportedJSONValueError
                   | ManifestMissingFieldError | ManifestUndeclaredFieldError
                   | ManifestDuplicateFixtureIDError | ManifestMissingFileError
                   | ManifestMalformedJSONError

The loader is the single entry point. There is no CLI-side
manifest loading, no test-side manifest loading, no second
manifest loader. ALL manifest loading goes through
:func:`load_and_validate_manifest`.

Validation layers (D2 — two-layer fail-closed):

1. **JSON Schema validation** against
   ``backend/src/cold_storage/evaluation/schema/manifest.schema.json``
   (loaded via D8 ``importlib.resources``).
2. **Application-level strict-value validation** performed by
   :mod:`cold_storage.evaluation.canonicalization` and Pydantic
   model validation in :mod:`cold_storage.evaluation.models`.

Both layers fail closed; either mismatch causes the loader to
raise one of the typed exceptions below.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from cold_storage.evaluation.canonicalization import (
    UnsupportedJSONValueError,
    canonicalize_production_outputs,
)
from cold_storage.evaluation.models import MANIFEST_SCHEMA_VERSION, Manifest
from cold_storage.evaluation.paths import (
    PathSafetyError,
    safe_resolve_manifest_path,
)
from cold_storage.evaluation.schema import (
    SCHEMA_FILENAME,
    SCHEMA_PACKAGE,
    load_manifest_schema_text,
)

#: Frozen V1 schema version (D5).
SCHEMA_VERSION: Final[str] = MANIFEST_SCHEMA_VERSION

#: Maximum manifest file size (defense-in-depth).
_MAX_MANIFEST_BYTES: Final[int] = 4 * 1024 * 1024  # 4 MB


# ── Typed exception classes (D6 mandatory list) ──────────────────────


class ManifestError(Exception):
    """Base class for all manifest-loader failures.

    Subclasses set a stable, machine-readable ``code`` attribute.
    Downstream code MUST classify via ``code``, NEVER by parsing
    ``str(exc)``.
    """

    code: str = "MANIFEST_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._details: dict[str, Any] = dict(details) if details else {}

    @property
    def details(self) -> dict[str, Any]:
        return dict(self._details)


class ManifestSchemaVersionError(ManifestError):
    """Raised when ``schema_version`` is missing, non-``"1.0"``, or numeric."""

    code = "MANIFEST_SCHEMA_VERSION_ERROR"


class ManifestUnsupportedJSONValueError(ManifestError):
    """Raised when a manifest value violates the strict JSON value domain (D2)."""

    code = "MANIFEST_UNSUPPORTED_JSON_VALUE_ERROR"


class ManifestMissingFieldError(ManifestError):
    """Raised when a required field is missing."""

    code = "MANIFEST_MISSING_FIELD_ERROR"


class ManifestUndeclaredFieldError(ManifestError):
    """Raised when an undeclared / extra field is present (pydantic ``extra=forbid``)."""

    code = "MANIFEST_UNDECLARED_FIELD_ERROR"


class ManifestDuplicateFixtureIDError(ManifestError):
    """Raised when two fixtures share the same ``fixture_id`` within a manifest."""

    code = "MANIFEST_DUPLICATE_FIXTURE_ID_ERROR"


class ManifestMissingFileError(ManifestError):
    """Raised when a referenced fixture / expected-output file does not exist."""

    code = "MANIFEST_MISSING_FILE_ERROR"


class ManifestMalformedJSONError(ManifestError):
    """Raised when the manifest text is not parseable as JSON."""

    code = "MANIFEST_MALFORMED_JSON_ERROR"


# ── Public API (D6 single entry point) ───────────────────────────────


def load_and_validate_manifest(manifest_path: Path) -> Manifest:
    """Load and validate the manifest at ``manifest_path``.

    This is the **single** entry point for manifest loading. It
    performs fail-closed validation in the order:

    1. Path-safety resolution of ``manifest_path`` (via
       :func:`safe_resolve_manifest_path` against the manifest's
       parent directory).
    2. UTF-8 read with size cap.
    3. JSON parse with typed error mapping. ``parse_constant`` is
       configured to reject ``NaN`` / ``Infinity`` / ``-Infinity``
       as :class:`ManifestUnsupportedJSONValueError`
       (P0-4 fail-closed).
    4. Recursive strict-value validation (D2 / D1 strict-JSON
       value domain) of the raw parsed object. The D1 authority
       is reused (:func:`canonicalize_production_outputs`); no
       second recursive canonicalizer is created. Failures map
       to :class:`ManifestUnsupportedJSONValueError`.
    5. JSON Schema validation against the V1 schema (loaded via
       :func:`load_manifest_schema_text`, which uses
       ``importlib.resources`` — no repository-relative fallback).
    6. Pydantic model validation (forbids unknown fields, enforces
       ``schema_version="1.0"`` literal, enforces empty
       ``excluded_paths``).
    7. Cross-scenario duplicate detection (fixture_id + scenario_id
       + per-scenario backend identity combination).
    8. Mandatory referenced-files existence check (file-safety
       and path-safety validation of every declared
       ``fixtures[].path`` and ``expected_output.path``).

    The ``referenced_files_check`` parameter was removed
    (review 4689545688 P0-4). The check is mandatory and
    internal; there is no public bypass.

    Parameters
    ----------
    manifest_path:
        Filesystem path to the manifest JSON. MUST be an absolute
        path. The path is validated for safety (no ``..`` escape,
        no absolute path under the parent, no symlink escape).

        Relative paths are rejected with
        :class:`ManifestError` (code ``MANIFEST_ERROR``) **before
        any file I/O**: the loader never resolves a relative
        input against the current working directory. The
        rejection is identical regardless of which directory the
        process is running in and regardless of whether a file
        with that relative name happens to exist in cwd.

    Returns
    -------
    Manifest
        The validated, typed manifest.

    Raises
    ------
    ManifestError (or one of the concrete subclasses)
        On any failure. The exception ``code`` attribute identifies
        the specific failure mode.
    """
    # 1. Path-safety
    manifest_path = _validate_manifest_path_safety(manifest_path)
    manifest_root = manifest_path.parent

    # 2. Read
    raw_text = _read_manifest_text(manifest_path)

    # 3. JSON parse with fail-closed ``parse_constant``. NaN /
    # Infinity / -Infinity are mapped to
    # ManifestUnsupportedJSONValueError before Pydantic sees the
    # value.
    try:
        raw_obj = json.loads(
            raw_text,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except _NonFiniteJSONConstantError as exc:
        raise ManifestUnsupportedJSONValueError(
            f"manifest contains a non-finite JSON constant: {exc.token!r}. "
            "NaN, Infinity, and -Infinity are not part of the V1 strict "
            "JSON value domain (D2).",
            details={
                "value": exc.token,
                "manifest_path": str(manifest_path),
            },
        ) from exc
    except json.JSONDecodeError as exc:
        raise ManifestMalformedJSONError(
            f"manifest is not valid JSON: {exc.msg} at line {exc.lineno} col {exc.colno}.",
            details={
                "line": exc.lineno,
                "column": exc.colno,
                "msg": exc.msg,
                "path": str(manifest_path),
            },
        ) from exc

    # 4. Recursive strict-value validation (D2). The D1 authority
    # is reused; the strict-JSON canonicalizer validates every
    # value against the D2 allow-list. Any non-JSON value
    # (NaN, Decimal, datetime, tuple, set, custom class, non-string
    # key, etc.) is rejected.
    try:
        canonicalize_production_outputs(raw_obj, excluded_paths=())
    except UnsupportedJSONValueError as exc:
        # Map the D1 typed error to the loader's typed error.
        raise ManifestUnsupportedJSONValueError(
            f"manifest contains an unsupported JSON value: {exc}",
            details={
                **(exc.details or {}),
                "manifest_path": str(manifest_path),
            },
        ) from exc

    # 5. JSON Schema validation
    _validate_against_json_schema(raw_obj, manifest_path)

    # 6. Pydantic model validation (forbids unknown fields, etc.)
    try:
        manifest = Manifest.model_validate(raw_obj)
    except ValidationError as exc:
        # Map pydantic errors to typed Manifest errors. We inspect
        # the error ``type`` string to map to the right code.
        raise _map_pydantic_error(exc, manifest_path) from exc

    # 7. Cross-scenario duplicate detection
    _check_no_duplicate_fixture_ids(manifest, manifest_path)

    # 8. Mandatory referenced-files existence + path-safety check.
    _check_referenced_files_exist(manifest, manifest_root, manifest_path)

    return manifest


def compute_manifest_sha(manifest: Manifest) -> str:
    """Compute the canonical SHA-256 of a manifest.

    The canonical form is the D1 canonicalizer's output
    (real :class:`bytes`, UTF-8 encoded, sorted keys, fixed
    separators). Downstream code uses this SHA to bind a run to
    a specific manifest.

    Per Charles's review 4689545688 P0-2, the SHA-256 is computed
    directly on the returned canonical bytes (no intermediate
    ``.encode(...)`` step).

    Parameters
    ----------
    manifest:
        A validated :class:`Manifest` instance.

    Returns
    -------
    str
        Lowercase hex SHA-256 digest of the canonical bytes.
    """
    # Pydantic v2 ``model_dump(mode="json")`` returns JSON-native
    # values: ``str``-mixin enums are serialized to their string
    # value, ``datetime``-typed fields (if any) to ISO strings, and
    # tuple containers remain as lists. The D2 strict-JSON
    # canonicalizer accepts the resulting value domain directly.
    dumped = manifest.model_dump(mode="json")
    canonical_bytes = canonicalize_production_outputs(
        dumped,
        excluded_paths=(),
    )
    # Hash the bytes directly. Per Charles's review 4689545688
    # P0-2, no second ``.encode("utf-8")`` is performed on the
    # canonical output.
    return hashlib.sha256(canonical_bytes).hexdigest()


# ── Private helpers (D6, D5, D7, D8) ────────────────────────────────


class _NonFiniteJSONConstantError(ValueError):
    """Internal sentinel raised by ``_reject_nonfinite_json_constant``.

    The loader catches this and re-raises as
    :class:`ManifestUnsupportedJSONValueError`. Using an internal
    exception type avoids message-text classification.
    """

    def __init__(self, token: str) -> None:
        super().__init__(f"non-finite JSON constant: {token!r}")
        self.token = token


def _reject_nonfinite_json_constant(_constant: str) -> None:
    """``parse_constant`` callback for :func:`json.loads`.

    The Python ``json`` module accepts the non-standard tokens
    ``NaN``, ``Infinity``, and ``-Infinity`` (and their lowercase
    forms) and maps them to ``float('nan')`` /
    ``float('inf')`` / ``float('-inf')`` respectively. These
    are NOT part of the V1 strict JSON value domain (D2). The
    V1 loader must reject them at parse time.

    The callback raises :class:`_NonFiniteJSONConstantError`; the
    loader catches it and re-raises as
    :class:`ManifestUnsupportedJSONValueError`.
    """
    raise _NonFiniteJSONConstantError(_constant)


def _validate_manifest_path_safety(manifest_path: Path) -> Path:
    if not isinstance(manifest_path, Path):
        raise ManifestError(
            f"manifest_path must be a pathlib.Path; got {type(manifest_path).__name__}.",
            details={"value_type": type(manifest_path).__name__},
        )
    if not manifest_path.is_absolute():
        # Per P0-3 of review 4689835238: relative manifest paths
        # are rejected **before any file I/O** so the loader is
        # strictly cwd-independent. The previous implementation
        # used ``Path.resolve()`` which silently binds the
        # relative path to the current working directory; that
        # behavior was non-deterministic across cwd changes.
        # The loader now refuses relative input outright. The
        # typed error ``ManifestError`` (code=MANIFEST_ERROR) is
        # raised regardless of whether the relative file happens
        # to exist in the current cwd.
        raise ManifestError(
            "manifest_path must be absolute.",
            details={"manifest_path_kind": "relative"},
        )
    # Use the path-safety helper to validate the path itself. We
    # treat the manifest's parent directory as the "manifest root"
    # for safety purposes. This catches the edge case where
    # manifest_path is itself a symlink that escapes.
    manifest_root = manifest_path.parent
    try:
        return safe_resolve_manifest_path(manifest_path.name, manifest_root=manifest_root)
    except PathSafetyError as exc:
        raise ManifestError(
            f"manifest_path failed path-safety validation: {exc}",
            details={
                "manifest_path": str(manifest_path),
                "path_safety_code": exc.code,
            },
        ) from exc


def _read_manifest_text(manifest_path: Path) -> str:
    try:
        data = manifest_path.read_bytes()
    except OSError as exc:
        raise ManifestError(
            f"cannot read manifest file {manifest_path!r}: {exc}.",
            details={"path": str(manifest_path)},
        ) from exc
    if len(data) > _MAX_MANIFEST_BYTES:
        raise ManifestError(
            f"manifest file exceeds max size {_MAX_MANIFEST_BYTES} bytes.",
            details={"path": str(manifest_path), "size": len(data)},
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestMalformedJSONError(
            f"manifest file is not valid UTF-8: {exc}.",
            details={"path": str(manifest_path)},
        ) from exc


def _validate_against_json_schema(
    raw_obj: Any,
    manifest_path: Path,
) -> None:
    """Run JSON Schema validation against the V1 schema.

    Imported lazily to keep the module import path light.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover
        raise ManifestError(
            "jsonschema is required for manifest validation; install it.",
            details={"package": "jsonschema"},
        ) from exc
    try:
        schema_text = load_manifest_schema_text()
    except (FileNotFoundError, OSError) as exc:
        raise ManifestError(
            f"cannot load manifest schema from {SCHEMA_PACKAGE}/{SCHEMA_FILENAME}: {exc}.",
            details={"schema_package": SCHEMA_PACKAGE, "schema_file": SCHEMA_FILENAME},
        ) from exc
    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError as exc:  # pragma: no cover — schema is static
        raise ManifestError(
            f"manifest schema is not valid JSON: {exc}.",
            details={"schema_file": SCHEMA_FILENAME},
        ) from exc
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(raw_obj))
    if not errors:
        return
    # Map the first error to a typed exception.
    err = errors[0]
    err_path = "/".join(str(p) for p in err.absolute_path) or "<root>"
    err_msg = err.message
    # If the error is about schema_version, raise the typed version error.
    if "schema_version" in err_path or "schema_version" in err_msg:
        raise ManifestSchemaVersionError(
            f"schema_version validation failed at {err_path}: {err_msg}.",
            details={"path": err_path, "msg": err_msg, "manifest_path": str(manifest_path)},
        )
    # If the error is about a required field missing.
    if err.validator == "required":
        missing = err.message
        raise ManifestMissingFieldError(
            f"required field missing: {missing} at {err_path}.",
            details={"path": err_path, "msg": err_msg, "manifest_path": str(manifest_path)},
        )
    # If the error is about additionalProperties (undeclared field).
    if err.validator == "additionalProperties":
        raise ManifestUndeclaredFieldError(
            f"undeclared field at {err_path}: {err_msg}.",
            details={"path": err_path, "msg": err_msg, "manifest_path": str(manifest_path)},
        )
    # Default: treat as a schema mismatch.
    raise ManifestError(
        f"manifest schema validation failed at {err_path}: {err_msg}.",
        details={
            "path": err_path,
            "msg": err_msg,
            "validator": err.validator,
            "manifest_path": str(manifest_path),
        },
    )


def _map_pydantic_error(
    exc: ValidationError,
    manifest_path: Path,
) -> ManifestError:
    """Map a pydantic ``ValidationError`` to a typed ``ManifestError``."""
    errors = exc.errors()
    if not errors:
        return ManifestError(
            f"manifest pydantic validation failed (no errors): {exc}.",
            details={"manifest_path": str(manifest_path)},
        )
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", ())) or "<root>"
    err_type = first.get("type", "validation_error")
    msg = first.get("msg", "validation failed")
    # Map well-known pydantic error types to typed codes.
    if err_type == "value_error" and "schema_version" in loc:
        return ManifestSchemaVersionError(
            f"schema_version validation failed: {msg} at {loc}.",
            details={"path": loc, "msg": msg, "manifest_path": str(manifest_path)},
        )
    if err_type == "missing":
        return ManifestMissingFieldError(
            f"required field missing: {msg} at {loc}.",
            details={"path": loc, "msg": msg, "manifest_path": str(manifest_path)},
        )
    if err_type == "extra_forbidden":
        return ManifestUndeclaredFieldError(
            f"undeclared field at {loc}: {msg}.",
            details={"path": loc, "msg": msg, "manifest_path": str(manifest_path)},
        )
    if "excluded_paths" in loc:
        return ManifestUnsupportedJSONValueError(
            f"excluded_paths policy violation at {loc}: {msg}.",
            details={"path": loc, "msg": msg, "manifest_path": str(manifest_path)},
        )
    return ManifestError(
        f"manifest pydantic validation failed at {loc}: {msg}.",
        details={
            "path": loc,
            "msg": msg,
            "type": err_type,
            "manifest_path": str(manifest_path),
        },
    )


def _check_no_duplicate_fixture_ids(
    manifest: Manifest,
    manifest_path: Path,
) -> None:
    """Reject duplicate ``fixture_id`` values across the manifest."""
    seen: dict[str, str] = {}
    for scenario in manifest.scenarios:
        for fixture in scenario.fixtures:
            existing = seen.get(fixture.fixture_id)
            if existing is not None:
                raise ManifestDuplicateFixtureIDError(
                    f"duplicate fixture_id {fixture.fixture_id!r} in manifest; "
                    f"first seen in scenario {existing!r}.",
                    details={
                        "fixture_id": fixture.fixture_id,
                        "first_scenario": existing,
                        "manifest_path": str(manifest_path),
                    },
                )
            seen[fixture.fixture_id] = scenario.scenario_id


def _check_referenced_files_exist(
    manifest: Manifest,
    manifest_root: Path,
    manifest_path: Path,
) -> None:
    """Check that every fixture / expected-output path resolves and exists."""
    # Validate and resolve the manifest root itself (canonicalize).
    manifest_root = manifest_root.resolve()
    for scenario in manifest.scenarios:
        for fixture in scenario.fixtures:
            try:
                resolved = safe_resolve_manifest_path(fixture.path, manifest_root=manifest_root)
            except PathSafetyError as exc:
                raise ManifestError(
                    f"fixture path failed safety check: {fixture.path!r} "
                    f"(scenario={scenario.scenario_id!r}, "
                    f"fixture_id={fixture.fixture_id!r}): {exc}",
                    details={
                        "fixture_id": fixture.fixture_id,
                        "scenario_id": scenario.scenario_id,
                        "path": fixture.path,
                        "path_safety_code": exc.code,
                    },
                ) from exc
            if not resolved.exists():
                raise ManifestMissingFileError(
                    f"fixture file does not exist: {resolved!r} "
                    f"(scenario={scenario.scenario_id!r}, "
                    f"fixture_id={fixture.fixture_id!r}).",
                    details={
                        "fixture_id": fixture.fixture_id,
                        "scenario_id": scenario.scenario_id,
                        "path": str(resolved),
                    },
                )
        if scenario.expected_output is not None and scenario.expected_output.path is not None:
            try:
                resolved = safe_resolve_manifest_path(
                    scenario.expected_output.path, manifest_root=manifest_root
                )
            except PathSafetyError as exc:
                raise ManifestError(
                    f"expected_output path failed safety check: "
                    f"{scenario.expected_output.path!r} "
                    f"(scenario={scenario.scenario_id!r}): {exc}",
                    details={
                        "scenario_id": scenario.scenario_id,
                        "path": scenario.expected_output.path,
                        "path_safety_code": exc.code,
                    },
                ) from exc
            if not resolved.exists():
                raise ManifestMissingFileError(
                    f"expected_output file does not exist: {resolved!r} "
                    f"(scenario={scenario.scenario_id!r}).",
                    details={
                        "scenario_id": scenario.scenario_id,
                        "path": str(resolved),
                    },
                )


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "ManifestDuplicateFixtureIDError",
    "ManifestError",
    "ManifestMalformedJSONError",
    "ManifestMissingFieldError",
    "ManifestMissingFileError",
    "ManifestSchemaVersionError",
    "ManifestUndeclaredFieldError",
    "ManifestUnsupportedJSONValueError",
    "SCHEMA_VERSION",
    "compute_manifest_sha",
    "load_and_validate_manifest",
]
