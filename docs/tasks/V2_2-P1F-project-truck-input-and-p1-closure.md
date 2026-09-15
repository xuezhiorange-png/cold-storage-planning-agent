# V2.2 P1F — 项目货车输入与 P1 收口

## 当前独立 Owner 决策

```ini
TASK_ID=V2_2_P1F_PROJECT_TRUCK_INPUT_AND_P1_CLOSURE_R1
BASE_MAIN_SHA=4244379953028899958ce1579d488288a49c5b82
P1F_AUTHORIZED=true
TRUCK_ENGINEERING_VALUES_SCOPE=PROJECT_LEVEL_INPUT
TRUCK_ENGINEERING_VALUES_ARE_VERSION_CONSTANTS=false
TRUCK_DEFAULT_PROFILE_ALLOWED=false
TRUCK_DEFAULT_DIMENSIONS_ALLOWED=false
DIMENSION_AUTHORITY_COMPLETE=true
PERSONNEL_ACCESS_AUTHORITY_COMPLETE=true
MATERIAL_ACCESS_AUTHORITY_COMPLETE=true
TRUCK_ACCESS_CONTRACT_COMPLETE=true
TRUCK_PROJECT_INPUT_CONTRACT_COMPLETE=true
TRUCK_VERSION_LEVEL_ENGINEERING_VALUES_REQUIRED=false
P1_COMPLETE=true
P1_CLOSURE_BLOCKERS=NONE
P2_READY_FOR_SEPARATE_AUTHORIZATION=true
P2_AUTHORIZED=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P1 完成只表示版本的 authority、dimension/access 合同和输入职责已完整，
不代表项目有货车参数、布局成功或任何路线已验证。本 PR 是 Draft 待独立评审。

## 已合并阶段的不可变证据

下表来自当前基线 first-parent merge 历史，每个 target 均为基线祖先。

| 阶段 | 状态 | PR | Merge SHA |
|---|---|---:|---|
| P1A | MERGED | 271 | ae9794d0454fa64ba7db6a94d9a3faeba5df00bd |
| P1B | MERGED | 272 | 09d9973d1c0fb0ea1ead09601d252c22448d213a |
| P1C0 | MERGED | 273 | 7785e877461a2c82980ed4e318bd04eabc0287df |
| P1C | MERGED | 274 | 4f8c3a0c3b8e866695a917990588caffdd60defc |
| P1D1 | MERGED | 275 | a848c2a3b44c6625db7a2546596f4bb3ceb3d7d3 |
| P1D3 | MERGED | 276 | 3910b4fbb4dde1952c1e05d2f7720e87119d3b57 |
| P1E | MERGED | 277 | 4244379953028899958ce1579d488288a49c5b82 |

```ini
P1A_STATUS=MERGED
P1B_STATUS=MERGED
P1C0_STATUS=MERGED
P1C_STATUS=MERGED
P1D1_STATUS=MERGED
P1D3_STATUS=MERGED
P1E_STATUS=MERGED
```

## 项目输入合同与组合

新增 [TruckProjectAccessInputV1](V2_2-truck-project-access-input-v1.schema.json)，
identity `truck-project-access-input@1.0.0`，schema_version `1.0.0`。
新增 [SiteLayoutProjectInputV1](V2_2-site-layout-project-input-v1.schema.json)：
`site_constraints: SiteLayoutInputV1` + `truck_access: TruckProjectAccessInputV1`。
旧 `V2_2-site-layout-input-v1.schema.json` 完全不修改；新 schema 使用引用组合，
不扩展六工具输入或注册新 API/MCP。

每份 truck_access 明确 `project_id`、`source_authority=PROJECT_INPUT`。
车宽 `vehicle_width_m`、车长 `vehicle_length_m` 必填，无默认；采用 JSON number、
positive、finite、non-bool、精确 0.001m grid，不接受隐式字符串数值、不舍入、不使用 epsilon。
沿用既有 Decimal 精度/资源上限，独立于调用方 Decimal context。

### 三个未定义求解几何的资料槽

当前 P1E 只列出了 turning_envelope、straight_approach、loading_operation_clearance 名称，
没有冻结这三项的求解几何表达，也未定义净空测量方向或单一标量的含义。
因此本轮保留三个原名，不私自把它们变成固定半径或任一方向上的 `_m` 标量。
每项使用版本化项目资料引用结构，必填：

- schema_version=1.0.0
- source_authority=PROJECT_INPUT
- project_id，与外层一致
- reference，项目提供的资料标识，非空
- content_sha256，资料版本摘要，严格 sha256:64 lowercase hex
- provided_by，资料提供方，非空

名称映射是一对一原名，不存在第二份面积、车辆或通行 authority。
这些槽要求项目明确提供可追溯资料，不从历史项目、注册表、Agent、网络或默认车型补值。
本验证器不读取资料，不核验摘要与文件内容，也不认证提供方，因此
`evidence_contents_verified=false`、`requires_review=true` 恒定。
项目声明与版本常量严格分离；引用完整不代表资料内容已可用于求解。

P2A 需单独冻结三类资料如何绑定 machine geometry，尤其 turning-envelope
不得替换成车辆运动学或默认半径：
`P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true`。
这属于未来求解前合同，不重新阻止 P1 的 source-of-authority 收口。

## 当前 handoff 与历史兼容

新增 `build_p1_project_handoff(zone_plan, truck_input=None)`，identity
`p1-project-access-handoff@1.0.0`，schema_version=1.0.0。
truck_input 是组合合同的 truck_access 成员；site_constraints 的几何校验留给未来 P2。

完整嵌入 P1E 历史 handoff 和 canonical hash，不改变旧 `P1_COMPLETE=false` 输出或文档。
新的顶层 authority_status 才表示 P1F 当前版本状态；同时独立给出 project_status。
维度完成状态依然来自实际 canonical dimension result，不把缺维度输入伪装成完成。
P1E 的 `outdoor-truck-owner-input@1.0.0` 原样保留；新 truck_input_binding 显式绑定
该 access requirement 到 PROJECT_INPUT 合同。保持户外限定、不许进建筑，
truck_entrance → shipping_channel.LONG_EDGE_LOADING_FACE。

9 DIMENSIONED / 3 FLEXIBLE_AUTHORIZED、包材 17.3×14.5、7 MUST / 5 SHOULD、
12 access requirements、人员1.5/2.0、物料2.4/2.5、冷间2.4、包材5.0直通和人车政策均不变。

## 完整性不是通行通过

| 项目输入状态 | truck input complete | P1 complete（当前完整维度） | final layout pass allowed |
|---|---|---|---|
| 缺参数或必需来源字段 | false / PROJECT_INPUT_REQUIRED | true | false |
| 非法数值、未知字段、跨项目来源 | false / INVALID_PROJECT_TRUCK_INPUT | true | false |
| 参数与资料声明齐全 | true / COMPLETE | true | false |

所有分支 `project_layout_ready=false`、`project_layout_validated=false`、
`truck_route_validated=false`，不能据 COMPLETE 声称已可转弯、装卸或形成有效场地布局。
调用方的 Mapping 每次重新验证，不信任 self-reported complete 或自造对象。
同源 canonical JSON/hash 一致；项目值/资料摘要改变会改变组合结果 hash。

## 非目标与验证

不实现 placement、路径、转弯、swept path、A*、通道/门洞坐标、flexible定尺、
建筑外框、MCP Tool7、前端、DB、SVG/PDF/DXF、发布或部署。
局部 input/profile/closure 测试及旧 P1A/B/C0/C/D1/D3/E 回归、完整 architecture、
SQLite、PostgreSQL CI、Ruff/format/mypy 必须通过；最终数值与 exact-head CI 记录在 PR。
历史 scope 使用引入文件的 immutable target / precommit candidate，不依赖 moving origin/main。
停止在 Draft review；P2 必须另行授权。
