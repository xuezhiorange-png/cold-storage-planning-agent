"""Unit tests for V0.5 P3 canonical source read adapters."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cold_storage.modules.schemes.application.canonical_source_reads import (
    index_canonical_calculation_records,
    require_canonical_scheme_sources,
)
from cold_storage.modules.schemes.domain.errors import (
    SourceCalculationMissingError,
    VersionConflictError,
)
from cold_storage.modules.workflow.application.canonical_calculation_reads import (
    index_canonical_calculation_runs,
    missing_canonical_calculator_names,
)
from tests.integration.v05_p3_canonical_fixtures import (
    CANONICAL_SNAPSHOTS,
    POWER_CONFIGURATION_SNAPSHOT,
)


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
        result_snapshot=CANONICAL_SNAPSHOTS["cold_room_zone_plan"],
    )
    with pytest.raises(VersionConflictError):
        index_canonical_calculation_records(
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
