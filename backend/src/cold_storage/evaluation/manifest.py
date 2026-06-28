"""Strict manifest loading, validation, and conversion to models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from cold_storage.evaluation.errors import (
    ConflictingComparisonPathError,
    DecimalPolicyError,
    DuplicateComparisonPathError,
    DuplicateScenarioIdError,
    IgnorePolicyError,
    ManifestFileNotFoundError,
    ManifestJsonDecodeError,
    ManifestSchemaError,
    ManifestSemanticError,
    UnknownSchemaVersionError,
    UnsafeEvaluationPathError,
)
from cold_storage.evaluation.models import (
    ArtifactCheckRule,
    ArtifactStatus,
    ComparisonPolicy,
    DecimalMode,
    DecimalPathRule,
    EvaluationManifest,
    EvaluationScenario,
    EvaluationStage,
    ExactPathRule,
    ExpectedOutcome,
    IgnoredPathRule,
    ManifestProvenance,
)
from cold_storage.evaluation.paths import (
    EvaluationReferenceKind,
    resolve_and_verify_path,
)

SCHEMA_VERSION = "1.0"

# Schema location (fixed — part of the package, not user data)
_HERE = Path(__file__).resolve().parent  # backend/src/cold_storage/evaluation/
_DEFAULT_SCHEMA_PATH = _HERE.parents[3] / "evaluation" / "manifest.schema.json"

# Eval root for data files (fixtures, expected outputs)
_DEFAULT_EVAL_ROOT = _HERE.parents[3] / "evaluation"  # repo root / evaluation/

# Ignore rationale denylist — placeholder/generic reasons that carry no
# meaningful justification and must be rejected.
_IGNORE_RATIONALE_DENYLIST: set[str] = {
    "dynamic",
    "ignore",
    "ignored",
    "nondeterministic",
    "non-deterministic",
    "temporary",
    "temp",
    "unknown",
    "n/a",
    "na",
    "none",
}

# Minimum meaningful rationale length after stripping.
_MIN_RATIONALE_LENGTH = 12


def _is_placeholder_rationale(reason: str) -> bool:
    """Check if an ignore reason is a placeholder."""
    stripped = reason.strip().lower()
    if len(stripped) < _MIN_RATIONALE_LENGTH:
        return True
    if stripped in _IGNORE_RATIONALE_DENYLIST:
        return True
    # Also catch single-word reasons
    return " " not in stripped


def load_evaluation_manifest(
    manifest_path: str | Path,
    *,
    evaluation_root: str | Path | None = None,
    require_referenced_files: bool = True,
) -> EvaluationManifest:
    """Load, validate, and convert a manifest into an immutable model.

    Performs, in order:
    1. File existence check
    2. UTF-8 JSON decode
    3. Pre-checks (root object, schema version)
    4. Duplicate preflight (scenario IDs, comparison paths)
    5. JSON Schema validation
    6. Semantic validation (conflicts, rationale quality)
    7. Path safety for all references
    8. Conversion to ``EvaluationManifest``

    Args:
        manifest_path: Path to the manifest JSON file.
        evaluation_root: Root directory for resolving relative paths.
            Defaults to the repository ``evaluation/`` directory.
        require_referenced_files: When True (default), every referenced
            file must exist on disk.

    Returns:
        A validated, immutable ``EvaluationManifest``.

    Raises:
        ManifestFileNotFoundError: Manifest file does not exist.
        ManifestJsonDecodeError: File is not valid JSON.
        ManifestSchemaError: JSON Schema validation fails.
        ManifestSemanticError: Semantic rules fail.
        UnsafeEvaluationPathError: Path security check fails.
    """
    path = Path(manifest_path)
    root = Path(evaluation_root) if evaluation_root else _DEFAULT_EVAL_ROOT

    # 1. File existence
    if not path.exists():
        raise ManifestFileNotFoundError(
            code="EVAL_MANIFEST_NOT_FOUND",
            message=f"Manifest file not found: '{path}'",
            field=str(path),
        )

    # 2. JSON decode
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestJsonDecodeError(
            code="EVAL_JSON_INVALID",
            message=f"Manifest is not valid JSON: {exc}",
            field=str(path),
        ) from exc

    # 3. Pre-checks before Schema
    if not isinstance(raw, dict):
        raise ManifestSchemaError(
            code="EVAL_SCHEMA_INVALID",
            message="Manifest root must be a JSON object",
        )

    sv = raw.get("schema_version")
    if sv not in (SCHEMA_VERSION,):
        raise UnknownSchemaVersionError(
            code="EVAL_SCHEMA_VERSION_UNSUPPORTED",
            message=(f"Schema version '{sv}' is not supported. Supported: {SCHEMA_VERSION}"),
            field="schema_version",
        )

    # 4. Duplicate preflight (before Schema to preserve dedicated error codes)
    _preflight_duplicate_scenarios(raw)
    _preflight_duplicate_comparison_paths(raw)

    # 5. JSON Schema validation
    schema_path = _DEFAULT_SCHEMA_PATH
    if not schema_path.exists():
        raise ManifestSchemaError(
            code="EVAL_SCHEMA_INVALID",
            message=f"Schema file not found at '{schema_path}'",
        )

    schema = json.loads(schema_path.read_text("utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(raw))
    if errors:
        raise ManifestSchemaError(
            code="EVAL_SCHEMA_INVALID",
            message="; ".join(f"[{list(e.absolute_path)}] {e.message}" for e in errors),
        )

    # 6. Semantic validation
    _validate_semantic(raw, root, require_referenced_files)

    # 7. Convert to models
    return _to_manifest(raw, root, require_referenced_files)


def _preflight_duplicate_scenarios(raw: dict[str, Any]) -> None:
    """Check for duplicate scenario IDs before Schema validation.

    Includes defensive type checks to prevent AttributeError/TypeError
    from malformed container shapes.
    """
    scenarios_raw = raw.get("scenarios")
    if not isinstance(scenarios_raw, list):
        raise ManifestSchemaError(
            code="EVAL_SCHEMA_INVALID",
            message="'scenarios' must be a list",
            field="scenarios",
        )

    seen_ids: set[str] = set()
    for sidx, scenario in enumerate(scenarios_raw):
        if not isinstance(scenario, dict):
            raise ManifestSchemaError(
                code="EVAL_SCHEMA_INVALID",
                message=f"Scenario at index {sidx} must be an object",
                field=f"scenarios/{sidx}",
            )
        sid = scenario.get("scenario_id", "")
        if not isinstance(sid, str):
            raise ManifestSchemaError(
                code="EVAL_SCHEMA_INVALID",
                message=f"Scenario 'scenario_id' at index {sidx} must be a string",
                field=f"scenarios/{sidx}/scenario_id",
            )
        if sid in seen_ids:
            raise DuplicateScenarioIdError(
                code="EVAL_SCENARIO_ID_DUPLICATE",
                message=f"Duplicate scenario ID: '{sid}'",
                field=f"scenarios/{sid}",
            )
        if sid:
            seen_ids.add(sid)


def _preflight_duplicate_comparison_paths(raw: dict[str, Any]) -> None:
    """Check for duplicate comparison policy paths before Schema validation.

    Includes defensive type checks to prevent AttributeError/TypeError
    from malformed container shapes.
    """
    scenarios_raw = raw.get("scenarios", [])
    if not isinstance(scenarios_raw, list):
        return

    for sidx, scenario in enumerate(scenarios_raw):
        if not isinstance(scenario, dict):
            continue

        policy_raw = scenario.get("comparison_policy")
        if not isinstance(policy_raw, dict):
            continue

        seen_exact: set[str] = set()
        seen_decimal: set[str] = set()
        seen_ignored: set[str] = set()

        exact_paths_raw = policy_raw.get("exact_paths", [])
        if isinstance(exact_paths_raw, list):
            for ridx, rule in enumerate(exact_paths_raw):
                p = rule.get("path", "") if isinstance(rule, dict) else ""
                if not isinstance(p, str):
                    scenario_id = (
                        scenario.get("scenario_id", "") if isinstance(scenario, dict) else ""
                    )
                    sid_label = f"'{scenario_id}'" if scenario_id else f"index {sidx}"
                    raise ManifestSchemaError(
                        code="EVAL_SCHEMA_INVALID",
                        message=(
                            f"exact_path path must be a string in scenario "
                            f"{sid_label}, got {type(p).__name__}"
                        ),
                        field=f"scenarios/{sidx}/exact_paths/{ridx}/path",
                    )
                if p in seen_exact:
                    sid = scenario.get("scenario_id", "") if isinstance(scenario, dict) else ""
                    raise DuplicateComparisonPathError(
                        code="EVAL_COMPARISON_PATH_DUPLICATE",
                        message=f"Duplicate exact path '{p}' in scenario '{sid}'",
                        field=f"scenarios/{sidx}/exact_paths/{ridx}",
                    )
                if p:
                    seen_exact.add(p)

        decimal_paths_raw = policy_raw.get("decimal_paths", [])
        if isinstance(decimal_paths_raw, list):
            for ridx, rule in enumerate(decimal_paths_raw):
                p = rule.get("path", "") if isinstance(rule, dict) else ""
                if not isinstance(p, str):
                    scenario_id = (
                        scenario.get("scenario_id", "") if isinstance(scenario, dict) else ""
                    )
                    sid_label = f"'{scenario_id}'" if scenario_id else f"index {sidx}"
                    raise ManifestSchemaError(
                        code="EVAL_SCHEMA_INVALID",
                        message=(
                            f"decimal_path path must be a string in scenario "
                            f"{sid_label}, got {type(p).__name__}"
                        ),
                        field=f"scenarios/{sidx}/decimal_paths/{ridx}/path",
                    )
                if p in seen_decimal:
                    sid = scenario.get("scenario_id", "") if isinstance(scenario, dict) else ""
                    raise DuplicateComparisonPathError(
                        code="EVAL_COMPARISON_PATH_DUPLICATE",
                        message=f"Duplicate decimal path '{p}' in scenario '{sid}'",
                        field=f"scenarios/{sidx}/decimal_paths/{ridx}",
                    )
                if p:
                    seen_decimal.add(p)

        ignored_paths_raw = policy_raw.get("ignored_paths", [])
        if isinstance(ignored_paths_raw, list):
            for ridx, rule in enumerate(ignored_paths_raw):
                p = rule.get("path", "") if isinstance(rule, dict) else ""
                if not isinstance(p, str):
                    scenario_id = (
                        scenario.get("scenario_id", "") if isinstance(scenario, dict) else ""
                    )
                    sid_label = f"'{scenario_id}'" if scenario_id else f"index {sidx}"
                    raise ManifestSchemaError(
                        code="EVAL_SCHEMA_INVALID",
                        message=(
                            f"ignored_path path must be a string in scenario "
                            f"{sid_label}, got {type(p).__name__}"
                        ),
                        field=f"scenarios/{sidx}/ignored_paths/{ridx}/path",
                    )
                if p in seen_ignored:
                    sid = scenario.get("scenario_id", "")
                    raise DuplicateComparisonPathError(
                        code="EVAL_COMPARISON_PATH_DUPLICATE",
                        message=f"Duplicate ignored path '{p}' in scenario '{sid}'",
                        field=f"scenarios/{sidx}/ignored_paths/{ridx}",
                    )
                if p:
                    seen_ignored.add(p)


def validate_manifest_structure(manifest_path: str | Path) -> dict[str, Any]:
    """Validate only structural/schema aspects. Pure schema + path check."""
    path = Path(manifest_path)
    root = _DEFAULT_EVAL_ROOT

    if not path.exists():
        raise ManifestFileNotFoundError(
            code="EVAL_MANIFEST_NOT_FOUND",
            message=f"Manifest file not found: '{path}'",
            field=str(path),
        )

    try:
        raw = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestJsonDecodeError(
            code="EVAL_JSON_INVALID",
            message=f"Manifest is not valid JSON: {exc}",
            field=str(path),
        ) from exc
    schema_path = root / "manifest.schema.json"
    schema = json.loads(schema_path.read_text("utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(raw))
    if errors:
        raise ManifestSchemaError(
            code="EVAL_SCHEMA_INVALID",
            message="; ".join(f"[{list(e.absolute_path)}] {e.message}" for e in errors),
        )

    return {"scenario_count": len(raw.get("scenarios", []))}


def _validate_semantic(
    raw: dict[str, Any],
    root: Path,
    require_files: bool,
) -> None:
    """Business-rule validation beyond JSON Schema."""
    if raw.get("schema_version") not in (SCHEMA_VERSION,):
        raise UnknownSchemaVersionError(
            code="EVAL_SCHEMA_VERSION_UNSUPPORTED",
            message=(
                f"Schema version '{raw.get('schema_version')}' is not supported. "
                f"Supported: {SCHEMA_VERSION}"
            ),
            field="schema_version",
        )

    seen_ids: set[str] = set()
    for sidx, scenario in enumerate(raw.get("scenarios", [])):
        sid = scenario.get("scenario_id", "")
        if sid in seen_ids:
            raise DuplicateScenarioIdError(
                code="EVAL_SCENARIO_ID_DUPLICATE",
                message=f"Duplicate scenario ID: '{sid}'",
                field=f"scenarios/{sid}",
            )
        seen_ids.add(sid)

        policy = scenario.get("comparison_policy", {})
        _validate_comparison_policy(sid, policy)

        # Path checks for referenced files
        for field_name, ref in [
            ("project_input_path", scenario.get("project_input_path", "")),
        ]:
            _validate_ref(
                sid,
                field_name,
                ref,
                root,
                require_files,
                reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
            )

        for field_name, ref in [
            ("expected_path", scenario.get("expected_path", "")),
        ]:
            _validate_ref(
                sid,
                field_name,
                ref,
                root,
                require_files,
                reference_kind=EvaluationReferenceKind.EXPECTED_OUTPUT,
            )

        for ref in scenario.get("document_refs", []):
            _validate_ref(
                sid,
                "document_ref",
                ref,
                root,
                require_files,
                reference_kind=EvaluationReferenceKind.DOCUMENT,
            )

        # Provenance semantic validation
        prov = scenario.get("provenance", {})
        prov_source = prov.get("source", "") if isinstance(prov, dict) else ""
        prov_rationale = prov.get("rationale", "") if isinstance(prov, dict) else ""
        if not prov_source.strip():
            raise ManifestSemanticError(
                code="EVAL_SCHEMA_INVALID",
                message=f"Empty or whitespace-only provenance source in scenario '{sid}'",
                field=f"scenarios/{sidx}/provenance/source",
            )
        if not prov_rationale.strip():
            raise ManifestSemanticError(
                code="EVAL_SCHEMA_INVALID",
                message=f"Empty or whitespace-only provenance rationale in scenario '{sid}'",
                field=f"scenarios/{sidx}/provenance/rationale",
            )


def _validate_ref(
    scenario_id: str,
    field_name: str,
    ref_str: str,
    root: Path,
    require_files: bool,
    reference_kind: EvaluationReferenceKind | None = None,
) -> None:
    """Validate a single referenced path."""
    try:
        resolve_and_verify_path(
            Path(ref_str),
            evaluation_root=root,
            reference_kind=reference_kind,
            allow_missing=not require_files,
        )
    except UnsafeEvaluationPathError:
        raise
    except Exception as exc:
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_ESCAPE",
            message=f"Invalid reference '{ref_str}' in scenario '{scenario_id}': {exc}",
            field=f"scenarios/{scenario_id}/{field_name}",
        ) from exc


def _validate_comparison_policy(scenario_id: str, policy: dict[str, Any]) -> None:
    """Validate comparison policy semantic rules."""
    exact_paths: set[str] = set()
    decimal_paths: set[str] = set()
    ignored_paths: set[str] = set()

    for rule in policy.get("exact_paths", []):
        p = rule.get("path", "")
        if p in exact_paths:
            raise DuplicateComparisonPathError(
                code="EVAL_COMPARISON_PATH_DUPLICATE",
                message=f"Duplicate exact path '{p}' in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/exact_paths",
            )
        if not p:
            raise ManifestSemanticError(
                code="EVAL_COMPARISON_PATH_DUPLICATE",
                message=f"Empty exact path in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/exact_paths",
            )
        if "*" in p or ".." in p:
            raise ManifestSemanticError(
                code="EVAL_COMPARISON_PATH_DUPLICATE",
                message=f"Wildcard or recursive path not allowed: '{p}'",
                field=f"scenarios/{scenario_id}/exact_paths",
            )
        exact_paths.add(p)

    for rule in policy.get("decimal_paths", []):
        p = rule.get("path", "")
        if p in decimal_paths:
            raise DuplicateComparisonPathError(
                code="EVAL_COMPARISON_PATH_DUPLICATE",
                message=f"Duplicate decimal path '{p}' in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/decimal_paths",
            )
        if not p:
            raise DecimalPolicyError(
                code="EVAL_DECIMAL_POLICY_INVALID",
                message=f"Empty decimal path in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/decimal_paths",
            )
        if not rule.get("unit"):
            raise DecimalPolicyError(
                code="EVAL_DECIMAL_POLICY_INVALID",
                message=f"Missing unit for decimal path '{p}' in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/decimal_paths",
            )
        if not rule.get("rationale"):
            raise DecimalPolicyError(
                code="EVAL_DECIMAL_POLICY_INVALID",
                message=f"Missing rationale for decimal path '{p}' in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/decimal_paths",
            )
        decimal_paths.add(p)

    for rule in policy.get("ignored_paths", []):
        p = rule.get("path", "")
        if p in ignored_paths:
            raise DuplicateComparisonPathError(
                code="EVAL_COMPARISON_PATH_DUPLICATE",
                message=f"Duplicate ignored path '{p}' in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/ignored_paths",
            )
        if p == "$":
            raise IgnorePolicyError(
                code="EVAL_IGNORE_POLICY_INVALID",
                message="Cannot ignore the root path '$'",
                field=f"scenarios/{scenario_id}/ignored_paths",
            )
        if not rule.get("reason"):
            raise IgnorePolicyError(
                code="EVAL_IGNORE_POLICY_INVALID",
                message=f"Missing reason for ignored path '{p}' in scenario '{scenario_id}'",
                field=f"scenarios/{scenario_id}/ignored_paths",
            )
        reason = rule.get("reason", "")
        if _is_placeholder_rationale(reason):
            raise IgnorePolicyError(
                code="EVAL_IGNORE_POLICY_INVALID",
                message=(
                    f"Placeholder or short ignore reason '{reason}' "
                    f"at path '{p}' in scenario '{scenario_id}'"
                ),
                field=f"scenarios/{scenario_id}/ignored_paths",
            )
        ignored_paths.add(p)

    # Conflict check: same path in multiple categories
    for p in exact_paths:
        if p in decimal_paths:
            raise ConflictingComparisonPathError(
                code="EVAL_COMPARISON_PATH_CONFLICT",
                message=(
                    f"Path '{p}' appears in both exact_paths and "
                    f"decimal_paths in scenario '{scenario_id}'"
                ),
                field=f"scenarios/{scenario_id}/exact_paths",
            )
        if p in ignored_paths:
            raise ConflictingComparisonPathError(
                code="EVAL_COMPARISON_PATH_CONFLICT",
                message=(
                    f"Path '{p}' appears in both exact_paths and "
                    f"ignored_paths in scenario '{scenario_id}'"
                ),
                field=f"scenarios/{scenario_id}/exact_paths",
            )

    for p in decimal_paths:
        if p in ignored_paths:
            raise ConflictingComparisonPathError(
                code="EVAL_COMPARISON_PATH_CONFLICT",
                message=(
                    f"Path '{p}' appears in both decimal_paths and "
                    f"ignored_paths in scenario '{scenario_id}'"
                ),
                field=f"scenarios/{scenario_id}/decimal_paths",
            )


def _to_manifest(raw: dict[str, Any], root: Path, require_files: bool = True) -> EvaluationManifest:
    """Convert validated raw dict to immutable models."""
    scenarios: list[EvaluationScenario] = []
    for s in raw.get("scenarios", []):
        policy = s.get("comparison_policy", {})

        exact = tuple(ExactPathRule(path=r["path"]) for r in policy.get("exact_paths", []))
        decimal = tuple(
            DecimalPathRule(
                path=r["path"],
                mode=DecimalMode(r["mode"]),
                scale=r["scale"],
                unit=r["unit"],
                rationale=r["rationale"],
            )
            for r in policy.get("decimal_paths", [])
        )
        ignored = tuple(
            IgnoredPathRule(path=r["path"], reason=r["reason"])
            for r in policy.get("ignored_paths", [])
        )
        artifact = tuple(
            ArtifactCheckRule(
                artifact_selector=r["artifact_selector"],
                required_status=ArtifactStatus(r["required_status"]),
                require_non_zero_size=r["require_non_zero_size"],
                require_integrity_hash=r["require_integrity_hash"],
            )
            for r in policy.get("artifact_checks", [])
        )

        # Resolve paths using the evaluation root
        stages = tuple(EvaluationStage(stage) for stage in s.get("required_stages", []))
        doc_refs = tuple(
            resolve_and_verify_path(
                Path(d),
                evaluation_root=root,
                reference_kind=EvaluationReferenceKind.DOCUMENT,
                allow_missing=not require_files,
            )
            for d in s.get("document_refs", [])
        )

        allow_missing = not require_files
        scenario = EvaluationScenario(
            scenario_id=s["scenario_id"],
            fixture_revision=s["fixture_revision"],
            project_input_path=resolve_and_verify_path(
                Path(s["project_input_path"]),
                evaluation_root=root,
                reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
                allow_missing=allow_missing,
            ),
            document_refs=doc_refs,
            required_stages=stages,
            expected_outcome=ExpectedOutcome(s["expected_outcome"]),
            expected_path=resolve_and_verify_path(
                Path(s["expected_path"]),
                evaluation_root=root,
                reference_kind=EvaluationReferenceKind.EXPECTED_OUTPUT,
                allow_missing=allow_missing,
            ),
            comparison_policy=ComparisonPolicy(
                exact_paths=exact,
                decimal_paths=decimal,
                ignored_paths=ignored,
                artifact_checks=artifact,
            ),
            provenance=ManifestProvenance(
                source=s["provenance"]["source"],
                rationale=s["provenance"]["rationale"],
            ),
        )
        scenarios.append(scenario)

    return EvaluationManifest(
        schema_version=raw["schema_version"],
        suite_id=raw["suite_id"],
        suite_revision=raw["suite_revision"],
        scenarios=tuple(scenarios),
    )
