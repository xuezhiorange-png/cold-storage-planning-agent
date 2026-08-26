# Data Integrity Matrix (V0.7 P1)

> **Audit date:** 2026-08-26
> **Branch:** `cursor/v07-p1-data-integrity-6c68`
> **Authority:** `docs/tasks/V0_7-P1-data-integrity-contract.md`
> **Purpose:** Lock default values, units, coefficient metadata, consumer
> mapping, and `KNOWN_CONFLICT` rows for demo/conflict leaves without
> choosing winning engineering values.

## Matrix columns

| Column | Meaning |
| --- | --- |
| `leaf_id` | Stable identifier (field code or registry code) |
| `source` | Where the value is defined |
| `unit` | Canonical unit for the leaf |
| `consumer` | Runtime path that applies the effective value |
| `non_consumer` | Why metadata exists but formula does not consume it |
| `known_conflict` | Expert item ID (`E1`–`E8`) when values diverge |
| `requires_review` | Expected review flag for demo/unverified leaves |

## 1. Bundle KEY zone leaves → execution snapshot → calculator

`EngineeringInputBundleV1.zone_planning_inputs` KEY fields project onto
`execution_snapshot["zone"]` via `project_execution_snapshot_from_bundle`.
`ZonePlanningAdapter` maps the zone stage dict onto `ColdRoomZonePlanInput`.

| leaf_id | source | unit | consumer | non_consumer | known_conflict | requires_review |
| --- | --- | --- | --- | --- | --- | --- |
| `daily_inbound_mass_kg` | bundle KEY | kg/day | `ColdRoomZonePlanner.plan` | | | true (demo path) |
| `working_time_h_per_day` | bundle KEY | h/day | `ColdRoomZonePlanner.plan` | | | true |
| `finished_storage_days` | bundle KEY | day | `ColdRoomZonePlanner.plan` | | | true |
| `packaging_storage_days` | bundle KEY | day | `ColdRoomZonePlanner.plan` (via dataclass default fill for unspecified extended fields) | | E4 | true |
| `precooling_required_ratio` | bundle KEY | ratio | `ColdRoomZonePlanner.plan` | | E5 | true |

Traceability proof: `backend/tests/integration/test_v07_p1_bundle_execution_traceability.py`

## 2. ColdRoomZonePlanInput defaults (effective when not in bundle KEY set)

Source: `ColdRoomZonePlanInput` dataclass in `zone_planning.py`. When the
execution snapshot omits extended fields, `ZonePlanningAdapter` applies these
defaults.

| leaf_id | default | unit | consumer | non_consumer | known_conflict | requires_review |
| --- | --- | --- | --- | --- | --- | --- |
| `raw_holding_hours` | dataclass default | h | | metadata + input field only | E8 | true |
| `storage_position_capacity_kg` | dataclass default | kg | `ColdRoomZonePlanner.plan` position math | DemoZoneCoefficient metadata differs | E3 | true |
| `secondary_fruit_ratio` | dataclass default | ratio | `ColdRoomZonePlanner.plan` | | | true |
| `frozen_fruit_ratio` | dataclass default | ratio | `ColdRoomZonePlanner.plan` | DemoZoneCoefficient metadata differs | E1 | true |
| `frozen_storage_days` | dataclass default | day | `ColdRoomZonePlanner.plan` | DemoZoneCoefficient metadata differs | E2 | true |
| `main_packaging_storage_days` | dataclass default | day | `_packaging_position_count` | | | true |
| `auxiliary_packaging_storage_days` | dataclass default | day | `_packaging_position_count` | | | true |

Alignment proof: `backend/tests/architecture/test_v07_p1_default_alignment_matrix.py`

## 3. DemoZoneCoefficient metadata leaves (zone planner output)

Source: `ColdRoomZonePlanner._coefficients`. Persisted on calculation runs as
`coefficients[]` with audit metadata. Values here are **not** automatically
the effective calculator input when they conflict with dataclass defaults.

| leaf_id | unit | consumer | non_consumer | known_conflict | requires_review |
| --- | --- | --- | --- | --- | --- |
| `frozen_fruit_ratio` | ratio | | non_consumer=output metadata when Input default wins | E1 | true |
| `frozen_storage_days` | day | | non_consumer=output metadata when Input default wins | E2 | true |
| `storage_position_capacity_kg` | kg/position | | non_consumer=output metadata when Input default wins | E3 | true |
| `raw_holding_hours` | h | | non_consumer=unused by zone formula body | E8 | true |
| `raw_area_loading` | kg/m2 | area loading helpers | | | true |
| `primary_precooling_area_loading` | kg/day/m2 | precooling zone helpers | | | true |
| `secondary_precooling_area_loading` | kg/day/m2 | precooling zone helpers | | | true |
| `sorting_area_loading` | kg/day/m2 | sorting zone helpers | | | true |
| `coating_area_loading` | kg/day/m2 | coating zone helpers | | | true |
| `storage_area_loading` | kg/m2 | storage zone helpers | | | true |
| `secondary_fruit_area_loading` | kg/m2 | secondary fruit zone | | | true |
| `frozen_area_loading` | kg/m2 | frozen zone helpers | | | true |
| `office_area_per_t_day` | m2/(t/day) | support zone helpers | | | true |
| `changing_area_per_t_day` | m2/(t/day) | support zone helpers | | | true |
| `packaging_area_per_t_day` | m2/(t/day*day) | packaging zone helpers | | | true |
| `precooling_position_daily_capacity_kg` | kg/day/position | precooling position math | | | true |

Metadata proof: `backend/tests/architecture/test_v07_p1_coefficient_metadata_alignment.py`

## 4. Legacy fallback path (`build_zone_plan_from_inputs`)

Source: `planning/application/service.py`. Not the five-stage bundle KEY path,
but still a documented consumer for legacy/demo routes.

| leaf_id | fallback | unit | consumer | non_consumer | known_conflict | requires_review |
| --- | --- | --- | --- | --- | --- | --- |
| `packaging_storage_days` | `7` when missing | day | consumer=`build_zone_plan_from_inputs` | non_consumer=not five-stage bundle KEY path | E4 | true |
| `precooling_required_ratio` | `0.8` when missing | ratio | consumer=`build_zone_plan_from_inputs` | non_consumer=not five-stage bundle KEY path | E5 | true |
| `main_packaging_storage_days` | `packaging_storage_days` or `3` | day | consumer=`build_zone_plan_from_inputs` | non_consumer=not five-stage bundle KEY path | E4 | true |

## 5. Investment embedded vs registry (E6)

| leaf_id | registry track | embedded track | unit registry | unit embedded | consumer embedded | non_consumer registry | known_conflict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| electrical / power distribution cost | `investment.electrical_installation_ratio` (`seed_demo_coefficients`) | `power_distribution_cost_cny_kw` (`InvestmentEstimator`) | CNY/m2 | CNY/kW | consumer=`InvestmentEstimator.estimate` | non_consumer=registry demo seed not wired to investment calculator | E6 |

## 6. Seed authority dual track (E7)

| track | entrypoint | source_type | status | consumer | non_consumer | known_conflict |
| --- | --- | --- | --- | --- | --- | --- |
| catalog manifest | `coefficients.infrastructure.seed.seed_catalog` | `standard` | `approved` (placeholder `1.0`) | coefficient registry CRUD / resolver tests | not zone/investment embedded calculators | E7 |
| demo seed | `DatabaseCoefficientService.seed_demo_coefficients` | `demo` | `unverified` | demo coefficient service demos | not automatic calculator substitution | E7 |

Dual-track proof: `backend/tests/integration/test_v07_p1_seed_authority.py`

## 7. Version snapshot authority (documented gap, not repaired in P1)

| artifact | authority on five-stage path | consumer | non_consumer |
| --- | --- | --- | --- |
| `EngineeringInputBundleV1` | authoritative input for workbench execution | `WorkbenchFiveStageExecutionService.execute` | |
| `project_version.input_snapshot` | legacy/demo project version JSON | demo overview routes | not bundle-complete on operator sample (V07-GAP-006) |
| `orchestration_execution_snapshots.input_snapshot` | persisted execution snapshot from bundle projection | Transaction B calculator port | |

Authority proof: `backend/tests/integration/test_v07_p1_version_snapshot_authority.py`

## 8. KNOWN_CONFLICT summary (E1–E8)

| ID | registration | resolution authorized in P1 |
| --- | --- | --- |
| E1 | `frozen_fruit_ratio` Input default vs DemoZoneCoefficient | NO |
| E2 | `frozen_storage_days` Input default vs DemoZoneCoefficient | NO |
| E3 | `storage_position_capacity_kg` Input default vs DemoZoneCoefficient | NO |
| E4 | packaging storage days legacy vs orchestration KEY path | NO |
| E5 | precooling required ratio legacy vs orchestration KEY path | NO |
| E6 | investment registry ratio semantic vs embedded CNY/kW coefficient | NO |
| E7 | seed_catalog vs seed_demo_coefficients authority | NO |
| E8 | `raw_holding_hours` unused by formula | NO (non_consumer only) |

P1 MUST NOT promote demo coefficients or pick winning values for E1–E7.
