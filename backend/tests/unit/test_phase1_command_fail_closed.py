"""Fail-closed unit tests for the Phase 1 (Task 11B) repository
and command contract.

P0-1 / P0-2 contract: 0035+0036+0037 made the
``orchestration_run_attempts.correlation_id`` and
``scheme_runs.database_backend`` columns NOT NULL with **no**
column-level server_default. The application / repository
layer must therefore require these fields explicitly at
construction time; the repository must fail-closed if a
caller attempts to pass an empty / None / non-enum value.

These tests live in ``tests/unit/`` because they exercise
the contract in isolation (no real database). They run on
both SQLite and PG envs because they don't touch the
network.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
    PersistedSchemeRun,
)
from cold_storage.modules.schemes.infrastructure.orm import Base
from cold_storage.modules.schemes.infrastructure.production_repository import (
    SqlAlchemyProductionSchemeRunRepository,
)

# ── P0-1 fail-closed: GenerateProductionSchemeCommand ──────────────


class TestGenerateProductionSchemeCommandContract:
    """P0-1: command construction must require ``database_backend``
    and ``correlation_id`` explicitly. There is no Python
    default that can mask an omission.
    """

    def test_command_without_database_backend_raises_typeerror(self) -> None:
        with pytest.raises(TypeError) as exc:
            GenerateProductionSchemeCommand(
                source_binding_id="sb-001",
                weight_set_revision_id="wsr-001",
                profile_codes=("balanced",),
                profile_parameters={},
                actor="test-actor",
                correlation_id="corr-001",
                # database_backend intentionally omitted
            )  # type: ignore[call-arg]
        assert "database_backend" in str(exc.value)

    def test_command_without_correlation_id_raises_typeerror(self) -> None:
        with pytest.raises(TypeError) as exc:
            GenerateProductionSchemeCommand(
                source_binding_id="sb-001",
                weight_set_revision_id="wsr-001",
                profile_codes=("balanced",),
                profile_parameters={},
                actor="test-actor",
                # correlation_id intentionally omitted
                database_backend="sqlite",
            )  # type: ignore[call-arg]
        assert "correlation_id" in str(exc.value)

    def test_command_with_all_required_fields_succeeds(self) -> None:
        cmd = GenerateProductionSchemeCommand(
            source_binding_id="sb-001",
            weight_set_revision_id="wsr-001",
            profile_codes=("balanced",),
            profile_parameters={},
            actor="test-actor",
            correlation_id="corr-001",
            database_backend="postgresql",
        )
        assert cmd.database_backend == "postgresql"
        assert cmd.correlation_id == "corr-001"


# ── P0-1 fail-closed: save_production_run ──────────────────────────


class TestSaveProductionRunFailClosed:
    """P0-1: ``save_production_run`` must reject empty / None /
    non-enum ``database_backend`` values at the repository
    boundary, before any SQL is executed.
    """

    @pytest.fixture()
    def session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        s = Session()
        yield s
        s.close()
        engine.dispose()

    @pytest.fixture()
    def repo(self) -> SqlAlchemyProductionSchemeRunRepository:
        return SqlAlchemyProductionSchemeRunRepository()

    @staticmethod
    def _kwargs(database_backend):  # noqa: ANN001
        return dict(
            run_id="run-001",
            project_id="proj-001",
            project_version_id="proj-001-v1",
            weight_set_id="ws-001",
            status="completed",
            generator_version="1.0.0",
            source_snapshot_hash="abc",
            input_snapshot={},
            assumption_snapshot={},
            comparison_snapshot={},
            candidates_snapshot={},
            requires_review=True,
            recommended_scheme_code=None,
            warning_messages=[],
            content_hash="h1",
            source_mode="production",
            source_binding_id="sb-001",
            source_contract_version="1.0.0",
            binding_schema_version="1",
            execution_snapshot_id="es-001",
            coefficient_context_id="cc-001",
            orchestration_identity_id="oi-001",
            authoritative_attempt_id="oa-001",
            orchestration_fingerprint="of-001",
            zone_calculation_id="zc-001",
            cooling_load_calculation_id="clc-001",
            equipment_calculation_id="ec-001",
            power_calculation_id="pc-001",
            investment_calculation_id="ic-001",
            zone_result_hash="zh",
            cooling_load_result_hash="clh",
            equipment_result_hash="eh",
            power_result_hash="ph",
            investment_result_hash="ih",
            combined_source_hash="csh",
            weight_set_revision_id="wsr-001",
            weight_set_content_hash="wsh",
            weight_set_generator_compatibility_version="1",
            profile_codes=("balanced",),
            profile_parameters={},
            candidates=[],
            database_backend=database_backend,
        )

    @pytest.mark.parametrize("bad", ["", None, "mysql", "POSTGRES"])
    def test_save_production_run_rejects_bad_database_backend(self, session, repo, bad) -> None:
        """Empty / None / non-enum values must raise ValueError
        before any SQL is executed.
        """
        with pytest.raises(ValueError) as exc:
            repo.save_production_run(session, **self._kwargs(bad))  # type: ignore[arg-type]
        assert "database_backend" in str(exc.value)

    @pytest.mark.parametrize("good", ["sqlite", "postgresql"])
    def test_save_production_run_accepts_valid_database_backend(self, session, repo, good) -> None:
        persisted: PersistedSchemeRun = repo.save_production_run(session, **self._kwargs(good))
        assert persisted.database_backend == good
