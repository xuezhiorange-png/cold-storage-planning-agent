# ADR-040: Surface per-zone cooling design temperature and height

- Status: Accepted (V1.8 per-zone temperature and height surface)
- Date: 2026-08-31
- Context: Zone planning already registers temperature bands
  (`8~10℃`, `1~3℃`, `-18℃`) per refrigerated zone. The cooling kernel
  already consumes per-zone `room_design_temperature` and `room_height`
  in `Q = U × A × ΔT` and infiltration volume. Before V1.8, the
  operator-minimal assembler stamped the v05 single-zone demo catalog
  onto **every** refrigerated zone: **−18.0 °C** and **5.0 m**. V1.7
  surfaced five load components but not these inputs. Charles asked to
  理清 each zone's temperature and height. This ADR records the surface
  plus Charles-authorized V18-T1 / V18-H1 demo catalog. This is not a
  formula recut.

## Decision

### 1. Copy bound inputs; do not recompute

After authorization, cooling snapshots copy:

```text
room_design_temperature
room_height
```

from the values the kernel used for that zone (input echo). Keep the V1.7
component leaves. Do **not** put `Q = U × A × ΔT` or
`wall = height × 4 × √A` in Vue, reports, prompts, or Aily. Keep
`cooling_load@1.0.0` (`KEEP_COOLING_LOAD_VERSION=YES`).
`FORMULA_RECUT_AUTHORIZED=NO`.

### 2. Snapshot schema stays backward compatible

`CoolingLoadZoneResultV1` keeps `extra="forbid"` but makes the new echo
leaves **optional** so historical V1.7 snapshots still parse. New writes
populate them. Equipment bind still uses `zone_code` + `subtotal_load_kw_r`
only.

### 3. Same columns on workbench and 豆包

Workbench `COOLING_ZONE_COLUMNS` and Aily `preview_cooling_load` extra
table add the same two keys. Do not invent a second temperature scale.

### 4. Catalog recut is gated and must not guess

```text
ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES
ZONE_TEMPERATURE_BAND_POINT=COLD_END
ZONE_TEMPERATURE_CATALOG_RECUT=YES
ZONE_HEIGHT_CATALOG_RECUT=YES
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
```

Do not treat zone-plan band **midpoints** as design temperatures (V0.8).
Charles authorized the **cold end** of each existing band (V18-T1:
8.0 / 1.0 / −18.0). `product_target_temperature` follows
`room_design_temperature`. Height is Charles-authorized demo **4.0 m**
for every refrigerated zone (V18-H1), replacing v05 5.0 m on the
operator-minimal path only. Missing height stays fail-closed.

### 5. Identities unchanged

Five KEY stay `OperatorProcessInputV1@1.1.0`. Calculator identities stay
`@1.0.0`. `AILY_OUTBOUND_LIVE_SESSION=NO`. Aily must not import
`cold_storage.modules.calculations`. Freeze `docs/contracts/aily/v1.7/**`.

## Consequences

- Operators can audit echoed °C / m. After implementation, height is 4.0 m
  and indoor °C is the zone-plan band cold end (8 / 1 / −18).
- Old persisted cooling snapshots without the echo leaves still verify.

## Alternatives rejected

1. Bump `cooling_load@1.0.0` and change formulas — out of scope.
2. Silently stamp band midpoints (9 °C / 2 °C) — forbidden by V0.8 and
   AGENTS.md (do not guess missing engineering parameters).
3. Invent per-zone heights — Charles set one demo height (4.0 m) for all
   refrigerated zones; do not further invent 6 m / 4.5 m.
4. Recut product mass 20 t/zone in the same slice — Charles asked for
   temperature and height only.
5. Recompute ΔT or wall area in Vue or Aily — forbidden.
