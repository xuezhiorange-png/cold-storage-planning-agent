"""Phase 4 Issue #35 Slice 2C — §16 #11 power-authority integration test (SQLite).

This module covers the design contract's §16 #11:

    Power authority test is implemented and passes on both
    backends.

The test pins the §16 contract end-to-end:

    - Sets up an equipment slot with an inflated compressor power
      (e.g., 999 kW).
    - Sets up a power slot with a correct calculation result (e.g.,
      50 kW).
    - Runs the roundtrip.
    - Asserts ``scheme_candidate.installed_power_kw_e == 50``,
      not 999.

Strategy
========

Rather than duplicate the canonical ``_seed_project_and_version`` /
``_seed_orchestration_prereqs`` / ``_seed_calculation_runs`` /
``_seed_source_binding`` / ``_seed_all_prereqs`` helpers (≈ 800
lines of Pydantic-validated fixtures), this test **imports them
verbatim** from ``tests/integration/test_production_scheme_sqlite.py``
and overrides only the two slots the §16 spec calls out (equipment
+ power).

The dual-backend parity mirror lives in
``test_phase4_slice2c_power_authority_postgresql.py``.

Slice 2C scope: this file is additive — it does NOT modify the
existing ``test_production_scheme_sqlite.py::TestPowerAuthority``
class which covers missing-power rejection at the snapshot-mapping
boundary.  This new file proves the §16 contract at the **whole
scheme candidate** boundary (full SourceBinding +
ProductionSchemeService + persisted SchemeCandidateRecord).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Pull in every module that contributes tables to ``Base.metadata`` so
# that ``create_all`` resolves every foreign key for both the
# underlying slice-2c test database AND the helper fixtures below.
import cold_storage.modules.coefficients.infrastructure.orm  # noqa: F401
import cold_storage.modules.orchestration.infrastructure.orm  # noqa: F401
import cold_storage.modules.projects.infrastructure.orm  # noqa: F401
import cold_storage.modules.schemes.infrastructure.orm  # noqa: F401
from cold_storage.modules.projects.infrastructure.orm import Base
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeCandidateRecord,
    SchemeRunRecord,
)
from tests.integration.test_production_scheme_sqlite import (
    COOLING_RESULT_SNAPSHOT as _GOLDEN_COOLING_RESULT_SNAPSHOT,
)

# Re-use the canonical fixture builders so we don't duplicate ~ 800
# lines of Pydantic-validated snapshots.  These privates ARE the
# contract — the production test directory co-locates them with the
# production tests because any change to the canonical snapshot
# shape MUST update them in lockstep with the suite.
from tests.integration.test_production_scheme_sqlite import (
    EQUIPMENT_RESULT_SNAPSHOT as _GOLDEN_EQUIPMENT_RESULT_SNAPSHOT,
)
from tests.integration.test_production_scheme_sqlite import (
    INVESTMENT_RESULT_SNAPSHOT as _GOLDEN_INVESTMENT_RESULT_SNAPSHOT,
)
from tests.integration.test_production_scheme_sqlite import (
    POWER_RESULT_SNAPSHOT as _GOLDEN_POWER_RESULT_SNAPSHOT,
)
from tests.integration.test_production_scheme_sqlite import (
    ZONE_RESULT_SNAPSHOT as _GOLDEN_ZONE_RESULT_SNAPSHOT,
)
from tests.integration.test_production_scheme_sqlite import (
    _compute_domain_hash,
    _make_command,
    _make_service,
    _seed_calculation_runs,
    _seed_orchestration_prereqs,
    _seed_project_and_version,
    _seed_source_binding,
    _seed_weight_set_and_revision,
)

_SLOT_DEFAULT_RUN_IDS = {
    "zone": "test-run-zone-001",
    "cooling_load": "test-run-cool-001",
    "equipment": "test-run-equip-001",
    "power": "test-run-power-001",
    "investment": "test-run-invest-001",
}


_SLOT_GOLDEN_SNAPSHOT_DEFAULTS = {
    "zone": _GOLDEN_ZONE_RESULT_SNAPSHOT,
    "cooling_load": _GOLDEN_COOLING_RESULT_SNAPSHOT,
    "equipment": _GOLDEN_EQUIPMENT_RESULT_SNAPSHOT,
    "power": _GOLDEN_POWER_RESULT_SNAPSHOT,
    "investment": _GOLDEN_INVESTMENT_RESULT_SNAPSHOT,
}


def _compute_combined_overrides(
    equip_result: dict[str, Any],
    power_result: dict[str, Any],
    per_calc: dict[str, str],
) -> str:
    """Compute the ``combined_source_hash`` matching my overrides.

    Mirrors ``tests/integration/test_production_scheme_sqlite.py::
    _compute_verifier_combined_source_hash`` but uses the §16 #11
    override per-calc hashes + the canonical fixture IDs / fingerprint.
    """
    from cold_storage.modules.schemes.application.source_binding_verifier import (
        _compute_combined_source_hash,
    )
    from tests.integration.test_production_scheme_sqlite import (
        _SLOT_STAGE_ORDER,
        ATTEMPT_ID,
        COEFF_CONTEXT_ID,
        COOL_RUN_ID,
        EQUIP_RUN_ID,
        EXEC_SNAPSHOT_ID,
        IDENTITY_ID,
        INVEST_RUN_ID,
        POWER_RUN_ID,
        PROJECT_ID,
        VERSION_ID,
        ZONE_RUN_ID,
    )

    slot_ids = {
        "zone": ZONE_RUN_ID,
        "cooling_load": COOL_RUN_ID,
        "equipment": EQUIP_RUN_ID,
        "power": POWER_RUN_ID,
        "investment": INVEST_RUN_ID,
    }
    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_attempt_id=ATTEMPT_ID,
        orchestration_fingerprint="test-fingerprint-001",
        slot_ids=slot_ids,
        result_hashes=per_calc,
        requires_reviews={stage: False for stage in _SLOT_STAGE_ORDER},
    )


def _override_per_calc(
    equip_result: dict[str, Any], power_result: dict[str, Any]
) -> dict[str, str]:
    """Compute the per-calc hash map using my overrides for equipment + power.

    The zone / cooling_load / investment slots use the suite's
    canonical defaults; equipment + power use the §16 override
    values.  The hash keys mirror ``_SLOT_STAGE_ORDER``.
    """
    return {
        "zone": _compute_domain_hash(
            stage="zone",
            result_snapshot=_SLOT_GOLDEN_SNAPSHOT_DEFAULTS["zone"],
            run_id=_SLOT_DEFAULT_RUN_IDS["zone"],
        ),
        "cooling_load": _compute_domain_hash(
            stage="cooling_load",
            result_snapshot=_SLOT_GOLDEN_SNAPSHOT_DEFAULTS["cooling_load"],
            run_id=_SLOT_DEFAULT_RUN_IDS["cooling_load"],
        ),
        "equipment": _compute_domain_hash(
            stage="equipment",
            result_snapshot=equip_result,
            run_id=_SLOT_DEFAULT_RUN_IDS["equipment"],
        ),
        "power": _compute_domain_hash(
            stage="power",
            result_snapshot=power_result,
            run_id=_SLOT_DEFAULT_RUN_IDS["power"],
        ),
        "investment": _compute_domain_hash(
            stage="investment",
            result_snapshot=_SLOT_GOLDEN_SNAPSHOT_DEFAULTS["investment"],
            run_id=_SLOT_DEFAULT_RUN_IDS["investment"],
        ),
    }


# ── §16 #11 — equipment=999, power=50 (the §12 scenario) ────────────────


_INFLATED_EQUIPMENT_RESULT: dict[str, Any] = {
    # Same canonical shape as
    # ``tests/integration/test_production_scheme_sqlite.py::EQUIPMENT_RESULT_SNAPSHOT``
    # but with every compressor capacity inflated to 999 — the §16
    # spec tests this exact value, asserting the production
    # mapping/SchemeService cannot be tricked by the inflated
    # equipment slot.
    "evaporator_total_cooling_capacity_kw": "30.0",
    "evaporator_quantity": 2,
    "single_evaporator_capacity_kw": "15.0",
    "compressor_operating_capacity_kw": "999",
    "compressor_installed_capacity_kw": "999",
    "standby_capacity_kw": "999",
    "condenser_heat_rejection_capacity_kw": "30.0",
    "evaporation_temperature_c": "-5.0",
    "condensing_temperature_c": "40.0",
    "defrost_method": "electric",
    "review_requirement": "",
}


_CORRECT_POWER_RESULT: dict[str, Any] = {
    # Same canonical shape as the suite's ``POWER_RESULT_SNAPSHOT``
    # except ``total_installed_power_kw_e`` is pinned to ``50.0``
    # per §12.  The other fields stay shape-conformant so
    # ``map_power_snapshot`` validates without rejecting.
    "total_installed_power_kw_e": "50.0",
    "total_estimated_demand_kw": "40.0",
    "equipment_rows": [],
    "summary_rows": [],
    "items": [],
    "assumptions": [],
}


@pytest.fixture()
def engine():
    """Build a fresh in-memory SQLite engine per test."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


class TestPowerAuthorityRoundtripSQLite:
    """§16 #11 — SchemeCandidate.installed_power_kw_e comes from power slot, not equipment."""

    def test_scheme_candidate_installed_power_uses_power_slot_not_equipment(
        self, engine, session_factory
    ) -> None:
        """Equipment slot inflated to 999 kW; power slot corrected to 50 kW.

        The §12 roundtrip contract: after running
        ``ProductionSchemeService.generate_production_scheme_run``,
        every persisted ``SchemeCandidateRecord.result_snapshot['installed_power_kw_e']``
        must equal ``50.0`` (the power slot) — never ``999`` (the
        equipment slot).

        Implementation: we seed the suite-wide canonical project /
        version / orchestration / weight fixtures, then override the
        equipment + power ``CalculationRunRecord`` slots with the
        §16 #11 inputs.  The §16 + canonical contract enforces
        ``map_equipment_snapshot(...).installed_power_kw_e ==
        Decimal(0)`` (so the inflated equipment slot contributes
        nothing to whole-project power); the production
        ``generator.py`` then takes its value from
        ``input_data.power_result.total_installed_power_kw_e``.
        """
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            # Override only the equipment + power slots — the other
            # three slots (zone / cooling_load / investment) use the
            # suite's canonical golden snapshots via the override
            # semantics of ``_seed_calculation_runs``.
            _seed_calculation_runs(
                seed_s,
                equip_result=_INFLATED_EQUIPMENT_RESULT,
                power_result=_CORRECT_POWER_RESULT,
            )
            # Build a per-calc hash map that matches our overrides
            # and feeds the binding seed directly — otherwise the
            # binding would use the pre-computed module-level
            # ``PER_CALC_HASHES`` and mismatch the verifier.
            per_calc = _override_per_calc(
                equip_result=_INFLATED_EQUIPMENT_RESULT,
                power_result=_CORRECT_POWER_RESULT,
            )
            combined_hash = _compute_combined_overrides(
                equip_result=_INFLATED_EQUIPMENT_RESULT,
                power_result=_CORRECT_POWER_RESULT,
                per_calc=per_calc,
            )
            _seed_source_binding(
                seed_s,
                per_calc=per_calc,
                combined_hash_override=combined_hash,
            )
            _seed_weight_set_and_revision(seed_s)
        finally:
            seed_s.close()

        # ── Run the production SchemeService ──
        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        # ── Read back the persisted SchemeCandidateRecord ──
        verify_s = session_factory()
        try:
            run_rec = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one_or_none()
            assert run_rec is not None, "SchemeRunRecord was not persisted"
            assert run_rec.source_mode == "production"

            candidates = (
                verify_s.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run.id
                    )
                )
                .scalars()
                .all()
            )
            assert candidates, "Expected at least one persisted SchemeCandidateRecord"

            # ── §16 #11 — assert power slot wins over equipment slot ──
            for cand in candidates:
                snap = cand.result_snapshot or {}
                installed_power_kw_e = snap.get("installed_power_kw_e")
                assert installed_power_kw_e is not None, (
                    f"Candidate {cand.scheme_code} has no installed_power_kw_e in result_snapshot"
                )
                val = Decimal(str(installed_power_kw_e))
                assert val == Decimal("50.0"), (
                    f"§16 #11 power-authority FAILED: candidate {cand.scheme_code} "
                    f"installed_power_kw_e={val!r} (expected 50.0); the value must "
                    f"come from the power slot, NOT the equipment slot. Equipment "
                    f"slot had inflated compressor power = 999 kW."
                )
        finally:
            verify_s.close()


__all__ = ["TestPowerAuthorityRoundtripSQLite"]
