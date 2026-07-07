"""PG mirror slice-n/a — see SQLite file.

The dual-backend parity mirror of
``test_phase4_slice2c_power_authority_sqlite.py`` is the same
``§16 #11 power-authority roundtrip`` test, but with
``DATABASE_BACKEND = postgresql`` so the CI ``backend-postgresql``
job exercises it.  PG mirrors reuse the SQLite helper fixtures via
``tests.integration.transaction_b_pg_parity_helpers`` or the
``pg_engine`` / ``pg_session_factory`` conftest fixtures defined in
``tests/integration/conftest.py``.

Skipped when no Postgres fixture is present (no PG service available
locally); the canonical CI is the ``backend-postgresql`` job at
``.github/workflows/ci.yml``.
"""

from __future__ import annotations

# Skip when DATABASE_BACKEND != postgresql OR no PG fixture is present.
# CI backend-postgresql job sets DATABASE_BACKEND=postgresql AND
# provides pg_engine / pg_session_factory fixtures.
import os
from decimal import Decimal

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "Slice 2C power-authority PG test requires DATABASE_BACKEND=postgresql; "
        "the canonical run is the backend-postgresql CI job",
        allow_module_level=True,
    )


_INFLATED_EQUIPMENT_RESULT = {
    "evaporator_total_cooling_capacity_kw": "30.0",
    "evaporator_quantity": 2,
    "single_evaporator_capacity_kw": "15.0",
    # §16 #11: compressor capacity inflated to 999 kW.
    "compressor_operating_capacity_kw": "999",
    "compressor_installed_capacity_kw": "999",
    "standby_capacity_kw": "999",
    "condenser_heat_rejection_capacity_kw": "30.0",
    "evaporation_temperature_c": "-5.0",
    "condensing_temperature_c": "40.0",
    "defrost_method": "electric",
    "review_requirement": "",
}

_CORRECT_POWER_RESULT = {
    # §16 #11: power slot owns the project-wide
    # total_installed_power_kw_e = 50 kW.
    "total_installed_power_kw_e": "50.0",
    "total_estimated_demand_kw": "40.0",
    "equipment_rows": [],
    "summary_rows": [],
    "items": [],
    "assumptions": [],
}


@pytest.mark.postgresql
def test_pg_scheme_candidate_installed_power_uses_power_slot_not_equipment(
    pg_engine, pg_session_factory
) -> None:
    """PG parity for the §16 #11 power-authority roundtrip.

    Same as the SQLite mirror — equipment slot inflated to 999 kW;
    power slot corrected to 50 kW; ``SchemeCandidateRecord.result_snapshot``
    must reflect the power slot's value.
    """
    from sqlalchemy import select

    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeCandidateRecord,
        SchemeRunRecord,
    )
    from tests.integration.test_production_scheme_sqlite import (
        _make_command,
        _make_service,
        _seed_calculation_runs,
        _seed_orchestration_prereqs,
        _seed_project_and_version,
        _seed_source_binding,
        _seed_weight_set_and_revision,
    )

    seed_s = pg_session_factory()
    try:
        _seed_project_and_version(seed_s)
        _seed_orchestration_prereqs(seed_s)
        _seed_calculation_runs(
            seed_s,
            equip_result=_INFLATED_EQUIPMENT_RESULT,
            power_result=_CORRECT_POWER_RESULT,
        )
        _seed_source_binding(seed_s)
        _seed_weight_set_and_revision(seed_s)
    finally:
        seed_s.close()

    service = _make_service(pg_engine)
    cmd = _make_command()
    run = service.generate_production_scheme_run(cmd)

    verify_s = pg_session_factory()
    try:
        rec = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
        ).scalar_one_or_none()
        assert rec is not None, "PG SchemeRunRecord was not persisted"

        candidates = (
            verify_s.execute(
                select(SchemeCandidateRecord).where(SchemeCandidateRecord.scheme_run_id == run.id)
            )
            .scalars()
            .all()
        )
        for cand in candidates:
            snap = cand.result_snapshot or {}
            installed_power_kw_e = snap.get("installed_power_kw_e")
            assert installed_power_kw_e is not None
            val = Decimal(str(installed_power_kw_e))
            assert val == Decimal("50.0"), (
                f"§16 #11 power-authority FAILED on PG: candidate {cand.scheme_code} "
                f"installed_power_kw_e={val!r} (expected 50.0); the value must come "
                f"from the power slot, not the equipment slot."
            )
    finally:
        verify_s.close()


__all__ = ["test_pg_scheme_candidate_installed_power_uses_power_slot_not_equipment"]
