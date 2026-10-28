# R11 R9 H5 实际空间重排与容量验证

TASK_ID=V2_2_2_R11_R9_H5_FUNCTIONAL_SPACE_RELAYOUT_R1
BASE_HEAD=9ab3851591b93c0bb0543ba2a96c16d49cfbc166

三种原H5组织均在450×650mm人体、100mm等候本位间隙、600×900mm柜前活动及1200mm假设通道下，取得两班各53人的完整条件流程。没有减少53人，没有修改原建筑矩形或1500mm Portal，也没有增加柜前并发算法。实际功能仍是 INPUT_REQUIRED。

| 方案 | 本位 / 90°转向本位 | 第1/2班完成 | 第1/2班条件分钟 |
|---|---:|---:|---:|
| A 混合本位 / 西北补位 | 53 / 6 | 53 / 53 | 94.09 / 82.29 |
| B 北墙等候 / 南侧分区 | 53 / 34 | 53 / 53 | 96.73 / 84.31 |
| C 分段柜组 / 北墙等候 | 53 / 34 | 53 / 53 | 96.67 / 81.23 |
| 原R8双排模板 / 47本位 | 47 / 0 | 0 / 0 | 未成立 / 未成立 |
| A完成面30mm / 保留失败 | 47 / 0 | 0 / 0 | 未成立 / 未成立 |

## 空间变化与尺寸链

A：原单侧柜组保留，东段47个常规本位与西北6个转向本位组合；北带身体只改变方向，从450×650变为650×450mm，面积、高度和人员身份都不变。B：34个北墙转向本位加19个东南常规本位；改变整体等候分区。C：两班柜组之间留1200mm分段间隙，仍为22列110格，34个北墙转向本位加19个东南常规本位。不是三张同一模板改名称。有限排布最多生成53位，不把53当作最大容量证明。
沿柜区横向链：完成面20 + 安装20 + 柜深500 + 人距380 + 运输人体深650 + 净通道1200 + 转向等候深450 + 余量10 + 完成面20 = 3250mm。北带可用460mm，转向本位深450mm。三种方案的完整本位、柜体坐标与尺寸链保存于原始JSON、dimension-chains.json及同比例SVG。100mm是等候本位的轴向净间隙，不是未经确认的动态人体舒适距离。
末柜600mm活动宽度以450mm人体中线定位，相对400mm柜列向右外伸125mm；原100mm回转退让会侵入25mm。新布置按包络计算125mm端部退让，保持原1200mm回转净区。原R8代码和47/46人历史结果均不改；该反例在独立回归中仍被原活动/通道校核拒绝。

## 连续转向、柜门和人员完整流程

没有把旋转后的静态矩形直接当成功。转向本位先以650×450mm姿态沿本位接入段移入实际通道，再在同一中心完成90°转向，之后恢复450×650mm运输姿态，调用原通道网络移动。入室顺序反向执行这一过程。整个90°转动用792×792mm保守对角方形连续包络覆盖所有中间角度；必须完整处于原1200mm通道并避开所有实际在室者和柜体。记录每段source/target、people_before、三维扫掠及冲突。该矩形模型仍不证明真实人体转身、弯腰和穿脱的人体工学。
每班全部53人先经东Portal到达各自本位，再按原R8间隔柜列分组完成：到本人柜前→开柜→取衣→关柜→本人柜前站立更衣→再开柜→存放→关柜→连续走至南Portal→离室。两班各14批，每人一次完整服务；剩余等候者始终作为实际碰撞体。原三维门扇、层高、净通道、1500mm Portal、人员碰撞及原柜前活动校核均保留。柜门关闭后才更衣、移动期间柜门关闭、房门不侵入通道仍是未批准工艺/设备假设。P01/P02两份原Access记录分别只读附在结果中，不计为两套独立H5矩形；外部通道未重新求解。

## 失败边界与反事实尺寸

原R8在同样450×650mm及100mm间隙条件下仅47个本位，完整流程拒绝。R9完成面改为30mm的独立敏感性反例中，北带只剩440mm，转向450mm深本位也不成立；保留其实际本位数与拒绝，不靠缩小身体或删除用户通过。默认20mm完成面仅10mm余量，25mm完成面时理论余量为零，实际施工公差、墙面设备及衣物占用可能使方案失效。
如坚持北带常规朝向650mm深本位，仅从同一柜区截面计算，20mm完成面需要建筑深3440mm，比原H5增加190mm；30mm完成面对应3460mm。这是未批准的截面必要条件，不是已证明的完整扩建方案，不能改写历史H5、P1或面积Authority。原H5下已找到条件重排，因此本轮不建议直接以有限模板失败要求扩建。其他未检查组织的可行性未知。

## 时间仅作必要条件对照

与R8相同的示例步速600mm/s、开/关各3s、取/放各20s、更衣90s；新增每次90°转向3s作为独立未批准参数。步行和转向串行，柜前动作按原分组并行，两班分别模拟。时间包含实际路线，不拿失败前缀作完整时长。未优化任何时间参数，不证明现场效率、舒适度、工间窗口或最大吞吐。

## 工程评审建议与真实输入

优先评审A：只补充6个西北转向本位，较少人员需要转向，原柜组保持连贯。B/C提供分区与柜组分段的对照，不因某班时间更短就宣布工程最优。必须现场确认北带完成面及安装公差，核实人穿工作服后的真实静态/活动/转向尺度、五层柜实际宽深高与顶层可达性、柜门和房门开向、站位方向可接受性、关柜更衣与两次开柜规程、洁污和清洁维护流程。

- selected_cabinet_model_and_column_grouping
- cabinet_column_and_compartment_clear_dimensions
- shelves_plinth_structure_and_finished_clear_height
- compartment_door_sweep_and_simultaneous_operation_rules
- cabinet_front_concurrent_users_and_staggered_service_plan
- 53_person_changing_spaces_and_transition_paths
- approved_reach_and_operating_clearance_for_all_five_tiers
- internal_divider_or_two_compartment_hygiene_approval
- finished_room_dimensions_and_internal_aisle_width
- actual_room_door_leaf_motion_and_landing_clearance
- clean_unclean_separation_and_cleaning_maintenance_plan
- both_shift_complete_reviewed_four_state_witnesses
- human_transport_and_dressing_activity_envelopes
- reviewed_action_times_and_allowed_shift_window
- approved_cabinet_front_concurrency_and_waiting_protocol
- approved_two_opening_handling_and_closed_door_changing_sequence

实际功能 INPUT_REQUIRED；未重新验收整厂工程。R9功能模板和报告生成不调用Native；没有20t求解、MAIN、Grant/Claim或正式完整CI。本地验证范围误扩张时执行了既有微型合成Native回归，已中断；见execution-boundary-exception.md，不宣称本任务整体Native次数为零。原P1、Stage B、历史有效状态、九/十二指标与生产默认均不变。
