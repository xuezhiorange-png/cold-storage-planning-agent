"""Unit tests for V0.5 P3 canonical source read adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cold_storage.modules.orchestration.application.canonical_calculation_index import (
    index_canonical_calculation_records,
    index_canonical_calculation_runs,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import (
    resolve_canonical_calculator_name,
)
from cold_storage.modules.schemes.application.canonical_source_reads import (
    require_canonical_scheme_sources,
)
from cold_storage.modules.schemes.domain.errors import (
    SourceCalculationMissingError,
    VersionConflictError,
)
from cold_storage.modules.workflow.application.canonical_calculation_reads import (
    missing_canonical_calculator_names,
)
from tests.integration.v05_p3_canonical_fixtures import (
    CANONICAL_SNAPSHOTS,
    POWER_CONFIGURATION_SNAPSHOT,
)


def _zone_row(*, calc_id: str, created_at: datetime) -> dict[str, object]:
    return {
        "project_id": "p1",
        "project_version_id": "v1",
        "calculator_name": "cold_room_zone_plan",
        "calculation_id": calc_id,
        "id": calc_id,
        "created_at": created_at.isoformat(),
        "requires_review": False,
        "result_snapshot": CANONICAL_SNAPSHOTS["cold_room_zone_plan"],
    }


def test_index_canonical_calculation_runs_last_write_wins_newer_last() -> None:
    older = _zone_row(calc_id="zone-old", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _zone_row(calc_id="zone-new", created_at=datetime(2026, 2, 1, tzinfo=UTC))
    indexed = index_canonical_calculation_runs(
        [older, newer],
        project_id="p1",
        project_version_id="v1",
    )
    assert indexed["cold_room_zone_plan"]["calculation_id"] == "zone-new"


def test_index_canonical_calculation_runs_last_write_wins_newer_first() -> None:
    older = _zone_row(calc_id="zone-old", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _zone_row(calc_id="zone-new", created_at=datetime(2026, 2, 1, tzinfo=UTC))
    indexed = index_canonical_calculation_runs(
        [newer, older],
        project_id="p1",
        project_version_id="v1",
    )
    assert indexed["cold_room_zone_plan"]["calculation_id"] == "zone-new"


def test_index_canonical_calculation_records_last_write_wins() -> None:
    older = SimpleNamespace(
        id="zone-old",
        project_id="p1",
        project_version_id="v1",
        calculator_name="cold_room_zone_plan",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        result_snapshot=CANONICAL_SNAPSHOTS["cold_room_zone_plan"],
    )
    newer = SimpleNamespace(
        id="zone-new",
        project_id="p1",
        project_version_id="v1",
        calculator_name="cold_room_zone_plan",
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
        result_snapshot=CANONICAL_SNAPSHOTS["cold_room_zone_plan"],
    )
    indexed = index_canonical_calculation_records(
        [older, newer],
        project_id="p1",
        project_version_id="v1",
    )
    assert indexed["zone"].id == "zone-new"


def test_resolve_canonical_calculator_name_rejects_short_name_aliases() -> None:
    assert resolve_canonical_calculator_name("zone") is None
    assert resolve_canonical_calculator_name("investment") is None
    assert resolve_canonical_calculator_name("power_configuration") is None
    assert resolve_canonical_calculator_name("cold_room_zone_plan") == "cold_room_zone_plan"
    assert resolve_canonical_calculator_name("installed_power") == "installed_power"


def test_short_name_zone_does_not_fill_cold_room_zone_plan_slot() -> None:
    calculations = [
        {
            "project_id": "p1",
            "project_version_id": "v1",
            "calculator_name": "zone",
            "id": "alias-zone",
            "created_at": "2026-01-01T00:00:00+00:00",
            "requires_review": False,
            "result_snapshot": CANONICAL_SNAPSHOTS["cold_room_zone_plan"],
        }
    ]
    indexed = index_canonical_calculation_runs(
        calculations,
        project_id="p1",
        project_version_id="v1",
    )
    assert "cold_room_zone_plan" not in indexed


def test_workflow_index_ignores_power_configuration_for_canonical_power_slot() -> None:
    calculations = [
        {
            "project_id": "p1",
            "project_version_id": "v1",
            "calculator_name": name,
            "id": f"id-{name}",
            "requires_review": False,
            "result_snapshot": snapshot,
        }
        for name, snapshot in CANONICAL_SNAPSHOTS.items()
        if name != "installed_power"
    ]
    calculations.append(
        {
            "project_id": "p1",
            "project_version_id": "v1",
            "calculator_name": "power_configuration",
            "id": "id-power-configuration",
            "requires_review": False,
            "result_snapshot": POWER_CONFIGURATION_SNAPSHOT,
        }
    )
    indexed = index_canonical_calculation_runs(
        calculations,
        project_id="p1",
        project_version_id="v1",
    )
    assert "installed_power" in missing_canonical_calculator_names(indexed)
    assert "power_configuration" not in indexed


def test_scheme_source_reads_fail_closed_on_project_version_mismatch() -> None:
    record = SimpleNamespace(
        id="calc-1",
        project_id="p1",
        project_version_id="v-other",
        calculator_name="cold_room_zone_plan",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        result_snapshot=CANONICAL_SNAPSHOTS["cold_room_zone_plan"],
    )
    with pytest.raises(VersionConflictError):
        require_canonical_scheme_sources(
            [record],
            project_id="p1",
            project_version_id="v1",
        )


def test_detect_canonical_lineage_stale_reasons_flags_upstream_id_drift() -> None:
    from cold_storage.modules.workflow.application.canonical_calculation_reads import (
        detect_canonical_lineage_stale_reasons,
    )

    indexed = {
        "cold_room_zone_plan": {
            "calculation_id": "zone-1",
            "result_hash": "zone-hash",
        },
        "cooling_load": {
            "calculation_id": "cool-1",
            "result_hash": "cool-hash",
            "upstream_calculation_ids": {"zone": "zone-1"},
        },
        "equipment": {
            "calculation_id": "equip-1",
            "result_hash": "equip-hash",
            "upstream_calculation_ids": {"cooling_load": "stale-cool"},
        },
        "installed_power": {
            "calculation_id": "power-1",
            "result_hash": "power-hash",
            "upstream_calculation_ids": {"equipment": "equip-1"},
        },
        "investment_estimate": {
            "calculation_id": "invest-1",
            "result_hash": "invest-hash",
            "upstream_calculation_ids": {"zone": "zone-1", "power": "power-1"},
        },
    }
    reasons = detect_canonical_lineage_stale_reasons(indexed)
    assert "calculation_upstream_id_mismatch:equipment:cooling_load" in reasons


def test_scheme_source_reads_require_installed_power_not_power_configuration() -> None:
    records = [
        SimpleNamespace(
            id=f"calc-{name}",
            project_id="p1",
            project_version_id="v1",
            calculator_name=name,
            result_snapshot=snapshot,
        )
        for name, snapshot in CANONICAL_SNAPSHOTS.items()
        if name != "installed_power"
    ]
    records.append(
        SimpleNamespace(
            id="calc-power-configuration",
            project_id="p1",
            project_version_id="v1",
            calculator_name="power_configuration",
            result_snapshot=POWER_CONFIGURATION_SNAPSHOT,
        )
    )
    with pytest.raises(SourceCalculationMissingError, match="installed_power"):
        require_canonical_scheme_sources(
            records,
            project_id="p1",
            project_version_id="v1",
        )
