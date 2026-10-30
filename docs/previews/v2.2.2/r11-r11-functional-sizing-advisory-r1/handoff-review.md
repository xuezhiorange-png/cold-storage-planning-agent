# H5功能尺寸建议与整厂只读预检查

BASE_HEAD=9629019ddd704426b5f7fe72b9a98d2273fca1c4

本报告只匹配已审阅H5与封存功能见证。条件流程通过不等于工程批准，也不证明原整厂可容纳扩建。

P01/P02按真实矩形与Portal、项目/P1/Site/Composition去重为1个物理房间。原P1需求40.000000㎡不变；引用现有DimensionAuthorityReferenceV1及原Authority行，不创建新面积Authority。

| 方案 | 长×宽mm | 面积㎡ | 新增㎡ | 完成面/安装输入mm | 最小余量mm | 最不利位置 |
|---|---:|---:|---:|---:|---:|---|
| 原H5 | 26331×3250 | 85.575750 | 0.000000 | 未确认 | 不推断 | 原工程状态保留 |
| C 较少边界调整 | 26331×3550 | 93.475050 | 7.899300 | 20/20 | 50 | cabinet_unit_installation / S1-U01 / S1-U02 |
| 3850mm组合敏感性 | 26331×3850 | 101.374350 | 15.798600 | 30/40 | 70 | waiting_finished_boundary / HOME-41 |
| B 更大局部余量 | 28000×4350 | 121.800000 | 36.224250 | 20/20 | 150 | cabinet_unit_installation / S1-U01 / S1-U02 |

C/B为20/20mm基础假设，3850mm为30/40mm组合敏感性。三者各自保留柜体/人体/排布条件、模板加量及实际余量；不归一化即不作全局最优或安全性排名。3850mm的70mm低于其100mm模板目标，不能标为目标通过。所有实际功能仍INPUT_REQUIRED。

## 来源与架构衔接

P1原始快照→现有尺寸Authority引用→已验收候选/P01-P02房间身份→R10原完整双班条件见证→只读建议合同。原composition_candidate_validation通过来源Hash校核候选的原则保留；本预检查只读取已封存候选，不调用重放、候选枚举或Native。不向dimension_handoff、整厂求解器、数据库或MCP注册建议。

输入文件须匹配固定内容摘要。改写JSON标签、重算建议自身Hash或替换候选不能获得适用性。其他房型返回FUNCTIONAL_ADAPTER_REQUIRED，错项目/源候选/证据缺失直接拒绝。

## 外部复核

全部扩建的Site、Footprint、外部Access、相邻功能房间及工艺关系保持NOT_EVALUATED。C/3850mm仅扩北边、Portal数值不变；B向北/东扩展，东Portal映射到新东边界。原门洞、原几何及其工程结论不被覆盖。

## Owner与工程师待确认

- 实际五层柜型号、实体柜分组、外形及格口净尺寸：INPUT_REQUIRED
- 工作服与私人衣物采用何种实际分隔，卫生工艺是否认可：INPUT_REQUIRED
- 柜门铰链、开启角度、分层扫掠及取放操作方式：INPUT_REQUIRED
- 实际完成面尺寸、安装间隙、公差和柜体固定要求：INPUT_REQUIRED
- 站立更衣、运输和转身的人体活动包络及五层可达性：INPUT_REQUIRED
- 已知53人同时在室条件下的柜前并发、等候本位和换位组织：INPUT_REQUIRED
- 洁污工艺、房门开向、门前停留与连续人员通行条件：INPUT_REQUIRED
- 真实取放、更衣和步行时间及允许的换班时间窗口：INPUT_REQUIRED
- 扩建后的Site、Footprint、外部Access、相邻房间及工艺关系：INPUT_REQUIRED

已确认的无坐凳、本人柜前站立、两班各53人、53人同时在室及五层柜形式不再列为未知。清单不生成审批记录。

## 软件证据与执行边界

R10原远端CI #40803856287的41项JUnit、原ZIP与验证记录均按原字节保留，属于软件测试证据，不是工程批准。R9 Native异常、R10所有文件与来源Hash均保持原样。本轮只读已有功能见证，无新布局求解、20t Native、MAIN、真实Grant/Claim或正式完整CI。自动快速CI中的既有合成Native单独识别，不能据此声称任务级所有环境Native为零。
