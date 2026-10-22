# Stage B — Truck / P2D 输入准入预检 R1

TASK=V2_2_2_STAGE_B_TRUCK_P2D_INPUT_ADMISSION_PREFLIGHT_R1

## 实际结论

本轮离线回读 **8 套原始 candidate.json**，逐一核对 Git 封存目录中的原件 SHA256、投影子树、原应用 canonical hash、实际几何 identity 和历史 SVG SHA256。8 套均保留 12 区、7 MUST、11 项原生非 Truck Access 历史通过记录；这是来源与结果回读，不是重新运行 Access。

8 套均为 `BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED`，`source_truck_maneuver_binding_hash=null`，`truck_search_provenance.visited_nodes=0`，`p2_complete=false`。**它们未执行车辆搜索，不能据此判断车辆不可通行。** `PROJECT_TRUCK_INPUT_ADMISSION=BLOCKED`、`TRUCK_SEARCH_READY_COUNT=0`、`P2D_FULL_PASS_COUNT=0`。

保留既有 8 个物理几何、6 个实质 construction、4 个主要家族事实，不重新计算或改写历史去重记录。construction 不等于 P2D full-pass；Stage B、P3 和版本均未完成。

## 逐套实际装卸面与状态

以下坐标为米，来源于各自应用 JSON。全部选中 `LEFT_LONG_EDGE`，且分别通过原 P2D 装卸长边和所选侧绑定谓词的只读校核；不代表项目装卸面批准或 Truck 可行。

| 候选 | 装卸面起点 → 终点 | Zone/MUST/非Truck | Truck节点 | P2D |
|---|---|---|---:|---|
| multi-solution-validation-01/candidate-01 | (32.4,33.079) → (32.4,40.772) | 12 / 7 / 11 | 0 | false |
| multi-solution-validation-01/candidate-02 | (32.4,33.078) → (32.4,40.771) | 12 / 7 / 11 | 0 | false |
| guided-fair-validation-02/candidate-01 | (2.817,30.501) → (2.817,38.194) | 12 / 7 / 11 | 0 | false |
| guided-fair-validation-02/candidate-02 | (0,39.384) → (0,47.077) | 12 / 7 / 11 | 0 | false |
| guided-fair-validation-02/candidate-03 | (1.656,38.904) → (1.656,46.597) | 12 / 7 / 11 | 0 | false |
| guided-fair-validation-02/candidate-04 | (1.656,41.037) → (1.656,48.730) | 12 / 7 / 11 | 0 | false |
| guided-fair-validation-02/candidate-05 | (1.656,41.036) → (1.656,48.729) | 12 / 7 / 11 | 0 | false |
| guided-fair-validation-02/candidate-06 | (1.656,41.035) → (1.656,48.728) | 12 / 7 / 11 | 0 | false |

8 套共享同一 Plan、P1 和 typed Site，**但装卸面的精确坐标有 8 组，包含区域/Portal/通道/Footprint/所选装卸面的 Truck 上下文 Hash 也有 8 个**。即使差别只有毫米，也不能跨候选复制 Truck 结果；这不是新增 construction 计数依据。guided candidate-02 的装卸面位于 x=0 场地边界上，这里只登记边界事实，不推断可行或不可行。

逐套完整 Hash、12 项 Access 原字段、真实阻断代码见 [Truck 状态](eight-candidate-truck-status.json)、[批量预检](eight-candidate-preflight.json)。Shipping 房间、人员 Corridor、建筑外轮廓和三块硬障碍见 [场地与装卸面矩阵](truck-site-loading-face-matrix.json)。没有将可建设区域认作已批准车辆道路，也没有用直线距离代替扫掠验证。

## 阻断来源，而不是继续寻找默认车型

P1F 的引用完整性状态确实是 `COMPLETE`。但冻结快照中的项目/提供者为 `fixture-project / fixture-engineer`，车辆宽长为 2.731 / 11.113m，引用摘要为示例 `aaaa…`，模板资料摘要为 `bbbb…`；没有相应真实车辆、实测大门及项目批准资料字节。**这些是回归输入中的值，绝不是本次选型或推荐尺寸。**

[P1F 合同第91行](../../../tasks/V2_2-P1F-project-truck-input-and-p1-closure.md#L91) 明确验证器不读取资料、不核验文件内容、不认证提供方；源码 `project_truck_input.py:49–65` 恒定保留 `evidence_contents_verified=false`。因此 P1 合同完成，不等于 Truck 几何输入就绪。

原始 v3 回归输入还含一个可被 P2B1解析的三类别模板对象。本轮只调用原输入验证器确认其语法/绑定状态，保留为 `REFERENCE_ONLY`；Stage B 实际输出并没有采用它。[原 Stage A/B 工程接线](../../../../backend/src/cold_storage/modules/layout/application/global_composition_solver.py#L751) 在原应用调用的第五参数显式传 `None`；[原 Truck 函数](../../../../backend/src/cold_storage/modules/layout/domain/access_routing.py#L1395) 因缺少 binding 在搜索前直接返回阻断。不是有限路径搜索后失败。

旧 v2.2.1 fixture 的历史全链 PASS 及 Owner 布局规整度 FAIL 记录不改写，也不能转授这 8 套新候选。上述数值的原始输入文件 Hash 为 `d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`。

## 1 mm 入口的合同语义

当前 `typed_site.entrances.truck_entrance` 为 `(0,33.700) → (0,33.701)`，精确长度为 **1 mm / 0.001m**。它来自原 v3 的 site_constraints，由 Site 规范化原样保留；P2D 将其用于机动模板**参考点**入场位置范围。

这证明了上游投影与运行时用途，**不证明 Owner 的物理大门就是 1mm，也不足以断言它原本就是占位符**。目前未找到把该线段解释为现场实测净开口的资料。R13 已明确区分 locator 与 clear opening，两者不能混用。详细来源、局限及修订传播见 [入口语义审计](truck-entrance-semantic-audit.md)。本轮不放大、替换或移动入口。

## 现有合同复用与安全边界

新增 `StageBTruckP2DPreflightV1 / stage-b-truck-p2d-preflight@1.0.0` 是离线 sidecar，不注册 API/MCP，也不是新车辆/审批系统。

- P1F：复用 `validate_project_truck_input`；冻结 canonical 字符串数值仅按原 P2B1 canonical 解码方式恢复 Decimal 后复核，不对任意请求隐式转换。
- P2B1：复用 `validate_truck_maneuver_project_binding`、`require_complete`，校核同项目、车宽长、模板版本及完整性。类别由项目 requirement 决定；P2D 靠台另有 `DOCK_REVERSE` 要求，不能为所有项目新增“三类全必需”。
- P2D：仅调用原 immutable result hash reader、装卸长边和所选侧谓词，**不调用** `route_site_placement`、`route_access_requirement` 或 `validate_truck_maneuver_chain`。
- R13：仅复用无搜索的 `_evidence`、`_vehicle_body`、`_verify_body_envelopes` 等输入谓词。其完整入口会直接搜索，本轮不能调用，也不能假称完成整个 R13 验证。

静态必要条件全部通过最多达到 `INPUT_VALIDATED_NOT_ROUTE_PASS`。合成输入始终 `REFERENCE_ONLY`；资料字节匹配不验证审批签名，调用方的 `verified / APPROVED` 不可提升项目准入。本工具不另造审批规则，现有完整 R13/P2D 验证和专业审批仍待单独授权执行。见 [验证器复用边界](validator-reuse-boundaries.md)。

项目缺口、逐字段状态和补救动作见 [准入矩阵](truck-project-input-gap-matrix.json)、[资料索取清单](project-truck-information-request.md)、[来源索引](truck-evidence-index.json)、[机器合同](truck-p2d-admission-contract.json)。`schema_version=1.0.0` 是软件合同版本，不是车辆图纸修订号；缺失的实际版本/审批不得自动补齐。

## 离线运行与复现

使用仓库既有锁定 Python 环境及 `backend/src`，无需新依赖。原始候选从可信操作端显式指定的项目 artifacts 中读取，固定为两个 MAIN 历史目录内的 2+6 个 candidate.json；不读取 Grant、不重建输入、不复制回放为新增方案。

```sh
PYTHONPATH=backend/src backend/.venv/bin/python3 \
  docs/previews/v2.2.2/stage-b-truck-p2d-preflight-r1/offline_stage_b_truck_preflight.py \
  --artifact-root /path/to/authorized/project/artifacts \
  --output /path/to/new/local/eight-candidate-preflight.json
```

输出文件必须不存在。资料搜索仅限本项目 docs、fixtures 和 artifacts；文件名发现不等于内容/项目适用性审核，不保证覆盖命名不明或 Owner 另存的资料。内部运输协议和图纸不得未经传播许可公开。

`validation.json` 提供实际测试、Node ID、日志 Hash、Ruff/Format/Mypy、确定性结果；`historical-evidence-integrity.json` 保存受保护来源 Hash。本地原始日志另行封存，不上传大型原生日志或私有材料。

本轮真实 Truck 搜索=0，真实整厂求解=0，原生 Solver 调用=0，新增 Grant=false。生产代码、Site 与 P2D Authority、8 套候选/SVG、V2业务合同、预算、D01/D03/D04及历史262 UNKNOWN均不修改。PR保持Draft，不Ready、Merge、Release、Deploy；完成本轮后停止。
