# R11 R10 功能房间尺寸反推

TASK_ID=V2_2_2_R11_R10_FUNCTIONAL_ROOM_REVERSE_SIZING_R1
BASE_HEAD=6b47d04d5835ef6a6068a15ab33b371ff94baa2c

本次为有限功能预览，不写入P1/Stage B/Authority。R9三套原件、10mm北侧余量、30mm完成面失败和Native越界异常原件均保留。R10新增计算与本地白名单不执行Native；继承快速CI中原有的合成Native测试另行识别，不报告任务级总Native为零。

共检查396个有限组合；184个取得两班各53人的完整条件流程，153个同时达到其假设余量目标。

| 目标 | 长×宽mm | 面积㎡ | 新增㎡ | 最小已定义空间余量mm | 北侧余量mm | 完成各班 |
|---|---:|---:|---:|---:|---:|---:|
| A_MIN_VERIFIED_AREA | 26331×3250 | 85.575750 | 0.000000 | 0 | 10 | [53, 53] |
| B_LARGER_MARGIN | 28000×4350 | 121.800000 | 36.224250 | 150 | 160 | [53, 53] |
| C_MIN_BOUNDARY_CHANGE | 26331×3550 | 93.475050 | 7.899300 | 50 | 60 | [53, 53] |

## 结论与范围

A命中本次范围下边界，保留原H5完整条件见证；其0mm最小额外余量和10mm北带仅作面积对照，不作为舒适/稳健推荐。没有测试更小长宽，不能把85.575750㎡称为项目必要面积或全局最小面积。P01/P02只计一个物理房间。原40㎡P1需求及其来源不变。
B按所声明空间余量族的最不利值择优，面积仅用于同余量时打破平局；C在达到可配置50mm假设评审目标的完整见证中，最小化|Δ长|+|Δ宽|。这些比较不改原九/十二指标，也不属于Stage B正式Pareto。

## 尺寸链与真实局部余量

每候选从实际柜体、人体、本位、通道、门洞和完整移动/门扇记录计算余量，不从总面积推断。分列安装退让、柜组间距、柜前活动到通道/柜体、本位墙距/净距/通道、通道净宽、门洞总宽余量、真实转身扫掠与其他对象的连续距离。完整位置和最不利bounds_mm均在evaluation-grid.jsonl.gz及结构化结果中。
0/50/100/150mm是本轮未批准的设计余量目标。试算模板将目标分别加到安装/柜组间距、柜前站距、柜前到通道、实际通道宽度及本位间隙；每项实际余量重新测量，不能由输入目标自动判PASS。门洞宽度余量是总净宽差；单侧门框余量另列。转向使用原R9的完整对角方形扫掠。不同余量定义不能误读为人体四周统一缓冲或规范值。人体水平/竖向可达性仍沿用旧条件检查，单独显示，未获实际人体工学批准。

## 长度、宽度与模板自由度

固定长度模式覆盖3250、3300、3350、3400、3440、3460、3500、3600mm，并按尺寸链补充必要检查点；联合模式含27000、28000、30000mm。除R9式混合本位、北侧转向/南侧常规外，加入北侧常规/南侧转向模板，避免把旧单一布置当作全局硬约束。3440mm只有特定模板的截面意义；其完整流程与余量另行验收。只有长度变化的方案也实际进入检查，不预设只能加宽。

| 边界调整类别 | 达到假设50mm目标的最少变化已验证方案 | 面积㎡ |
|---|---|---:|
| 仅加宽 | 26331×3550 | 93.475050 |
| 仅加长 | 30000×3250 | 97.500000 |
| 长宽联合 | 27000×3600 | 97.200000 |

## 完成面/安装敏感性与评审建议

选定A/B/C分别在完成面30mm、安装间隙40mm及二者同时变化时重新做完整功能检查。它们仍是未批准敏感性条件。达到原20mm完成面的目标，不意味着完成面变化后还达到相同余量；每一新结果独立记录，不改历史PASS。

额外取得仅加宽方案 26331×3850mm，在完成面30mm、安装间隙40mm的组合假设下仍完成两班各53人，最小已定义空间余量70mm，面积101.374350㎡。可优先将该更稳健对照与C最小改动方案、B大余量方案一起评审；不把它直接批准为实际尺寸。

在默认组合敏感性中，3600mm宽方案仍有两班完整流程，但HOME-23到南Portal通道的实际间距40mm，低于50mm假设目标。它说明只增加横向面积不一定消除纵向本位/门前通道的局部瓶颈。3850mm宽、采用100mm模板加量的对照取得70mm最小实际余量：达到单独的50mm稳健评审目标，但没有达到其100mm模板目标。两类目标不混报。所有尝试均保存在robustness-evidence.jsonl.gz。

## Portal与工程批准

反事实对象与封存H5是不同对象；西/南边界固定，北/东按候选尺寸变化。仅加宽时两处Portal数值坐标不变；加长时东Portal保持y区间、映射到新东边界，原Portal完整来源另存。任何扩展的Site、Footprint及外部Access均NOT_EVALUATED_REVALIDATION_REQUIRED；房门不侵入通道仍是待批假设。不能把内部连续通行通过提升为外部Access或整厂工程批准。
每班全部53人先到实际本位，再完整经过本人柜位开柜、取衣、关柜、更衣、再开柜存放、关柜及南Portal离室。原三维门扇/人员/柜体/通道校核保留，既有R8并发分组仅作提案，每组在R10实际通道上重新验证。没有Native、旧授权、Grant/Claim或生产求解接入。

## 未确认输入与接口

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
- 实际完成面、安装公差及各余量目标。
- 反事实建筑扩展和门洞映射对应的外部Site/工艺/Access批准。

结构化接口：application.room_reverse_sizing_review.preview_request()/preview_room_sizing()；只接受条件参数与有限搜索范围，拒绝审批标签或Owner事实覆盖。当前完整流程适配器为H5两班53人，其他功能房间可复用输入/有限搜索/余量结构，需另加经验证的功能适配器，不宣称已支持全部房型。
index.html可切换全部已计算平面和阶段结果；本地服务支持Python预览接口，浏览器不复制工程公式。完整原始证据、选定见证、敏感性与来源Hash均随报告保存。实际结果始终INPUT_REQUIRED。

## 本地验证与执行边界记录

最终明确白名单回归：1307 passed、16项既有skip，77.78s；其中新增R10测试41项全部通过。Ruff、Format（1108文件）、Mypy（503源码文件）及浏览器JavaScript语法通过。具体文件清单、JUnit、完整输出、子进程启动防护日志见validation/。没有运行整个Stage B或历史Native测试目录。

本轮新计算与本地白名单未执行Native；两个Solve API的故意拒绝测试覆盖父进程与Python子进程。启动防护失效会退出。继承的自动快速CI保持原工作流，包含原有合成Native，不能据此宣称整个任务所有环境Native总数为零。R9越界异常及其原始XML来源Hash未改。

初次R10测试曾错误期待3600mm组合敏感性余量达到50mm；实际为40mm。保留初次失败输出，修正测试期望并新增3850mm/70mm真实对照，没有放松功能验收或改写实际结果。

本地浏览器已核对C默认方案、B具体本位模板选择、柜区放大、尺寸链和失败静态方案的NOT_EVALUATED状态；原始报告及预览接口下载经HTTP回归。图纸为概念功能评审。扩展后外部Site/Footprint/Access、人体工学、实际柜型、门扇及洁污仍待审。自动快速CI结果按新PR精确HEAD另行报告，不等同正式完整CI或工程批准。
