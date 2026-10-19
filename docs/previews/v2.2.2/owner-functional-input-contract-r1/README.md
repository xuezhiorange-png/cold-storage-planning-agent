# Owner工厂功能输入合同 R1

TASK=V2_2_2_OWNER_FACTORY_FUNCTIONAL_INPUT_CONTRACT_R1

`OwnerFactoryFunctionalInputsV1`，业务参数版本 `owner-factory-functional-inputs@1.0.0`。
确认日期为本次Owner指令接收日 **2026-10-19（Asia/Shanghai）**，不是追认历史项目批准日期。
来源为本任务Owner明确指令；不是标准条文、项目设备选型、专业审查或新的求解Grant。

## 已确认的业务条件

|范围|本次确认|仍不能据此推断|
|---|---|---|
|办公室|小型12人、中型20人、大型30人，均为设计容纳人数|规模分级阈值、实际项目规模、工位及通道是否放得下|
|包装生产率|15件/人·时 × 1.6kg/件 × 8时/班 = **192kg/人·班**|原果量等于包装成品量；人员连续工作16小时|
|班次|每日两班，各8小时，设施包装时段合计16小时|默认平均分配；封膜设备有效运行也为16小时|
|更衣|仅包装工人；交班更衣不重叠；每员工独立一柜，不跨班共用|加入其他岗位、班内继续分批、更衣面积已足够|
|柜位|两班人数之和；柜内工作服与个人衣物分隔|柜内两类储物需两个独立柜位|
|同时更衣|两班人数最大值，按整个班次一次更衣设计|卫生、隐私及分区已经合规|
|包装封膜|独立`coating_room`，设计按进入该房间的包装产品100%需封膜|果品打蜡、托盘缠绕；设备型号/数量或有效运行时长|
|不封膜产品|可穿过同一覆膜间，不经过封膜设备，不默认另建绕行房间|实际穿行包络及人货冲突已校核|

Owner不预设男女独立功能分区；该业务偏好**不免除卫生、隐私及适用规范的专业复核**。
柜体型号、宽深、门扇、操作、通道、凳及其他设施仍待确认。

工艺顺序固定为：

```text
SORTING_PACKAGING -> SECONDARY_PRECOOLING -> COATING_ROOM -> FINISHED_GOODS
sorting_packaging_room -> secondary_precooling_room -> coating_room -> finished_goods_room
```

这是现有顺序的业务细化，不修改P0图、7条MUST或生产角色身份。
封膜设备须另行确认产能、数量和有效运行时间，并核验进出料、操作、检修、
不封膜穿行与人员物流冲突；本轮不生成设备面积、房间尺寸或功能PASS。

## 分班计算与来源要求

```text
SHIFT_1_WORKERS = ceil(SHIFT_1_PACKAGING_KG / 192)
SHIFT_2_WORKERS = ceil(SHIFT_2_PACKAGING_KG / 192)
LOCKER_COUNT = SHIFT_1_WORKERS + SHIFT_2_WORKERS
SIMULTANEOUS_CHANGING_USERS = max(SHIFT_1_WORKERS, SHIFT_2_WORKERS)
```

每班输入必须是**包装产品质量kg**，有明确来源引用，并明确班次分配。
只有原果进厂量时返回缺失输入，不计算默认出成率，不用历史20t进厂量自动替代包装量。
若上游做了出成率转换，须保留原果质量、产品质量口径、转换依据及来源；本离线函数不实现该转换。
填写来源字符串只是记录引用，不等于校验了外部文件或建立了服务端Authority。

|显式示例（不是项目事实）|班1/班2包装kg|班1/班2人数|独立柜位|同时更衣|
|---|---|---|---|---|
|两班平均分配|500 / 500|3 / 3|6|3|
|同为1000kg、非平均|800 / 200|5 / 2|7|5|

两例总量相同，逐班向上取整可能使人数之和不同；不能先将日产量除以192取整后再分班。
不得直接用 `ceil(日量 / 384)` 得到两班员工或柜位总数。
示例明确选择平均分配，并未冻结平均分配规则。缺一班时也不自动用日量减去另一班补齐。
零生产量的班次算得零包装人员，仅是该岗位算术结果，不代表工厂可以没有其他人员。

## 与历史Authority的关系

- 现有P1面积继续为办公室60、更衣室40、覆膜间80m²，不因本合同重算或覆盖。
- 历史336kg/人·日规则、生产计算器、输入快照、已生成布局和Hash全部保留。
  新192kg/人·班与历史336kg/人·日的单位和排班语义不同，不能静默替换。
- 后续生产接入必须独立授权、显式选择新版本并说明历史兼容与面积影响，不能只改系数或P1 Hash。
- `UNMODELED_FLEXIBLE_DIMENSION_RULE`保持Fail-closed；不修改GlobalModel、AccessModel或正式Selector。
- 不改变D01/D03/D04、资源合同、P3历史262 UNKNOWN；不操作Tool7、MCP和Truck。

这些确认补齐了[上一轮尺度研究](../functional-room-dimension-calibration-01/README.md)
中的部分业务缺口，但没有改写旧报告的历史缺失状态。通用净宽、进深、比例和功能面积仍未校准。

## 文件与复现

- [Owner确认字段及完整元数据](owner-confirmed-business-rules.json)
- [分班人数与柜位合同](staffing-calculation-contract.json)
- [统一功能房间输入合同](functional-room-input-contract.json)
- [尚缺的工程输入](unresolved-engineering-inputs.json)
- [显式示例及错误场景结果](calculation-examples.json)
- [未来P1接入边界](p1-integration-boundary.md)
- [历史文件完整性](historical-integrity.json)、[验证记录](validation.json)、[SHA清单](source_manifest.json)

已有Python3.12标准库即可复现，不安装依赖、不导入生产计算器或求解器：

```sh
python3 docs/previews/v2.2.2/owner-functional-input-contract-r1/contract.py
python3 docs/previews/v2.2.2/owner-functional-input-contract-r1/test_contract.py
```

本目录是文档及离线验证，不是注册的API或已投产参数契约。
计算采用精确有理数；数量接受十进制字符串/整数/Decimal，拒绝二进制浮点、负数和非有限值。
`SOURCE=OWNER_CONFIRMED`仅用于本次明确确认值；计算结果由其推导，示例数据明确为合成。

`NUMERIC_CALIBRATION_READY=false`；`P2D_FULL_PASS_COUNT=0`；`VERSION_COMPLETE=false`。
不Ready、Merge、Release、Deploy，不自动启动生产实现或真实求解。
