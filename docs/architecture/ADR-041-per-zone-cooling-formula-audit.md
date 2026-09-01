# ADR-041: Surface per-zone cooling CalculationStep formulas for audit

- Status: Proposed (V1.9 per-zone cooling formula audit)
- Date: 2026-09-01
- Context: `cooling_load@1.0.0` already records per-zone
  `CalculationStep` rows (formula, inputs, output) while computing
  transmission / product / infiltration / internal / defrost. V1.7
  persisted the five component **values**. V1.8 persisted temperature
  and height **inputs**. The cooling adapter still drops the steps from
  the durable payload (`_build_steps` exists but is unused on the
  cooling snapshot). Workbench 「计算依据」 reads legacy
  `formula_references`, which the new kernel does not populate. Charles
  asked to 逐个区域核算冷量计算公式. This ADR records a **copy/display**
  surface. This is not a formula recut.

## Decision

### 1. Copy kernel steps; do not recompute

After authorization, cooling snapshots copy each zone's
`CalculationStep` leaves:

```text
zone_code, zone_name, step_id, output_name, formula, inputs, output_value
```

Keep V1.7 component leaves and V1.8 T/H echo. Do **not** put
`Q = U × A × ΔT` (or any other cooling formula) as a source literal in
Vue, reports, prompts, or Aily. Render persisted `formula` / `inputs`
only. Keep `cooling_load@1.0.0`
(`KEEP_COOLING_LOAD_VERSION=YES`). `FORMULA_RECUT_AUTHORIZED=NO`.

### 2. Snapshot schema stays backward compatible

`CoolingLoadResultSnapshotV1` keeps `extra="forbid"` but makes the new
formula-audit collection **optional** so historical V1.8 snapshots still
parse. New writes populate it. Equipment bind still uses `zone_code` +
`subtotal_load_kw_r` only.

### 3. Same columns on workbench and 豆包

Workbench and Aily `preview_cooling_load` extra table add the same
formula-audit keys. Do not invent a second formula text.

### 4. Honesty about demo coefficients

Do **not** retune per-zone product mass, U values, air change,
diversity, or margin (`ZONE_PRODUCT_MASS_CATALOG_RECUT=NO`,
`ZONE_THERMAL_CATALOG_RECUT=NO`). Caption must still say envelope
geometry is square-plan + demo height, U-values / product mass are demo
catalog, and formulas are kernel copies, not recut.

### 5. Identities unchanged

Five KEY stay `OperatorProcessInputV1@1.1.0`. Calculator identities stay
`@1.0.0`. `AILY_OUTBOUND_LIVE_SESSION=NO`. Aily must not import
`cold_storage.modules.calculations`. Freeze `docs/contracts/aily/v1.8/**`
until implementation is authorized.

## Consequences

- Operators can 核算 each zone's formula against the numbers already
  shown in V1.7 / V1.8.
- Old persisted cooling snapshots without formula steps still verify.
- Changing the math stays a later dispatch
  (`FORMULA_RECUT_AUTHORIZED=YES`).

## Alternatives rejected

1. Bump `cooling_load@1.0.0` and change formulas — out of scope until
   Charles authorizes a recut.
2. Hardcode formula strings in Vue or 豆包 skill — forbidden by
   AGENTS.md.
3. Keep adapter dropping steps and only document formulas in markdown —
   operators still cannot 核算 against persisted results.
