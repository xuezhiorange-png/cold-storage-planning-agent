"""TASK-012 Slice 2 live attestation preparation and schema boundary.

This module creates and validates the single live ``write_once_integrity``
attestation contract. It does not request external signing credentials,
upload Artifacts, or perform Assembly itself.
"""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cold_storage.release.canonical_serialization import (
    canonical_bytes,
    load_json_strict,
    reject_secret_values,
)
from cold_storage.release.provenance_statement import (
    LIVE_ATTESTATION_FIELD_ORDER,
    LIVE_ATTESTATION_MECHANISM,
    LIVE_ATTESTATION_SCHEMA_VERSION,
    LIVE_ATTESTATION_SUBJECT_SCHEMA,
    compute_live_attestation_subject_digest,
)


class LiveAttestationError(Exception):
    """Fail-closed live attestation error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _require_digest(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != len("sha256:") + 64
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value.removeprefix("sha256:"))
    ):
        raise LiveAttestationError(
            "ATTESTATION_BINDING_INVALID",
            f"{field} must be sha256:<64 lowercase hex>",
        )
    return value


def compute_subject_digest(provenance_digest: str, artifact_manifest_digest: str) -> str:
    """Return S = SHA-256(canonical(P, M) subject)."""
    try:
        return compute_live_attestation_subject_digest(
            _require_digest(provenance_digest, field="provenance_digest"),
            _require_digest(artifact_manifest_digest, field="artifact_manifest_digest"),
        )
    except LiveAttestationError:
        raise
    except Exception as exc:
        raise LiveAttestationError("ATTESTATION_BINDING_INVALID", str(exc)) from exc


def build_attestation(
    provenance_digest: str, artifact_manifest_digest: str
) -> OrderedDict[str, Any]:
    """Create the exact eight-field attestation payload from verified P and M."""
    return OrderedDict(
        [
            ("schema_version", LIVE_ATTESTATION_SCHEMA_VERSION),
            ("task", "TASK-012"),
            ("version", "V0.2"),
            ("slice", 2),
            ("mechanism", LIVE_ATTESTATION_MECHANISM),
            ("subject_schema", LIVE_ATTESTATION_SUBJECT_SCHEMA),
            ("subject_digest_algorithm", "sha256"),
            ("binding", compute_subject_digest(provenance_digest, artifact_manifest_digest)),
        ]
    )


def validate_attestation(
    attestation: Mapping[str, Any],
    *,
    expected_provenance_digest: str,
    expected_artifact_manifest_digest: str,
) -> str:
    """Validate exact live schema and return the verified S binding."""
    _validate_attestation_schema(attestation)
    expected_binding = compute_subject_digest(
        expected_provenance_digest, expected_artifact_manifest_digest
    )
    binding = _require_digest(attestation.get("binding"), field="binding")
    if binding != expected_binding:
        raise LiveAttestationError(
            "ATTESTATION_SUBJECT_MISMATCH",
            "attestation binding does not match recomputed P/M subject",
        )
    return binding


def _validate_attestation_schema(attestation: Mapping[str, Any]) -> None:
    """Validate the exact schema without requiring the external P/M values."""
    if not isinstance(attestation, Mapping):
        raise LiveAttestationError("ATTESTATION_SCHEMA_INVALID", "attestation must be an object")
    for value in attestation.values():
        if isinstance(value, str) and any(
            marker in value for marker in ("TEST_ONLY", "SYNTHETIC_ONLY")
        ):
            raise LiveAttestationError(
                "ATTESTATION_SYNTHETIC_REJECTED",
                "test-only or synthetic attestation is not accepted on the live path",
            )
    if tuple(attestation.keys()) != LIVE_ATTESTATION_FIELD_ORDER:
        raise LiveAttestationError(
            "ATTESTATION_SCHEMA_INVALID",
            "attestation must contain exactly the frozen fields in order",
        )
    expected: tuple[tuple[str, Any], ...] = (
        ("schema_version", LIVE_ATTESTATION_SCHEMA_VERSION),
        ("task", "TASK-012"),
        ("version", "V0.2"),
        ("slice", 2),
        ("mechanism", LIVE_ATTESTATION_MECHANISM),
        ("subject_schema", LIVE_ATTESTATION_SUBJECT_SCHEMA),
        ("subject_digest_algorithm", "sha256"),
    )
    for field, expected_value in expected:
        if attestation.get(field) != expected_value:
            code = (
                "ATTESTATION_MECHANISM_UNSUPPORTED"
                if field == "mechanism"
                else "ATTESTATION_SCHEMA_INVALID"
            )
            raise LiveAttestationError(code, f"attestation {field} mismatch")
    _require_digest(attestation.get("binding"), field="binding")


def load_attestation(path: str | Path) -> OrderedDict[str, Any]:
    """Read an attestation with strict duplicate-key rejection."""
    attestation_path = Path(path).expanduser().resolve()
    if not attestation_path.is_file() or attestation_path.is_symlink():
        raise LiveAttestationError("ATTESTATION_MISSING", str(attestation_path))
    try:
        value = load_json_strict(attestation_path.read_text(encoding="utf-8"))
        reject_secret_values(value)
        _validate_attestation_schema(value)
    except LiveAttestationError:
        raise
    except Exception as exc:
        raise LiveAttestationError("ATTESTATION_SCHEMA_INVALID", str(exc)) from exc
    return OrderedDict(value)


def create_attestation_from_observation(
    *,
    observation_bundle: str | Path,
    output_dir: str | Path,
    tooling_root: str | Path = ".",
    expected_source_sha: str | None = None,
) -> tuple[Path, str]:
    """Prepare verified observations and write only ``attestation.json``."""
    from cold_storage.release.live_evidence_runner import (
        prepare_pre_attestation_from_observation,
    )

    prepared = prepare_pre_attestation_from_observation(
        observation_bundle=observation_bundle,
        tooling_root=tooling_root,
        expected_source_sha=expected_source_sha,
    )
    attestation = build_attestation(prepared.provenance_digest, prepared.artifact_manifest_digest)
    output = Path(output_dir).expanduser().resolve()
    if not output.is_absolute():
        raise LiveAttestationError("OUTPUT_PATH_INVALID", "attestation output must be absolute")
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise LiveAttestationError("OUTPUT_PATH_COLLISION", str(output))
    else:
        output.mkdir(parents=True, exist_ok=False)
    destination = output / "attestation.json"
    destination.write_bytes(canonical_bytes(attestation))
    return destination, attestation["binding"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-012 live attestation boundary")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--observation-bundle", required=True)
    create.add_argument("--output-dir", required=True)
    create.add_argument("--tooling-root", default=".")
    create.add_argument("--expected-source-sha")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        path, binding = create_attestation_from_observation(
            observation_bundle=args.observation_bundle,
            output_dir=args.output_dir,
            tooling_root=args.tooling_root,
            expected_source_sha=args.expected_source_sha,
        )
        print(f"ATTESTATION_FILE={path}")
        print(f"SUBJECT_DIGEST={binding}")
        return 0
    except LiveAttestationError as exc:
        print(f"{exc.code}: {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ATTESTATION_ARTIFACT_PAYLOAD_FILE_COUNT",
    "LiveAttestationError",
    "build_attestation",
    "compute_subject_digest",
    "create_attestation_from_observation",
    "load_attestation",
    "main",
    "validate_attestation",
    "validate_attestation_schema",
]


ATTESTATION_ARTIFACT_PAYLOAD_FILE_COUNT = 1


validate_attestation_schema = _validate_attestation_schema
