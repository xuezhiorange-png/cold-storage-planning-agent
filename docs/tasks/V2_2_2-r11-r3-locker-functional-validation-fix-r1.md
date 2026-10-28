# R3 功能校核修正

TASK_ID=`V2_2_2_R11_R3_LOCKER_FUNCTIONAL_VALIDATION_FIX_R1`

继续Draft PR #323；修正基线 `d6d36b31d3a9c335ffdf5888bc79e4d0c171b699`。
20000kg/天、53人/班、106独立柜和项目Scope不变。

## 两班分别证明

`evaluate_reviewed_locker_witness()` 新增 `shift_witnesses={1:..., 2:...}`。
每份见证包含相同106柜和固定座凳，但人员位置、净通道和路线可以随错峰班次变化。
正常使用及交接状态分别要求本班53人位置与本班53柜一一关联，人员空间接触所关联柜的操作面。
另一班的位置不能复用为本班证据；单份旧式witness不能得到 `CONDITIONAL_FIT`。

R11 R1保持原样：先对每班分别执行原四状态校核，然后由R3扩展排除人员/其他排他功能空间、
活动操作净区、房门及柜门扫掠对净AISLE和真实路线包络的侵占。自己柜位的人员操作空间可以
与自己的操作区共享，但不能与其他活动柜位操作区、其他人的空间或净通道发生冲突。
外接两处原Portal必须在每班、每个状态中均有有效连通证明。

已审 `BasisValue` 额外提供 `field_name=r3_shift_operation_plan`、`unit=mapping`；
原有字段引用机制仍检查房间Scope、语义、单位、来源和非空参考。
该字段的value必须有字符串键 `1`、`2`，每班覆盖USE、SHIFT_CHANGE、CLEANING、MAINTENANCE。
各状态必须明确active_locker_ids、未用柜排关闭依据、door_motion_basis及逐个活动柜的
locker_door_motion。无地面侵入也必须有明确已审机制；不能把缺少扫掠数据当作零扫掠。
柜门有排除范围时，必须检查其与人员、其他实体、其他操作区、净通道和路线的实际冲突。
普通JSON和页面假设参数不能形成这个已审字段；没有资料时始终 `INPUT_REQUIRED`。

## 修正必要长度

双侧理想长度 `max(n1, N-n1) × locker_width_mm`。
53/53、90/16、1/105在400mm柜宽下，分别得到21200、36000、42000mm。
真实门洞分段及端部空间继续单独检查；不能用理想公式替代实际柜位数量。

## H5 条件模拟

仅在假设柜400×500mm、人位400×600mm、柜前操作600mm、净通道1200mm、净高4000mm、
柜门不侵入地面、房门无门扇、另一班柜排关闭、无座凳及无需洁污分隔的条件下，
可以构造两班分别53人/53柜、连接原两处Portal的几何见证。
每班有独立内部路线，中心y分别为1700和1550mm。
未用柜前地面在该明确关闭假设下可纳入净通行区，因此原“同时预留双排操作带需3400mm”
不能作为所有H5布置不可能的结论。

模拟同时通过原R11和R3扩展也只标 `GEOMETRY_VALID_ONLY_UNDER_HYPOTHESES`。
其原R11计算采用独立HYPOTHETICAL Scope，不是项目已审设计输入。
真实项目仍缺柜型及开门机制、房门、完成面、净高、净宽、座凳、洁污及维护计划；
8组真实房间均为 `INPUT_REQUIRED`。1.2m内部通道是假设，不是对原Access Authority的改动或批准。

P01、P02原Candidate分别核对源SHA、两条Access的PASS状态及本地Portal坐标/净宽，
各自留存readback；房间几何仍只计一个G01，不能把两班或两个Access记录计为新增房间。

产物仍在 `docs/previews/v2.2.2/r11-r3-locker-layout-review-r1/`，新增两班SVG、
`h5-staggered-simulation.json`、`unequal-row-checks.json` 和 `record-access-readbacks.json`。
原报告前版在Git冻结基线中保留，不修改R11原件、历史MAIN、P1、Stage B、比较器或生产默认。

本轮不执行Native、MAIN、真实Grant/Claim、正式完整CI、Ready、Merge、Deploy。
