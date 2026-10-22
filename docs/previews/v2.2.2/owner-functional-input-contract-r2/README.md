# Owner功能业务输入合同 R2 / V2

TASK=V2_2_2_OWNER_FACTORY_FUNCTIONAL_INPUT_CONTRACT_R2

新版身份`OwnerFactoryFunctionalInputsV2`，版本`owner-factory-functional-inputs@2.0.0`。
Owner已批准默认均分、显式覆盖、3人/台、两班共台及峰值台数。
本目录是**业务政策及离线计算实现**，不是生产P1算法或面积Authority的启用。
确认日期为本次指令接收日2026-10-19（Asia/Shanghai），不追认历史项目资料批准。

## 新规则

- 对**有明确来源的每日包装成品质量Q**，默认两班各承担精确的Q/2，不先取整班次质量。
- 项目完整提供Q1/Q2时，使用`EXPLICIT_SHIFT_OVERRIDE`；若另有Q，须Q1+Q2=Q。
- 只给一个班次时拒绝，不以日量减出另一班，也不回退50/50。
- 缺Q且无完整显式分班时拒绝。不得用daily_inbound_mass_kg或默认100%出成率代替Q。
- N1=ceil(Q1/192)、N2=ceil(Q2/192)，192=15件/人·时×1.6kg/件×8时/班。
- 两班共用包装台，3人/台：台数=ceil(max(N1,N2)/3)，不是ceil((N1+N2)/3)。
- 两班员工各一独立柜：柜位=N1+N2；同时整班更衣=max(N1,N2)。柜内分隔不倍增柜位。

|显式合成输入|分班方式|Q1 / Q2 kg|N1 / N2|总员工/柜位|峰值/同时更衣|需求台数|
|---|---|---|---|---|---|---|
|20000kg包装产品|默认50/50|10000 /10000|53 /53|106|53|18|
|20000kg包装产品|项目覆盖|16000 /4000|84 /21|105|84|28|
|仅两班800/200kg|项目覆盖，无日量|800 /200|5 /2|7|5|2|
|1kg包装产品|默认50/50|0.5 /0.5|1 /1|2|1|1|
|192kg包装产品|默认50/50|96 /96|1 /1|2|1|1|
|384kg包装产品|默认50/50|192 /192|1 /1|2|1|1|

这不是实际项目包装量证明，也不是旧20吨原果自动转换的结果。
需求台数是n_need，不是排布格位n_actual；本轮不调用旧排布算法生成新版面积。
交班清洁、设备实际可用性及必要缓冲仍需工程核验。

## 完整继承及未决条件

办公室仍按显式SMALL/MEDIUM/LARGE对应12/20/30设计容纳人数；规模阈值未知，
不从旧25/50吨面积档推导等级。人数、工位、家具及净空间不完整时不能证明面积足够。

更衣仅含包装人员；两班错峰、不跨班共柜，柜内工作服与私人衣服分隔；
整个班次更衣，不默认班内分批。不预设男女独立功能区，但卫生/隐私仍须专业复核。
V1旧字段名称及原件不改，语义按[此前明确映射](../owner-factory-p1-compatibility-readiness-r1/role-and-field-alias-mapping.json)解释。

独立coating_room仍为包装箱封膜，顺序保持：
分选包装→二级预冷→包装封膜→成品冷藏。
进入房间的包装产品按100%需封膜设计；实际不封膜产品可在同室不经设备穿行，不默认新绕行房间。
设备型号/能力/数量/Envelope、正常操作/检修/物料及穿行包络、有效运行时长仍缺失。
包装设施16小时不自动成为封膜设备有效运行16小时，不产生设备数量、面积或功能PASS。

## 来源、身份及缺失处理

[确认值及元数据](owner-confirmed-business-rules-v2.json)逐条保留FIELD_NAME、VALUE、UNIT、
SOURCE=OWNER_CONFIRMED、CONFIRMATION_DATE、APPLICABILITY、CONTRACT_VERSION。
继承项注明V1出处；新默认政策注明旧值，不原地修改旧记录。

调用必须显式指定V2身份和版本；V1请求或只改版本不改身份均拒绝。
每日/班次包装质量与项目、时段、kg口径和本地源文件实际字节Hash匹配后，才进行本轮离线业务计算。
默认分班的来源是Owner V2比例政策加日质量来源；覆盖模式另保留实际分班来源。
内容匹配不是发布者真实性、项目批准或Server Authority。
若源文件已经记载显式班次分配，请求必须显式带入，不能省略它们后用50/50覆盖实际来源。
合成文件即使SHA完全正确，也不能取得`P1_AUTHORITY_PASS`。
无来源、伪Hash、口径冲突、只给一班或总量不一致均Fail-closed，无结果不填0。

## 历史兼容及P1边界

V1仍是`OwnerFactoryFunctionalInputsV1` / `owner-factory-functional-inputs@1.0.0`，
仍要求显式两班输入。其全部原件、输出与Hash保持不变。
旧生产336kg/人·日、20吨60人/20台/622.34m²/2194.59m²及P1尺寸Hash只读重放保持。
旧25/50吨房间面积分档、排布格位/台距/通道/排序及1.1系数不变。
本轮已确认的是台数**业务政策**，并未批准旧面积公式在V2的适用性，也不生成正式V2面积。
历史60/40/80m²代表性面积保留，不用新员工数宣布其功能足够。

- [默认及覆盖政策](shift-allocation-policy.json)
- [已确认的台数政策及面积边界](packing-table-policy.json)
- [精确计算与示例](staffing-and-locker-calculation.json)
- [V1/V2/Legacy对照](v1-v2-compatibility-matrix.md)
- [P1接入边界](p1-integration-boundary.md)
- [剩余输入与Authority](missing-authority-and-engineering-inputs.json)
- [历史完整性](historical-compatibility.json)、[验证](validation.json)、[SHA清单](source_manifest.json)

## 离线复现

使用已有锁定Python3.12环境，不新增依赖；脚本读取旧合同、只读调用旧区域计算及P1尺寸投影，
不调用CP-SAT、Placement或完整工厂MAIN/REPLAY。

```sh
PYTHONPATH=backend/src backend/.venv/bin/python3 docs/previews/v2.2.2/owner-functional-input-contract-r2/offline_contract_v2.py
PYTHONPATH=backend/src backend/.venv/bin/python3 docs/previews/v2.2.2/owner-functional-input-contract-r2/test_offline_contract_v2.py
```

BUSINESS_POLICY_READY=true；P1_AREA_CALIBRATION_READY=false；P1_PRODUCTION_ACTIVATED=false。
不修改生产代码、P0/P1/P2、Selector、Tool7、MCP、Truck或资源合同；D04轮次和262 UNKNOWN保留。
无新Grant、无真实布局或原生求解调用；不Ready/Merge/Release/Deploy，交付后STOP。
