# H5实物参数校准与同条件复核

TASK_ID=V2_2_2_R11_R13_H5_PHYSICAL_INPUT_CALIBRATION_R1
BASE_HEAD=5b7ec33f258bacc0797148edb70766b47c47298f

当前没有实际设备/人体/现场完整资料。真实字段空值不填默认；供应商和现场资料仅验证来源字节，不自动审核其内容。既有ReviewedProjectDatum是唯一复用的审阅输入边界，没有新增审批体系。

ACTUAL_CALIBRATION=INPUT_REQUIRED
ENGINEERING_APPROVAL=NOT_EVALUATED
FACTORY_APPLICABILITY=NOT_EVALUATED

| 同条件组 | 房间 | 面积㎡ | 本位 | 两班完成 | 完整条件流程 | 最不利已定义余量 |
|---|---|---:|---:|---|---|---|
| 实际参数（未齐全/未审阅） | C | 93.475050 | 未算 | 未算 | INPUT_REQUIRED | NOT_EVALUATED |
| 实际参数（未齐全/未审阅） | 3850 | 101.374350 | 未算 | 未算 | INPUT_REQUIRED | NOT_EVALUATED |
| 20/20mm · 相同50mm填充（未批准） | C | 93.475050 | 53 | [53, 53] | CONDITIONAL_FLOW_PASS | 50mm / S1-U01 / S1-U02 |
| 20/20mm · 相同50mm填充（未批准） | 3850 | 101.374350 | 53 | [53, 53] | CONDITIONAL_FLOW_PASS | 50mm / S1-U01 / S1-U02 |
| 30/40mm · 相同100mm填充（未批准） | C | 93.475050 | 40 | [] | NOT_EVALUATED_UPSTREAM_REJECTED | 76mm / HOME-21（失败布置局部值，不是候选余量） |
| 30/40mm · 相同100mm填充（未批准） | 3850 | 101.374350 | 53 | [53, 53] | CONDITIONAL_FLOW_PASS | 70mm / HOME-41 |

20/20与30/40是分别明确的回归输入；每组C和3850mm使用同一组柜体、人体、通道、门扇和填充参数。没有以历史R10 PASS替代新流程。完整新事件、两班人员名单、门扇和局部余量保存在各组full-witnesses.json.gz中。

三维柜门按原解析扇形逐批检查；取衣/存衣时开门，更衣时关门。实际五层净宽/净深、衣物尺寸、分隔与取放方式、操作可达性仍缺少资料；110个格口仅算容量，不构成106人储物功能合格。

外矩形没有因内部参数改变：C和3850mm分别用两份原候选的12区/通道/Site几何重新叠加，已检查范围无新增正面积碰撞。外部Access、Truck、洁污工艺及最终整厂适用仍未验证。B仅保留原3.338㎡通道与0.982㎡禁建区冲突，不参与本轮校准。

适配器边界明确列在projection中：不支持的门扇、非均匀层位、不同旋转包络或流程不被近似为旧模型。默认20mm框/15mm门厚/左铰链/参考可达范围等只属于R10受限模型，绝不是规范或Owner要求。实际更改需相应功能适配器。

每侧不利施工公差预算加入完成面厚度并重新计算；不是未经审核的施工允许公差。所有参数、文件字节或审阅来源变化均改变input_fingerprint；旧见证不能继续用于新输入。Hash校验不等于审批。

## Owner仍需提供/复核

- 实际五层柜型号、实体柜分组、外形及格口净尺寸：INPUT_REQUIRED
- 工作服与私人衣物采用何种实际分隔，卫生工艺是否认可：INPUT_REQUIRED
- 柜门铰链、开启角度、分层扫掠及取放操作方式：INPUT_REQUIRED
- 实际完成面尺寸、安装间隙、公差和柜体固定要求：INPUT_REQUIRED
- 站立更衣、运输和转身的人体活动包络及五层可达性：INPUT_REQUIRED
- 已知53人同时在室条件下的柜前并发、等候本位和换位组织：INPUT_REQUIRED
- 洁污工艺、房门开向、门前停留与连续人员通行条件：INPUT_REQUIRED
- 真实取放、更衣和步行时间及允许的换班时间窗口：INPUT_REQUIRED
- 扩建后的Site、Footprint、外部Access、相邻房间及工艺关系：INPUT_REQUIRED

原53人同时在室、两班人数、无坐凳、本人柜前站立及五层形式不重新列为未知。P01/P02只计一个物理房间。未修改历史P1、Stage B、比较器、面积Authority、MCP、MAIN或默认。无Native、MAIN或真实Grant/Claim。
