# P1 → CP-SAT 功能尺度消费设计草案（不实施）

状态：`ENGINEERING_PROPOSAL / OWNER_INPUT_REQUIRED / NUMERIC_CALIBRATION_NOT_READY`。
本文件不是新Authority、Schema发布或生产实现授权。

## 1. 当前已证明的链路与直接成因

下列位置对应参考HEAD `78f42b3956d3569e5a887fb578ce5e773275cc5b`；
精确源码SHA和类/守卫行号见[code-audit.json](code-audit.json)。

- `backend/src/cold_storage/modules/layout/domain/dimension_handoff.py:34`：
  `flexible_authority()`只授权Office/Changing/Coating三个角色；保留面积、0/90旋转，
  min/max width/depth和aspect_ratio_bounds均为null。
- `backend/src/cold_storage/modules/layout/application/dimension_handoff.py:30`：
  `build_dimension_handoff()`从后端canonical snapshot重建，不接受调用方自填profile/hash。
- `backend/src/cold_storage/modules/layout/application/layout_authority_binding.py:88`：
  绑定Canonical Plan、P1身份/完整性和可信typed Site，检查历史handoff与Zone Plan Hash。
  将来不能直接改JSON里的min_width并重算Hash来冒充合法Authority。
- `backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py:139`：
  GlobalModel令nominal width/depth从1mm取到场地诱导的有限上界，乘积面积≥原面积下界；
  0/90旋转将nominal尺寸转换成physical世界坐标边长，再共同满足场地、障碍、非重叠和接口。
  因此面积40m²并不阻止短边0.875m，长边可相应增加。
- 同文件`:176`：五类配置非null时抛出`UNMODELED_FLEXIBLE_DIMENSION_RULE`。
  存在字段不等于支持消费；这是一道正确的Fail-closed边界，本轮保留。
- 同文件`:407`：AccessModel继承GlobalModel并调用父初始化；修订将来不能仅覆盖一个分支。
- `backend/src/cold_storage/modules/layout/domain/placement.py:587`附近：
  柔性zone record复核当前面积，并不证明家具、设备、操作或检修空间可用。

直接成因是**当前Authority及消费者未表达功能模块**。这不证明哪一种软引导造成了某个异常解，
也不证明面积合格的所有狭长房间均不可用；本轮不归因于未执行的参数实验。

## 2. 现有参数清单与语义缺口

|字段|现状|未来消费前必须确定|
|---|---|---|
|dimension_mode|三个目标房间FLEXIBLE_RECTANGLE|保留角色范围，不扩展其他九区|
|required_area_m2|Office60 / Changing40 / Coating80|原几何面积下界不变；不可直接当成室内净使用面积|
|min_width_m / min_depth_m|字段存在、当前null；配置时未建模拒绝|局部轴、边长参考、来源及批准；不能猜其当前已有定义|
|max_width_m / max_depth_m|字段存在、当前null；配置时同样拒绝|仅有明确项目来源才成为上界，不为美观添加面积/尺寸上限|
|aspect_ratio_bounds|当前null，消费者拒绝非null|方向相关W/D还是旋转不变L/S须明确定义；当前没有可冻结建议范围|
|rotation_allowed|0/90；模型消费rot布尔值|局部规则与设备/接口一同旋转，不把min_width错套到世界X|

目前nominal width/depth有模型局部方向，physical w/d为旋转后世界方向。
这能解释变量映射，**不能追认尚为空的min_width字段已规定“成品室内净宽”语义**。

## 3. 向后兼容的独立扩展提案

建议另行评审`FunctionalRoomUseRequirementsV1`，而非直接破坏冻结V1 handoff：

```text
identity/version, project_id, zone_role, process_variant
dimension_reference: LOCAL_FINISHED_CLEAR / AXIS / OUTER_GEOMETRIC_ENVELOPE
area_reference, local_axis_definition, allowed_equipment_orientation
staffing: shift_count / simultaneous_users / storage_users / workstation_count
furniture_or_equipment: model, count, assembled_dimensions, chosen_revision
operation_envelopes, maintenance_envelopes, material_flow_envelopes
door_sweeps, wall/column/partition deductions, vertical_clearance
spatial_and_temporal_overlap_policy, hygiene_zoning, exceptions_with_reasons
source_files: actual_bytes_sha256, publisher, section, effective_date
applicability_review, Owner_approval_reference, professional_review_status
server_binding: Plan/P1/Site/source Hash, policy version, derived_module Hash
```

这是概念字段表，不是已实施接口。工程资料必须验证实际文件内容、适用版本与审批来源，
不能靠格式正确的Hash、verified=true或自造Authority Token。不得复制历史执行Grant。
调用方可提供真实业务人数/设备资料，但不得注入最终房间坐标或替代server-owned布局绑定。

## 4. 净空间与几何空间分开

建筑面积、轴线包络、房间几何矩形、装修后净空、家具摆好后的有效通道是五个不同对象。
若边界为轴线/外包络，可在有来源的构造厚度下转换，不能固定减去一段经验墙厚。
柱、卫生隔断、门扇等通常是非矩形占用；不能仅用一个min(short_side)代替完整净空多边形。
转换证据缺失时，几何短边至多用于显式假设下的乐观条件筛查，不能给功能PASS。

设备净高、吊装、管线、排水、卫生和消防/无障碍也不能由2D矩形容纳自动证明。

## 5. 后续Hard与Soft的边界

可考虑Hard：经适用性复核的强制要求、已批准项目设备与其正常/检修/物料Envelope、
经批准的门和净通道/卫生布置以及已正式授权的功能最小尺寸。
仅可考虑Soft：尚无批准强制依据的比例偏好、布局紧凑或推荐模块的优先顺序。
推荐标准/厂商示例不是本项目选型；外国指南不是中国强制条文。
max边长、比例范围和例外不能从这8套问题样本反推。

未来新增Hard会有意缩小原工程可行域，必须在新Authority版本、变更记录与验收中披露；
不能一面加约束，一面宣称旧可行域完全不变。历史候选/Hash和当时PASS范围均保持原样。

## 6. 精确整数与旋转正确性条件（仅设计）

1. 全部单位明示。最小局部长度a m向外取`ceil(1000*a)`mm，最大b向内取`floor(1000*b)`；
   面积A为`ceil(1000000*A)`mm²。不能使用epsilon填补狭缝。
2. 对0°：physical_w=nominal_w、physical_d=nominal_d；90°交换。
   局部最小宽度约束nominal_w；旋转不变最短边另有明确字段，不能混同。
3. 若未来经批准定义比例为L/S，设置L=max(nominal_w,nominal_d)、S=min(...)。
   有理数上界p/q表示为`q*L <= p*S`，下界同理，避免浮点近似。
4. 净空/设备相对坐标与房间一起旋转。每种运行状态分别验证真实几何并集、碰撞和通行，
   不以全包围矩形通过替代实际Envelope通过。
5. 检修停机、临时移开设备或共享通道，仅在审批的时序/隔离条件下使用；
   不能自动将门扇、站立区、通道取max来虚减同时占用空间。
6. 不因设备在几何短边内就认定路线、清洗、检修、Portal或P2D通过。

## 7. Fail-closed与兼容迁移

- 无扩展输入：现有Stage A/Stage B/老P1行为完全不变，不能默注入默认新宽度。
- 扩展输入缺来源、人数、净空参考或关键Envelope：`OWNER_INPUT_REQUIRED`或明确不支持，
  不输出新的功能合格结论。
- 输入非null但消费者尚未实现：继续`UNMODELED_FLEXIBLE_DIMENSION_RULE`，
  不能先吞掉字段让模型静默忽略。
- 合同与消费者均经独立授权实现、测试通过后，才考虑切换到明确版本的新服务端构建流程。
  绑定Plan/P1/typed Site、结构handoff及结果身份，拒绝hash失配、旧来源复用及越权角色。
- 预算与资源计量继续原合同；新校验/建模成本必须计费，不以新模块刷新额度。

## 8. 后续生产实现所需回归计划（本轮不执行实现）

|测试主题|必须证明|
|---|---|
|空/旧输入|Stage A和旧Stage B输出行为不变|
|未支持非null字段|五种限制分别真实触发原Fail-closed，而不是被忽略|
|最小/最大长度与面积|整数mm上下界边界，差1mm，非终止有理数，矛盾上下界明确拒绝|
|0°/90°与禁止旋转|局部/世界、宽深/短边、设备和接口同步正确|
|比例|L/S对旋转不变；零边、非法范围、min>max拒绝|
|功能模块|同面积不同宽深、门扇/柜门、人员峰值、洁污分隔、操作与检修状态分别覆盖|
|来源绑定|实际文件Hash不匹配、未经批准选型、跨项目和旧P1复用均拒绝|
|独立工程验证|尺寸/非重叠/7 MUST/Portal/Access/Footprint/Site仍原权威；不能用功能模块替代|
|资源与结果|各调用累计、Host保护及UNKNOWN语义不变；测试费用不能伪装Owner新配额|

本轮只运行标准库离线计算和既有不求解的P1/文档测试。
不实例化GlobalModel/AccessModel、不调用CP-SAT、不生成房间、不运行MAIN/REPLAY。

## 9. 原合同边界

D01三层责任及262 UNKNOWN不变；D03的0.90产品目标/未校准numeric gate分开，
当前P1A Secondary归PROCESSING_CORE、历史P0归属保留；D04不重置轮次或追认例外。
ADR-047的工程有效/质量有效分层以及ADR-049/050原结构/证明权威均不改变。
本提案不实现Scheduler、Selector、Tool7、MCP或Truck，不冻结任何新的正式阈值。
