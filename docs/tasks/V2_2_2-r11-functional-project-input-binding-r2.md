# R11 R2 — 封存20t项目级功能设计输入绑定

TASK_ID=`V2_2_2_R11_FUNCTIONAL_PROJECT_INPUT_BINDING_R2`

基线：PR #321 HEAD `834acd7f0f486f01465c9030e5f7e520fc6a4b32`。

## 研发判断

R11 R1正确地将原Stage B工程有效、P1面积与功能适用性分开，且历史9份记录/8组物理矩形的27份房间记录均为`INPUT_REQUIRED`。R2不是又一轮搜索，而是将此前确认的Owner V2业务规则与**项目级实际输入**分离、绑定，避免把进厂20t用作实际已包装质量，或自动采用53人/106柜示例。

## 两层来源与字段语义

1. Owner V2合同为`docs/previews/v2.2.2/owner-functional-input-contract-r2/owner-confirmed-business-rules-v2.json`。读取时与R11已封存报告中的Owner规则SHA256逐字节校验；再次核对15件/人时、1.6kg/件、8小时、192kg/人班、两班不共柜、错峰更衣、默认50/50、办公室规模映射、覆膜设计100%及覆膜工时不得自动继承。
2. 仅接受由应用侧**已完成文档、适用范围和项目身份审核后**构造的`ReviewedProjectDatum`。这个Python对象不负责认证审核人，source_label/Hash也不能作为授权令牌。R2离线CLI刻意**没有**将普通JSON或用户自填`OWNER_CONFIRMED`标签转换成已审数据的入口。
3. 项目Scope由R11封存的zone_plan_hash和p1_handoff_hash构成；衍生至每套候选房间时加Candidate Hash及房间代码。不同项目或不同候选的已审资料不能相互替代。

可审阅的项目事实（当前均缺失）：`PACKAGED_PRODUCT_MASS_KG_PER_DAY`、`FACTORY_SIZE`，以及可选择性明确提供的`SHIFT_1_WORKERS`与`SHIFT_2_WORKERS`（覆盖时两项必须同时提供）。它们均不是进厂日质量的别名。

包装人员计算：仅在项目已包装质量获得审阅、且没有显式两班覆盖时，按各班日质量的50%及每人每班192kg计算，逐班向上取整；每班各自配置个人柜，合计柜数=N1+N2，同时更衣人数=max(N1,N2)，包装台数=ceil(max(N1,N2)/3)。如果显式人数和质量同时提供且已证实产能不足，返回`INPUT_CONFLICT`，绝不声称容量满足。

办公室人数只有在项目规模明确选择SMALL、MEDIUM、LARGE后，才可对应12、20、30。覆膜工艺为`PACKAGING_BOX_FILM_SEALING`，设计比率为1.0；设备选型、能力、安装/进出料/维修净距、运行小时必须另行确认，不从包装班制直接继承。

## 与R11 R1功能校核的接口

新模块：`layout/application/functional_project_input_binding.py`。

`bind_project_functional_inputs(review, owner_source, reviewed_project=...)`仅准备有来源的项目事实、缺失和冲突，不生成布局或工程合格证。

`project_candidate_room_inputs(review, binding)`将已绑定字段按房间Scope转换为R11已有`BasisValue`，调用原`evaluate_functional_room`只读评估。每条记录重新检查原工程状态与P1面积完全一致；无柜型/净尺寸/设备实物见证时结果仍为`INPUT_REQUIRED`。当前封存20t默认27条均不可能变为`CONDITIONAL_FIT`。

未新增P1硬规则、CP-SAT约束、项目面积上限或长宽比限制，也没有触碰历史Owner Store、Claim、R9/R10源文件、原SVG和九项/十二项比较器。

## 使用及报告

以仓库Python3.12锁定环境执行：

```sh
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_project_input_binding.py \
  --output ../artifacts/r11-functional-project-input-binding-r2
```

CLI只读取仓库已封存R11 `review-data.json`及Owner V2业务文件，依据原`source-manifest.json`校验R11字节身份。输出必须是不存在的新目录，包含：

- `project-binding.json`：真实已审输入目前缺失；规则、状态与计算来源；
- `room-input-projection.json`：9份×3种房间的已绑定字段和`INPUT_REQUIRED`；
- `project-input-request.json`：待填资料清单，状态`UNREVIEWED_PROPOSAL_NOT_APPROVED`，不接受其自批；
- `readiness-report.md`和`index.html`：可浏览的27条房间输入缺口。

若后续取得实际项目资料，先经现有工程审批流程完成来源/型号/适用范围审核，再由可信应用构造`ReviewedProjectDatum`；**不得把本离线请求JSON直接当作审阅完成证据**。新项目事实可减少输入缺口，但功能可用性仍要经过R11真实设备布置见证及独立专业审批。

## 保持冻结的边界

`NATIVE_SOLVES=0`；`MAIN=false`；`NEW_GRANT=false`；`NEW_CLAIM=false`；`FULL_CI=NOT_REQUESTED`；`READY/MERGE/DEPLOY=false`。允许独立Draft PR、针对性测试、自动快速CI。用户尚未确认的项目数据不允许填默认真值。

## 本次交付与本地验证

按所提供补丁先通过 `git apply --check` 后应用。包 SHA256：
`69720fb716ccb06ed44db30985ab95b017ea3ebc90b5163586b3f9a7a2f1ba2a`。
补丁之后只补齐仓库要求：字段单位表改为不可变映射、三个新增 Python 文件的锁定 Ruff 格式、
报告从已落盘 JSON 回读，以及只读生成器和拒绝覆盖输出的回归测试。

Python 3.12.13、`uv sync --locked`：R2 21 PASS、原 R11 85 PASS、架构 771 PASS / 16 原有 skip，
CI 契约 65 PASS；Ruff、Format（1053 文件）、Mypy（468 文件，含本轮生成器）通过。
测试及报告生成均禁止两种 Native Solve API，实际调用为零。

可浏览报告及 JSON：[`r11-functional-project-input-binding-r2/`](../previews/v2.2.2/r11-functional-project-input-binding-r2/)。
27 条房间记录仍全部为 `INPUT_REQUIRED`；9 份记录 / 8 组物理矩形、原工程状态和 P1 面积状态不变。
项目已审事实为空，未绑定 20t 已包装产量、53 人 / 106 柜、工厂规模、柜型或覆膜设备。
`validation-summary.json` 与 `source-manifest.json` 提供本地检查和来源摘要；快速 CI 状态在 PR 中另行核验。
