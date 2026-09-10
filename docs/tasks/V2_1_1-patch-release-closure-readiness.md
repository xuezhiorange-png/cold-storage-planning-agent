# V2.1.1 Patch Release Closure / 14h Readiness

本文件记录 PR #264 合并后的 14h 有效工作时间修正的 v2.1.1 patch
release-closure readiness。它只固化已合并事实与验收证据，不执行 tag、GitHub
Release、部署或任何下一阶段工作。

## 1. Closure 状态

```text
TASK_ID=V2_1_1_PATCH_RELEASE_CLOSURE_R1
BASE_RELEASE=v2.1.0
BASE_RELEASE_SHA=2221077d4ebe0ee90e218b8869ccb3bb000b1d60
PATCH_TARGET=v2.1.1
PATCH_TARGET_SHA=c3f4be969bfbc65531c38338e3712355e74b6776
SOURCE_PR=264

MAIN_CI_RUN_ID=34462264950
MAIN_CI_RUN_NUMBER=2335
MAIN_CI_RESULT=SUCCESS
MAIN_CI_HEAD_SHA=c3f4be969bfbc65531c38338e3712355e74b6776
MAIN_CI_SHA_MATCH=YES

V2_1_1_IMPLEMENTATION_COMPLETE=YES
V2_1_1_RELEASE_CANDIDATE=YES
V2_1_1_RELEASE_READY=YES
TAG_CREATION_AUTHORIZED=NO
GITHUB_RELEASE_CREATION_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`V2_1_1_RELEASE_READY=YES` 只表示本 patch 的实现、回归和 release-closure
审计已通过。它不代表创建 tag、发布 GitHub Release 或部署已获授权。

## 2. Patch 内容

本 patch 仅收录 PR #264 已合并的有效工作时间修正：

```text
SECONDARY_PRECOOL_EFFECTIVE_HOURS=14
SECONDARY_PRECOOL_POSITION_DAILY_CAPACITY_KG=2800
SECONDARY_PRECOOL_CAPACITY_FORMULA=400 / 2 * 14

PACKING_EFFECTIVE_HOURS=14
PACKING_PERSON_DAILY_CAPACITY_KG=336
PACKING_PERSON_CAPACITY_FORMULA=16 * 1.5 * 14

FORMULA_AUTHORITY=POST-V0.9-P4-charles-zone-area-recut
```

当前 20 t/day 回归样例保持：

```text
SECONDARY_PRECOOLING_ROOM_AREA_M2=84.00
SORTING_PACKAGING_ROOM_AREA_M2=565.76
TOTAL_AREA_M2=2138.01
```

有效工作时间由输入参数进入既有 zone planner 计算路径；本 patch 没有创建新的
calculator identity，也没有修改工厂功率计算器。

## 3. Historical compatibility

历史快照继续按其原始语义重放，当前默认值不被反向改写：

```text
V07_HISTORICAL_REPLAY_HOURS=16
V07_GOLDEN_CHANGED=NO
V09_HISTORICAL_ORACLE_REWRITTEN=NO
HISTORICAL_SCOPE_GUARDS=IMMUTABLE_BASE_TO_TARGET
```

V0.7 historical fixture 的 16h dedicated inputs 是 test-local compatibility
注入；当前生产执行仍使用二级预冷 14h、分选包装 14h。

## 4. Unchanged product and release boundaries

```text
FACTORY_POWER_CALCULATOR=factory_power_estimation@2.0.0-p1
MCP_TOOL_COUNT=6
MCP_CONTRACT_CHANGED=NO
DOUBAO_SKILL_CHANGED=NO
DATABASE_MIGRATION_CHANGED=NO
DEPLOYMENT_CHANGED=NO
```

以下能力不属于本 patch 的改动范围：冷负荷、设备、五阶段装机功率、投资、工厂
功率、Doubao MCP 六工具接口、Doubao Skill、数据库 schema、Alembic migration、
部署以及已发布的 `v2.1.0`。

## 5. Immutable release lineage

`v2.1.0` 必须保持不可变：

```text
V2_1_0_TAG_TARGET=2221077d4ebe0ee90e218b8869ccb3bb000b1d60
V2_1_0_TAG_TARGET_IMMUTABLE=YES
V2_1_0_TAG_MOVED=NO
V2_1_0_RELEASE_REWRITTEN=NO
```

`v2.1.1` 的未来 target 不在本 closure 中预先创建或移动。任何正式 release
执行都必须以 closure 合并后的新 `main`、对应 exact-main CI 成功和单独的 release
授权为准。

## 6. Closure scope evidence

closure 的 scope guard 使用固定的 closure candidate snapshot：

```text
CLOSURE_SCOPE_BASE_SHA=c3f4be969bfbc65531c38338e3712355e74b6776
CLOSURE_SCOPE_SNAPSHOT_SHA=96854d0c9a19321355794da874329871592978c4
CLOSURE_SCOPE_TARGET_IS_IMMUTABLE=YES
CLOSURE_SCOPE_CHECKS_CURRENT_HEAD_FOR_LINEAGE_ONLY=YES
ORIGIN_MAIN_HEAD_EQUALITY_USED=NO
V2_1_1_CLOSURE_ALLOWED_SCOPE=DOCS_AND_ARCHITECTURE_EVIDENCE_ONLY
```

该 snapshot 用于验证 closure 当时的 base-to-target 变更；合并后的未来 HEAD
只用于验证 snapshot lineage，不被当作历史 scope diff 的终点。因此，未来正常
runtime 开发不会把已完成的 patch closure 误报为 scope violation。

## 7. Gate result

```text
PATCH_14H_REGRESSION=PASS
V07_HISTORICAL_GOLDEN=PASS
ARCHITECTURE_EVIDENCE=PASS
MAIN_LINEAGE=PASS
MAIN_CI=PASS
NO_NEW_PATCH_RELEASE_BLOCKER=YES
```

本 closure 停在 release-closure review gate：

```text
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
```
