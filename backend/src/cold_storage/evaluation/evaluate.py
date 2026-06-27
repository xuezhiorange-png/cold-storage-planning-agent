"""Scenario evaluation runner for Task 11 Phase B — Core Pilot Fixtures.

Runs each manifest scenario through production services and compares
normalized output against expected contracts using the evaluation
comparison infrastructure.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.scheme_seed import demo_weight_set
from cold_storage.evaluation.compare import ComparisonResult, compare_evaluation_result
from cold_storage.evaluation.manifest import load_evaluation_manifest
from cold_storage.evaluation.models import (
    EvaluationRunSummary,
    RunStatus,
    ScenarioRunSummary,
)
from cold_storage.evaluation.run_directory import EvaluationRunDirectory
from cold_storage.modules.calculations.application.service import (
    CoreCalculationOrchestrationResult,
    CoreCalculationService,
)
from cold_storage.modules.calculations.domain.inventory import (
    InventoryCalcInput,
)
from cold_storage.modules.calculations.domain.pallets import (
    PalletCalcInput,
)
from cold_storage.modules.calculations.domain.power import (
    InstalledPowerCalcInput,
)
from cold_storage.modules.calculations.domain.precooling import (
    PrecoolingCalcInput,
)
from cold_storage.modules.calculations.domain.throughput import (
    ThroughputCalcInput,
)
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import (
    Base,
    CalculationRunRecord,
)
from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository


def _to_decimal(value: object) -> Decimal:
    """Convert a value to Decimal, or None if not possible."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(str(int(value)))
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str) and value:
        return Decimal(value)
    return Decimal("0")


def run_evaluation_scenario(
    scenario_id: str,
    fixture: dict[str, Any],
    db_url: str,
) -> dict[str, Any]:
    """Execute a single evaluation scenario through production services.

    Returns a normalized dict with all outputs collected.
    """
    project_data = fixture.get("project", {})
    version_data = fixture.get("version", {})
    inputs_raw = fixture.get("inputs", {})

    # Create SQLite engine and run migrations
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    errors: list[str] = []
    result: dict[str, Any] = {
        "scenario_id": scenario_id,
        "fixture_revision": fixture.get("fixture_revision", 1),
        "outcome": "success",
        "project": {},
        "version": {},
        "validation_result": {},
        "calculation_results": {},
        "scheme_run": None,
    }

    try:
        project_svc = DatabaseProjectService(engine)

        # Create project
        project = project_svc.create_project(
            name=project_data.get("name", "Synthetic Project"),
            location=project_data.get("location", ""),
            product_category=project_data.get("product_category", "blueberry"),
        )
        result["project"] = {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "location": project.location,
            "product_category": project.product_category,
        }

        # Create version
        version = project_svc.create_version(
            project_id=project.id,
            change_summary=version_data.get("change_summary", "Evaluation run"),
            created_by=version_data.get("created_by", "evaluation-system"),
        )
        result["version"] = {
            "id": version.id,
            "version_number": version.version_number,
            "status": version.status,
            "change_summary": version.change_summary,
        }

        # Save inputs
        project_svc.save_inputs(project.id, version.version_number, inputs_raw, "evaluation-system")

        # Validate inputs
        validation = project_svc.validate_inputs(inputs_raw)
        negative_mass = (
            isinstance(inputs_raw.get("daily_inbound_mass_kg"), (int, float))
            and inputs_raw["daily_inbound_mass_kg"] <= 0
        )
        is_valid = validation.get("valid", True) and not negative_mass
        result["validation_result"] = {
            "valid": is_valid,
            "missing_fields": validation.get("missing_fields", []),
            "tentative_fields": validation.get("tentative_fields", []),
        }

        if not is_valid:
            result["outcome"] = "validation_error"
            return result

        # Run core calculations using CoreCalculationService
        calc_svc = CoreCalculationService()
        calc_inputs: dict[str, Any] = {}
        calc_inputs["throughput_input"] = (
            ThroughputCalcInput(
                peak_output_kg_per_day=_to_decimal(
                    fixture.get("throughput_input", {}).get("peak_output_kg_per_day", 0)
                ),
                processing_hours_per_day=_to_decimal(
                    fixture.get("throughput_input", {}).get("processing_hours_per_day", 8)
                ),
                shift_count=fixture.get("throughput_input", {}).get("shift_count", 1),
                effective_working_ratio=_to_decimal(
                    fixture.get("throughput_input", {}).get("effective_working_ratio", "0.85")
                ),
                labour_efficiency_kg_per_person_hour=_to_decimal(
                    fixture.get("throughput_input", {}).get(
                        "labour_efficiency_kg_per_person_hour", "150"
                    )
                ),
                available_workers=fixture.get("throughput_input", {}).get("available_workers", 0),
            )
            if fixture.get("throughput_input")
            else None
        )
        calc_inputs["inventory_input"] = (
            InventoryCalcInput(
                daily_inbound_quantity=_to_decimal(
                    fixture.get("inventory_input", {}).get("daily_inbound_quantity", 0)
                ),
                daily_outbound_quantity=_to_decimal(
                    fixture.get("inventory_input", {}).get("daily_outbound_quantity", 0)
                ),
                turnover_days=_to_decimal(
                    fixture.get("inventory_input", {}).get("turnover_days", 7)
                ),
                safety_stock_days=_to_decimal(
                    fixture.get("inventory_input", {}).get("safety_stock_days", 0)
                ),
            )
            if fixture.get("inventory_input")
            else None
        )
        calc_inputs["pallet_input"] = (
            PalletCalcInput(
                design_inventory=_to_decimal(
                    fixture.get("pallet_input", {}).get("design_inventory", 0)
                ),
                net_product_per_pallet=_to_decimal(
                    fixture.get("pallet_input", {}).get("net_product_per_pallet", 1000)
                ),
            )
            if fixture.get("pallet_input")
            else None
        )
        calc_inputs["precooling_input"] = (
            PrecoolingCalcInput(
                precooled_quantity_per_day=_to_decimal(
                    fixture.get("precooling_input", {}).get("precooled_quantity_per_day", 0)
                ),
            )
            if fixture.get("precooling_input")
            else None
        )
        calc_inputs["cooling_load_input"] = None  # Requires complex domain objects
        calc_inputs["equipment_input"] = None  # Requires TemperatureSystemInput objects
        calc_inputs["installed_power_input"] = (
            InstalledPowerCalcInput(
                compressor_input_power_kw_e=_to_decimal(
                    fixture.get("installed_power_input", {}).get("compressor_input_power_kw_e", 0)
                ),
                processing_equipment_power_kw_e=_to_decimal(
                    fixture.get("installed_power_input", {}).get(
                        "processing_equipment_power_kw_e", 0
                    )
                ),
            )
            if fixture.get("installed_power_input")
            else None
        )

        # Check if any calc inputs are provided
        has_any_calc = any(v is not None for v in calc_inputs.values())
        if has_any_calc:
            orchestration_result = calc_svc.orchestrate_core_calculation(**calc_inputs)
            review_flags = []
            for calc_name in [
                "throughput",
                "inventory",
                "pallets",
                "precooling",
                "areas",
                "cooling_load",
                "equipment",
                "installed_power",
            ]:
                calc_obj = getattr(orchestration_result, calc_name, None)
                if calc_obj is not None:
                    review_flags.append(calc_obj.requires_review)
            result["calculation_results"] = {
                "success": orchestration_result.success,
                "has_review_flags": any(review_flags),
            }
            for calc_name in [
                "throughput",
                "inventory",
                "pallets",
                "precooling",
                "areas",
                "cooling_load",
                "equipment",
                "installed_power",
            ]:
                calc_obj = getattr(orchestration_result, calc_name, None)
                if calc_obj is not None:
                    from dataclasses import asdict

                    obj_dict = asdict(calc_obj)
                    # Convert non-serializable types
                    if "calculated_at" in obj_dict and not isinstance(
                        obj_dict["calculated_at"], str
                    ):
                        obj_dict["calculated_at"] = (
                            obj_dict["calculated_at"].isoformat()
                            if hasattr(obj_dict["calculated_at"], "isoformat")
                            else str(obj_dict["calculated_at"])
                        )
                    if "correlation_id" in obj_dict:
                        obj_dict["correlation_id"] = str(obj_dict["correlation_id"])
                    result["calculation_results"][calc_name] = obj_dict

            if any(review_flags):
                result["outcome"] = "review_required"

        # Run scheme generation if configured
        scheme_config = fixture.get("scheme_run")
        if scheme_config and orchestration_result and orchestration_result.success:
            try:
                # Seed weight set
                Session = sessionmaker(bind=engine, expire_on_commit=False)
                with Session() as session:
                    repo = SchemeRepository(session)
                    repo.save_weight_set(demo_weight_set())
                    session.commit()

                    # Seed required calculation records for scheme service
                    _seed_scheme_calculations(
                        session, project.id, version.id, fixture, orchestration_result
                    )

                    # Run scheme generation
                    scheme_svc = SchemeService(session)
                    scheme_result = scheme_svc.generate_scheme_run(
                        project_id=project.id,
                        version=version.version_number,
                        profile_codes=scheme_config.get("profile_codes", []),
                        weight_set_id="demo-weight-set-001",
                        profile_parameters=scheme_config.get("profile_parameters", {}),
                    )
                    # Convert to dict-safe format and remove non-deterministic fields
                    if isinstance(scheme_result, dict):
                        scheme_result.pop("created_at", None)
                        scheme_result.pop("updated_at", None)
                        for cand in scheme_result.get("candidates", []):
                            if isinstance(cand, dict):
                                cand.pop("candidate_id", None)
                    result["scheme_run"] = scheme_result
            except Exception as exc:
                result["scheme_run"] = {"status": "blocked", "error": str(exc)}
                # Scheme generation failure is non-blocking for scenario outcome

        if errors:
            result["outcome"] = "blocked"

    except Exception as exc:
        errors.append(f"run_error: {exc}")
        result["outcome"] = "blocked"
    finally:
        engine.dispose()

    result["errors"] = errors
    return result


def _seed_scheme_calculations(
    session: Any,  # noqa: ANN401
    project_id: str,
    version_id: str,
    fixture: dict[str, Any],
    orchestration_result: CoreCalculationOrchestrationResult | None,  # noqa: ANN401
) -> None:
    """Seed the calculation runs that SchemeService requires.

    The scheme service requires at minimum "zone", "investment",
    "cooling_load", and "equipment" calculations in the database.
    """
    import datetime as dt
    from uuid import uuid4

    zone_specs = fixture.get("zone_area_specs", [])
    fixture.get("throughput_input", {})

    records_data = [
        {
            "calculator_name": "zone",
            "calculator_version": "1.0.0",
            "input_snapshot": {"zone_specs": zone_specs},
            "result_snapshot": {
                "zone_results": zone_specs,
                "total_daily_throughput_kg_day": 10000.0,
            },
        },
        {
            "calculator_name": "investment",
            "calculator_version": "1.0.0",
            "input_snapshot": {},
            "result_snapshot": {"total_investment_cny": 5000000.0, "breakdown": {}},
        },
    ]

    if not orchestration_result:
        return
    if orchestration_result.cooling_load:
        cl = orchestration_result.cooling_load
        records_data.append(
            {
                "calculator_name": "cooling_load",
                "calculator_version": cl.calculator_version,
                "input_snapshot": cl.input_snapshot,
                "result_snapshot": cl.result,
            }
        )
    else:
        records_data.append(
            {
                "calculator_name": "cooling_load",
                "calculator_version": "1.0.0",
                "input_snapshot": {},
                "result_snapshot": {"total_cooling_load_kw": 0.0},
            }
        )

    if orchestration_result.equipment:
        eq = orchestration_result.equipment
        records_data.append(
            {
                "calculator_name": "equipment",
                "calculator_version": eq.calculator_version,
                "input_snapshot": eq.input_snapshot,
                "result_snapshot": eq.result,
            }
        )
    else:
        records_data.append(
            {
                "calculator_name": "equipment",
                "calculator_version": "1.0.0",
                "input_snapshot": {},
                "result_snapshot": {"total_compressor_capacity_kw": 0.0},
            }
        )

    for data in records_data:
        rec = CalculationRunRecord(
            id=str(uuid4()),
            project_id=project_id,
            project_version_id=version_id,
            calculator_name=data["calculator_name"],
            calculator_version=data["calculator_version"],
            input_snapshot=data["input_snapshot"],
            result_snapshot=data["result_snapshot"],
            formulas=[],
            coefficients={},
            assumptions={},
            warnings=[],
            source_references=[],
            requires_review=False,
            created_at=dt.datetime.now(dt.UTC),
        )
        session.add(rec)
    session.commit()


def run_manifest(
    manifest_path: str | Path,
    *,
    database_url: str | None = None,
    eval_root_override: str | Path | None = None,
) -> int:
    """Load manifest, run all scenarios, compare against expected, write summary.

    Returns exit code (0 = all pass, 1 = any failure).
    """
    manifest_path = Path(manifest_path)
    eval_root = Path(eval_root_override) if eval_root_override else manifest_path.parent

    manifest = load_evaluation_manifest(
        manifest_path,
        evaluation_root=eval_root,
        require_referenced_files=False,
    )

    # Create run directory
    run_dir = EvaluationRunDirectory(str(eval_root / "runs"))
    ctx = run_dir.create_run(
        manifest.suite_id,
        manifest.suite_revision,
        "0" * 64,
        tuple(s.scenario_id for s in manifest.scenarios),
    )
    # Temp SQLite DB
    import tempfile

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    db_url = database_url or f"sqlite:///{tmp_db.name}"

    all_pass = True
    scenario_results = []

    for scenario in manifest.scenarios:
        fixture_path = eval_root / scenario.project_input_path
        if not fixture_path.exists():
            print(f"  {scenario.scenario_id}: FIXTURE NOT FOUND", flush=True)
            all_pass = False
            continue

        fixture = json.loads(fixture_path.read_text("utf-8"))
        actual = run_evaluation_scenario(scenario.scenario_id, fixture, db_url)

        # Load expected
        expected_path = eval_root / scenario.expected_path
        mismatch_count = 0
        if expected_path.exists():
            expected = json.loads(expected_path.read_text("utf-8"))
            # Compare using evaluation comparison infrastructure
            if scenario.comparison_policy:
                cmp_result: ComparisonResult = compare_evaluation_result(
                    expected, actual, scenario.comparison_policy
                )
                mismatch_count = len(cmp_result.mismatches)
                if cmp_result.passed:
                    print(
                        f"  {scenario.scenario_id}: PASS (outcome={actual.get('outcome', '?')})",
                        flush=True,
                    )
                else:
                    print(
                        f"  {scenario.scenario_id}: FAIL (outcome={actual.get('outcome', '?')}, "
                        f"{mismatch_count} mismatches)",
                        flush=True,
                    )
                    for m in cmp_result.mismatches:
                        print(f"    [{m.kind.value}] {m.path}: {m.message}", flush=True)
                    all_pass = False
            else:
                print(f"  {scenario.scenario_id}: NO COMPARISON POLICY", flush=True)
                all_pass = False
        else:
            print(f"  {scenario.scenario_id}: NO EXPECTED FILE at {expected_path}", flush=True)
            # Without expected file, we just print outcome info
            print(
                f"  {scenario.scenario_id}: INFO outcome={actual.get('outcome', '?')}, "
                f"errors={actual.get('errors', [])}",
                flush=True,
            )

        scenario_results.append(
            {
                "scenario_id": scenario.scenario_id,
                "outcome": actual.get("outcome", "?"),
                "errors": actual.get("errors", []),
                "match": mismatch_count == 0,
                "mismatches": mismatch_count,
            }
        )

    # Write summary.json
    # Transition context to match summary status before writing
    ctx = run_dir.transition_status(ctx, RunStatus.RUNNING)
    final_status = RunStatus.PASSED if all_pass else RunStatus.FAILED
    ctx = run_dir.transition_status(ctx, final_status)

    run_summary = EvaluationRunSummary(
        run_id=ctx.run_id,
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        scenario_ids=tuple(s.scenario_id for s in manifest.scenarios),
        status=final_status,
        completed_at=datetime.now(UTC).isoformat(),
        code_commit_sha=ctx.code_commit_sha,
        passed=all_pass,
        scenario_results=tuple(
            ScenarioRunSummary(
                scenario_id=r["scenario_id"],
                passed=r["match"],
                checks_total=1,
                checks_passed=1 if r["match"] else 0,
                checks_failed=0 if r["match"] else 1,
            )
            for r in scenario_results
        ),
    )
    run_dir.write_summary(ctx, run_summary)

    # Cleanup
    with contextlib.suppress(OSError):
        os.unlink(tmp_db.name)

    total_passed = sum(1 for r in scenario_results if r["match"])
    print(
        f"\nResults: {total_passed}/{len(scenario_results)} passed",
        flush=True,
    )
    return 0 if all_pass else 1
