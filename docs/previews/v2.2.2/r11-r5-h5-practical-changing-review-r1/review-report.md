# R11 R5 · H5更衣室工程深化

## 结论与实际批准边界

推荐进一步深化A：西段单侧组合柜，东段更衣/等候与座凳，保留真实东入口和南侧分选包装Portal。它是有明确参数的条件空间见证，实际功能仍为 INPUT_REQUIRED，不能成为 CONDITIONAL_FIT 或施工图。

项目事实：成品20000kg/日；设计两班各53人；每班53人同时在室。五层格口基本方案每班11列，共22列110格；双格方案每班22列，共44列220格。设计编号不是花名册。R4原审批来源和R3项目级审阅机制原样复用。

P01/P02共用同一26331×3250mm物理矩形；分别从原档回读其Access。东Portal x26331,y875–2375；南Portal y0,x12415–13915，两处1500mm净宽。外部Access未重新规划，原工程通过状态和历史九/十二指标未变。

## 明示假设

每列宽400、深500、总高1800mm；格净高300、底座100、层板20mm；每2列组合成一实体柜，末列独立，因此22列为12个假设采购单元。完成面四边内缩20mm，柜后安装间隙20mm，单元间20mm。真实厂家、结构、锚固/安装运输净空和装修尺寸尚未确认。

柜门为左铰链外开0–90°，柜框20、门厚15、扫掠半径360mm；各层按真实模型的z高度独立检查。柜前退让380mm，人体/操作占位400×600×1800mm，柜前每批最多4人；并未将53人在室减少为4人。此占位只证明指定包络，不证明人体弯腰、穿脱衣、提取衣物和动作工学。

两张1800×400×450mm座凳，各3个600mm节距座位。坐姿上身从450至1300mm、腿部从凳前缘至600mm占位前缘。两班均有53处独立本位；操作人员离开自己的本位后，该处保持空置供返回。静态快照通常4名柜前、6名座凳、1名独立更衣操作、42名等候人员。东端北侧另留800×900mm的假设更衣操作包络，人员始终计入53人；该包络仅为待审动作空间模型，并非人体工学验证。53人完整更衣动作能力尚未证明。

净通道1200mm；真实房门暂按打开后不侵入室内的条件假设，实际门型/开向未确认。实际柜门闭合后人员才换位，其他未操作格门保持关闭。无平面侵入柜门只是独立敏感性选项，不作为真实柜型结论。

## 参数方案核验

|方案|列/容量|组合柜|柜长mm/占地mm²|净通道mm|静态通过|相邻批次通过|具体失败|
|---|---|---:|---|---:|---|---|---|
|A 单侧分区 · 22列 · 铰链门|22/110|12|8800/4400000|1200|30/30|2/2|{}|
|B 相对双侧 · 22列 · 铰链门|22/110|12|8800/4400000|1200|0/30|0/2|{'FIXED_BODY_INTRUDES_NET_AISLE': 210}|
|C 分段1200 · 22列 · 铰链门|22/110|12|8800/4400000|1200|0/30|0/2|{'ALL_53_DISTINCT_SHIFT_USERS_REQUIRED': 30, '53_DISTINCT_HOME_POSITIONS_NOT_AVAILABLE': 30, 'ACTIVE_OPERATOR_ACTION_BINDING_MISMATCH': 4}|
|D 分段600 · 22列 · 铰链门|22/110|12|8800/4400000|1200|30/30|2/2|{}|
|E 单侧分区 · 44列双格 · 铰链门|44/220|22|17600/8800000|1200|0/60|0/2|{'ALL_53_DISTINCT_SHIFT_USERS_REQUIRED': 60, '53_DISTINCT_HOME_POSITIONS_NOT_AVAILABLE': 60, 'FIXED_BODY_INTRUDES_NET_AISLE': 120, 'ACTIVE_OPERATOR_ACTION_BINDING_MISMATCH': 50, 'STATIONARY_PERSON_INTRUDES_NET_AISLE': 4, 'DOOR_PROJECTION_REDUCES_RESERVED_PASSAGE': 20}|
|F 单侧分区 · 22列 · 无平面侵入门假设|22/110|12|8800/4400000|1200|30/30|2/2|{}|
|G 柜深600敏感性 · 22列|22/110|12|8800/5280000|1200|30/30|2/2|{}|
|H 格高350敏感性 · 22列|22/110|12|8800/4400000|1200|24/30|2/2|{'HYPOTHETICAL_REACH_RANGE_NOT_MET': 20}|

## 真实碰撞与动作证据

门扇校核采用完整90°扇形加保守门厚膨胀，与各物体三维体积逐项相交；SVG弧线采样只用于显示，不参与判定。高层扫掠与矮凳的同平面投影单独记录，不能把所有门扫掠视为地面占用，也不能忽略高层门风险。预留通道无论高度均不得被开门投影侵入。

首组相邻批次按两班分别核验：前4人逐一返回各自本位，后4人逐一进入自己的柜列。每步完整轴向扫掠盒与52名固定人员、柜体、座凳、完成面和预留通道/端部接近区逐项核验；包含转角与端部的完整人体包络，不用端点或直线距离替代路径。所有端部站位在换位完成后与下一快照吻合。

仅两班首组相邻批次，共16条人员移动见证。没有把其他28组快照自动升级成动态能力；座凳起坐、持续取衣更衣、全部53人的整轮转换、同时穿行、交接班重叠、清洁维护及疏散未验证。不能由本例估计吞吐时间或证明53人能完成全部更衣流程。

安装评估仅含外形、完成面、假设安装间隙和打开包络；未证明设备可搬入、锚固、调平、维修拆卸。清洁/维护作业流程缺少真实工具和净空，标记 NOT_EVALUATED。

## 洁污分隔

A每人一格内部隔断：保留分隔要求，隔板厚度、有效容积、衣物尺度和卫生效果 INPUT_REQUIRED。B每人两格：独立分配工衣/私衣，仍不证明两条洁污人流完全隔离。东入口至南包装门的示意方向只来自真实Portal，不代表已批准卫生流程。44列方案若空间冲突，保留失败，不减少53人、座凳或校核功能换取通过。

## 待确认输入

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
- benches_dimensions_quantity_and_operation_spaces
- clean_unclean_separation_and_cleaning_maintenance_plan
- both_shift_complete_reviewed_four_state_witnesses

另需：柜门铰链位置/角度/厚度、门把及锁具突出、完成面净高、锚固及搬运要求、实际人体和穿衣操作包络、每批人数与时间、座凳起坐和维护清洁工具、房门开向及内外候门空间、洁污工艺审批。

## 本地查看与参数复算

直接打开 index.html 可查看所有保存方案和批次。启动仅本机服务可复算假设，不写入Authority：

```bash
cd backend
PYTHONPATH=src:scripts uv run --frozen python scripts/build_r11_r5_h5_review.py --serve-existing ../docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1 --port 52992
```

函数版本、单位、公式、输入、冲突组件、每次移动的52人位置和门扇状态均在 hypothetical-results.json；来源及衍生哈希在 source-manifest.json。无Native、MAIN、Grant/Claim、正式CI或生产默认改变。
