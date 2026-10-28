# R11 R3 · 106柜功能布置评审

项目确认：包装成品20000kg/天；原Owner V2默认均分。各班质量['10000.0', '10000.0']kg、设计人数[53, 53]；独立柜106、同时更衣53人、包装台18。全部为设计计算值，不是实际人员名册。

8组真实物理矩形来自9份原记录。原门洞和外部路线只读回读；历史P1、工程有效性、九/十二指标与资源记录不变。

所有真实房间功能结论仍为 INPUT_REQUIRED。柜型、完成面、内部通行、门扇、操作、座凳与清洁分隔均尚未审定。以下参数仅为 HYPOTHETICAL_NOT_APPROVED，不写入Authority；指定模板失败不代表其他模板不可行。

假设：柜400×500×1800mm；通道1200mm；柜前操作600mm；人员空间400×600mm；无座凳、完成面内缩0（并非确认完成面）。

|组|记录|Handoff|矩形mm|单侧理想上界|双侧剩余宽mm|双侧基本必要条件|真实功能结论|
|---|---|---|---|---|---|---|---|
|G01|P01/P02|H5|26331×3250|65|2250|NECESSARY_CONDITIONS_MET_ONLY|INPUT_REQUIRED|
|G02|P03|H6|39683×1008|99|8|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|
|G03|P04|H6|39635×1010|99|10|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|
|G04|P05|H6|39633×1011|99|11|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|
|G05|P06|H6|39630×1012|99|12|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|
|G06|P07|H6|39627×1013|99|13|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|
|G07|P08|H6|39624×1014|99|14|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|
|G08|P09|H6|39621×1015|99|15|CONFIGURATION_NOT_FIT|INPUT_REQUIRED|

H6单侧理想上界99<106；实际扣除门洞缺口、端部或装修后更少。双侧两柜深1000mm后只剩8–15mm，低于假设净通道1200mm。

H5双侧基本所需21200×2200mm，外包矩形26331×3250mm，故仅通过必要条件。当前假设两侧独立柜前操作区加净通道所需宽3400mm，超过现有宽度；这是指定模板失败，不是所有模板无解。实际两门的净通行、人员、座凳及四状态仍需完整已审见证。

完整已审输入由可信应用提供BasisValue后，evaluate_reviewed_locker_witness调用原R11校核器。页面参数不是审阅入口；假设预览永远不产生正式CONDITIONAL_FIT。零Native、MAIN、Grant/Claim。

## 两班独立证明与净通行修正

R3要求分别提交shift_witnesses[1]与[2]，各班53人必须与本班53柜一一关联并位于对应柜体操作面。两班固定柜体/座凳位置一致。原R11四状态先校核，再由R3排除人员、门扇、其他功能占用及当前活动柜门操作区侵占净AISLE或路线包络；未知柜门运动或另一排关闭条件不得默认通过。

经审阅的r3_shift_operation_plan须逐班、逐状态声明活动柜、未用柜关闭依据及柜门排除范围。人员可使用自己的操作区，但不能占用另一用户的活动操作区；缺少任一班或任一状态的完整证据不能CONDITIONAL_FIT。

## H5错峰条件模拟（不是实际项目批准）

模拟状态：GEOMETRY_VALID_ONLY_UNDER_HYPOTHESES。仍假设无侵入式柜门、房门无门扇、净高4000mm、无座凳、无需洁污分隔及完成面零内缩；这些均未确认。
- 班次1：原R11=CONDITIONAL_FIT，R3=SHIFT_USE_VALIDATED，记录使用人位=53，内部路线中心y=1700mm，门洞证明=['portal:access:changing_room->sorting_packaging_room@1.0.0:changing_room@1.0.0', 'portal:access:main_entrance->changing_room@1.0.0:changing_room@1.0.0']。
- 班次2：原R11=CONDITIONAL_FIT，R3=SHIFT_USE_VALIDATED，记录使用人位=53，内部路线中心y=1550mm，门洞证明=['portal:access:changing_room->sorting_packaging_room@1.0.0:changing_room@1.0.0', 'portal:access:main_entrance->changing_room@1.0.0:changing_room@1.0.0']。

错峰时，仅当前班操作区保持活动，已明确假设关闭的另一班柜前地面可用于净通行。此条件下两班可以采用不同内部通道；并非要求106人同时使用，也不能把原3400mm同时双排操作模板的失败推广到所有安排。实际柜门机制、房门开启、净完成面、净宽、座凳和洁污条件仍缺失，8组真实房间均INPUT_REQUIRED。

## 不均等柜排

双侧理想必要长度=max(n1,N-n1)×柜宽；均分53/53只是特例。实际Portal分段容量另行检查，不能由总长公式替代。
- 假设柜排53/53：理想必要长度21200mm，H5基础状态NECESSARY_CONDITIONS_MET_ONLY。
- 假设柜排90/16：理想必要长度36000mm，H5基础状态CONFIGURATION_NOT_FIT。
- 假设柜排1/105：理想必要长度42000mm，H5基础状态CONFIGURATION_NOT_FIT。

## P01与P02分别回读

- P01：源SHA=faa7a645bef1be1b61e84102b041a1cfe4c0bf002a5f8485d47c039158406d9f；两条原Access均PASS=True；原Portal坐标和净宽匹配=True。
- P02：源SHA=c9e38907e5a6924ab261550c0478237924ac61f24f68e9185ba5782e8733c99b；两条原Access均PASS=True；原Portal坐标和净宽匹配=True。
