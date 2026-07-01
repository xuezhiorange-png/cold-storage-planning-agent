"""Cross-backend golden parity test — SQLite.

Uses real Alembic Head SQLite schema. Seeds golden prerequisites directly,
runs Transaction B with FixedTransactionBIdFactory, reads back from DB,
and compares with the golden JSON artifact.

Skips if DATABASE_BACKEND == "postgresql".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite golden parity tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from sqlalchemy import create_engine, event, select
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
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
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
from tests.integration.transaction_b_golden import (
    _CALCULATOR_META,
    _CALCULATOR_OUTPUTS,
    GOLDEN_ATTEMPT_ID,
    GOLDEN_COEFFICIENT_CONTEXT_ID,
    GOLDEN_FINGERPRINT,
    GOLDEN_ORCHESTRATION_IDENTITY_ID,
    GOLDEN_PROJECT_ID,
    GOLDEN_PROJECT_VERSION_ID,
    GOLDEN_REQUEST_ID,
    GOLDEN_SNAPSHOT_ID,
    _seed_golden_prerequisites,
    assert_matches_cross_backend_golden,
    load_cross_backend_golden,
    read_transaction_b_artifact,
    validate_typed_snapshots_parse_all,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── Required codes & version vector ────────────────────────────────────────

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
    """Build resolved coefficient context matching golden seed."""
    coefficients: list[dict[str, object]] = []
    revision_ids: list[str] = []
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

    content: dict[str, object] = {
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


# ── Calculator fixtures ────────────────────────────────────────────────────


_STAGE_DATA: dict[str, tuple[str, str, str]] = {
    "zone": ("cold_room_zone_plan", "1.0.0", "zone"),
    "cooling_load": ("cooling_load", "1.0.0", "cooling_load"),
    "equipment": ("equipment", "1.0.0", "equipment"),
    "power": ("installed_power", "1.0.0", "power"),
    "investment": ("investment_estimate", "1.0.0", "investment"),
}


class _GoldenCalculatorPort:
    """Mock CalculatorPort returning deterministic golden outputs for each stage."""

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, Any],
    ) -> StageExecutionResult:
        calc_name, calc_version, calc_type = _STAGE_DATA[stage_name]
        return StageExecutionResult(
            calculator_name=calc_name,
            calculator_version=calc_version,
            calculation_type=calc_type,
            result_snapshot=dict(_CALCULATOR_OUTPUTS[stage_name]),
            formulas=[],
            coefficients=[],
            assumptions=[],
            warnings=[],
            source_references=[],
            requires_review=False,
        )


class _GoldenVersionPort(ProjectVersionReadPort):
    def load_by_id(self, session: Any, project_version_id: str) -> _LoadedVersion | None:
        record = session.execute(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        project_record = session.execute(
            select(ProjectRecord).where(ProjectRecord.id == record.project_id)
        ).scalar_one_or_none()
        product_category = project_record.product_category if project_record else ""
        return _LoadedVersion(
            project_id=record.project_id,
            project_product_category=product_category,
            status=record.status,
            version_number=record.version_number,
            input_snapshot=record.input_snapshot or {},
        )


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    """Create a SQLite DB and run Alembic upgrade head."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}\n{r.stdout}")

    e = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def service(session_factory):
    """Fully wired OrchestrationService with golden calculator and FixedTransactionBIdFactory."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)
    version_port = _GoldenVersionPort()

    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.return_value = _make_resolved_coefficient()

    return OrchestrationService(
        uow_factory=uow_factory,
        request_repo=SqlAlchemyOrchestrationRequestRepository(),
        outbox_repo=SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
        version_port=version_port,
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
        calc_run_repo=SqlAlchemyCalculationRunRepository(),
        source_binding_repo=SqlAlchemySourceBindingRepository(),
        calculator_port=_GoldenCalculatorPort(),
        verification_read_port=SqlAlchemyVerificationReadPort(),
        id_factory=FixedTransactionBIdFactory(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────


EXPECTED_ARTIFACT_KEYS = {
    "result_hashes",
    "combined_source_hash",
    "canonical_result_snapshots",
    "upstream_provenance",
    "requires_review",
    "calculator_identity",
    "source_snapshot_schema_version",
    "binding_schema_version",
    "authority_chain",
    "source_binding_slot_ids",
    "source_snapshot_schema_versions",
}


class TestGoldenParitySQLite:
    """Golden parity tests that run on SQLite."""

    def test_golden_artifact_loads(self) -> None:
        """Golden artifact JSON is valid and has expected structure."""
        golden = load_cross_backend_golden()
        assert set(golden.keys()) == EXPECTED_ARTIFACT_KEYS, (
            f"Golden artifact keys mismatch: got {sorted(golden.keys())}"
        )

    def test_typed_snapshots_parse_all_calculator_outputs(self) -> None:
        """All 5 calculator outputs pass through real typed snapshot adapters."""
        validate_typed_snapshots_parse_all()

    def test_golden_transaction_b_produces_canonical_artifact(
        self, service, session_factory
    ) -> None:
        """Run Transaction B with golden IDs and compare artifact against golden JSON.

        Golden comparison is unconditional — missing file or degraded
        structure causes immediate test failure (fail-closed).
        """
        # Seed golden prerequisites directly (NOT via Transaction A)
        with session_factory() as session:
            _seed_golden_prerequisites(session)

        # Execute Transaction B
        result = service.execute_transaction_b(
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

        assert result.status == "COMPLETED"
        assert len(result.persisted_stages) == 5

        # Read back from DB
        with session_factory() as session:
            artifact = read_transaction_b_artifact(session, attempt_id=GOLDEN_ATTEMPT_ID)

        # Verify structure — must match EXPECTED_ARTIFACT_KEYS exactly
        assert set(artifact.keys()) == EXPECTED_ARTIFACT_KEYS, (
            f"Artifact keys mismatch: got {sorted(artifact.keys())}"
        )

        # Verify result hashes are non-empty strings
        for stage_name in ("zone", "cooling_load", "equipment", "power", "investment"):
            assert isinstance(artifact["result_hashes"][stage_name], str)
            assert len(artifact["result_hashes"][stage_name]) > 0

        # Verify calculator identity matches expected
        for stage_name in ("zone", "cooling_load", "equipment", "power", "investment"):
            meta = _CALCULATOR_META[stage_name]
            ci = artifact["calculator_identity"][stage_name]
            assert ci["calculator_name"] == meta["calculator_id"]
            assert ci["calculator_version"] == meta["calculator_version"]
            assert ci["calculation_type"] == stage_name

        # Verify combined_source_hash is non-empty
        assert isinstance(artifact["combined_source_hash"], str)
        assert len(artifact["combined_source_hash"]) > 0

        # Verify schema versions
        assert artifact["source_snapshot_schema_version"] == "1.0.0"
        assert artifact["binding_schema_version"] == "1.0.0"

        # Verify per-stage schema versions
        for stage_name in ("zone", "cooling_load", "equipment", "power", "investment"):
            assert artifact["source_snapshot_schema_versions"][stage_name] == "1.0.0"

        # Verify authority chain
        ac = artifact["authority_chain"]
        assert ac["project_id"] == GOLDEN_PROJECT_ID
        assert ac["project_version_id"] == GOLDEN_PROJECT_VERSION_ID
        assert ac["execution_snapshot_id"] == GOLDEN_SNAPSHOT_ID
        assert ac["coefficient_context_id"] == GOLDEN_COEFFICIENT_CONTEXT_ID
        assert ac["orchestration_identity_id"] == GOLDEN_ORCHESTRATION_IDENTITY_ID
        assert ac["orchestration_attempt_id"] == GOLDEN_ATTEMPT_ID
        assert ac["orchestration_fingerprint"] == GOLDEN_FINGERPRINT

        # Verify source binding slot IDs point to expected fixed CalculationRun IDs
        slots = artifact["source_binding_slot_ids"]
        assert slots["zone"] == "golden-run-zone-001"
        assert slots["cooling_load"] == "golden-run-cooling-load-001"
        assert slots["equipment"] == "golden-run-equipment-001"
        assert slots["power"] == "golden-run-power-001"
        assert slots["investment"] == "golden-run-investment-001"

        # Verify slot IDs match the run_ids from the 5 CalculationRuns
        run_ids = sorted(
            f"golden-run-{s}-001"
            for s in ("zone", "cooling-load", "equipment", "power", "investment")
        )
        slot_run_ids = sorted(slots.values())
        assert slot_run_ids == run_ids, (
            f"Slot IDs {slot_run_ids} don't match expected run IDs {run_ids}"
        )

        # ── UNCONDITIONAL golden comparison (fail-closed) ──────────────
        golden_path = (
            Path(__file__).resolve().parent.parent
            / "golden"
            / "transaction_b_cross_backend_v1.json"
        )
        assert golden_path.exists(), f"Golden artifact file missing: {golden_path}"
        golden = json.loads(golden_path.read_text())
        assert "result_hashes" in golden, (
            "Golden artifact missing 'result_hashes' — file is corrupted"
        )
        assert_matches_cross_backend_golden(artifact, golden)
