# P1未来接入边界（仅设计，不实施）

## 三种状态必须分开

1. 本次Owner业务确认：办公室12/20/30、包装生产率/班制、更衣柜位与包装封膜规则。
2. 项目实际输入：明确工厂规模、各班包装产品质量及其来源、实际封膜比例、具体设备与空间资料。
3. 正式工程Authority及验收：当前P1面积、尺寸、工艺、Site/Access和生产求解器合同。

第1项不自动提供第2项，不自动修改第3项，也不构成规范符合性或空间功能验收。
所有Owner确认项见主记录的FIELD_NAME、VALUE、UNIT、SOURCE、CONFIRMATION_DATE、
APPLICABILITY及CONTRACT_VERSION。其他合同通过字段名称引用它，不自行创造默认值。

## 历史边界与实际源码

基线`f1b284f94f153153c8b67d5eb963bc7378056aaa`：

- `backend/src/cold_storage/modules/calculations/domain/zone_planning.py:736`附近
  `_sorting_packaging_zone()`当前使用原果日进厂量和历史每人日能力计算人员/面积。
  `:769`的`_packing_person_daily_capacity_kg()`消费历史效率、单件重与工作小时。
  本轮不调用该函数重算、不改变其当前语义。
- `docs/tasks/V2_1_2-patch-release-closure-readiness.md:48`冻结历史336kg/人·日，
  同文件PACKING_HOURS=14。封存业务输入仍含336，原件不替换为192或384。
- `backend/src/cold_storage/modules/layout/domain/dimension_handoff.py:34`
  保留原面积和FLEXIBLE_RECTANGLE；功能min/max/比例字段仍为空。
- `backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py:176`
  对未支持的非空柔性尺度规则仍报`UNMODELED_FLEXIBLE_DIMENSION_RULE`。
- `docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md:101-120`
  已有分选包装→二级预冷→覆膜→成品顺序保持。本次不修改P0可选角色定义或MUST。

上述文件字节SHA记录在historical-integrity.json；本任务只新增本目录文件。

## 未来显式版本消费（需要另行授权）

建议由可信业务输入入口选择`OwnerFactoryFunctionalInputsV1`，记录Owner来源、版本、
项目引用与实际输入。名称与版本是本次文档合同，不是已经注册、可调用的公共Schema。

包装：先验证包装产品质量口径/来源，再读取两个显式班次质量；若只有原果量，
须在上游提供有来源的出成率/质量平衡。不得由下游默认为100%或复用旧进厂量。
若同时提供日包装量，必须与两班总和一致；不能用日量推断未提供的班次分配。
分别计算ceil(kg/192)。新规则与旧336规则应有显式选择及迁移报告，而不是静默覆盖。
384仅可描述两名不同班员工各192的合计，不是每名员工日能力或新柜位除数。

办公室：先显式选择工厂规模，才映射设计容纳人数。不得根据每日进厂量或60m²推断规模/人数。
规模分类阈值缺失时保持OWNER_INPUT_REQUIRED，不自行发布分级表。

更衣：人数仅为包装岗位，两个独立员工集合各一柜；内部隔板不倍增独立柜位。
同时更衣按较大班整个班次，无班内分批假设。柜体、门扇、操作和通道仍需真实资料。
不预设男女功能分区仅是Owner业务要求；必须专业复核卫生/隐私/适用规范，不能免除要求。

封膜：保持独立coating_room身份与工艺序列，明确为包装箱封膜，不再用果品蜡液机或托盘机替代。
设计质量按所有进入该房间包装产品的100%计；实际比例不抵减设计能力。
有效设备运行小时、产能单位/产品基准、设备数量均需另行确认，不沿用包装设施16小时。
非封膜产品在同房间不经设备穿行；其路径与正常、检修、物料及人员Envelope必须做冲突校核。
未选设备时，设备数量、裸机面积和总功能面积必须保持缺失，不按100%比例凭空推导。

## 面积、空间与Fail-closed

本轮继续Office60、Changing40、Coating80m²；不能因为人数算完就宣称足够。
后续P1功能面积计算还须取得净空间参考、家具/设备尺寸、状态Envelope、门墙柱扣除、
操作及卫生消防等条件，获得独立审批后才能形成新面积/尺寸Authority。
未来新增Hard及任何可行域变化必须版本化、披露并独立回归，不得直接编辑Hash凑绑定。
无来源、缺班次或不支持的尺度规则应明确缺失/拒绝，不静默忽略。

本轮离线函数只校验引用存在，不验证来源文件真实性，不创建可信服务器Placement、P1绑定或Owner Grant。
不增加通道默认净距、长宽比、柜体型号或设备效率损耗系数。

## 后续实施的必要验证（本轮不执行）

新旧版本显式隔离；原336及历史P1快照重放不变；两班分开向上取整；原果转换缺失拒绝；
人数/柜位/同时人数三个概念分离；封膜100%设计和实际比例分离；16小时不得自动流入设备运行；
来源Hash及项目身份绑定；未选设备和未知尺度Fail-closed；面积/尺寸变化影响审查。
未来若改变P1面积或求解约束，旧布局验证不能自动作为新Authority下的验收证据。

本轮不修改D04恢复轮次、资源预算、P3历史262 UNKNOWN，不产生求解配额，不启动生产实现。
