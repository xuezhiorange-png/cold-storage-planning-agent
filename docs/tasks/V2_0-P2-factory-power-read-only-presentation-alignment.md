# V2.0 P2：工厂功率 canonical result 只读呈现对齐

## 授权与停止点

P0 contract freeze 和 P1 canonical calculator 是已完成的上游阶段；它们的
历史 authorization block 原样保留在 P0/P1 文档与 ADR-042 中。P1 已合并到
`main@2a1a2797767a52834143a78b3e80193b5752b2e6`。本文件记录 Charles 对 P2
的单独授权及本分支的实施边界。

~~~text
TASK_ID=V20_P2_FACTORY_POWER_CANONICAL_RESULT_READ_ONLY_PRESENTATION_ALIGNMENT_R1
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_MERGED=YES
P1_MERGE_COMMIT_SHA=2a1a2797767a52834143a78b3e80193b5752b2e6
P2_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V20_P2_IMPLEMENTATION_AUTHORIZED=YES
V20_P2_IMPLEMENTATION_EXECUTED=YES

CANONICAL_SOURCE=factory_power_estimation@2.0.0-p1
BACKEND_READ_ONLY_PROJECTION_AUTHORIZED=YES
WORKBENCH_READ_ONLY=YES
WORKBENCH_READ_ONLY_PRESENTATION_AUTHORIZED=YES
FRONTEND_READ_ONLY_PRESENTATION_AUTHORIZED=YES
AILY_READ_ONLY=YES
AILY_READ_ONLY_PRESENTATION_AUTHORIZED=YES
DOUBAO_READ_ONLY=YES
DOUBAO_READ_ONLY_PRESENTATION_AUTHORIZED=YES
WORKBENCH_AND_AILY_READ_SAME_RESULT=YES

FRONTEND_RECALCULATION=NO
AILY_RECALCULATION=NO
CANONICAL_POWER_FORMULA_RECUT=NO
FACTORY_POWER_RECALCULATION_IN_P2=NO
INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_USED_AS_V2_AUTHORITY=NO
FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO

OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
DATABASE_MIGRATION_CREATED=NO
NEW_DATABASE_SCHEMA_AUTHORIZED=NO
P3_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

## 实施内容

### 共享 read-model

`calculations.application.factory_power_presentation` 接受已序列化的 P1
canonical result，验证 schema、calculator identity、单位语义、审核状态、八
个 detail 字段和八个 summary 字段，然后只复制原字段；
`projects.application.factory_power_presentation` 是提供给项目/消费者边界的
公共只读入口。它可以生成
`sha256:<digest>` 完整性标识和 presentation-only 中文标签，但不执行任何工程
公式，不重建数量、功率池、同时系数或总功率。

现有通用 `CalculationRunRecord[]` 列表在读取 exact V2 calculator identity 时附带
该 read-model；不增加 API、表、列或迁移。缺失或 malformed canonical result 以
空值交给消费者，保持 fail closed。

### 工作台

新增独立的“估算工厂电功率（V2.0）”只读卡片和类型/映射。它严格选择：

~~~text
calculator_name=factory_power_estimation
calculator_version=2.0.0-p1
~~~

页面直接读取 canonical summary/details、review、assumptions、provenance 和单位
语义。旧的“装机功率结果”仍然绑定五阶段 `installed_power@1.0.0`；
`power_configuration` 仍然是 supplemental 数据，二者都不是 V2 authority。V2 记录
缺失时页面显示独立的不可用状态，不回退旧结果。

### Aily / 豆包

新增纯 `project_factory_power_table(...)`。它只接受 canonical result 或共享
`FactoryPowerPresentation` 对象，输出 V2-specific `reply_kind`、精确 calculator
identity/hash、details、summary、review、assumptions、provenance 和单位语义。普通
`Mapping` 只代表 P1 serialized canonical result，并统一经过
`build_factory_power_presentation(...)`，重新绑定 canonical 内容与 hash；带有
`source_calculator_identity`/`canonical_result_hash` 的可变 presentation dict 不再
被当作可信 read-model。当前五阶段 `project_power_table()`、
`preview_installed_power()` 和其 `installed_power@1.0.0` 身份未修改；本任务没有
出站实时 Aily 会话。

## Review correction R1

PR #258 的独立复审发现了两个 canonical integrity / fail-closed blocker。R1 已在
同一 feature lane 中完成窄修正，等待独立 re-review；不改变 P1 calculator、公式、
数据库、旧功率链路或任何下游发布门禁。

~~~text
CORRECTION_TASK_ID=V20_P2_FACTORY_POWER_CANONICAL_RESULT_READ_ONLY_PRESENTATION_REVIEW_CORRECTION_R1
SOURCE_PR=258
SOURCE_HEAD_SHA=ec25f6842c3150d04c93128cc83d76aa3f33ead4
REVIEW_RESULT=FAIL_CORRECTION_REQUIRED
BLOCKER_COUNT=2
FRONTEND_SHARED_PRESENTATION_ONLY=YES
FRONTEND_RAW_CANONICAL_FALLBACK=NO
GENERIC_RESULT_HASH_USED_AS_CANONICAL_HASH=NO
FRONTEND_BACKEND_REJECTION_BYPASS=NO
AILY_MAPPING_CANONICAL_ONLY=YES
AILY_UNVERIFIED_READ_MODEL_MAPPING_ACCEPTED=NO
STRICT_SHA256_FORMAT=YES
HASH_BOUND_TO_CANONICAL_CONTENT=YES
MUTATED_READ_MODEL_WITH_OLD_HASH_BLOCKED=YES
~~

## 一致性与测试

共享 golden fixture 分别从 backend shared presentation 与 canonical source 进入工作台
和 Aily projector，比较 source identity、canonical hash、details、summary、review、
unit semantics 和审计字段。hostile fixtures 证明工作台在 attached presentation 缺失、
为空或 malformed 时不读取 raw snapshot；Aily 对 fake hash、可变 serialized read-model
以及“修改工程值但保留旧 hash”的 payload 统一不可用。canonical 数值即使与可推导的
数学关系被故意打破，也不会在消费者侧重算。

架构测试锁定 P0/P1 历史授权、P2 独立授权、旧 calculator 身份分离、无公式复制、
无 migration、无 outbound Aily、无五阶段枚举变化和精确的允许范围。

## 门禁与停止

本任务完成后只允许保持 Draft PR，等待 Charles 独立 Review。CI 通过不推导 Ready
或 Merge；本任务不创建或移动 tag，不创建 release，也不启动 P3。

~~~text
READY_EXECUTED=NO
MERGE_EXECUTED=NO
TAG_CREATED=NO
RELEASE_CREATED=NO
~~~
