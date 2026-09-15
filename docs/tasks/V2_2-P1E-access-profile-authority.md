# V2.2 P1E — 二维通行规则与逐连接绑定

## 独立授权与交付边界

```ini
TASK_ID=V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1
BASE_MAIN_SHA=3910b4fbb4dde1952c1e05d2f7720e87119d3b57
PREVIOUS_PR=276
PREVIOUS_STATUS=MERGED
P1E_AUTHORIZED=true
HANDOFF_IDENTITY=p1-dimension-access-handoff@1.0.0
HANDOFF_SCHEMA_VERSION=1.0.0
DIMENSION_AUTHORITY_COMPLETE=true
DIMENSIONED_ZONE_COUNT=9
FLEXIBLE_AUTHORIZED_ZONE_COUNT=3
DIMENSION_BLOCKED_ZONE_COUNT=0
PERSONNEL_ACCESS_AUTHORITY_COMPLETE=true
MATERIAL_ACCESS_AUTHORITY_COMPLETE=true
TRUCK_ACCESS_CONTRACT_COMPLETE=true
TRUCK_ACCESS_ENGINEERING_VALUES_COMPLETE=false
P1_COMPLETE=false
P1_CLOSURE_REQUIRES_CONTRACT_DECISION=true
P2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Source authority 是 `Charles:V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1`。
本次只新增 domain profiles/predicates 和 application handoff；原 dimensioning、
P1D3 handoff、zone planner、MCP、前端、数据库均不修改。没有路径、通道、门洞坐标、
货车转弯求解或图纸输出。

## 已批准的二维净宽

| Profile identity | 类型/运输方式 | 门洞净宽 m | 通道净宽 m | 路线规则 |
|---|---|---:|---:|---|
| personnel-clear-envelope@1.0.0 | PERSONNEL / PEDESTRIAN | 1.5 | 2.0 | 未冻结转弯规则 |
| manual-pallet-jack-clear-envelope@1.0.0 | MATERIAL_LOGISTICS / MANUAL_PALLET_JACK | 2.4 | 2.5 | 未冻结转弯规则 |
| cold-room-material-portal@1.0.0 | MATERIAL_LOGISTICS / MANUAL_PALLET_JACK | 2.4 | 继承物料 2.5 | 只覆盖冷间门洞净宽 |
| packaging-sorting-straight-access@1.0.0 | MATERIAL_LOGISTICS / MANUAL_PALLET_JACK | 2.4 | 5.0 | STRAIGHT_ONLY |

`PlanarAccessProfileV1` 是独立版本化二维 profile 家族，不改写历史
`dimensioning.AccessProfileV1`。`AccessRequirementV1` 逐连接绑定版本 identity。
生产校验入口只接收服务器生成的 requirement identity 和观察值；不接受调用方
自造 profile 作为工程 authority。缺 profile 返回 `ACCESS_PROFILE_REQUIRED`。

这些净宽是本项目 Owner authority，不是通用叉车规范。运输方式是手动托盘搬运车，
不得当成叉车包络。门高不参与二维校验；不增加门前净空、叉车转弯半径等未批准参数。
`NOT_FROZEN` 不代表任意转弯已通过；这里只检查明确授权的谓词。

## 逐连接绑定

| From | To | 类型 | Profile |
|---|---|---|---|
| main_entrance | changing_room | PEOPLE | personnel |
| changing_room | sorting_packaging_room | PEOPLE | personnel |
| raw_fruit_buffer | primary_precooling_room | MAIN_PROCESS | material |
| primary_precooling_room | sorting_packaging_room | MAIN_PROCESS | material |
| sorting_packaging_room | secondary_precooling_room | MAIN_PROCESS | material |
| secondary_precooling_room | coating_room | MAIN_PROCESS | material |
| coating_room | finished_goods_room | MAIN_PROCESS | material |
| finished_goods_room | shipping_channel | MAIN_PROCESS | material |
| sorting_packaging_room | secondary_fruit_buffer | SIDE_FLOW | material |
| sorting_packaging_room | frozen_fruit_room | SIDE_FLOW | material |
| packaging_material_storage | sorting_packaging_room | PACKAGING | packaging |
| truck_entrance | shipping_channel | TRUCK | outdoor-truck-owner-input@1.0.0 |

表中 MAIN_PROCESS / SIDE_FLOW 为说明分组，代码保留原 graph 的 flow_kind，不另造 flow。
原 11 条 flow 每条恰好生成一个 requirement，另附一个户外 truck access requirement；
不向 process graph 添加或复制 flow。主链 6 段、侧物流 2 段、人员 2 段、包材 1 段。
前 11 段均要求门洞，允许直接或通道连接；主链仍独立受原 MUST 邻接约束，
通道选项不能豁免共享正长度边要求。次果/冻果仍只是 SHOULD 邻接，不升级为 MUST。
`office ↔ shipping_channel` 不隐含人员门：`OFFICE_SHIPPING_PERSONNEL_PORTAL_REQUIRED=false`。

冷间端点复用现有 `REFRIGERATED_ZONE_REGISTRY`，为物料连接附加冷间门 profile。
涵盖 primary/secondary precool、finished goods、secondary fruit、frozen fruit，
也覆盖 registry 中其他适用冷区；不重新定义温区。门洞净宽最低 2.4m。

## 包材方向、直连与通道

保持 P1D3 原有 edge-oriented relationship 原样：包材 LONG_EDGE 面向分选包装
SHORT_EDGE_EXIT_SIDE。两种连接都允许，不增加普通 MUST adjacency，不重复 PACKAGING flow。
直接连接要求方向对齐及 2.4m 门洞，无独立通道时不强加 5m 通道。
有通道时净宽至少 5.0m，必须直通，90° 或多次转弯均不允许。
不得把方向对齐退化为“最终可达”；未来 P2 必须实际核验中心线及净包络。

## 观察值谓词不等于布局已通过

`evaluate_access_observation(requirement_identity, observation)` 只验证提交的
DIRECT_SHARED_EDGE / CORRIDOR_MEDIATED 拓扑、净宽比较、方向确认和直通元数据。
`portal_clear_width_m` 表示该连接所有适用门洞中的最小净宽；
`corridor_clear_width_m` 表示所有通道段中的最小净宽，不能挑较宽门/段代替。
观察值必须来自后续几何验证，不是可由 LLM 填写的工程结论。
缺观察值 BLOCKED，非法/nonfinite/bool 数值 FAIL，净宽使用 Decimal 精确比较、无 epsilon。
包材通道要求 `route_shape=STRAIGHT`、整数 `turn_count=0`、`edge_alignment_verified=true`。

输出恒定 `full_access_validated=false`、`requires_review=true`，scope 为
`SUPPLIED_ACCESS_OBSERVATION_PREDICATES_ONLY`。PASS 仅表示这些观察谓词满足，
不证明门洞存在、实际共享边/连接可达、位置正确、净空连续或交叉必要性。
主链 MUST adjacency 仍须单独验证。P2 未授权，不生成/校验实际路径。

## 人员与货车

```ini
PERSONNEL_TRUCK_SEPARATION=PREFERRED
PERSONNEL_TRUCK_SHARED_ROUTE_ALLOWED=false
PERSONNEL_TRUCK_CROSSING_ALLOWED_IF_NECESSARY=true
PERSONNEL_TRUCK_CROSSING_REQUIRES_REVIEW=true
```

共用同一路线直接 FAIL。必要交叉返回 PASS_WITH_REVIEW 和
`PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW`，不自动判整个候选解不合法。
交叉必要性是需复核的输入证据，不是本谓词对地块的求解结论。
不新增安全距离或交叉口尺寸，也不扩展成人员/叉车政策。

## 货车未完成项与 P1 closure

`TruckAccessContractV1` / `outdoor-truck-owner-input@1.0.0` 只冻结字段要求：

- vehicle_width_m
- vehicle_length_m
- turning_envelope
- straight_approach
- loading_operation_clearance

五者均为 null / OWNER_INPUT_REQUIRED，不是 0，也不是不适用。不接受调用方
自报数值覆盖未批准的 Owner authority。户外限定，进建筑 FAIL；其余观察仍 BLOCKED。
truck_entrance 必须连到 shipping LONG_EDGE_LOADING_FACE，保持既有月台、坑宽及净距。
这里的 truck 连接不是室内物料门，因此不套 2.4m 门洞或 2.5m 室内走道。

人员和物料 authority 已齐全，货车合同齐全但工程值未齐全，所以 P1_COMPLETE=false。
还需 Charles 裁决：上述货车参数是否改为未来每项目 SiteLayoutInput 的输入，
以及对应 P1 closure 条件；记录 `P1_CLOSURE_REQUIRES_CONTRACT_DECISION`，本次不改合同。
不会重复询问已经冻结的 1.5 / 2.0 / 2.4 / 2.5 / 5.0m。

## 组合 handoff 与兼容性

新 `p1-dimension-access-handoff@1.0.0` schema 1.0.0 嵌入旧 dimension_handoff 全量
canonical payload 和 hash；旧 schema、不完整 access 的历史标记原样保留。
新顶层 authority_status 表示当前 P1E 状态，不把旧嵌套状态冒充当前完整 access 结论。
同时绑定 access profiles、12 requirements、空间关系和人员/货车政策。
canonical JSON/hash 采用现有确定性序列化；同源重放一致，篡改 profile/内容不能保持旧 hash。
9 concrete + 3 flexible（包材 17.3×14.5）、7 MUST / 5 SHOULD 不变。

## 验证与停止门

本地执行 P1E focused、全部 P1 regression、architecture、SQLite full、Ruff/format/mypy。
PostgreSQL 由 exact-head GitHub backend lane 核验；PR 记录最终测试数与 CI run。
本次 production backend 新增文件应触发 BACKEND CI，不绕过 path-aware classifier。
历史 scope guard 使用 introducing immutable commit / precommit candidate，不使用 moving origin/main。
完成后停在 Draft review，不 Ready/Merge/P2/tag/release/deploy。
