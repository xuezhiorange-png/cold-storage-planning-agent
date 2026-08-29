# ADR-036: Operator process input is workflow input authority; v09 sample is demo authority

- Status: Accepted (V1.4 workbench debt TD-023 + TD-008)
- Date: 2026-08-29
- Context: After V1.3 (`v1.3.0`), conversation preview reuses workbench lineage
  in memory. The operator workbench still named the first guided step
  `PROJECT_INPUT` and treated a V0.4 `save_inputs` snapshot as “inputs present”.
  Sidebar copy therefore disagreed with 「工程输入」, and a leftover
  `save_inputs` body could mark the first step complete without the V0.9 five
  KEY. Separately, Vue leftover catalogs still embedded `25000` kg/day and
  `2.5` storage days while `samples/v09-process-input/manifest.json` freezes
  `20000 / 7 / 10 / 4 / 12`.

## Decision

### 1. Recut the first guided step (TD-023)

Rename the operator-visible first step to `OPERATOR_PROCESS_INPUT`.
Operator copy is 「工程输入」; next-action copy is 「完成工程输入」.
Bump the workflow aggregate contract to `WorkflowAggregateV2`.

### 2. Five KEY / five-stage runs are input authority

Complete `OPERATOR_PROCESS_INPUT` when:

- canonical five-stage calculator runs are present, or
- persisted `OperatorProcessInputV1@1.1.0` five KEY are present
  (including an `EngineeringInputBundleV1` zone_planning section or a
  persisted `cold_room_zone_plan` input snapshot that carries those KEY).

A V0.4 `save_inputs` snapshot alone does **not** complete the step.
Keep the Path A HTTP API; do not delete it.

`INPUT_COMPLETENESS` uses the same V0.9 five-KEY list. Empty snapshots list
those five KEY only.

### 3. One operator demo numeric authority (TD-008 slice)

`samples/v09-process-input/manifest.json` is the only operator demo source
for the five KEY and storage-day defaults. Frontend leftover design-input
defaults must read that file (or the read-only GET that returns it).
Do not embed a second numeric set in Vue.

The V0.9 工程输入 form stays empty by default so the workbench does not
silently fill KEY. `GET /api/v1/demo/overview` stays a legacy overview and
is not retuned as a new formula source in this version.

Power / equipment / envelope catalog duplication is explicitly not closed
(`TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO`).

### 4. Identities unchanged

`OperatorProcessInputV1@1.1.0` five KEY stay frozen. Calculator identities
stay `cold_room_zone_plan@1.0.0`, `cooling_load@1.0.0`, `equipment@1.0.0`,
`installed_power@1.0.0`, `investment_estimate@1.0.0`. V1.3 Aily skill stays
the Feishu paste target.

### 5. Outbound and formula recut stay off

`AILY_OUTBOUND_LIVE_SESSION=NO`. `FORMULA_RECUT_AUTHORIZED=NO`.
`ENVELOPE_WALL_ROOF_FROM_PLAN=NO`.

## Consequences

- Guided workflow copy matches the 工程输入 nav item.
- Operators who only used Path A `save_inputs` will see the first step still
  open until they submit five KEY via 工程输入 (or five-stage runs exist).
- Leftover V0.4 design-input defaults stop drifting from the v09 sample.
- Reports and Vue still must not recompute formulas.

## Alternatives rejected

1. Persist `operator_process_input` onto every version snapshot as the only
   fix — optional later; step recut plus five-KEY authority is enough for
   TD-023.
2. Delete Path A `save_inputs` — compatibility still required.
3. Prefill the V0.9 工程输入 form with demo KEY — contradicts fail-closed
   missing KEY on the operator path.
4. Retune `demo_overview` calculator inputs to v09 — would make a legacy
   overview look like a new formula source.
5. Unify power/equipment catalogs in the same version — out of slice.
