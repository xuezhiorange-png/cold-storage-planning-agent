"""One-shot script to capture the golden artifact from a real SQLite Transaction B run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
    ProjectVersionReadPort,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    FixedTransactionBIdFactory,
    StageExecutionResult,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyAuditOutboxRepository,
    SqlAlchemyCalculationRunRepository,
    SqlAlchemyCoefficientContextRepository,
    SqlAlchemyExecutionSnapshotRepository,
    SqlAlchemyOrchestrationAttemptRepository,
    SqlAlchemyOrchestrationIdentityRepository,
    SqlAlchemyOrchestrationRequestRepository,
    SqlAlchemySourceBindingRepository,
    SqlAlchemyVerificationReadPort,
)
from cold_storage.modules.projects.infrastructure.orm import (
    ProjectRecord,
    ProjectVersionRecord,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "tests" / "integration"))

from transaction_b_golden import (  # noqa: E402
    GOLDEN_ATTEMPT_ID,
    GOLDEN_COEFFICIENT_CONTEXT_ID,
    GOLDEN_FINGERPRINT,
    GOLDEN_ORCHESTRATION_IDENTITY_ID,
    GOLDEN_PROJECT_ID,
    GOLDEN_PROJECT_VERSION_ID,
    GOLDEN_REQUEST_ID,
    GOLDEN_SNAPSHOT_ID,
    _seed_golden_prerequisites,
    get_calculator_output,
    read_transaction_b_artifact,
)

from cold_storage.modules.orchestration.domain.fingerprint import result_hash  # noqa: E402

_REQUIRED_CODES: tuple[str, ...] = (
    "area.auxiliary_area_ratio",
    "area.circulation_allowance_ratio",
    "investment.building_unit_cost",
    "investment.electrical_installation_ratio",
    "investment.other_expenses_ratio",
    "investment.refrigeration_equipment_ratio",
    "pallet.net_load_kg",
    "pallet.turnover_factor",
    "power.design_margin_ratio",
    "power.standby_ratio",
)
_REGISTRY_VERSION = "1.0.0"
_CV_VECTOR: dict[str, str] = {
    "zone": "1.0.0",
    "cooling_load": "1.0.0",
    "equipment": "1.0.0",
    "power": "1.0.0",
    "investment": "1.0.0",
}


def _make_resolved_coefficient() -> ResolvedCoefficientContextCandidate:
    coefficients = []
    revision_ids = []
    for i, code in enumerate(_REQUIRED_CODES, 1):
        rev_id = f"rev-{i:03d}"
        revision_ids.append(rev_id)
        coefficients.append(
            {
                "definition_id": f"def-{i:03d}",
                "code": code,
                "revision_id": rev_id,
                "revision_number": 1,
                "unit": "dimensionless",
                "source_type": "standard",
                "status": "approved",
                "value_decimal": "1.0",
            }
        )
    req_hash = result_hash(
        {
            "registry_version": _REGISTRY_VERSION,
            "calculator_version_vector": dict(_CV_VECTOR),
            "required_codes": list(_REQUIRED_CODES),
        }
    )
    content = {
        "source_type": "catalog",
        "validity_status": "approved",
        "project_id": GOLDEN_PROJECT_ID,
        "project_version_id": GOLDEN_PROJECT_VERSION_ID,
        "schema_version": "1.0.0",
        "coefficient_count": len(coefficients),
        "coefficients": coefficients,
        "requirement_registry_version": _REGISTRY_VERSION,
        "calculator_version_vector": dict(_CV_VECTOR),
        "required_codes": list(_REQUIRED_CODES),
        "requirement_hash": req_hash,
    }
    return ResolvedCoefficientContextCandidate(
        project_id=GOLDEN_PROJECT_ID,
        project_version_id=GOLDEN_PROJECT_VERSION_ID,
        schema_version="1.0.0",
        content=content,
        content_hash=result_hash(content),
        approved_revision_ids=tuple(revision_ids),
    )


# ── Calculator metadata ──────────────────────────────────────────────────
_STAGE_META: dict[str, tuple[str, str, str]] = {
    "zone": ("cold_room_zone_plan", "1.0.0", "zone"),
    "cooling_load": ("cooling_load", "1.0.0", "cooling_load"),
    "equipment": ("equipment", "1.0.0", "equipment"),
    "power": ("installed_power", "1.0.0", "power"),
    "investment": ("investment_estimate", "1.0.0", "investment"),
}


class _GoldenCalculatorPort:
    """Calculator port returning fixed golden outputs."""

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, Any],
    ) -> StageExecutionResult:
        calc_name, calc_version, calc_type = _STAGE_META[stage_name]
        output = get_calculator_output(stage_name)
        return StageExecutionResult(
            calculator_name=calc_name,
            calculator_version=calc_version,
            calculation_type=calc_type,
            result_snapshot=output,
            formulas=[
                {
                    "formula_id": f"form-{stage_name}-01",
                    "formula_version": "1.0.0",
                    "expression": f"Q = m * cp * dT ({stage_name})",
                    "description": f"Heat load calculation for {stage_name}",
                }
            ],
            coefficients=[
                {
                    "code": "pallet.net_load_kg",
                    "value": "1000",
                    "unit": "kg",
                    "status": "approved",
                    "source_type": "catalog",
                    "source_reference": "standard-table-1",
                    "requires_review": False,
                    "revision_id": "rev-001",
                }
            ],
            assumptions=[f"Assumption for {stage_name}: standard operating conditions"],
            warnings=[
                {
                    "code": f"WARN_{stage_name.upper()}",
                    "message": f"Review {stage_name} calculation values",
                    "details": {},
                }
            ],
            source_references=[
                {
                    "source_type": "standard",
                    "source_reference": f"GB-{stage_name}-2024",
                    "version": "2024",
                    "validity_status": "approved",
                    "approval_status": "approved",
                    "requires_review": False,
                    "notes": "",
                }
            ],
            requires_review=False,
        )


class _VP(ProjectVersionReadPort):
    def load_by_id(self, session, project_version_id):
        from sqlalchemy import select

        rec = session.execute(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        ).scalar_one_or_none()
        if rec is None:
            return None
        pr = session.execute(
            select(ProjectRecord).where(ProjectRecord.id == rec.project_id)
        ).scalar_one_or_none()
        return _LoadedVersion(
            project_id=rec.project_id,
            project_product_category=pr.product_category if pr else "",
            status=rec.status,
            version_number=rec.version_number,
            input_snapshot=rec.input_snapshot or {},
        )


def main() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        print(f"Alembic failed:\n{r.stderr}", file=sys.stderr)
        sys.exit(1)

    e = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    sf = sessionmaker(bind=e, expire_on_commit=False)

    with sf() as s:
        _seed_golden_prerequisites(s)

    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(sf)
    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.resolve.return_value = _make_resolved_coefficient()

    svc = OrchestrationService(
        uow_factory=uow_factory,
        request_repo=SqlAlchemyOrchestrationRequestRepository(),
        outbox_repo=SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
        version_port=_VP(),
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
        calc_run_repo=SqlAlchemyCalculationRunRepository(),
        source_binding_repo=SqlAlchemySourceBindingRepository(),
        calculator_port=_GoldenCalculatorPort(),
        verification_read_port=SqlAlchemyVerificationReadPort(),
        id_factory=FixedTransactionBIdFactory(),
    )

    svc.execute_transaction_b(
        request_id=GOLDEN_REQUEST_ID,
        project_id=GOLDEN_PROJECT_ID,
        project_version_id=GOLDEN_PROJECT_VERSION_ID,
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_attempt_id=GOLDEN_ATTEMPT_ID,
        orchestration_fingerprint=GOLDEN_FINGERPRINT,
        execution_snapshot={"throughput_t": "25.0"},
        coefficient_context={"coefficients": []},
    )

    with sf() as s:
        artifact = read_transaction_b_artifact(s, attempt_id=GOLDEN_ATTEMPT_ID)

    golden_path = BACKEND_DIR / "tests" / "golden" / "transaction_b_cross_backend_v1.json"
    golden_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n")
    print(f"Golden artifact written to {golden_path}", file=sys.stderr)

    e.dispose()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
