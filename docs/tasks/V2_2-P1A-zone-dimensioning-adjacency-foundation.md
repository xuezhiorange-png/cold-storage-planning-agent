# V2.2 P1A — Zone dimensioning and adjacency foundation

## Separate authorization and truthful result

```ini
TASK_ID=V2_2_P1A_ZONE_DIMENSIONING_AND_ADJACENCY_FOUNDATION_R1
BASE_MAIN_SHA=e963256c56d20f90a880a61d0bc721d28c0a9c38
TARGET_VERSION=v2.2.0
ACTIVE_GOVERNANCE_LANE=V2.2_P1
P0_STATUS=MERGED
P1A_STATUS=IMPLEMENTATION_DRAFT_REVIEW
RESULT=PARTIAL_ENGINEERING_AUTHORITY
DIMENSIONED_ZONE_COUNT=4
BLOCKED_ZONE_COUNT=8
P2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
SITE_PLACEMENT_IMPLEMENTED=false
MCP_RUNTIME_CHANGED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

This is P1A, not completion of all P1 engineering authority and not P2 placement.
Prior P0 authorization snapshots remain historical. No existing calculator,
profile coefficient, six-tool MCP interface, five-key input, frontend, migration,
deployment, or Skill is changed. No new API is exposed.

## Module boundary and canonical evidence

`modules/layout/application/dimension_zones.py` binds a backend-generated successful
serialized `cold_room_zone_plan@1.0.0` result to `layout/domain` models. The source
must have the current `POST-V2.1.1-charles-engineering-rule-adjustments` formula
authority, exactly 12 unique zones and finite nonnegative required areas.
It is an internal application boundary, not an authentication mechanism for
LLM/user-supplied engineering payloads. No user profile/area input route is added.

`zone_dimensioning_foundation@1.0.0` / result schema `1.0.0` is a **foundation**
identity, not the future `site_constrained_factory_layout@1.0.0` placement identity.
Each result includes source identity, formula authority and a freshly computed
source hash; dimensions, complete copied source zone metadata, versioned profiles,
graph, authority matrix, units, review flag and unevaluated-constraint statuses.
Canonical JSON sorts object keys, uses compact UTF-8 and exact decimal strings
without trailing zeros for decimal/float values. The source hash covers the entire
serialized backend source envelope (including its zone row order); no caller hash
can override it. Dimension/profile rows are sorted by zone code. No correlation ID,
timestamp or random seed is generated. Result hash covers the complete canonical
foundation payload including source/profile content and identity, excluding itself.
`canonical_result_hash` is exposed by the result object; `to_dict()` returns a new
copy, never a mutable authority backing the hash. No hash claims completed layout.

## Real 20 t/day replay and authority matrix

Input: 20000 kg/day, finished 7 days, frozen 10 days, main packaging 4 days,
auxiliary packaging 12 days, using current canonical planner. The replay test calls
the real planner, not a copied area oracle. The 12-zone source totals 2194.59 m²;
P1A never sums/recalculates those required areas. `required_area_m2` is immutable
upstream area authority; dimensions are a separate envelope authority.

| ZONE_CODE | AREA_AUTHORITY | CAPACITY_GEOMETRY_AVAILABLE | DIMENSIONING_PROFILE_AVAILABLE | DIMENSIONING_RESULT | BLOCK_REASON |
| --- | --- | --- | --- | --- | --- |
| office | canonical zone plan | no, area only | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| changing_room | canonical zone plan | no, area only | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| primary_precooling_room | canonical zone plan | selected scheme/counts, no room edges | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| secondary_precooling_room | canonical zone plan | selected scheme/counts, no room edges | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| raw_fruit_buffer | canonical zone plan | grid + three-side aisle | yes | 15.2 × 8.7 = 132.24 m² | NONE |
| sorting_packaging_room | canonical zone plan | original table grid, not final envelope | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| coating_room | canonical zone plan | no, area only | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| finished_goods_room | canonical zone plan | grid + one-long-side aisle | yes | 32.4 × 18.6 = 602.64 m² | NONE |
| secondary_fruit_buffer | canonical zone plan | grid + one-long-side aisle | yes | 8.4 × 6.9 = 57.96 m² | NONE |
| frozen_fruit_room | canonical zone plan | grid + one-long-side aisle | yes | 10.8 × 8.2 = 88.56 m² | NONE |
| packaging_material_storage | canonical zone plan | position count, no arrangement | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |
| shipping_channel | canonical zone plan | platform count, no access envelope | no | BLOCKED | ZONE_DIMENSIONING_AUTHORITY_REQUIRED |

Runtime matrix `capacity_geometry_available` means arrangement metadata (`layout`
or `schemes`) is present, not that complete room dimensions or access are approved.
Every matrix row carries the full upstream zone and its hash for detailed review.
Missing-profile errors include zone_code, missing_profile, required_area_m2.

## Existing grid reuse, not a second capacity calculator

Only four profiles ship: `upstream-storage-grid-{zone_code}@1.0.0`. Application
imports the existing planner pitch and aisle constants; domain receives explicit
versioned profiles. For raw storage the already-selected grid's outer edges are
`n_long × pitch_along_wall + 2 × aisle` and `n_short × pitch_depth + aisle`;
the other three retain one-long-side aisle: `n_long × pitch_along_wall` and
`n_short × pitch_depth + aisle`. These are the factors of the existing canonical
planner's rectangle calculation, not a new packing search or throughput formula.
Counts must be positive, n_long/n_short must match nested layout, n_actual must
match their product and position_count; aisle identity must match. No counts are
repaired or recalculated. Full upstream rows preserve all counts, schemes,
clearances, metadata and capacity evidence.

No ASPECT_RATIO_* is imported or used as a building constraint. The source planner
alone orders capacity-grid candidates. First-stage dimensioning has no ambiguous
search candidates: a frozen grid or an explicitly supplied fixed envelope yields
one width/depth pair. Output defaults to rotation 0, explicit 90 is supported;
no arbitrary rotation or alternative layout optimizer exists. Fixed-envelope
profiles are a domain/test seam only; none is bound for blocked production zones.
Generic fixed rectangles are rejected for upstream schemes/grids, because they
cannot prove internal capacity preservation.

Widths/depths round **outward** to their profile increments (multiples of 0.001 m).
actual_area is exactly width × depth with deterministic Decimal context; if smaller
than required_area, fail closed rather than stretch or invent a shape. Explicit
profiles allow testing controlled rounding, not guessing engineering profiles.
For the current storage grids the source envelopes already meet required area.

Precooling 7 batches/1540 kg and 14h/2800 kg capacities remain source-only. Room
counts/selected schemes are copied, but 42/56 m² per room does not establish room
width/depth or the combined-room envelope. Sorting raw 565.76 m² and final 622.34 m²
are copied unchanged: **no second ×1.1**. A new reviewed profile is needed to locate
the additional perimeter area without repacking the table array.

## Graph and predicate scope

The graph binds the current P0/ADR main flow:
raw_fruit_buffer → primary_precooling_room → sorting_packaging_room → secondary_precooling_room → coating_room → finished_goods_room → shipping_channel.
Its six consecutive pairs are the **exact six** undirected MUST edges. Packaging,
secondary-fruit and frozen-fruit directed branches remain, with no packaging MUST.
The four SHOULD zone pairs and shipping-to-truck access proximity are read/locked
against current P0 by architecture tests. PEOPLE flows retain main entrance →
changing room → sorting/production-side logical node; office is not raw-material flow.

`RectangleObservationV1` holds supplied predicate observations, not generated x/y.
`ZoneDimensionV1` has no x/y. Shared positive-length edge is adjacency; corners,
separation and internal overlap do not qualify. Evaluator reports missing
observations, overlap/MUST failures and unfulfilled SHOULD edges separately.
`geometry_passed` only means the complete adjacency/no-overlap subset passed;
access and site acceptance are **not evaluated**, regardless of that boolean.
Input order must not affect evaluation output.

`AccessProfileV1` and `require_access_profile` are authority prerequisites only.
No profile is shipped. Missing authority raises ACCESS_PROFILE_REQUIRED; even a
supplied profile is not route validation, door approval, fire/hygiene approval,
truck turning or forklift clearance approval. Those remain later engineering work.

## Acceptance and stop gate

Tests cover live planner replay, the four/eight matrix, area/source preservation,
profile/schema errors, hash determinism/copy isolation, exact main/side graphs,
outward rounding, rotation, missing authority, overlap/corner/edge predicates and
no fabricated access acceptance. Historical scope guard uses the immutable
introducing task commit as endpoint, never future moving origin/main.
Local target/architecture/SQLite/Ruff/mypy precede push. Backend code additions
select BACKEND via the existing classifier; clean CI and ci-gate must pass.
Stop at Draft review. P1B/P2, placement, SVG/PDF/DXF, tool 7, database and frontend
implementation are not authorized by this task.

### Local environment diagnosis

Initial macOS SQLite run: 5602 passed, 470 skipped, 7 failed, all existing PDF
pagination/text-binding checks in `test_multilingual_report_pilot.py` and
`test_real_storage_e2e.py`. The exact seven failures reproduced on a detached
`e963256c56d20f90a880a61d0bc721d28c0a9c38` checkout, without this module.
The automatic macOS font was `/System/Library/Fonts/STHeiti Light.ttc`; CI installs
WenQuanYi. Using the existing `COLD_STORAGE_CJK_FONT_PATH` override with
`wqy-zenhei.ttc` from Debian `fonts-wqy-zenhei_0.9.45-8_all.deb` made all seven
pass unchanged. This is test-environment alignment only: no renderer, fixture,
oracle, dependency manifest or machine-wide font setting was changed.

### Final local acceptance

- P1A unit: 35 passed; backend architecture: 615 passed, 16 existing skipped.
- Final SQLite full run with CI font: **5609 passed, 470 existing skipped** (1195.03s).
- Ruff check and format: PASS (800 files); mypy src: PASS (362 source files).
- Decimal profile/dimension/predicate operations use fresh fixed contexts;
  the same result/hash and bounds also pass under caller precision=2.
- Diff whitespace and existing runtime/consumer/migration/workflow boundaries: PASS.
- Test-created PDF/DOCX files were archived outside the checkout, not committed,
  ignored by a widened allowlist, or deleted. No skip/xfail/oracle changes.
- GitHub exact-head BACKEND lane / ci-gate is the final clean-environment gate;
  local success does not authorize Ready, Merge or P2.
