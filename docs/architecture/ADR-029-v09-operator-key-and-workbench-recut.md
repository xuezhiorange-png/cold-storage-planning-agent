# ADR-029: V0.9 Operator KEY Recut And Workbench Split

- Status: Proposed (V0.9 P0 freeze; not implemented by P0)
- Context: At `v0.8.0` the operator types five process KEY leaves, but zone
  area formulas ignore several of them, the workbench layout wastes screen,
  and review is confused with report export.

## Context

V0.8 delivered `OperatorProcessInputV1` with:

```text
daily_inbound_mass_kg
working_time_h_per_day
finished_storage_days
packaging_storage_days
precooling_required_ratio
```

Expert walk-through after `v0.8.0` locked zone-planning rules in
`docs/tasks/V0_9-version-plan.md`. Those rules require user-filled finished
days, frozen days, and two packaging-store days. They require **100%
precooling** of plant inbound mass. They do not use operator working hours
for area (written-dead hours stay in the planner). Review must not block
draft export. Formal export stays distinct. Live Aily stays off.

V0.8 ADR-028 remains the assembler / three-leaf-source authority. This ADR
amends **which** five KEY leaves the operator types and records that formula
code stays in P2, not P0.

## Decision

### 1. Operator-visible KEY (exactly five)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Deleted from the operator surface:

- `precooling_required_ratio` — all inbound is precooled
- `working_time_h_per_day` — not an area KEY this version
- `packaging_storage_days` — split into main + auxiliary

次果 storage days stay hardcoded in the planner (not operator KEY).

### 2. Full bundle remains execution authority

`EngineeringInputBundleV1` remains Path A. Application assembler expands
the V0.9 five KEY. Vue must not assemble downstream KEY or compute formulas.
Reports must not recalculate formulas.

### 3. Three leaf sources unchanged

User / persisted / explicit demo-or-coefficient catalog, as ADR-028.
Catalog leaves stay `requires_review=true`. Assembler must not invent
engineering numbers. Formula recut is a later P2 package with
`FORMULA_RECUT_AUTHORIZED=YES`.

### 4. Review is not export

Draft export must not be blocked because review is pending. Formal export
remains approved/archived. `mark_reviewed` stays a TestClient trusted
seam, not production RBAC. `AILY_LIVE_IMPLEMENTATION=NO`.

### 5. Zone result display is read-only

Workbench calculations UI may show persisted layout fields (precooling
schemes, packed positions, shipping platforms). Vue must not reimplement
planner geometry.

### 6. Compatibility

Do not mutate `test_v05_*` / `test_v06_*` / `test_v07_*` / `test_v08_*`
assertion bodies. Do not mutate `v07_sample_loader.py` or
`v08_sample_loader.py`. V0.9 sample is a new loader.

## Consequences

- Operator KEY matches the locked zone-planning inputs.
- Cooling / equipment / power / investment formulas are not recut here.
- Implementation of KEY, formulas, UI, export, and layout is P1–P7 after
  separate dispatch. This ADR is not authorization to edit
  `modules/calculations/domain/**`.
