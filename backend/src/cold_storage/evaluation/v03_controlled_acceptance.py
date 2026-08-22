"""V0.3 P5 controlled-acceptance harness and gate verification.

This module implements the Stage-3 harness only. It validates dispatch,
operator, source-identity, and execution-authorization gates, then fails closed
before any Scenario A/B/C planning run. It is not a second engineering engine.
"""

from __future__ import annotations

import os
from typing import Any

HARNESS_SCHEMA_VERSION = "v0.3-p5-controlled-acceptance-harness.v1"
EVIDENCE_SCHEMA_VERSION = "v0.3-p5-controlled-acceptance-evidence.v1"
CONTRACT_PATH = "docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md"
RUNBOOK_PATH = "docs/runbooks/V0_3-P5-controlled-acceptance-and-release.md"
WORKFLOW_PATH = ".github/workflows/v0-3-p5-controlled-acceptance-and-release.yml"

SCENARIO_NAMES: frozenset[str] = frozenset({"A", "B", "C"})
FIXTURE_PATHS: dict[str, str] = {
    "A": "backend/tests/pilot/data/v03-scenario-a-normal-formal-report.v1.json",
    "B": "backend/tests/pilot/data/v03-scenario-b-review-required-formal-report.v1.json",
    "C": "backend/tests/pilot/data/v03-scenario-c-agent-knowledge-deterministic.v1.json",
}

REJECTED_OPERATOR_NAMES = frozenset({"system", "api", "background", "llm"})
EXECUTION_AUTHORIZATION_ENV = "V03_P5_CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED"
AUTHORIZATION_RECORD_ENV = "V03_P5_CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_ID"
ALLOWED_EXECUTION_AUTHORIZED_VALUES = frozenset({"YES", "true", "True", "1"})
MAIN_REF = "refs/heads/main"
WORKFLOW_DISPATCH_EVENT = "workflow_dispatch"


class V03ControlledAcceptanceError(RuntimeError):
    """Machine-readable fail-closed harness error."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_json(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
        }


def _require(condition: bool, code: str, message: str, **details: object) -> None:
    if not condition:
        raise V03ControlledAcceptanceError(code, message, **details)


def execution_authorized_from_env() -> bool:
    """Return whether the explicit execution-authorization env gate is set."""

    value = os.environ.get(EXECUTION_AUTHORIZATION_ENV, "").strip()
    return value in ALLOWED_EXECUTION_AUTHORIZED_VALUES


def validate_trusted_operator(operator: str) -> str:
    """Validate the explicit trusted-operator seam."""

    value = operator.strip()
    _require(bool(value), "TRUSTED_OPERATOR_MISSING", "trusted operator is required")
    _require(
        value.lower() not in REJECTED_OPERATOR_NAMES,
        "TRUSTED_OPERATOR_NOT_HUMAN",
        "system/api/background/llm actors are not controlled human proof",
        operator=value,
    )
    return value


def validate_execution_source_identity(
    source_sha: str,
    source_tree_sha: str,
) -> tuple[str, str]:
    """Require the workflow/runner to provide the actual executing checkout."""

    _require(
        isinstance(source_sha, str) and bool(source_sha.strip()),
        "EXECUTION_SOURCE_SHA_MISSING",
        "controlled execution source commit must be supplied explicitly",
    )
    _require(
        isinstance(source_tree_sha, str) and bool(source_tree_sha.strip()),
        "EXECUTION_SOURCE_TREE_SHA_MISSING",
        "controlled execution source tree must be supplied explicitly",
    )
    return source_sha.strip(), source_tree_sha.strip()


def validate_authorization_record_id(authorization_record_id: str | None) -> str:
    """Require a non-empty separately authorized record identifier."""

    value = (authorization_record_id or "").strip()
    _require(
        bool(value),
        "CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_MISSING",
        "authorization record id is required for controlled acceptance",
    )
    return value


def validate_execution_authorization(
    authorization_record_id: str | None,
    *,
    execution_authorized: bool,
) -> str:
    """Fail closed unless explicit execution authorization is present."""

    record = validate_authorization_record_id(authorization_record_id)
    _require(
        execution_authorized,
        "CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED",
        "V0.3 P5 controlled acceptance execution is not authorized",
        authorization_record_id=record,
        execution_authorized=execution_authorized,
    )
    return record


def validate_scenario_name(scenario: str) -> str:
    """Validate the frozen Scenario A/B/C identifier."""

    value = scenario.strip().upper()
    _require(
        value in SCENARIO_NAMES,
        "SCENARIO_INVALID",
        "scenario must be one of A, B, or C",
        scenario=scenario,
    )
    return value


def validate_workflow_dispatch_gates(
    *,
    event_name: str,
    git_ref: str,
    checked_out_sha: str,
    checked_out_tree_sha: str,
    declared_source_sha: str,
    declared_source_tree_sha: str,
    authorization_record_id: str,
    trusted_operator: str,
) -> dict[str, str]:
    """Validate workflow_dispatch-only, main-only, exact-source-bound gates."""

    _require(
        event_name == WORKFLOW_DISPATCH_EVENT,
        "WORKFLOW_DISPATCH_REQUIRED",
        "controlled acceptance must be workflow_dispatch only",
        event_name=event_name,
    )
    _require(
        git_ref == MAIN_REF,
        "WORKFLOW_MAIN_REF_REQUIRED",
        "controlled acceptance must run on refs/heads/main only",
        git_ref=git_ref,
    )
    record = validate_authorization_record_id(authorization_record_id)
    operator = validate_trusted_operator(trusted_operator)
    execution_sha, execution_tree = validate_execution_source_identity(
        declared_source_sha,
        declared_source_tree_sha,
    )
    _require(
        checked_out_sha == execution_sha,
        "EXECUTION_SOURCE_SHA_MISMATCH",
        "declared source sha must match the checked-out commit",
        checked_out_sha=checked_out_sha,
        declared_source_sha=execution_sha,
    )
    _require(
        checked_out_tree_sha == execution_tree,
        "EXECUTION_SOURCE_TREE_MISMATCH",
        "declared source tree must match the checked-out tree",
        checked_out_tree_sha=checked_out_tree_sha,
        declared_source_tree_sha=execution_tree,
    )
    return {
        "authorization_record_id": record,
        "trusted_operator": operator,
        "execution_source_sha": execution_sha,
        "execution_source_tree_sha": execution_tree,
        "workflow_dispatch_only": "YES",
        "main_only": "YES",
    }


def build_harness_status() -> dict[str, object]:
    """Return the frozen harness authorization posture for evidence uploads."""

    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "contract_path": CONTRACT_PATH,
        "runbook_path": RUNBOOK_PATH,
        "workflow_path": WORKFLOW_PATH,
        "scenarios": sorted(SCENARIO_NAMES),
        "fixture_paths": dict(FIXTURE_PATHS),
        "authorization": {
            "CONTROLLED_ACCEPTANCE_AUTHORIZED": "NO",
            "CONTROLLED_ACCEPTANCE_EXECUTED": "NO",
            "SCENARIO_A_RUN_AUTHORIZED": "NO",
            "SCENARIO_B_RUN_AUTHORIZED": "NO",
            "SCENARIO_C_RUN_AUTHORIZED": "NO",
            "FIXTURE_JSON_CREATE_AUTHORIZED": "NO",
            "V0_3_TAG_AUTHORIZED": "NO",
            "GITHUB_RELEASE_AUTHORIZED": "NO",
            "PRODUCTION_ENABLEMENT_AUTHORIZED": "NO",
            "ORDINARY_PR_CI_IS_CONTROLLED_ACCEPTANCE": "NO",
            "NO_STEP_IMPLIES_THE_NEXT": "TRUE",
        },
        "harness_round": "IMPLEMENTATION_R1",
        "scenario_execution_implemented": "NO",
    }


def verify_harness_gates(
    *,
    authorization_record_id: str,
    trusted_operator: str,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    event_name: str | None = None,
    git_ref: str | None = None,
    checked_out_sha: str | None = None,
    checked_out_tree_sha: str | None = None,
) -> dict[str, object]:
    """Verify operator/source gates and return harness status evidence."""

    validate_trusted_operator(trusted_operator)
    validate_authorization_record_id(authorization_record_id)
    validate_execution_source_identity(execution_source_sha, execution_source_tree_sha)
    payload: dict[str, object] = {
        "status": "PASS",
        "gate": "HARNESS_VERIFY",
        "authorization_record_id": authorization_record_id.strip(),
        "trusted_operator": trusted_operator.strip(),
        "execution_source_sha": execution_source_sha.strip(),
        "execution_source_tree_sha": execution_source_tree_sha.strip(),
        "harness": build_harness_status(),
    }
    if (
        event_name is not None
        and git_ref is not None
        and checked_out_sha is not None
        and checked_out_tree_sha is not None
    ):
        payload["workflow_gates"] = validate_workflow_dispatch_gates(
            event_name=event_name,
            git_ref=git_ref,
            checked_out_sha=checked_out_sha,
            checked_out_tree_sha=checked_out_tree_sha,
            declared_source_sha=execution_source_sha,
            declared_source_tree_sha=execution_source_tree_sha,
            authorization_record_id=authorization_record_id,
            trusted_operator=trusted_operator,
        )
    return payload


def refuse_scenario_execution(
    *,
    scenario: str,
    authorization_record_id: str,
    trusted_operator: str,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    execution_authorized: bool,
    backend: str,
    run_index: int,
) -> dict[str, object]:
    """Validate all gates, then fail closed before any scenario planning run."""

    scenario_name = validate_scenario_name(scenario)
    record = validate_execution_authorization(
        authorization_record_id,
        execution_authorized=execution_authorized,
    )
    operator = validate_trusted_operator(trusted_operator)
    source_sha, source_tree = validate_execution_source_identity(
        execution_source_sha,
        execution_source_tree_sha,
    )
    _require(
        backend in {"sqlite", "postgresql"},
        "BACKEND_INVALID",
        "controlled acceptance backend must be sqlite or postgresql",
        backend=backend,
    )
    _require(run_index > 0, "RUN_INDEX_INVALID", "run_index must be positive", run_index=run_index)
    fixture_path = FIXTURE_PATHS[scenario_name]
    raise V03ControlledAcceptanceError(
        "SCENARIO_EXECUTION_NOT_AUTHORIZED",
        "V0.3 P5 scenario execution is not authorized in harness R1",
        scenario=scenario_name,
        authorization_record_id=record,
        trusted_operator=operator,
        execution_source_sha=source_sha,
        execution_source_tree_sha=source_tree,
        backend=backend,
        run_index=run_index,
        fixture_path=fixture_path,
        fixture_binding_required="YES",
        harness_round="IMPLEMENTATION_R1",
    )


def ordinary_ci_is_controlled_acceptance() -> bool:
    """Ordinary PR CI must never be treated as controlled acceptance evidence."""

    return False


__all__ = [
    "AUTHORIZATION_RECORD_ENV",
    "CONTRACT_PATH",
    "EVIDENCE_SCHEMA_VERSION",
    "EXECUTION_AUTHORIZATION_ENV",
    "FIXTURE_PATHS",
    "HARNESS_SCHEMA_VERSION",
    "MAIN_REF",
    "RUNBOOK_PATH",
    "SCENARIO_NAMES",
    "WORKFLOW_DISPATCH_EVENT",
    "WORKFLOW_PATH",
    "V03ControlledAcceptanceError",
    "build_harness_status",
    "execution_authorized_from_env",
    "ordinary_ci_is_controlled_acceptance",
    "refuse_scenario_execution",
    "validate_authorization_record_id",
    "validate_execution_authorization",
    "validate_execution_source_identity",
    "validate_scenario_name",
    "validate_trusted_operator",
    "validate_workflow_dispatch_gates",
    "verify_harness_gates",
]
