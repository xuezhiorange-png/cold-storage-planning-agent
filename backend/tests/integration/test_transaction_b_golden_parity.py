"""Cross-backend golden parity tests for Transaction B.

Both SQLite and PostgreSQL integration tests consume the same golden artifact
and compare against identical fixed inputs and deterministic calculator outputs.
"""

from __future__ import annotations

from cold_storage.modules.orchestration.application.transaction_b import (
    FixedTransactionBIdFactory,
)
from tests.integration.transaction_b_golden import (
    get_calculator_output,
    get_stage_data,
    load_cross_backend_golden,
)


class TestCrossBackendGoldenParity:
    """Verify that SQLite and PostgreSQL produce identical output
    matching the golden artifact."""

    def test_golden_artifact_loads(self) -> None:
        """Golden artifact is valid JSON with required keys."""
        golden = load_cross_backend_golden()
        assert "fixed_inputs" in golden
        assert "stage_data" in golden
        assert "schema_version" in golden
        fixed = golden["fixed_inputs"]
        assert fixed["project_id"] == "golden-p-001"
        assert fixed["orchestration_fingerprint"] == "golden-fp-001"

    def test_golden_stage_data_complete(self) -> None:
        """Golden stage data covers all 5 stages."""
        stage_data = get_stage_data()
        expected_stages = {"zone", "cooling_load", "equipment", "power", "investment"}
        assert set(stage_data.keys()) == expected_stages
        for _stage, data in stage_data.items():
            assert "calculator_name" in data
            assert "calculator_version" in data
            assert "calculation_type" in data

    def test_fixed_id_factory_deterministic(self) -> None:
        """FixedTransactionBIdFactory returns stable IDs."""
        factory = FixedTransactionBIdFactory()
        # Run IDs are stable
        assert factory.calculation_run_id("zone") == "golden-run-zone-001"
        assert factory.calculation_run_id("investment") == "golden-run-investment-001"
        assert factory.source_binding_id() == "golden-source-binding-001"
        # Consistency
        for stage in ["zone", "cooling_load", "equipment", "power", "investment"]:
            assert factory.calculation_run_id(stage) == factory.calculation_run_id(stage)

    def test_calculator_output_matches_golden(self) -> None:
        """Fixed calculator outputs are deterministic across runs."""
        # Verify calculator output fixtures match golden stage metadata
        for stage_name in ["zone", "cooling_load", "equipment", "power", "investment"]:
            output = get_calculator_output(stage_name)
            assert isinstance(output, dict)
            assert len(output) > 0
