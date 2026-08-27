# V0.9 Overall Version Plan

**Status:** Overall plan freeze — identity, operator KEY, zone-formula lock, package DAG  
**Dispatch:** `NO` — this document does not authorize P0 contract freeze or P1–P7 implementation  
**Previous release:** `v0.8.0`  
**Base `main` SHA:** `0dc8de5b3c711aaa662b0bbda3988def037fda3b`  
**Base tree:** `db5c9298c1be7a922b0cacaf84a8c9f176c87838`  
**Authority:** Charles (process / product). Coordinator records the plan; Wave packages wait for `可以派发`.

```text
TASK=V09_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V0.9
PREVIOUS_RELEASE=v0.8.0
BASE_MAIN_SHA=0dc8de5b3c711aaa662b0bbda3988def037fda3b
BASE_TREE=db5c9298c1be7a922b0cacaf84a8c9f176c87838
TARGET_FILE=docs/tasks/V0_9-version-plan.md

PLAN_STATUS=OVERALL_PLAN_FROZEN_P0_CONTRACT_IN_PROGRESS
DISPATCH_AUTHORIZED=NO
V09_P0_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The **formula recut is one package inside V0.9**, not the whole version.
Workbench layout, draft-vs-formal export, blocker-banner recut, and
result display ship in the same version.

## 1. Version identity

V0.9 is an **operator workbench recut + zone-planning formula recut**.

It is not a cooling/equipment/power/investment formula rewrite, not a
Feishu Aily live integration, not production RBAC, and not a tag/Release
until separately `授权`.

Judgement for V0.9:

- operators type only the V0.9 KEY leaves in §2;
- zone areas (including 出货通道) come from the locked formulas in §4;
- Vue never duplicates those formulas;
- draft report export is not blocked by pending review;
- formal export remains a distinct, later step (future Feishu review is
  out of scope);
- the workbench uses the screen instead of a single 960 px column with
  stacked “阻断” banners on every page.

## 2. Operator KEY (locked for this plan)

Exactly five operator-visible KEY leaves. Units fail-closed. Missing KEY
must not be guessed.

```text
zone_planning_inputs.daily_inbound_mass_kg          kg/day
zone_planning_inputs.finished_storage_days          day
zone_planning_inputs.frozen_storage_days            day
zone_planning_inputs.main_packaging_storage_days    day
zone_planning_inputs.auxiliary_packaging_storage_days  day
```

Removed from the operator surface (V0.8 five KEY → this set):

| V0.8 KEY | V0.9 |
|---|---|
| `precooling_required_ratio` | **Deleted.** 100% of inbound is precooled. Primary and secondary precooling use full-plant daily inbound \(M\). |
| `working_time_h_per_day` | **Deleted from operator KEY.** Area formulas use written-dead hours (primary 6 h, secondary 16 h, packing 16 h, loading 4 h). |
| `packaging_storage_days` | **Split** into main + auxiliary user days. |

Added:

- `frozen_storage_days` (user)
- `main_packaging_storage_days` (user)
- `auxiliary_packaging_storage_days` (user)

Hardcoded in zone formulas (not operator KEY):

- 次果比例 10%, 次果天数 **3 day**
- 冻果比例 10% (days are user KEY)
- 原果暂存比例 0.40
- 预冷 / 分选 / 装车工时 as in §4

Full `EngineeringInputBundleV1` remains Path A for V0.5–V0.8 clients.
V0.9 operator path posts compact process input only. Vue must not assemble
downstream KEY or compute formulas.

## 3. Problems this version closes

Recorded after `v0.8.0` and included in V0.9 (not deferrable leftovers):

1. **Zone formulas** — walk every room; replace demo loading / fixed aisle
   factors / unused KEY; add 出货通道.
2. **Workbench layout** — single column, page `max-width: 960px`, large
   empty regions, almost no workbench-level responsive layout.
3. **Report export confused with review** — formal DOCX/PDF requires
   `approved`/`archived`; browser actor is `system`, so trusted
   `mark_reviewed` fail-closes. Draft export already exists after
   `generated`, but UI + “正式导出阻断” makes export look impossible.
   Review may later bind 飞书; V0.9 must not mix the two, must not fake
   production RBAC, must not enable live Aily.
4. **Stacked blockers** — every workbench page stacks 核心阻断, formal
   export blockers, and 溯源阻断. Demo `requires_review=true` must not
   be presented as a core stop for draft work. Stale copy on calculations
   still tells operators to fill `EngineeringInputBundleV1`.
5. **Zone results display** — `ZoneResultsTable` shows little more than
   an area number. V0.9 must show persisted scheme/layout fields (two
   precooling schemes, need vs packed positions, dock count). Vue reads
   persisted results only.

## 4. Zone formula lock (expert, not yet in code)

Calculator remains `cold_room_zone_plan`. Large models must not compute
these values. Missing KEY fail-closed. Demo leftovers that are **not**
used in `required_area_m2` must not be presented as the area basis.

Shared pallet pitch (storage rooms unless noted):

- along-wall pitch \(1.2\,\mathrm{m}\)
- depth pitch \(1.0+0.3=1.3\,\mathrm{m}\)

Storage rectangle packing (原果 / 成品 / 次果 / 冻果 / 分选台数):

- \(n_{\mathrm{need}}\) from the room rule
- choose \(n_{\mathrm{long}}\times n_{\mathrm{short}}\ge n_{\mathrm{need}}\)
  with \(n_{\mathrm{long}}\ge n_{\mathrm{short}}\) (long side of the
  assembled rectangle against the wall, except 分选 which is a free
  four-sided matrix)
- target aspect \(n_{\mathrm{long}}/n_{\mathrm{short}}\) in
  **1.67–2.40** (10×6 … 12×5)
- pick: fewest unused cells, then closest to ratio 2, then smaller area
- results **must** expose \(n_{\mathrm{need}}\), packed layout,
  \(n_{\mathrm{actual}}=n_{\mathrm{long}}\times n_{\mathrm{short}}\)
  (may exceed need), and area from the packed rectangle

### 4.1 办公室 / 更衣室 / 覆膜间

Fixed areas: **60 / 100 / 120 m²**. No formula this version.

### 4.2 一级预冷间 8~10℃

Throughput = full-plant \(M\). 100% precool.

- pallet 220 kg, 1 h/pallet, **6 h/day** (written dead)
- \(q_d=220\times 6=1320\,\mathrm{kg/day\cdot position}\)
- \(n_{\mathrm{need}}=\lceil M/q_d\rceil\)
- **Always emit both schemes** (not `min` of one area):

| Scheme | Rooms | Positions | Area |
|---|---|---|---|
| 6-position room | \(N=\lceil n_{\mathrm{need}}/6\rceil\) | \(N\times 6\) | \(N\times 52\,\mathrm{m}^2\) |
| 8-position room | \(N=\lceil n_{\mathrm{need}}/8\rceil\) | \(N\times 8\) | \(N\times 68\,\mathrm{m}^2\) |

Do not use \(5.6\,\mathrm{m}^2\)/position. Do not treat the rounded
multiple as position count.

### 4.3 二级预冷间 1~3℃

Same room modules and dual-scheme output as primary.

- pallet 400 kg, 2 h/pallet, **16 h/day**
- \(q_d=200\times 16=3200\,\mathrm{kg/day\cdot position}\)
- throughput = full-plant \(M\)

### 4.4 原果暂存间 8~10℃

\[
M_{\mathrm{raw}}=M\times 0.40,\quad
n_{\mathrm{need}}=\lceil M_{\mathrm{raw}}/220\rceil
\]

Long side against wall; **3 m aisles on the other three sides**:

\[
A=(n_{\mathrm{long}}\times 1.2+3+3)\times(n_{\mathrm{short}}\times 1.3+3)
\]

Demo loading 240 kg/m² and fixed aisle factor 1.2 are **not** the area
formula.

### 4.5 分选包装间 8~10℃

Throughput = full-plant \(M\) (do not deduct 次果 / 冻果).

- 16 pieces/h/person, 1.5 kg/piece, **16 h**, 3 persons/table
- \(q_{\mathrm{person}}=16\times 1.5\times 16=384\,\mathrm{kg/person\cdot day}\)
- \(N_{\mathrm{workers}}=\lceil M/384\rceil\)
- \(N_{\mathrm{table,need}}=\lceil N_{\mathrm{workers}}/3\rceil\)
- table pitch 5.5 m × 3.5 m **already includes inter-table spacing**
- pack tables to a rectangle (actual tables may exceed need)
- **4 m aisle on all four sides** of the matrix (not against a wall):

\[
A=(n_{\mathrm{long}}\times 5.5+4+4)\times(n_{\mathrm{short}}\times 3.5+4+4)
\]

Drop `packing_area_factor=1.5`.

### 4.6 成品间 1~3℃

\[
M_{\mathrm{fin}}=M\times D_f,\quad
n_{\mathrm{need}}=\lceil M_{\mathrm{fin}}/400\rceil
\]

\(D_f\) is operator `finished_storage_days` (not hardcoded). Layout
identical to 原果 (three-side 3 m, long side against wall, pad). Do not
deduct 次果 / 冻果 from \(M\).

### 4.7 次果暂存间 8~10℃

\[
M_{\mathrm{sec}}=M\times 0.10\times 3,\quad
n_{\mathrm{need}}=\lceil M_{\mathrm{sec}}/220\rceil
\]

Days **hardcoded 3**. Layout like 原果 packing, but **only the free long
side has a 3 m aisle** (no 3 m on the two short ends):

\[
A=(n_{\mathrm{long}}\times 1.2)\times(n_{\mathrm{short}}\times 1.3+3)
\]

Do not use frozen-room area × 0.80.

### 4.8 冻果间 -18℃

\[
M_{\mathrm{fr}}=M\times 0.10\times D_{\mathrm{fr}},\quad
n_{\mathrm{need}}=\lceil M_{\mathrm{fr}}/600\rceil
\]

\(D_{\mathrm{fr}}\) is operator `frozen_storage_days`. Ratio 10%
hardcoded. Layout identical to 次果 (one long-side 3 m aisle).

### 4.9 包材库 常温

Operator supplies **two** days. Position count keeps the existing named
main/auxiliary material coefficients \(c_{\mathrm{main}}\), \(c_{\mathrm{aux}}\):

\[
n=\lceil M\times(D_{\mathrm{main}}\sum c_{\mathrm{main}}+D_{\mathrm{aux}}\sum c_{\mathrm{aux}})\rceil
\]

\[
A=n\times 1.56\times 2.5
\]

Replace area factor 1.5 with **2.5**. No aisle-geometry recut this
version.

### 4.10 出货通道 1~3℃ (new zone)

Independent zone. Nothing extra for the operator. Do not deduct 次果 /
冻果. Written-dead parameters:

- finished pallet 400 kg (same as 成品)
- 9.6 m truck = 16 finished pallets
- 1 h per truck, 4 h loading per day → 4 trucks per platform per day
- 55 m² per platform

\[
P=\lceil M/400\rceil,\quad
N_{\mathrm{trucks}}=\lceil P/16\rceil,\quad
N_{\mathrm{platforms}}=\lceil N_{\mathrm{trucks}}/4\rceil,\quad
A=N_{\mathrm{platforms}}\times 55
\]

Results must expose pallet count, truck count, platform count, and area.
Proposed `zone_code`: `shipping_channel`.

V0.9 does **not** recut cooling-load formulas. If this 1~3℃ zone is
registered for cooling identity, it may still receive the existing demo
thermal catalog (`requires_review=true`). Do not invent a shipping-dock
cooling formula in this version.

## 5. Review vs export vs Feishu (locked policy)

| Surface | V0.9 rule |
|---|---|
| Draft export (zh-CN / en-US DOCX / PDF) | Allowed on draft/generated (existing `DRAFT_EXPORT_STATUSES`). **Must not** be blocked because review is pending. |
| Formal export | Remains `approved` / `archived` (`FORMAL_EXPORT_STATUSES`). |
| Review | Still the V0.7 TestClient trusted-operator seam. **Not** production RBAC. **Not** live 飞书. |
| UI | Draft download and formal download are separate actions. Formal blockers must not disable draft export. |
| Aily | `AILY_LIVE_IMPLEMENTATION=NO`. `/api/v1/agent/**` stays V0.6 internal compatibility. |

Do not implement Feishu review in V0.9.

## 6. Package DAG

```text
P0 → (P1 || P4 || P5)
P1 → P2 → P3
(P2 || P3 || P4 || P5) → P6 → P7
```

Wave 1 after P0 merge: **P1 ∥ P4 ∥ P5**.  
Wave 2: **P2** (needs P1 KEY / assembler).  
Wave 3: **P3** (needs P2 persisted result shape).  
Wave 4: **P6**.  
Wave 5: **P7**.

| Pkg | Name | Owns | Must not |
|---|---|---|---|
| **P0** | Contract freeze | Version identity, KEY list, formula lock reference, DAG, allowlists, architecture tests, ADR for KEY recut | Application behavior; formula code |
| **P1** | Operator KEY + assembler | `OperatorProcessInputV1` five KEY in §2; expand catalog; zone identity including `shipping_channel`; Vue 工程输入 five fields only | Zone area formulas; cooling formulas; Feishu |
| **P2** | Zone formula recut | `calculations/domain/zone_planning.py` and calculator tests implementing §4; persist dual precooling schemes and layout fields | Vue formulas; export policy; layout CSS |
| **P3** | Zone result display | Calculations UI reads persisted zone fields (schemes, need vs actual, docks). File-scan: no engineering formulas in Vue | Recalculate area; invent missing fields |
| **P4** | Draft vs formal export | Operator-visible draft export path; copy and blockers so review pending does not hide draft download; keep formal gate | Production RBAC; live Aily; `mark_reviewed` as a browser production role |
| **P5** | Workbench layout + banners | Workbench grid/responsive layout; stop stacking demo-review as 核心阻断 on every page; fix stale EngineeringInputBundleV1 empty-state copy | Formulas; export status machine rewrite (P4) |
| **P6** | Sample + runbook | V0.9 sample with the five KEY in §2; Makefile seed/verify; trusted TestClient actor only in tests | New formulas; live Aily |
| **P7** | Controlled acceptance | Prove §1 judgement on unmodified `create_app` (sqlite + postgresql); Vue file-scan; dual precooling in persisted JSON; draft export without review; formal still gated | Mutate P1–P6 production code; tag/Release |

P7 does not authorize tag or Release.

## 7. Global non-goals (every V0.9 package)

```text
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
FIELD_EQUIPMENT_CONTROL=NO
AGENT_TO_ENGINEERING_VALUE=NO
REPORT_FORMULA_RECALCULATION=NO
VUE_ENGINEERING_FORMULAS=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
MICROSERVICES=NO
```

Issues **#11 / #13 / #17 / #176 / #20 stay CLOSED**. Do not reopen.

## 8. Known leftovers (honest, not this version)

- E1–E8 demo `KNOWN_CONFLICT` rows that P2 does not replace with expert
  values remain `requires_review=true` unless §4 supersedes that leaf.
- Cooling envelope is not auto-fed from zone plan area (V0.5/V0.8).
- `product_mass_per_day` catalog may still be demo per zone until a later
  cooling recut.
- Precooling rooms may still receive the v05 freezer envelope demo
  package until a cooling recut.
- 次果天数 stays hardcoded 3 (not an operator KEY this version).

## 9. Next step (not done by this document)

P0 contract freeze is the current dispatched docs package
(`docs/tasks/V0_9-P0-version-contract.md`). P1–P7 stay
`IMPLEMENTATION_AUTHORIZED=NO`.

After P0 merge, Charles replies **可以派发** for Wave 1 (`P1 ∥ P4 ∥ P5`).
P2 formula recut waits for P1. Merge still needs **可以ready合并**.
Tag `v0.9.0` needs separate **授权**.
