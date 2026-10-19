# 1 mm Truck入口：四种对象必须区分

| 对象 | 本轮可核验内容 | 不可推导 |
|---|---|---|
| SITE_TRUCK_ENTRANCE_SEGMENT | 原始v3 `site_constraints.truck_entrance` 与冻结 typed Site 同为(0,33.700)→(0,33.701)，精确1mm | 不是实测大门净宽证书 |
| SITE_ENTRY_REFERENCE_POINT | P2D搜索将上述线段用作首段模板 entry_pose 参考点的候选位置域 | 参考点可在此不代表车辆本体/扫掠能过门 |
| MEASURED_GATE_CLEAR_OPENING | 当前实测来源、有效开口、净宽、限高/方向/限制及净空依据缺失 | 不能把1mm放大，也不能断言现场门只有1mm |
| R13_ENTRANCE_CLEAR_OPENING_SEGMENT | 原合同独立于locator，要求开口长度匹配clear_width、至少容纳车宽、位于边界、包含locator，并在搜索后校核实际首包络过门 | 当前typed Site没有这组实测字段，不能静默互换 |

## 来源链

1. 原始 Owner 收录的回归输入 `backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json:39–47` 保留1mm线段；其 provenance 标记 `intended_use=regression-and-calibration`、`not_engineering_authority=true`。该收录证据不是新的大门实测批准。
2. `backend/scripts/run_stage_b_owner_pool.py:43–75` 读取冻结输入并将原site_constraints送入Site验证。此处仅审计源码，没有执行该启动器。
3. Site应用 `application/site_geometry.py:238–242` 只规范化正长度边界线段；`:402` 将该值输出为typed Site入口。[P2A合同](../../../tasks/V2_2-P2A-site-geometry-foundation.md#L112) 的入口门禁是正长度且完整位于边界，不是车辆净开口适配。
4. P2D `domain/access_routing.py:1461–1485` 取参考点搜索位置，并检查变换模板entry_pose在此线段上；这里没有把其长度解释成车道宽度。
5. [R13合同第35–39行](../../../tasks/V2_2_2-R13-parameterized-truck-preview.md#L35) 显式区分 `locator_segment / clear_opening_segment / clear_width_m / measurement_reference / clearance_reference`。源码 `truck_parameter_input.py:214–235` 检查基础开口几何，`:282–319` 对实际选中车辆及扫掠过门作进一步判断。本轮未执行该搜索及搜索后检查。

精确源码行号、合同引用及各文件SHA见 `source-contract-references.json`。来源结论：**已证明是上游原样投影，运行时用作参考点位置域；物理门洞语义待项目资料确认。** 不能仅凭1mm给其补写“临时占位”业务意图。

## 如果将来修订入口，身份如何变化

- 仅改site入口、保持业务Plan和truck_access不变：原Plan及P1 handoff Hash未必变化；`source_project_input_hash` 和 typed Site canonical Hash会变化。这一点有离线敏感性测试，不把所有Hash一概说成必然改变。
- 如果同时改真实车辆输入或项目来源，则P1项目handoff及其Site绑定也可能改变，必须按原构建器重建并核验，不能手填Hash。
- P1A composition、placement 和P2D应用结果绑定Site来源；8套旧候选的 `source_site_geometry_hash` 都是旧值。不能改入口后继续沿用原Site验收PASS，或只更新字段/Hash伪造重新验证。
- 几何原件、旧SVG和历史工程验收记录应继续封存；新Authority的适用性与每候选独立工程复验需另行授权。坐标改变可能影响结构入口关系和车辆可行性，不能由预检推断仍有效。

本轮不修改Site、不扩展门洞、不执行Truck搜索、不创建Grant。
