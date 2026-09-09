# V2.1 Release Closure / v2.1.0 Readiness

## 1. 当前状态

本文件记录 V2.1 的 release-closure readiness determination。它固化已经合并
到 `main` 的 P0、P1、P2 事实，并不执行 tag、GitHub Release、部署或下一条
feature lane。V2.1 没有定义 P3；P0、P1、P2 完成后直接进入本 release-closure
门禁。

```text
TASK_ID=V21_RELEASE_CLOSURE_READINESS_R1
TARGET_RELEASE=v2.1.0
BASE_RELEASE=v2.0.0
BASE_MAIN_SHA=b314f08c74296e23e2a1729dd4f84dc8387c7a4e
BASE_MAIN_CI_RUN_ID=34349430563
BASE_MAIN_CI_RESULT=SUCCESS
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=MERGED
V21_IMPLEMENTATION_COMPLETE=YES
V21_P3_DEFINED=NO
V21_P3_EXECUTED=NO
V21_RELEASE_CANDIDATE=YES
V2_1_0_RELEASE_READY=YES
RELEASE_CLOSURE_AUTHORIZED=YES
RELEASE_CLOSURE_EXECUTED=YES
TAG_CREATION_AUTHORIZED=NO
TAG_MOVEMENT_AUTHORIZED=NO
GITHUB_RELEASE_CREATION_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 2. V2.1 实施阶段闭合

V2.1 相对 `v2.0.0` 的已交付增量如下：

- P0 冻结 canonical `cold_room_zone_plan@1.0.0` upstream authority、12-zone
  factory area、9-zone refrigerated area、temperature integrity、append-only
  `preview_factory_power` MCP contract 和 five-key-only consumer contract。
- P1 实现 canonical zone-plan 到 `factory_area_m2`、`cold_storage_area_m2` 的
  upstream authority adapter，并调用既有
  `factory_power_estimation@2.0.0-p1`。
- P2 实现 stateless `preview_factory_power` MCP tool 6、V2.1 standalone
  Doubao Skill、V2.1 connector runbook 和 shared-projector presentation path。

合并记录：

```text
V21_P0_PR_NUMBER=260
V21_P0_MERGE_COMMIT_SHA=1d0a8e23f550b3c9ced413932fde0995acb227c0
V21_P0_STATUS=MERGED
V21_P1_PR_NUMBER=261
V21_P1_MERGE_COMMIT_SHA=95b6cbf839ba584f29f13735b07f8f8309b1cf37
V21_P1_REVIEW_RESULT=PASS
V21_P2_PR_NUMBER=262
V21_P2_FINAL_HEAD_SHA=6c6bb2401b04a59f7b6fef7e02ffd47231bfd08b
V21_P2_MERGE_COMMIT_SHA=b314f08c74296e23e2a1729dd4f84dc8387c7a4e
V21_P2_REVIEW_RESULT=PASS
V21_P2_BLOCKER_COUNT=0
V21_P2_MAIN_CI_RUN_ID=34349430563
V21_P2_MAIN_CI_RESULT=SUCCESS
```

## 3. Release lineage

`v2.0.0` 是 V2.1 的不可变基线。`v2.0.0^{}` 解析为
`a7049ca93d238013c0cf62069fe1e0a89ff834d7`，该 release target 必须是当前
V2.1 candidate 的祖先；它不是未来 `v2.1.0` tag 的固定 target。

```text
V20_RELEASE=v2.0.0
V20_RELEASE_TARGET_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7
V20_RELEASE_IS_ANCESTOR_OF_V21_CANDIDATE=YES
MAIN_LINEAGE_RESULT=PASS
BASE_MAIN_SHA_IS_ANCESTOR_OF_HEAD=YES
```

未来 release target policy 必须是：

```text
FUTURE_V21_TAG_TARGET_POLICY=CLOSURE_MERGE_COMMIT_PLUS_EXACT_MAIN_CI_AND_SEPARATE_AUTHORIZATION
```

因此，本 closure 不使用 `V2_1_0_TAG_TARGET=b314f08c...` 之类会冻结错误
target 的断言。dispatch 时的外部状态记录如下，architecture test 不把它写成
“未来永远不存在”的断言：

```text
V2_1_0_TAG_EXISTS_AT_CLOSURE_START=NO
V2_1_0_GITHUB_RELEASE_EXISTS_AT_CLOSURE_START=NO
```

## 4. Release blocker audit

本次审计没有发现阻止 `v2.1.0` candidate 的 V2.1 blocker：

```text
P0_CONTRACT_CONTRADICTION=NONE
P1_REVIEW_BLOCKER=NONE
P2_REVIEW_BLOCKER=NONE
FACTORY_AREA_AUTHORITY=EXPLICIT
COLD_STORAGE_AREA_AUTHORITY=EXPLICIT
V20_CALCULATOR_AUTHORITY=PRESERVED
P1_ADAPTER_AUTHORITY=PRESERVED
MCP_SIX_TOOL_CONTRACT=PASS
FIVE_KEY_INPUT_CONTRACT=PASS
DOUBAO_SKILL_CONTRACT=PASS
CANONICAL_RESULT_HASH_PARITY=PASS
DETAILS_PARITY=PASS
SUMMARY_PARITY=PASS
V18_COMPATIBILITY=PASS
V20_RUNTIME_REGRESSION=PASS
V21_RUNTIME_REGRESSION=PASS
ARCHITECTURE=PASS
MAIN_LINEAGE=PASS
EXACT_MAIN_CI=PASS
NO_NEW_RELEASE_BLOCKER=YES
```

### Factory and cold-storage area authority

```text
FACTORY_AREA_AUTHORITY=CANONICAL_12_ZONE_ROWS
FACTORY_ZONE_COUNT=12
FACTORY_AREA_FROM_USER=NO
FACTORY_AREA_FROM_DOUBAO=NO
FACTORY_AREA_FROM_LLM=NO
FACTORY_AREA_TOTAL_CROSS_CHECK=YES
COLD_STORAGE_AREA_AUTHORITY=REFRIGERATED_ZONE_REGISTRY
REFRIGERATED_ZONE_COUNT=9
FROZEN_FRUIT_ROOM_INCLUDED=YES
SHIPPING_CHANNEL_INCLUDED=YES
REFRIGERATED_AREA_M2_IS_AUTHORITY=NO
REFRIGERATED_ZONE_TEMPERATURE_MISMATCH=FAIL_CLOSED
```

The adapter remains fail-closed for `DUPLICATE_ZONE_CODE`,
`ZONE_AUTHORITY_SET_MISMATCH`, `MISSING_ZONE_REQUIRED_AREA`,
`INVALID_ZONE_REQUIRED_AREA` and `FACTORY_AREA_TOTAL_MISMATCH`.

### Calculator and adapter authority

```text
FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1
MAIN_SYSTEM_COP=3.3
POOL_A=DEFROST
POOL_B=OTHER
POOL_C=PRODUCTION
FACTORY_POWER_FORMULA_RECUT=NO
V20_CALCULATOR_CHANGED=NO
V20_SHARED_PRESENTATION_CHANGED=NO
AILY_FACTORY_POWER_ENGINEERING_ENTRYPOINT=P1_ADAPTER_ONLY
P1_ADAPTER_AUTHORITY=PRESERVED
RAW_POSITION_COUNT_FORBIDDEN=YES
MINIMUM_ESTIMATED_COOLING_LOAD_KW_R_AUTHORITY=PRESERVED
```

`preview_installed_power` remains `installed_power@1.0.0`; it is not replaced by
factory power, and `power_configuration` is not a V2.1 authority.

## 5. MCP / Doubao compatibility invariants

```text
MCP_TOOL_COUNT=6
NEW_MCP_TOOL=preview_factory_power
NEW_TOOL_POSITION=6
EXISTING_FIVE_TOOL_ORDER_CHANGED=NO
PREVIEW_INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_USED_AS_V21_AUTHORITY=NO
FACTORY_POWER_INPUT_KEY_COUNT=5
FACTORY_POWER_INPUT_SHAPE=FLAT_TOP_LEVEL_FIVE_KEYS_ONLY
FACTORY_POWER_FLAT_FIVE_KEY_ONLY=YES
FACTORY_POWER_REQUIRES_PRECEDING_ZONE_TOOL_CALL=NO
BACKEND_STATELESS_ZONE_PLAN_REPLAY=YES
DOUBAO_CARRIES_ZONE_RESULT=NO
DOUBAO_CARRIES_ENGINEERING_AREA=NO
FACTORY_POWER_SHARED_PROJECTOR=project_factory_power_table
MCP_ENGINEERING_RECALCULATION=NO
MARKDOWN_ENGINEERING_RECALCULATION=NO
```

The only factory-power input keys are:

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

Area fields, `zone_plan`, `zone_result`, `chat_text`,
`zone_planning_inputs` wrapper and unknown fields are not accepted. When the five
keys are already available, the supplemental factory-power path may call
`preview_factory_power` directly; the five-stage normal flow still begins with
`preview_zone_plan` and remains:

```text
preview_zone_plan
→ preview_cooling_load
→ preview_equipment
→ preview_installed_power
→ preview_investment
```

The V2.1 Skill is standalone and preserves the V1.8 semantic surface:

```text
V21_SKILL_STANDALONE_V18_SEMANTIC_SUPERSET=YES
FACTORY_POWER_FLAT_TOP_LEVEL_FIVE_KEY_ONLY=YES
FACTORY_POWER_ZONE_PLANNING_INPUTS_WRAPPER_ALLOWED=NO
FACTORY_POWER_REQUIRES_PRECEDING_ZONE_TOOL_CALL=NO
AGENT_TO_ENGINEERING_VALUE=NO
AILY_OUTBOUND_LIVE_SESSION=NO
SERVER_SIDE_CHAT_NLP=NO
V18_SKILL_CHANGED=NO
V18_RUNBOOK_CHANGED=NO
```

The calculations import lock remains narrow and durable:

```text
P2_CALCULATIONS_IMPORT_ALLOWLIST_DURABLE=YES
P2_ONLY_ALLOWED_CALCULATIONS_IMPORTS=YES
P2_P1_ADAPTER_ENTRYPOINT_LOCKED=YES
```

## 6. Runtime and product boundaries

The factory-power result remains a concept-design estimate in `kW`, requires review,
and is not `kWh`, a meter value, monthly electricity consumption, an electricity
bill, transformer sizing, formal distribution design, short-circuit calculation,
cable selection, protection setting or a construction drawing.

```text
CONCEPT_PREVIEW_STAGE_COUNT=5
CALCULATION_TYPE_COUNT=5
V20_CALCULATOR_CHANGED=NO
V20_PRESENTATION_CHANGED=NO
RUNTIME_CHANGED=NO
FRONTEND_CHANGED=NO
DATABASE_MIGRATION_CREATED=NO
WORKFLOW_CHANGED=NO
DEPLOYMENT_CHANGED=NO
OUTBOUND_LIVE_AILY_SESSION_EXECUTED=NO
```

Unrelated technical debt is not closed by this release closure. In particular,
`TD-008`, `TD-019`, `TD-021` and `TD-024` retain their documented real states.

## 7. Release execution gate

`V2_1_0_RELEASE_READY=YES` means the implementation and readiness audit passed. It
does not execute release operations. The next permitted release action requires a
separate authorization after this closure PR is independently reviewed, made Ready,
merged, and the resulting `main` head has a successful exact-main CI run.

```text
RELEASE_EXECUTION=NO
TAG_CREATED=NO
TAG_MOVED=NO
GITHUB_RELEASE_CREATED=NO
DEPLOYMENT_EXECUTED=NO
READY_EXECUTED=NO
MERGE_EXECUTED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

### Future release-note facts

```text
v2.1.0 — Factory Power Upstream Authority + Doubao MCP Integration
```

The future notes may summarize canonical zone-plan area authority, no user area
re-entry, MCP tool 6, the unchanged V2.0 calculator, the standalone V2.1 Skill and
stateless five-key direct preview. They must not claim deployment completed.
