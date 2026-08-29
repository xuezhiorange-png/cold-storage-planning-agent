# ADR-035: Aily conversation preview uses workbench lineage in memory

- Status: Accepted (V1.3 inbound preview lineage)
- Date: 2026-08-29
- Context: V1.2 (ADR-034) delivered five-stage conversation preview with
  demo envelope catalog, demo installed-power leaves, and demo investment
  placeholders. The operator workbench already binds zone `required_area_m2`
  to cooling `floor_area` / `zone_area` after persist (V0.8), captures
  equipment electrical kW(e) for installed power, and binds investment from
  zone totals plus power. Conversation preview skipped those binds because
  `persisted: false`.

## Decision

### 1. Same lineage, no persist

When Charles dispatches V1.3, inbound preview (REST `concept-preview` and the
five MCP tools) must apply the **same bind semantics** as
`five_stage_execution` lineage, in memory. Responses stay `persisted: false`.
Do not open Transaction B from 豆包.

### 2. Floor / plan area only — not wall / roof auto-feed

Bind zone-planner `required_area_m2` into cooling `zone_area` and `floor_area`.
Do **not** derive wall or roof area from plan geometry
(`ENVELOPE_WALL_ROOF_FROM_PLAN=NO`, `FORMULA_RECUT_AUTHORIZED=NO`).
U-values and outdoor design temperatures stay demo catalog.

### 3. Electrical kW(e) from equipment, not COP in Aily

Keep `total_compressor_input_power_kw_e` on the equipment result used by
preview (canonical snapshot or the existing electrical-capturing adapter).
Aily must not import `calculations` and must not compute kW(e) = kW(r) / COP.

### 4. Investment from zone + power, not v05 placeholders

Bind refrigerated / frozen / total area and power the way the workbench
operator-minimal path already does after persist.

### 5. Identities unchanged

`OperatorProcessInputV1@1.1.0` five KEY stay frozen. Calculator identities
stay `cold_room_zone_plan@1.0.0`, `cooling_load@1.0.0`, `equipment@1.0.0`,
`installed_power@1.0.0`, `investment_estimate@1.0.0`.

### 6. Outbound stays off

`AILY_OUTBOUND_LIVE_SESSION=NO` (TD-024).

## Consequences

- 豆包 cooling / power / investment tables should match the workbench chain
  for floor area and electrical lineage, with wall/roof still demo.
- V1.2 skill and ADR-034 remain historical; V1.3 adds a new skill pack after
  dispatch.
- Reports and Vue still must not recompute formulas.

## Alternatives rejected

1. Derive wall/roof from floor area × height — formula recut; later umbrella.
2. Leave conversation on demo catalog — V1.2 honesty gap stays user-visible.
3. Persist chat runs as Transaction B — out of scope for preview.
4. Open live Feishu outbound session — TD-024, needs tenant wiring.
