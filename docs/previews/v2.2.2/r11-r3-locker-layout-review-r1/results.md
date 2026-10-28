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
