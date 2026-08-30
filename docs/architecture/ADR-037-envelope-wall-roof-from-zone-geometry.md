# ADR-037: Cooling wall and roof areas bind from zone-plan geometry

- Status: Accepted (V1.5 envelope wall/roof input lineage)
- Date: 2026-08-30
- Context: V1.3 (ADR-035) bound zone `required_area_m2` into cooling
  `floor_area` / `zone_area` in memory, matching the workbench persist path.
  Wall and roof stayed the v05 demo catalog (`200` / `100` m²) because
  `ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO` and
  `FORMULA_RECUT_AUTHORIZED=NO`. Charles authorized V1.5 to recut **that
  input lineage only**. The cooling kernel formula `Q = U × A × ΔT` stays
  unchanged. ADR-028 and ADR-035 bodies remain historically frozen; this
  ADR supersedes envelope auto-feed semantics for V1.5.

## Decision

### 1. Shared bind, not a kernel bump

Derive wall and roof in
`projects.application.preview_lineage_bind` after the existing floor bind.
Workbench `five_stage_execution` and Aily preview already call that function.
Do **not** put the geometry derivation in `cooling_load.py`. Keep
`cooling_load@1.0.0` (`KEEP_COOLING_LOAD_VERSION=YES`).

### 2. Frozen demo geometry (no new KEY)

Zone planning still emits `required_area_m2` only (no perimeter). V1.5 does
not add operator KEY. Explicit demo assumptions
(`source_type=demo`, `validity_status=unverified`, `requires_review=true`):

```text
floor_area = zone_area = required_area_m2
roof_area  = floor_area                    # single-story
wall_area  = room_height × 4 × √floor_area # square plan
room_height = v05 catalog 5.0 m
```

U-values, outdoor/indoor design temperatures, and product thermal leaves
stay demo/coefficient catalog. Ambient `常温` zones stay skipped.

### 3. Fail closed on missing height

If `room_height` is missing, null, non-numeric, or not positive, bind fails.
Do not guess `5.0` inside the binder. Catalog assembly still supplies `5.0`
on the operator-minimal path.

### 4. Rejected wall rule stays rejected

Do **not** use `wall = floor × height` (already rejected in ADR-035).
Square-plan `height × 4 × √A` is the V1.5 authorized substitute.

### 5. Assembler catalog 200/100 is not authority after bind

Operator-minimal assembly may still emit lineage-pending `wall_area` /
`roof_area` (replacing catalog `200` / `100` as the pre-bind placeholder).
Bind overwrites those leaves. Do not treat v05 `200` / `100` as the
post-bind cooling input.

### 6. Honesty flags and captions

Success path:

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true
```

Caption / skill: 地板、墙、屋面来自分区几何（正方形平面 + 演示层高）；U 值与设计温度仍为演示目录，需复核.

### 7. Identities and outbound unchanged

`OperatorProcessInputV1@1.1.0` five KEY stay frozen. Calculator identities
stay `@1.0.0`. `AILY_OUTBOUND_LIVE_SESSION=NO`. Aily must not import
`cold_storage.modules.calculations`. Vue / reports / prompts must not
embed the wall/roof formulas.

## Consequences

- Same five KEY, different inbound mass → refrigerated-zone `roof_area`
  tracks `required_area_m2`; `wall_area` tracks the frozen square-plan rule
  with demo height `5.0`.
- Workbench persist and 豆包 `concept-preview` / `preview_cooling_load`
  wall/roof numbers match.
- Historical ADRs still say envelope auto-feed was NO; V1.5 readers use
  this ADR for current semantics.

## Alternatives rejected

1. `wall = floor × height` — not a closed envelope; rejected since ADR-035.
2. Bump `cooling_load@1.0.0` and move geometry into the kernel — input
   lineage, not a load-formula change.
3. Invent perimeter KEY — zone planner does not emit perimeter.
4. Guess missing `room_height` — fail-closed.
5. Open TD-024 outbound or invent fan kW(e) from equipment — out of scope.
