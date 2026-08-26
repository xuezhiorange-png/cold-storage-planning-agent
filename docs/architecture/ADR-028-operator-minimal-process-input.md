# ADR-028: Operator-Minimal Process Input

- Status: Proposed (V0.8 P0 freeze; not implemented by P0)
- Context: At `v0.7.0` the operator workbench requires a full
  `EngineeringInputBundleV1` KEY surface. The original product intent is that
  an operator supplies only plant-level process quantities. V0.5 P0 froze
  cooling-load geometry as explicit user KEY and forbade silent auto-feed from
  zone area. V0.8 amends operator-visible authority, not calculator formulas.

## Context

V0.7 delivered the trust loop on unmodified `create_app` (five-stage
persistence, production scheme-run, report JSON, review, formal export). The
operator form still asks for cooling geometry, equipment grouping, installed
power components, and investment quantities. That makes the operator substitute
for the calculators.

Deterministic calculators already exist:

- `cold_room_zone_plan` accepts five KEY process fields and uses demo
  coefficients for the remainder of `ColdRoomZonePlanInput`.
- `cooling_load`, `equipment`, `installed_power`, and `investment_estimate`
  consume typed stage inputs.
- Execution-time lineage already exists for some downstream leaves
  (`design_cooling_load_kw_r`, investment area/power) when provenance is
  `persisted_upstream_confirmed`, but bundle validation currently requires those
  KEY leaves **before** lineage binding.

Silent `.get()` defaults inside calculators remain forbidden as authoritative
input. V0.8 does not promote demo coefficients.

## Decision

### 1. Operator-visible input is `OperatorProcessInputV1`

The operator may supply only these five KEY leaves (plus project-version
identity supplied by the workbench, not typed as engineering values):

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.working_time_h_per_day
zone_planning_inputs.finished_storage_days
zone_planning_inputs.packaging_storage_days
zone_planning_inputs.precooling_required_ratio
```

The V0.4 `planning-run` project page is leftover and is not V0.8 operator
authority.

### 2. Full `EngineeringInputBundleV1` remains execution authority

Five-stage execution still validates and persists a complete bundle. V0.8 adds
an application-layer **assembler** that expands `OperatorProcessInputV1` into
that bundle **before** calculator execution. Vue must not assemble downstream
KEY leaves. Prompts must not embed assembly logic.

### 3. Three leaf sources (must not be mixed)

| Source | Meaning | `source_type` |
| --- | --- | --- |
| Operator KEY | The five process quantities | `user` |
| Persisted upstream lineage | Typed outputs of a prior canonical stage | `persisted` |
| Explicit demo/coefficient catalog | Remaining KEY leaves copied into the bundle with provenance | `demo` or `coefficient` |

Catalog leaves MUST keep `validity_status=unverified` or `conflict` and
`requires_review=true`. Assembler MUST copy existing catalog/calculator demo
authority already in the repository. It MUST NOT invent new engineering
numbers and MUST NOT recut formulas.

### 4. V0.5 auto-feed amendment (V0.8 only)

V0.5 remains the baseline for the **full-bundle** compatibility path.

V0.8 operator-minimal path amends as follows:

```text
OPERATOR_PROCESS_INPUT_FIVE_KEY_LEAVES_ONLY=YES
ZONE_RESULT_TO_COOLING_LOAD_IDENTITY_AND_PLAN_AREA_LINEAGE=YES
ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO
PERSISTED_UPSTREAM_RESULT_TO_DOWNSTREAM_TYPED_INPUT=YES
DEMO_CATALOG_TO_EXPLICIT_BUNDLE_LEAF=YES
DEMO_DEFAULT_TO_AUTHORITATIVE_INPUT_WITHOUT_BUNDLE_LEAF=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

Allowed lineage examples (types must match; missing match fail-closed):

- Zone plan `zones[].` identity and `required_area_m2` → cooling-load
  `zone_code` / `zone_name` / `temperature_level` / `zone_area` / `floor_area`
- Cooling-load result → equipment `design_cooling_load_kw_r`
- Equipment result compressor electrical input → installed-power compressor KEY
- Zone + power results → investment area / position / power KEY

Not allowed:

- Copying zone plan area into wall/roof/height/U-value/product-temperature
  leaves without an explicit catalog or operator leaf
- Using `power_configuration` as installed-power authority
- Guessing E1–E8 conflict winners

Envelope geometry that the zone planner does not output (height, wall/roof
area, U-values, design temperatures, product thermal KEY) MUST appear as
explicit catalog leaves, not as silent calculator defaults.

### 5. Validation timing

Bundle KEY completeness is judged **after assembly** (and, for lineage-bound
leaves, after the producing stage has persisted). Operator-minimal submit MUST
NOT require the operator to type downstream KEY values. A missing operator
five-field KEY still fail-closes. A catalog hole still fail-closes. Lineage
mismatch still fail-closes.

### 6. Compatibility

Existing V0.5/V0.6/V0.7 tests that post a complete `EngineeringInputBundleV1`
MUST keep their assertion bodies. The assembler is additive. Do not mutate
`test_v05_*` / `test_v06_*` / `test_v07_*` assertions or `v07_sample_loader.py`.

## Consequences

- Operator UX matches the original process-quantity vision.
- Provenance stays auditable: every non-user KEY leaf is lineage or catalog.
- Cooling envelope quality remains concept-design / demo and requires review.
- Expert conflicts E1–E8 stay `KNOWN_CONFLICT`.
- Implementation is V0.8 P1+; this ADR is not authorization to edit
  `modules/calculations/domain/**`.
