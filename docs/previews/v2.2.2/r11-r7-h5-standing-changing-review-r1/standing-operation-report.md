# H5 无坐凳站立更衣 R11 R7

## 结论与输入边界

Owner已确认本项目BENCH_COUNT=0、CHANGING_POSTURE=STANDING。通过原项目Scope、封存目录内容身份及本任务已审来源字节绑定为ReviewedProjectDatum，不接受普通JSON审批标签。不是新的Grant/Claim机制。
两班各53名设计使用者、22列110格、H5 P01/P02同一26331×3250mm矩形及两处1500mm Portal不变。模拟先完成全53人进入，随后每人走完本人柜位、取放衣物、站立更衣、原南门离室。未完成者不会被提前移除。
实际功能持续INPUT_REQUIRED。无坐凳的事实不批准任何具体更衣位置、人体动作尺度、柜型、通道或卫生工艺。R5/R6原报告及代码保留，旧必须坐凳流程不再用于R7。

## 同条件方案结果

|方案|完成各班人数|完整条件分钟 / 班|人员总行程m / 班|首个阻塞|
|---|---|---|---|---|
|A 分散站立 · 4人 · 420×700活动包络|[53, 53] / 53|[103.4, 90.09]|[2732.533, 2253.413]|[None, None]|
|B 柜前站立 · 4人 · 420×700活动包络|[0, 0] / 53|[None, None]|[578.823, 560.743]|['PARALLEL_STANDING_CHANGE', 'PARALLEL_STANDING_CHANGE']|
|C 柜前站立 · 1人 · 420×700活动包络|[53, 53] / 53|[156.7, 143.39]|[2143.063, 1663.943]|[None, None]|
|D 分散站立 · 2人 · 420×700活动包络|[53, 53] / 53|[127.24, 113.93]|[2732.533, 2253.413]|[None, None]|
|E 分散站立 · 6人 · 420×700活动包络|[53, 53] / 53|[94.24, 80.93]|[2732.533, 2253.413]|[None, None]|
|F 分散站立 · 4人 · 600×900活动包络|[0, 0] / 53|[None, None]|[640.243, 604.083]|['PARALLEL_STANDING_CHANGE', 'PARALLEL_STANDING_CHANGE']|
|G 450×650人体 · 100间隙|[0, 0] / 53|[None, None]|[0.0, 0.0]|['STATIC_TEMPLATE', 'STATIC_TEMPLATE']|
|H 柜前静态身体边界 · 非更衣可用性证明|[53, 53] / 53|[87.03, 73.72]|[2143.063, 1663.943]|[None, None]|

## 身体活动与并发的真正边界

A条件模型：运输身体400×600mm、等候间隔20mm、站立更衣活动包络420×700mm、柜前4人。两班分别完成53人、15批及14个批次边界；无座位分配、无坐下起身或坐姿动作。分散活动位置来自本人等候位，沿通道分布，不再要求每人往返唯一800×900mm操作区。活动包络向净通道外侧展开，同时校核所有其他在室者及柜体，不移除等候人员。
B柜前4人并行在420×700mm活动范围下发生邻列人员包络重叠；C改为1人可在相同假设内完成，但时间成本较大。H仅用400×600mm身体边界通过不是更衣可用性证明。不得为制造通过而把活动范围等同静态身体。
F分散600×900mm包络碰到仍在室等候者，保留具体人员ID及冲突体积；G450×650mm人体加100mm间隙只排下47个本位，整班拒绝，不把设计人数降低为47。失败仅针对这些模板，不证明所有站立布置均不可行。
柜门仍使用原三维扫掠与通道投影校核。取放衣物阶段并行开门，更衣和移动阶段均明确假设柜门关闭；真实房门开向、五层格口取物能力、穿脱/弯腰/转身动作及衣物体积仍待审。原Portal内侧连接保留；外部Access只作封存参考，本轮未重验外部人流能力。

## 时间与路径

示例时间：600mm/s步行、20s取放衣物并关门、90s站立更衣。source_type=demo、validity_status=unverified、requires_review=true。按批次同步操作计时：每个并发组20s及90s各计一次；进室、柜前换位、到分散位置和离室均按实际通行中心线及连续身体扫掠逐人计时。并发只覆盖已证明互不冲突的静止操作阶段，不假设通道并行通行。
完整时长=全部成功移动路径长度/步速 + 各批取放衣物时长 + 各批站立更衣时长。每个人都保留相同组的实际开始/结束时间，未将并发人数除进步行耗时。失败后时长为空，只保留已执行前缀。没有时间输入也返回空时长，不宣称满足班次窗口。
R6和R7功能程序已因Owner取消座凳而不同，条件时间不能作为同一程序的真实提速率。R7仍采用单人移动和同步批次，不能视为最优排队或现场实测。柜前并发增加并未减少同一路径的行走总距离。

## 真实缺失输入

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
- standing_mode_and_parallel_protocol
- human_transport_and_dressing_activity_envelopes
- reviewed_action_times_and_allowed_shift_window

## 可复核文件

index.html可本地打开：切换方案、两班与全部动作，显示实时人员、柜门、活动范围、路径和失败位置。每个方案两张SVG来自实际条件计算，原始全部状态/路径/并发组/时间见standing-operation-results.json.gz。comparison.json记录8方案指标；project-binding.json保留Owner来源和Scope。
无Native、MAIN、Grant/Claim、正式完整CI。P1、Stage B、九/十二指标、生产默认与历史记录不变。实际功能仍为INPUT_REQUIRED。
