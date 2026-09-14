# V2.2 P1C0 — Area precision contract correction

## Separate authority

```ini
TASK_ID=V2_2_P1C0_AREA_PRECISION_CONTRACT_CORRECTION_R1
BASE_MAIN_SHA=09d9973d1c0fb0ea1ead09601d252c22448d213a
TARGET_VERSION=v2.2.0
ACTIVE_LANE=V2.2_P1
AREA_REQUIREMENT_MODEL=AreaRequirementV1
CALCULATOR_IDENTITY=zone_dimensioning_foundation@1.2.0
RESULT_SCHEMA_VERSION=1.1.0
DIMENSIONED_ZONE_COUNT=6
BLOCKED_ZONE_COUNT=6
SORTING_PACKAGING_STILL_BLOCKED=true
NO_EPSILON=true
NO_SPECIAL_CASE=true
ACTUAL_AREA_IS_EXACT_PRODUCT=true
GEOMETRY_INFLATION_REQUIRED=false
ZONE_PLANNER_CHANGED=false
MCP_RUNTIME_CHANGED=false
FRONTEND_CHANGED=false
DATABASE_MIGRATION_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
P1C_SORTING_PROFILE_AUTHORIZED=false
P2_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Investigation and precise decision

Current zone planner emits `raw_required_area_m2=round(layout.required_area_m2,2)`,
then `required_area_m2=round(raw_required_area_m2 * area_factor,2)` using Python floats.
It does not emit a separate final unrounded requirement. No upstream code changes.
P0 previously treated the reported area as an unconditional exact lower bound.
This independently authorized overlay explicitly replaces that rule, not geometry.

`ZoneDimensionV1` retains required_area_m2 as an unchanged reporting compatibility
field and adds AreaRequirementV1. Width/depth/actual remain exact geometric values.
Case A: verified exact formula evidence + matching reporting projection allows
comparison to exact_geometry_required_area_m2. Case B: no exact authority compares
strictly to reported_required_area_m2. Invalid supplied evidence is an error, not
a reason to discard evidence silently. Both cases always require actual=width*depth.

## Evidence and trust boundary

ExactAreaAuthorityV1 contains a versioned profile source identity, Owner authority,
canonical source snapshot JSON/hash, ordered operand JSON Pointer paths, operands,
and exact-decimal-product@1.0.0. Operands must equal their source snapshot fields;
hash must match the parsed snapshot. Decimal product is computed, not caller-supplied.
The model checks source identity/authority/hash against the dimension's profile and
capacity reference. All nested evidence is immutable (strings/tuples/Decimals).

These internal domain objects are not an external authentication mechanism or proof
of Owner approval. A future production binder must verify canonical source and
select only an independently approved profile and its expression paths. P1C0 ships
NO such exact binder and no user/MCP/profile override input route. Existing production
dimension_zones always creates requirements without exact evidence, so all six
existing profiles remain on the strict reported lower-bound branch.

Technical expression bounds: 1–4 nonnegative operands, existing decimal digit/exponent
limits, mapping-only literal JSON Pointer paths. This is an explicit product contract,
not a universal formula evaluator or a mechanism to reverse-engineer reported area.

## Reporting projection

Identity: `cold-room-zone-plan-binary64-product-2dp@1.0.0`.
Quantum: 0.01 m². Source: cold_room_zone_plan@1.0.0:required_area_m2.
Method: PYTHON_BINARY64_ORDERED_PRODUCT_THEN_ROUND_2.

Replay float(operand0), then multiply remaining operands in order, then Python
round(product,2), then Decimal(str(reported)). This is intentionally NOT ROUND_HALF_UP,
nor blindly Decimal.quantize, nor float(exact_product) when intermediate rounding
matters. The binary64 arithmetic exists only in the reporting projection; exact
requirement/actual geometry use isolated Decimal contexts. No epsilon comparisons.
For sorting parity, the operands are the actual upstream rounded raw value and its
factor; no second raw geometry computation is substituted in the projection.

Synthetic proof: source operands565.76 and1.10 produce exact622.336, project622.34.
The rectangle45.76×13.60 has actual622.336 and is accepted without enlargement.
This fixture is not a production sorting profile. Multi-throughput real planner
replays verify reporting equality and distinct grid candidates; tie examples such
as Python round(2.675,2)=2.67 rule out an incorrect half-up implementation.

## Existing geometry and historical versions

P1B calculator1.1.0/schema1.0.0 are historical. Current calculator1.2.0/schema1.1.0
add area_requirement metadata; canonical hashes intentionally change for version/schema
reasons. The four storage and two precool widths/depths/actuals and source capacity
remain unchanged; no profile, precool implementation or adjacency changes.
Blocked remains office/changing_room/sorting_packaging_room/coating_room/
packaging_material_storage/shipping_channel. No P1C production hookup, placement,
x/y, building footprint, rendering, tool7 or deployment.

## Acceptance

Tests cover exact product, below-exact failure, reported mismatch, missing exact
strict behavior, invalid projection, source/operand tampering, determinism, real
planner parity, and unchanged six-zone geometry. Scope is frozen to this task's
immutable introducing commit; later HEAD is ancestry evidence only.
Local full SQLite/Ruff/mypy/architecture and exact-head BACKEND CI evidence are recorded
in the Draft PR body; baseline main #2375 must also be green before any separately
authorized Ready/Merge. No passing test implies that authorization.
