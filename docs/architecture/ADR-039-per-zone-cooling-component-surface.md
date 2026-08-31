# ADR-039: Persist kernel per-zone cooling components for operator audit

- Status: Accepted (V1.7 per-zone cooling component surface)
- Date: 2026-08-31
- Context: `cooling_load@1.0.0` already computes five components per
  refrigerated zone (transmission, product, infiltration, internal, defrost)
  plus a subtotal, with `CalculationStep` traceability. The cooling adapter
  then projected durable `zones` down to `zone_code` + `subtotal_load_kw_r`
  so equipment lineage could bind. 豆包 extra tables therefore showed only
  a subtotal. Charles authorized V1.7 to **audit how each zone load is
  calculated** by surfacing those existing kernel fields. This is not a
  formula recut and not a zone-thermal catalog recut.

## Decision

### 1. Copy kernel zone fields; do not recompute

`_canonical_cooling_snapshot_payload` copies:

```text
zone_code, zone_name, temperature_level,
transmission_load_kw_r, product_load_kw_r,
infiltration_load_kw_r, internal_load_kw_r,
defrost_load_kw_r, subtotal_load_kw_r
```

from the calculator zone dict. Plant-wide aggregate component rows stay.
Do **not** put `Q = U × A × ΔT` (or any other cooling formula) in Vue,
reports, prompts, or Aily. Keep `cooling_load@1.0.0`
(`KEEP_COOLING_LOAD_VERSION=YES`). `FORMULA_RECUT_AUTHORIZED=NO`.

### 2. Snapshot schema stays backward compatible

`CoolingLoadZoneResultV1` keeps `extra="forbid"` but makes the new
component leaves **optional** so historical two-field snapshots still
parse. New writes populate all listed leaves. Equipment bind still uses
`zone_code` + `subtotal_load_kw_r` only.

### 3. Same columns on workbench and 豆包

Workbench `COOLING_ZONE_COLUMNS` already names these kernel fields.
Aily `preview_cooling_load` extra table and markdown must show the same
five components + subtotal. Do not invent a second aggregation.

### 4. Honesty about demo thermal catalog

Do **not** retune per-zone product mass or room temperature
(`ZONE_THERMAL_CATALOG_RECUT=NO`). Caption must still say envelope
geometry is square-plan + demo height, and U-values / design temperatures
are demo catalog. Also say zone product thermal still shares the v05 demo
catalog.

### 5. Identities unchanged

Five KEY stay `OperatorProcessInputV1@1.1.0`. Calculator identities stay
`@1.0.0`. `AILY_OUTBOUND_LIVE_SESSION=NO`. Aily must not import
`cold_storage.modules.calculations`.

## Consequences

- Same five KEY: operators can see why zone A and zone B differ (today:
  mainly area; thermal catalog still shared).
- Old persisted cooling snapshots without component leaves still verify.
- Remaining work (true per-zone thermal catalog) stays a later dispatch.

## Alternatives rejected

1. Bump `cooling_load@1.0.0` and change formulas — out of scope.
2. Recut every zone to different product mass / −18°C — Charles did not
   authorize `ZONE_THERMAL_CATALOG_RECUT`.
3. Recompute zone loads in Vue or Aily — forbidden.
4. Keep adapter stripping and only document formulas — operators still
   cannot 核对 numbers.
