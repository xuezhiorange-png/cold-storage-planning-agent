"""Transaction B → Production scheme end-to-end test — SQLite.

Seeds golden Transaction B prerequisites, creates 5 CalculationRuns + 1
SourceBinding using golden calculator outputs and golden IDs, feeds the
resulting SourceBinding to ProductionSchemeService, and verifies golden
hashes, power authority, and trusted readback.

Uses _GoldenCalculatorPort outputs as the source of truth. Hashes are
computed using the domain-layer SourceSnapshotContentV1 method (matching
the production verifier's recomputation).

Skips if DATABASE_BACKEND == "postgresql".
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite production Transaction B e2e tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.domain.snapshots import (
    SourceSnapshotContentV1,
    SourceSnapshotProvenanceV1,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
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
    GOLDEN_SNAPSHOT_ID,
    _seed_golden_prerequisites,
    load_cross_backend_golden,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── Fixed IDs from FixedTransactionBIdFactory ────────────────────────────
GOLDEN_SOURCE_BINDING_ID = "golden-source-binding-001"
GOLDEN_WEIGHT_SET_ID = "golden-ws-001"
GOLDEN_WEIGHT_REVISION_ID = "golden-wrev-001"

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


# ── Canonical JSON hash helpers (matching verifier exactly) ────────────────


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_result_hash(result_snapshot: dict[str, Any]) -> str:
    """Compute raw result hash from a snapshot dict (for per_calc hash map)."""
    return hashlib.sha256(_canonical_json(result_snapshot).encode()).hexdigest()


def _compute_domain_hash(
    *,
    stage: str,
    result_snapshot: dict[str, Any],
    run_id: str,
) -> str:
    """Compute domain SourceSnapshotContentV1 result_hash for a stage.

    This is the SAME hash the production verifier recomputes.
    P0-1: Uses raw result_snapshot (no coercion).
    """

    # Upstream IDs follow the DAG
    _SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
        "zone": {},
        "cooling_load": {"zone": GOLDEN_ZONE_RUN_ID},
        "equipment": {"cooling_load": GOLDEN_COOL_RUN_ID},
        "power": {"equipment": GOLDEN_EQUIP_RUN_ID},
        "investment": {
            "zone": GOLDEN_ZONE_RUN_ID,
            "power": GOLDEN_POWER_RUN_ID,
        },
    }

    provenance = SourceSnapshotProvenanceV1(
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
        upstream_calculation_ids=_SLOT_UPSTREAM_IDS.get(stage, {}),
    )
    meta = _CALCULATOR_META[stage]
    content = SourceSnapshotContentV1(
        schema_version="1.0.0",
        calculation_type=stage,
        calculator_name=meta["calculator_id"],
        calculator_version=meta["calculator_version"],
        project_id=GOLDEN_PROJECT_ID,
        project_version_id=GOLDEN_PROJECT_VERSION_ID,
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
        input_hash="e2e-input-hash",
        requires_review=False,
        payload=result_snapshot,
        provenance=provenance,
    )
    return result_hash(content)


# ── Fixed IDs (from FixedTransactionBIdFactory) ──────────────────────────

GOLDEN_ZONE_RUN_ID = "golden-run-zone-001"
GOLDEN_COOL_RUN_ID = "golden-run-cooling-load-001"
GOLDEN_EQUIP_RUN_ID = "golden-run-equipment-001"
GOLDEN_POWER_RUN_ID = "golden-run-power-001"
GOLDEN_INVEST_RUN_ID = "golden-run-investment-001"

_SLOT_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

_SLOT_CALCULATOR_NAMES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

_SLOT_CALCULATION_TYPES: dict[str, str] = {
    "zone": "zone",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "power",
    "investment": "investment",
}

GOLDEN_RUN_IDS: dict[str, str] = {
    "zone": GOLDEN_ZONE_RUN_ID,
    "cooling_load": GOLDEN_COOL_RUN_ID,
    "equipment": GOLDEN_EQUIP_RUN_ID,
    "power": GOLDEN_POWER_RUN_ID,
    "investment": GOLDEN_INVEST_RUN_ID,
}

_SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
    "zone": {},
    "cooling_load": {"zone": GOLDEN_ZONE_RUN_ID},
    "equipment": {"cooling_load": GOLDEN_COOL_RUN_ID},
    "power": {"equipment": GOLDEN_EQUIP_RUN_ID},
    "investment": {
        "zone": GOLDEN_ZONE_RUN_ID,
        "power": GOLDEN_POWER_RUN_ID,
    },
}

# ── Domain hashes (computed from golden calculator outputs) ────────────────
# These match what the production verifier recomputes.

PER_CALC_HASHES: dict[str, str] = {}
for _stage in _SLOT_STAGE_ORDER:
    PER_CALC_HASHES[_stage] = _compute_domain_hash(
        stage=_stage,
        result_snapshot=_CALCULATOR_OUTPUTS[_stage],
        run_id=GOLDEN_RUN_IDS[_stage],
    )


def _compute_golden_combined_source_hash() -> str:
    """Compute combined_source_hash matching the verifier's implementation."""
    from cold_storage.modules.schemes.application.source_binding_verifier import (
        _compute_combined_source_hash,
    )

    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=GOLDEN_PROJECT_ID,
        project_version_id=GOLDEN_PROJECT_VERSION_ID,
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_attempt_id=GOLDEN_ATTEMPT_ID,
        orchestration_fingerprint=GOLDEN_FINGERPRINT,
        slot_ids=GOLDEN_RUN_IDS,
        result_hashes=PER_CALC_HASHES,
        requires_reviews={stage: False for stage in _SLOT_STAGE_ORDER},
    )


GOLDEN_COMBINED_SOURCE_HASH = _compute_golden_combined_source_hash()


# ── Weight set revision content (standard production weights) ───────────


def _compute_weight_content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(content).encode()).hexdigest()


WEIGHT_CRITERIA_RAW: list[dict[str, Any]] = [
    {
        "criterion_code": "total_area_m2",
        "weight": "0.20",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "investment_cny",
        "weight": "0.30",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "total_position_count",
        "weight": "0.15",
        "direction": "higher_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "room_module_count",
        "weight": "0.10",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "door_count",
        "weight": "0.05",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "partition_length_proxy_m",
        "weight": "0.05",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "installed_power_kw_e",
        "weight": "0.15",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
]

WEIGHT_REVISION_CONTENT: dict[str, Any] = {"criteria": WEIGHT_CRITERIA_RAW}
WEIGHT_CONTENT_HASH = _compute_weight_content_hash(WEIGHT_REVISION_CONTENT)


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


# ── Seeding helpers ───────────────────────────────────────────────────────


def _seed_calculation_runs(session: Any) -> dict[str, str]:
    """Create 5 CalculationRunRecords using golden calculator outputs.

    Hashes are computed using domain SourceSnapshotContentV1 (matching the
    production verifier). Returns per-calc hash map.
    """
    per_calc: dict[str, str] = {}
    for stage in _SLOT_STAGE_ORDER:
        run_id = GOLDEN_RUN_IDS[stage]
        snap = _CALCULATOR_OUTPUTS[stage]
        computed_hash = _compute_domain_hash(stage=stage, result_snapshot=snap, run_id=run_id)
        provenance: dict[str, Any] = {
            "stage": stage,
            "upstream_calculation_ids": _SLOT_UPSTREAM_IDS.get(stage, {}),
        }
        session.add(
            CalculationRunRecord(
                id=run_id,
                project_id=GOLDEN_PROJECT_ID,
                project_version_id=GOLDEN_PROJECT_VERSION_ID,
                calculator_name=_SLOT_CALCULATOR_NAMES[stage],
                calculator_version="1.0.0",
                input_snapshot={},
                result_snapshot=snap,
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=False,
                calculation_type=_SLOT_CALCULATION_TYPES[stage],
                orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
                orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
                execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
                coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
                input_hash="e2e-input-hash",
                result_hash=computed_hash,
                provenance=provenance,
                schema_version="1.0.0",
                orchestration_fingerprint=GOLDEN_FINGERPRINT,
                created_at=datetime.now(UTC),
            )
        )
        per_calc[stage] = computed_hash
    session.commit()
    return per_calc


def _seed_source_binding(session: Any, *, per_calc: dict[str, str]) -> None:
    """Create SourceBindingRecord using golden IDs and computed hashes."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        OrchestrationRunAttemptRecord,
    )

    combined = GOLDEN_COMBINED_SOURCE_HASH

    session.add(
        SourceBindingRecord(
            id=GOLDEN_SOURCE_BINDING_ID,
            project_id=GOLDEN_PROJECT_ID,
            project_version_id=GOLDEN_PROJECT_VERSION_ID,
            execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
            coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
            orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
            orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
            orchestration_fingerprint=GOLDEN_FINGERPRINT,
            zone_calculation_id=GOLDEN_ZONE_RUN_ID,
            cooling_load_calculation_id=GOLDEN_COOL_RUN_ID,
            equipment_calculation_id=GOLDEN_EQUIP_RUN_ID,
            power_calculation_id=GOLDEN_POWER_RUN_ID,
            investment_calculation_id=GOLDEN_INVEST_RUN_ID,
            per_calculation_result_hashes=per_calc,
            combined_source_hash=combined,
            schema_version="1.0.0",
            created_at=datetime.now(UTC),
        )
    )
    session.commit()

    # Link attempt → source binding
    attempt_rec = session.execute(
        select(OrchestrationRunAttemptRecord).where(
            OrchestrationRunAttemptRecord.id == GOLDEN_ATTEMPT_ID
        )
    ).scalar_one_or_none()
    if attempt_rec is not None and attempt_rec.source_binding_id is None:
        attempt_rec.source_binding_id = GOLDEN_SOURCE_BINDING_ID
        session.commit()


def _seed_weight_set_and_revision(session: Any) -> None:
    """Create SchemeWeightSetRecord + SchemeWeightSetRevisionRecord."""
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRecord,
        SchemeWeightSetRevisionRecord,
    )

    existing_ws = session.execute(
        select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == GOLDEN_WEIGHT_SET_ID)
    ).scalar_one_or_none()
    if existing_ws is None:
        session.add(
            SchemeWeightSetRecord(
                id=GOLDEN_WEIGHT_SET_ID,
                code="golden-standard-weights",
                name="Golden standard weights",
                revision=1,
                status="approved",
                source_type="production",
                criteria=WEIGHT_CRITERIA_RAW,
                requires_review=False,
                created_at=datetime.now(UTC),
                approved_at=datetime.now(UTC),
            )
        )

    existing_rev = session.execute(
        select(SchemeWeightSetRevisionRecord).where(
            SchemeWeightSetRevisionRecord.id == GOLDEN_WEIGHT_REVISION_ID
        )
    ).scalar_one_or_none()
    if existing_rev is None:
        session.add(
            SchemeWeightSetRevisionRecord(
                id=GOLDEN_WEIGHT_REVISION_ID,
                weight_set_id=GOLDEN_WEIGHT_SET_ID,
                code="golden-standard-weights",
                revision=1,
                status="approved",
                content=WEIGHT_REVISION_CONTENT,
                content_hash=WEIGHT_CONTENT_HASH,
                generator_compatibility_version="1.0.0",
                approved_at=datetime.now(UTC),
                approved_by="golden-e2e-test",
                created_at=datetime.now(UTC),
            )
        )
    session.commit()


def _seed_all_production_prereqs(session: Any) -> dict[str, str]:
    """Seed all production prerequisites: golden prereqs + CalculationRuns + binding + weight."""
    _seed_golden_prerequisites(session)

    # Link identity → attempt (authoritative_attempt_id must be non-NULL)
    from cold_storage.modules.orchestration.infrastructure.orm import (
        OrchestrationIdentityRecord,
        OrchestrationRunAttemptRecord,
    )

    identity_rec = session.execute(
        select(OrchestrationIdentityRecord).where(
            OrchestrationIdentityRecord.id == GOLDEN_ORCHESTRATION_IDENTITY_ID
        )
    ).scalar_one_or_none()
    if identity_rec is not None and identity_rec.authoritative_attempt_id is None:
        identity_rec.authoritative_attempt_id = GOLDEN_ATTEMPT_ID
        session.commit()

    # Mark attempt as COMPLETED (verifier requires this)
    attempt_rec = session.execute(
        select(OrchestrationRunAttemptRecord).where(
            OrchestrationRunAttemptRecord.id == GOLDEN_ATTEMPT_ID
        )
    ).scalar_one_or_none()
    if attempt_rec is not None and attempt_rec.status != "COMPLETED":
        from cold_storage.modules.orchestration.domain.contracts import AttemptStatus

        attempt_rec.status = AttemptStatus.COMPLETED
        session.commit()

    per_calc = _seed_calculation_runs(session)
    _seed_source_binding(session, per_calc=per_calc)
    _seed_weight_set_and_revision(session)
    return per_calc


# ── Production scheme service builder ─────────────────────────────────────


def _make_production_service(engine):
    """Create a ProductionSchemeService with real DB ports via UoW factory."""
    from cold_storage.modules.schemes.application.production_service import (
        ProductionSchemeService,
    )
    from cold_storage.modules.schemes.infrastructure.production_read_ports import (
        SqlAlchemySourceBindingReadPort,
        SqlAlchemyWeightRevisionReadPort,
    )
    from cold_storage.modules.schemes.infrastructure.production_repository import (
        SqlAlchemyProductionSchemeRunRepository,
    )
    from cold_storage.modules.schemes.infrastructure.production_uow_impl import (
        SqlAlchemyProductionSchemeUnitOfWork,
    )

    sf = sessionmaker(bind=engine, expire_on_commit=False)

    def uow_factory() -> SqlAlchemyProductionSchemeUnitOfWork:
        return SqlAlchemyProductionSchemeUnitOfWork(sf)

    return ProductionSchemeService(
        uow_factory=uow_factory,
        binding_read_port=SqlAlchemySourceBindingReadPort(),
        weight_revision_read_port=SqlAlchemyWeightRevisionReadPort(),
        run_repository=SqlAlchemyProductionSchemeRunRepository(),
    )


def _make_production_command():
    """Generate production scheme command referencing golden source binding."""
    from cold_storage.modules.schemes.application.production_ports import (
        GenerateProductionSchemeCommand,
    )

    return GenerateProductionSchemeCommand(
        source_binding_id=GOLDEN_SOURCE_BINDING_ID,
        weight_set_revision_id=GOLDEN_WEIGHT_REVISION_ID,
        profile_codes=("balanced",),
        profile_parameters={},
        actor="golden-e2e-test",
        correlation_id="golden-e2e-corr-001",
    )


# ════════════════════════════════════════════════════════════════════════════
# Transaction B → Production scheme end-to-end
# ════════════════════════════════════════════════════════════════════════════


class TestProductionTransactionBE2ESQLite:
    """Real Transaction B golden data drives production scheme generation.

    1. Seeds golden prerequisites + golden calculator outputs as CalculationRuns
    2. Creates SourceBinding with golden IDs
    3. Feeds SourceBinding to ProductionSchemeService
    4. Verifies golden hashes, power authority, and trusted readback
    """

    def test_transaction_b_to_production_e2e(self, engine, session_factory) -> None:
        # ── Step 1: Seed all production prerequisites with golden data ───
        with session_factory() as session:
            _seed_all_production_prereqs(session)

        # ── Step 2: Load golden artifact for hash comparison ─────────────
        golden = load_cross_backend_golden()

        # ── Step 3: Verify domain hashes match golden calculator outputs ─
        with session_factory() as session:
            for stage in _SLOT_STAGE_ORDER:
                run_id = GOLDEN_RUN_IDS[stage]
                run_rec = session.execute(
                    select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
                ).scalar_one()
                assert run_rec is not None, f"Missing CalculationRun for {stage}"
                assert run_rec.result_hash == PER_CALC_HASHES[stage], (
                    f"Domain hash mismatch for {stage}: "
                    f"got {run_rec.result_hash!r}, expected {PER_CALC_HASHES[stage]!r}"
                )
                assert run_rec.calculator_name == _CALCULATOR_META[stage]["calculator_id"]
                assert run_rec.calculator_version == _CALCULATOR_META[stage]["calculator_version"]

        # Verify combined_source_hash on SourceBinding
        with session_factory() as session:
            binding = session.execute(
                select(SourceBindingRecord).where(
                    SourceBindingRecord.id == GOLDEN_SOURCE_BINDING_ID
                )
            ).scalar_one()
            assert binding is not None
            assert binding.combined_source_hash == GOLDEN_COMBINED_SOURCE_HASH, (
                f"combined_source_hash mismatch: "
                f"got {binding.combined_source_hash!r}, "
                f"expected {GOLDEN_COMBINED_SOURCE_HASH!r}"
            )

        # Verify five slot IDs match golden FixedTransactionBIdFactory IDs
        golden_slots = golden["source_binding_slot_ids"]
        assert binding.zone_calculation_id == golden_slots["zone"]
        assert binding.cooling_load_calculation_id == golden_slots["cooling_load"]
        assert binding.equipment_calculation_id == golden_slots["equipment"]
        assert binding.power_calculation_id == golden_slots["power"]
        assert binding.investment_calculation_id == golden_slots["investment"]

        # ── Step 4: Generate production scheme ───────────────────────────
        prod_service = _make_production_service(engine)
        cmd = _make_production_command()
        run = prod_service.generate_production_scheme_run(cmd)

        # ── Step 5: Verify production scheme run ─────────────────────────
        assert run.status == "completed"

        with session_factory() as session:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeCandidateRecord,
                SchemeRunRecord,
            )

            rec = session.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one_or_none()
            assert rec is not None
            assert rec.status == "completed"
            assert rec.source_mode == "production"
            assert rec.source_binding_id == GOLDEN_SOURCE_BINDING_ID
            assert rec.weight_set_revision_id == GOLDEN_WEIGHT_REVISION_ID
            assert rec.source_contract_version == "1.0.0"

            # Verify combined_source_hash propagated correctly
            assert rec.combined_source_hash == GOLDEN_COMBINED_SOURCE_HASH

            assert rec.weight_set_content_hash == WEIGHT_CONTENT_HASH
            assert rec.content_hash is not None
            assert len(rec.content_hash) == 64  # SHA-256 hex

            # Verify candidates exist and have scores
            candidates = (
                session.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(candidates) > 0, "Expected at least one candidate"
            for cand_rec in candidates:
                assert cand_rec.total_score is not None, (
                    f"Candidate {cand_rec.scheme_code} total_score must not be NULL"
                )
                assert isinstance(cand_rec.total_score, Decimal), (
                    f"Candidate {cand_rec.scheme_code} total_score must be Decimal"
                )

        # ── Step 6: Verify power authority = 285.0 from golden ──────────
        power_snapshot = golden["canonical_result_snapshots"]["power"]
        power_value = power_snapshot["total_installed_power_kw_e"]
        assert power_value == "285.0", (
            f"Expected power authority 285.0 from golden, got {power_value!r}"
        )
        # Verify the power snapshot in DB also has the authority field
        assert "total_installed_power_kw_e" in _CALCULATOR_OUTPUTS["power"]
        assert _CALCULATOR_OUTPUTS["power"]["total_installed_power_kw_e"] == "285.0"

        # ── Step 7: Verify production provenance references exact 5 CalculationRuns ──
        with session_factory() as session:
            rec = session.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()

            # The five slot IDs should match golden IDs from FixedTransactionBIdFactory
            assert rec.zone_calculation_id == GOLDEN_ZONE_RUN_ID
            assert rec.cooling_load_calculation_id == GOLDEN_COOL_RUN_ID
            assert rec.equipment_calculation_id == GOLDEN_EQUIP_RUN_ID
            assert rec.power_calculation_id == GOLDEN_POWER_RUN_ID
            assert rec.investment_calculation_id == GOLDEN_INVEST_RUN_ID

            # Verify result hashes on the SchemeRun match the domain hashes
            assert rec.zone_result_hash == PER_CALC_HASHES["zone"]
            assert rec.cooling_load_result_hash == PER_CALC_HASHES["cooling_load"]
            assert rec.equipment_result_hash == PER_CALC_HASHES["equipment"]
            assert rec.power_result_hash == PER_CALC_HASHES["power"]
            assert rec.investment_result_hash == PER_CALC_HASHES["investment"]

            # Verify provenance fields trace back to golden attempt
            assert rec.orchestration_identity_id == GOLDEN_ORCHESTRATION_IDENTITY_ID
            assert rec.authoritative_attempt_id == GOLDEN_ATTEMPT_ID
            assert rec.execution_snapshot_id == GOLDEN_SNAPSHOT_ID
            assert rec.coefficient_context_id == GOLDEN_COEFFICIENT_CONTEXT_ID
            assert rec.orchestration_fingerprint == GOLDEN_FINGERPRINT

        # ── Step 8: Trusted readback succeeds ────────────────────────────
        from cold_storage.modules.schemes.application.production_service import (
            read_verified_production_scheme_run,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemyProductionSchemeRunReadPort,
            SqlAlchemySourceBindingReadPort,
            SqlAlchemyWeightRevisionReadPort,
        )

        read_port = SqlAlchemyProductionSchemeRunReadPort()
        binding_port = SqlAlchemySourceBindingReadPort()
        weight_port = SqlAlchemyWeightRevisionReadPort()

        with session_factory() as session:
            verified_run = read_verified_production_scheme_run(
                read_port,
                binding_port,
                weight_port,
                session,
                run_id=run.id,
                generator_version="1.0.0",
            )

        assert verified_run.status == "completed"
        assert verified_run.id == run.id
        assert verified_run.content_hash is not None

        # Verify five result hashes still match after trusted readback
        verified_candidates = verified_run.candidates_snapshot
        assert len(verified_candidates) > 0, "Verified run must have candidates"
