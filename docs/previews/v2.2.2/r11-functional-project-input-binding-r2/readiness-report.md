# R11 R2｜封存20t功能设计输入绑定与缺口

当前结论：**INPUT_REQUIRED**。未收到经应用侧资料/适用性审阅的项目专属输入。

本项目为 FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO；20t 是进厂量，
不能当作已包装产品质量推导包装人数或柜数量。

## 已确认、但不等于项目设计批准的通用规则

- 两班独立更衣柜，一人一柜，不能跨班共用。
- 两班错峰更衣，同时人数按实际两班较大人数计算。
- 产能按已包装产品质量：15件/人时×1.6kg/件×8小时=192kg/人班。
- 包装人员默认两班均分，仅当已包装产品日质量经项目审阅后启用；显式班次覆盖须同时提供两班人数。
- 显式两班人数不会自动分配50/50工作量；合计产能充足只证明总量容量，逐班满足须有各班已审包装质量并分别校核。
- 办公人员按经确认的项目工厂规模选 SMALL=12/MEDIUM=20/LARGE=30。
- 覆膜设计比率为100%，但设备型号、独立运行时数、有效产能均未确认。

## 项目专属输入现状

- 已包装产品日质量：INPUT_REQUIRED。
- 办公厂型：INPUT_REQUIRED；办公人数：INPUT_REQUIRED。
- 两班包装人数：INPUT_REQUIRED。
- 同时更衣人数：INPUT_REQUIRED。
- 已审核人数依据状态：INPUT_REQUIRED；逐班产能校核：INPUT_REQUIRED_PACKAGED_MASS。
- 合计容量校核：INPUT_REQUIRED_PACKAGED_MASS；班次工作量依据：INPUT_REQUIRED_SHIFT_WORKLOAD_ALLOCATION。
- 显式人数已知但各班工作量未知时，保留人数及柜数需求，产能仍为待验证。
- 更衣柜规格、内部净尺寸、门操作包络、人员空间及内部通道：INPUT_REQUIRED。
- 办公家具及合法办公出入口：INPUT_REQUIRED。
- 覆膜设备型号、台数、运行工时、进出料与维护包络：INPUT_REQUIRED。

## 历史27份房间记录（只读投影）

|候选|Handoff|物理组|房间|已绑定项目字段|功能结论|
|---|---|---|---|---|---|
|P01|H5|G01|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P01|H5|G01|office|—|INPUT_REQUIRED|
|P01|H5|G01|coating_room|process_type|INPUT_REQUIRED|
|P02|H5|G01|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P02|H5|G01|office|—|INPUT_REQUIRED|
|P02|H5|G01|coating_room|process_type|INPUT_REQUIRED|
|P03|H6|G02|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P03|H6|G02|office|—|INPUT_REQUIRED|
|P03|H6|G02|coating_room|process_type|INPUT_REQUIRED|
|P04|H6|G03|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P04|H6|G03|office|—|INPUT_REQUIRED|
|P04|H6|G03|coating_room|process_type|INPUT_REQUIRED|
|P05|H6|G04|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P05|H6|G04|office|—|INPUT_REQUIRED|
|P05|H6|G04|coating_room|process_type|INPUT_REQUIRED|
|P06|H6|G05|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P06|H6|G05|office|—|INPUT_REQUIRED|
|P06|H6|G05|coating_room|process_type|INPUT_REQUIRED|
|P07|H6|G06|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P07|H6|G06|office|—|INPUT_REQUIRED|
|P07|H6|G06|coating_room|process_type|INPUT_REQUIRED|
|P08|H6|G07|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P08|H6|G07|office|—|INPUT_REQUIRED|
|P08|H6|G07|coating_room|process_type|INPUT_REQUIRED|
|P09|H6|G08|changing_room|internal_clothing_separation, shift_change_policy|INPUT_REQUIRED|
|P09|H6|G08|office|—|INPUT_REQUIRED|
|P09|H6|G08|coating_room|process_type|INPUT_REQUIRED|

## 下一步设计输入的办理方式

填写 `project-input-request.json` 的候选值及可验证来源；这只是待审资料清单，
不具备 OWNER_CONFIRMED 或工程批准效力。应用侧逐项核对项目范围、原始文件、
班制、人员、设备版本并生成可信 ReviewedProjectDatum，方可用于真实绑定。
不允许通过修改 JSON 的 status/label 自行授权。

本模块只减少可追溯的输入缺口，绝不修改原 P1、Stage B 验收、九/十二指标、
历史账本、Grant/Claim 或生产默认；Native=0。
