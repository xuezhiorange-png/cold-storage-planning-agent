# V1.9 P0 — Per-zone cooling estimation basis contract

**Status:** Contract frozen for Charles review; implementation is not authorized.
**Task:** `V19_P0_PER_ZONE_COOLING_ESTIMATION_BASIS_CONTRACT_FREEZE_R1`
**Direction:** `PER_ZONE_COOLING_ESTIMATION_BASIS`
**Authority:** `CHARLES_CONFIRMED_ENGINEERING_REFERENCE`
**Base:** `main@ae3814f3b0c644d5ae23aabfc24825ac7b29ca2b`

This P0 reuses the existing zone-plan output and freezes only a transparent
minimum-estimate basis for nine refrigerated zones. It does not define a
detailed thermal load algorithm, recut `cooling_load`, select equipment, or
change runtime behavior. The computed
`minimum_estimated_cooling_load_kw_r` is exactly the frozen basis; any future
selected or design capacity must be **not less than** that minimum.

The JSON block below is the machine-readable contract surface used by the
architecture test. Each rule carries the unified `reference_factor` /
`reference_factor_unit` pair and `requires_review=true`. Its `formula` values
are reference-basis expressions, not an authorization to implement a new
calculator.

```json
{
  "contract_id": "V19_P0_PER_ZONE_COOLING_ESTIMATION_BASIS_CONTRACT_FREEZE_R1",
  "direction": "PER_ZONE_COOLING_ESTIMATION_BASIS",
  "output_field": "minimum_estimated_cooling_load_kw_r",
  "output_relation": "minimum_estimated_cooling_load_kw_r = frozen_reference_basis",
  "area_semantic": "PLANNED_ZONE_AREA",
  "area_source_field": "required_area_m2",
  "authority_source": "CHARLES_CONFIRMED_ENGINEERING_REFERENCE",
  "zone_rules": [
    {
      "zone_code": "primary_precooling_room",
      "basis": "FINAL_POSITION_COUNT",
      "source_field": "position_count",
      "reference_factor": 20,
      "reference_factor_unit": "kW(r)/final position",
      "formula": "position_count * 20",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": ["raw_position_count"]
    },
    {
      "zone_code": "secondary_precooling_room",
      "basis": "FINAL_POSITION_COUNT",
      "source_field": "position_count",
      "reference_factor": 15,
      "reference_factor_unit": "kW(r)/final position",
      "formula": "position_count * 15",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": ["raw_position_count"]
    },
    {
      "zone_code": "raw_fruit_buffer",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 400,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.40",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    },
    {
      "zone_code": "sorting_packaging_room",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 300,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.30",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    },
    {
      "zone_code": "coating_room",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 300,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.30",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    },
    {
      "zone_code": "finished_goods_room",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 300,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.30",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    },
    {
      "zone_code": "secondary_fruit_buffer",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 400,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.40",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    },
    {
      "zone_code": "frozen_fruit_room",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 550,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.55",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    },
    {
      "zone_code": "shipping_channel",
      "basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "reference_factor": 300,
      "reference_factor_unit": "W/m2",
      "formula": "required_area_m2 * 0.30",
      "result_semantics": "MINIMUM_ESTIMATE",
      "requires_review": true,
      "forbidden_source_fields": []
    }
  ],
  "semantic_lock": {
    "minimum_estimate_semantics": "YES",
    "minimum_computed_value_relation": "minimum_estimated_cooling_load_kw_r = frozen_reference_basis",
    "engineering_reference_relation": "required cooling capacity >= frozen_reference_basis",
    "engineering_required_capacity_is_lower_bound": true,
    "allowed_terms": [
      "minimum estimated cooling load",
      "minimum cooling capacity reference",
      "最低估算制冷量",
      "最低制冷能力参考值"
    ],
    "forbidden_terms": [
      "exact cooling load",
      "final design cooling load",
      "formal thermal load",
      "precise heat load calculation"
    ]
  },
  "fail_closed": {
    "missing_or_unmapped_inputs": [
      "position_count",
      "required_area_m2",
      "zone_code",
      "reference_factor"
    ],
    "forbidden_fallbacks": [
      "raw_position_count",
      "demo thermal catalog",
      "U × A × ΔT",
      "product sensible heat",
      "infiltration model",
      "legacy cooling output",
      "AI guessed values",
      "arbitrary defaults"
    ]
  },
  "authorization": {
    "EXISTING_ZONE_PLAN_REUSE": "YES",
    "USER_CONFIRMED_ESTIMATION_REFERENCE": "YES",
    "MINIMUM_ESTIMATE_SEMANTICS": "YES",
    "RUNTIME_IMPLEMENTATION_AUTHORIZED": "NO",
    "DETAILED_THERMAL_LOAD_ALGORITHM_AUTHORIZED": "NO",
    "COOLING_LOAD_FORMULA_RECUT_AUTHORIZED": "NO",
    "EQUIPMENT_SELECTION_RECUT_AUTHORIZED": "NO",
    "INSTALLED_POWER_RECUT_AUTHORIZED": "NO",
    "INVESTMENT_RECUT_AUTHORIZED": "NO",
    "FRONTEND_IMPLEMENTATION_AUTHORIZED": "NO"
  },
  "pr_252": {
    "PR_252_FORMULA_AUDIT_DIRECTION": "SUPERSEDED_BY_PER_ZONE_COOLING_ESTIMATION_BASIS",
    "PR_252_MERGE_AUTHORIZED": "NO",
    "PR_252_CLOSE_AUTHORIZED": "NO",
    "PR_252_RUNTIME_IMPLEMENTATION_AUTHORIZED": "NO"
  }
}
```

## Contract rules

The engineering requirement remains a lower bound on capacity:

```text
ENGINEERING_REFERENCE:
required cooling capacity >= frozen reference basis

COMPUTED_MINIMUM_VALUE:
minimum_estimated_cooling_load_kw_r = frozen reference basis
```

In a future separately authorized design or selection flow,
`future_selected_or_design_cooling_capacity` may be greater than or equal to
the computed minimum. That phrase is a semantic distinction only; this P0
does not add that runtime field or design an equipment-selection algorithm.

### Canonical lineage

The contract consumes `zone_plan.result.zones[]`. The canonical area field is
`required_area_m2`, whose frozen semantic is `PLANNED_ZONE_AREA`. Pre-cooling
rules consume the final `position_count`; `raw_position_count` is explicitly
forbidden even though the existing planner exposes it as an intermediate.

### Nine-zone reference matrix

| Zone | Basis | Reference factor |
| --- | --- | --- |
| `primary_precooling_room` | final `position_count` | 20 kW(r)/final position |
| `secondary_precooling_room` | final `position_count` | 15 kW(r)/final position |
| `raw_fruit_buffer` | `required_area_m2` | 400 W/m² |
| `sorting_packaging_room` | `required_area_m2` | 300 W/m² |
| `coating_room` | `required_area_m2` | 300 W/m² |
| `finished_goods_room` | `required_area_m2` | 300 W/m² |
| `secondary_fruit_buffer` | `required_area_m2` | 400 W/m² |
| `frozen_fruit_room` | `required_area_m2` | 550 W/m² |
| `shipping_channel` | `required_area_m2` | 300 W/m² |

The area reference factors are 0.40, 0.30, 0.30, 0.30, 0.40, 0.55 and 0.30 kW/m²
respectively. The historical 300 W/m² raw-fruit basis is obsolete and is not
an alternative in this contract. All nine rules retain `requires_review=true`
to preserve manual engineering review; that flag does not mean the contract is
unfrozen or the result is invalid.

### Fail-closed behavior

Missing final position count, missing canonical area, an unmapped `zone_code`,
or a missing reference factor is a hard failure. No demo thermal catalog,
legacy output, sensible-heat model, infiltration model, arbitrary default, AI
guess, or formula such as `U × A × ΔT` may be used as a substitute.

### Authorization and stop gate

This is a docs/contract/architecture-test-only slice. It does not authorize
runtime implementation, detailed thermal algorithm work, cooling-load formula
recut, equipment selection, installed-power or investment recut, or frontend
implementation. PR #252 remains untouched and not closed. The next required
stage is `CHARLES_V19_P0_CONTRACT_REVIEW`; V1.9 P1 is not authorized.
