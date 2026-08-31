# ADR-038: v05 sample is the evaporator/condenser fan demo catalog

- Status: Accepted (V1.6 power-fan demo catalog authority)
- Date: 2026-08-31
- Context: V1.3 bound equipment electrical kW(e) into compressor installed
  power (`power_from_demo_catalog: false`). Fan kW(e) stayed demo because
  equipment results do not include fan electrical power, and Charles did not
  authorize inventing fan kW(e) from equipment (`FAN_KW_FROM_EQUIPMENT=NO`).
  The demo numbers already existed in
  `samples/v05-local-workbench/manifest.json` (`10.0` / `8.0`), but authority
  was split: kernel dataclass defaults `0` / `0`, assembler copied those
  zeros as demo leaves, workbench persist often stored `0+0` fans, and Aily
  preview filled pending/zero with a second hardcoded dict. Same five KEY
  therefore produced a 18 kW(e) fan delta between 豆包 preview and workbench
  persist. Charles authorized V1.6 to unify **that catalog only**.

## Decision

### 1. One reader, not a kernel bump

Add `projects.application.demo_power_fan_catalog` that walks the repo for
`samples/v05-local-workbench/manifest.json` and extracts the two fan leaves.
Workbench assembler and Aily `prepare_power_fan_catalog_inputs` both call it.
Delete Aily `_PREVIEW_POWER_FAN_DEMO`. Do **not** change
`InstalledPowerCalcInput` defaults away from `0` / `0`
(`KEEP_INSTALLED_POWER_VERSION=YES`). Missing sample or missing leaves
fail-closed.

### 2. Honesty is demo even if the sample says user

The frozen v05 bundle marked those fan leaves `source_type=user` because it
was a full-bundle fixture. Operator-minimal assembly stamps:

```text
source_type=demo
validity_status=unverified
requires_review=true
source_path=samples/v05-local-workbench/manifest.json
```

Do not treat the sample `user` marker as operator-entered five-KEY authority.

### 3. Compressor 120 is not this catalog

v05 `compressor_input_power_kw_e = 120.0` stays a historical fixture value.
Operator-minimal compressor remains lineage-pending until equipment bind.
`V05_COMPRESSOR_120_NOT_AUTHORITY=YES`. `power_from_demo_catalog` stays
`false` for the compressor path.

### 4. Equipment nine-zone catalog stays out of scope

v05 is a single-zone frozen sample (`S1` / `Z1`). Assembler still uses the
nine-zone `REFRIGERATED_ZONE_REGISTRY` plus `ZoneEquipmentInput` defaults.
Do not retune that catalog from v05 Z1
(`TD008_EQUIPMENT_CATALOG_UNIFIED=NO`).

### 5. Captions

蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)），不是设备结果，需复核.

### 6. Identities and outbound unchanged

`OperatorProcessInputV1@1.1.0` five KEY stay frozen. Calculator identities
stay `@1.0.0`. `AILY_OUTBOUND_LIVE_SESSION=NO`. `FORMULA_RECUT_AUTHORIZED=NO`
for this slice (V1.5 envelope recut remains shipped; this ADR does not recut
`P = compressor + fans + …`). Aily must not import
`cold_storage.modules.calculations`. Vue / reports / prompts must not embed
installed-power formulas or a second 10/8 assignment set.

## Consequences

- Same five KEY: workbench persist and 豆包 `preview_installed_power` fan
  leaves match (`10` / `8` kW(e) demo).
- Kernel still fail-closes at 0 if a caller constructs
  `InstalledPowerCalcInput()` without fans.
- Remaining TD-008 equipment / `demo_overview` copies stay open.

## Alternatives rejected

1. Change `InstalledPowerCalcInput` defaults to 10/8 — hides missing inputs
   inside the kernel.
2. Invent fan kW(e) from equipment or COP — equipment has no fan electrical
   output; out of scope.
3. Keep Aily hardcoded dict and only change the assembler — second authority.
4. Treat v05 compressor `120` as operator authority — regresses V1.3 lineage.
5. Unify nine-zone equipment from v05 Z1 — different shape; later TD-008.
