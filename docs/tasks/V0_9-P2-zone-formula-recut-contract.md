# V0.9 P2 Zone Formula Recut Contract

**Status:** Implementation R1 — zone planner §4 formula recut  
**Authority:** `docs/tasks/V0_9-version-plan.md` §4 (expert formula lock)  
**Base `main` SHA:** `e9514c59ab6882f59c979191aa6b4ab33c9bfdaa`  
**Base tree:** `21484ad4c716ff72851eaa733188fb07fffb8f19`  
**Previous release:** `v0.8.0`  
**Parent:** P0 #213 + Wave 1 P1 #216 / P4 #215 / P5 #214 on `main`  
**Target branch:** `cursor/v09-p2-zone-formula-recut-6c68`

This document authorizes **P2 only**: deterministic Python recut of
`cold_room_zone_plan` per version-plan §4. It does not authorize merge,
tag, Release, Vue edits, or P3–P7 implementation.

Companion documents:

- Overall plan (formula lock §4): `docs/tasks/V0_9-version-plan.md`
- P0 contract (allowlist reference): `docs/tasks/V0_9-P0-version-contract.md`

## 0. Contract identity and governance

```text
TASK=V09_P2_ZONE_FORMULA_RECUT_R1
GOVERNANCE_OWNER=V0.9
BASE_MAIN_SHA=e9514c59ab6882f59c979191aa6b4ab33c9bfdaa
BASE_TREE=21484ad4c716ff72851eaa733188fb07fffb8f19
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-p2-zone-formula-recut-6c68
TARGET_FILE=docs/tasks/V0_9-P2-zone-formula-recut-contract.md
TARGET_PR_STATE=DRAFT

V09_P2_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
VUE_ENGINEERING_FORMULAS=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Formula numbers are authoritative in version-plan §4, not in this contract
file. P0 may still record `FORMULA_RECUT_AUTHORIZED=NO`; P2 overrides that
for the zone planner package only.

## 1. Objective

Implement version-plan §4 in `zone_planning.py`:

- Calculator name remains `cold_room_zone_plan`; `VERSION` bumps to `1.1.0`.
- Shared pallet/table rectangle packing with aspect target 1.67–2.40.
- Dual precooling schemes (6-position and 8-position); scalar
  `position_count` / `required_area_m2` project the **6-position** scheme
  (`reporting_scheme_id="6_position"`), not `min()`.
- New `shipping_channel` zone emitted in planner results.
- Packaging area uses `n × 1.56 × 2.5`.
- Secondary fruit: hardcoded 10% × 3 days; frozen: 10% × operator
  `frozen_storage_days`.
- Demo coefficients not used in `required_area_m2` must not appear as
  `area_basis` on zone rows.

## 2. Exclusive allowlist (P0 §7.3)

```text
V09_P2_FILE_ALLOWLIST
docs/tasks/V0_9-P2-zone-formula-recut-contract.md
backend/src/cold_storage/modules/calculations/domain/zone_planning.py
backend/tests/unit/test_zone_planner.py
backend/tests/unit/test_v09_p2_zone_planning.py
backend/tests/architecture/test_v09_p2_zone_formula_contract.py
```

**Out of scope for P2 (do not edit):**

- `operator_process_input.py` (P1)
- `REFRIGERATED_ZONE_REGISTRY` — `shipping_channel` registry add is a
  **Charles-authorized follow-on**; P2 emits the zone from the planner only.
- `cooling_load.py`, equipment, power, investment, Vue, sample loaders
- `test_v05_*` / `test_v06_*` / `test_v07_*` / `test_v08_*` assertion bodies

## 3. Known living-test pressure (record only)

These tests may fail after P2 without violating §4. Do **not** weaken §4
or edit off-allowlist tests to restore old gold values:

| Test | Pinned expectation | P2 impact |
|---|---|---|
| `backend/tests/integration/test_v07_p1_bundle_execution_traceability.py` | `position_count==24`, `total_area_m2==1813.57` | Precool reporting scalar + full §4 recut |
| `backend/tests/test_v03_p1_report_unit_quality.py` | exact `area_basis` code set | `area_basis` removed from recut zones |
| `backend/tests/integration/test_project_api_persistence.py` | legacy planning-run position_count / fan quantity | downstream scalar drift |
| Any `test_v08_*` pinning old planner gold | v0.8 area/position totals | §4 replaces demo formulas |

## 4. Verification

```text
cd backend
uv run ruff format --check <P2 py files>
uv run ruff check <P2 py files>
PYTHONPATH=src uv run pytest -q \
  tests/architecture/test_v09_p2_zone_formula_contract.py \
  tests/unit/test_v09_p2_zone_planning.py \
  tests/unit/test_zone_planner.py
```

## 5. Leftover registry note

`shipping_channel` is **emitted** by `cold_room_zone_plan` v1.1.0 but is
**not** added to `REFRIGERATED_ZONE_REGISTRY` in this package (off
allowlist). Cooling-identity registry alignment is deferred to a later
Charles-authorized follow-on.
