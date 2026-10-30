# H5尺寸扩展的整厂空间影响预验证

TASK_ID=V2_2_2_R11_R12_FUNCTIONAL_ROOM_SITE_IMPACT_REVIEW_R1
BASE_HEAD=5a652a05afa438bd43631b7ffdaf4b541899c8ca

只读使用原20t回归输入、P01/P02的12区、原Site与原通道，不求解、不重规划、不改变原工程状态。两份候选分别读取和验证，但扩建面积按一个物理更衣室计算。

| 原记录 | 方案 | 房间新增㎡ | 其他房间交集㎡ | 原通道交集㎡ | 禁建/Hard去重交集㎡ | 净Footprint新增㎡ |
|---|---|---:|---:|---:|---:|---:|
| P01 | C 较少边界调整 | 7.899300 | 0.000000 | 0.000000 | 0.000000 | 7.899300 |
| P01 | 3850mm组合敏感性 | 15.798600 | 0.000000 | 0.000000 | 0.000000 | 15.798600 |
| P01 | B 更大局部余量 | 36.224250 | 0.000000 | 3.338000 | 0.982000 | 32.886250 |
| P02 | C 较少边界调整 | 7.899300 | 0.000000 | 0.000000 | 0.000000 | 7.899300 |
| P02 | 3850mm组合敏感性 | 15.798600 | 0.000000 | 0.000000 | 0.000000 | 15.798600 |
| P02 | B 更大局部余量 | 36.224250 | 0.000000 | 3.338000 | 0.982000 | 32.886250 |

## B的实际交集及影响

- P01 入口通道：源边界[[41031, 24275, 74460, 26275]]mm；交集[[41031, 24275, 42700, 26275]]mm；面积3338000mm² / 3.338000㎡。来源docs/evidence/v2.2.2/r11-r11-h5-sizing-sources/previews/proposal-01/candidate-01/candidate.json#/engineering_validation/corridors/0/envelope/2；对象Hash sha256:ea3033defef5a2c47696f2042889871229d4546ac80b7bcc39e89c7273dfe2e2。
- P01 禁建区（亦为Hard Obstacle）：源边界[[41718, 27000, 74999, 39385]]mm；交集[[41718, 27000, 42700, 28000]]mm；面积982000mm² / 0.982000㎡。来源docs/evidence/v2.2.2/r11-r11-h5-sizing-sources/server-authorities.json#/site/obstacles/no_build_zones/1；对象Hash sha256:ed2cf0a0823161d1c9efc60e3d4e9935e96891ac07c63711c00ff90b82aec487。
- P02 入口通道：源边界[[41031, 24275, 74460, 26275]]mm；交集[[41031, 24275, 42700, 26275]]mm；面积3338000mm² / 3.338000㎡。来源docs/evidence/v2.2.2/r11-r11-h5-sizing-sources/previews/proposal-02/candidate-01/candidate.json#/engineering_validation/corridors/0/envelope/2；对象Hash sha256:ea3033defef5a2c47696f2042889871229d4546ac80b7bcc39e89c7273dfe2e2。
- P02 禁建区（亦为Hard Obstacle）：源边界[[41718, 27000, 74999, 39385]]mm；交集[[41718, 27000, 42700, 28000]]mm；面积982000mm² / 0.982000㎡。来源docs/evidence/v2.2.2/r11-r11-h5-sizing-sources/server-authorities.json#/site/obstacles/no_build_zones/1；对象Hash sha256:ed2cf0a0823161d1c9efc60e3d4e9935e96891ac07c63711c00ff90b82aec487。

受影响的是access:main_entrance->changing_room@1.0.0。B原入口通道需重新设计/验证，标记ARCHIVED_CORRIDOR_INTERSECTION_DETECTED。旧更衣室东Portal位于原墙线，条件Portal移到新东墙，旧通道末端已不在映射门洞上。南侧更衣室→分选包装间的原1500mm Portal及共享边几何保持；这不是完整Access复验通过。

B还占用归档No-build Zone。该区域同时列在Hard Obstacles与No-build Zones中，按空间并集去重。结论只针对本次固定原通道、原禁建区的叠加；不宣布B全局不可行，不生成替代通道，不调整禁建Authority。

## C及3850mm与边界

两种向北扩展带分别计算，均未检测到与已归档其他房间、通道、Hard Obstacles和No-build Zones的正面积交集；三种条件房间均位于原Site/可建边界内。门洞坐标未变化不代表外部工程适用。所有方案最终整厂适用仍NOT_EVALUATED。

## Footprint与原工艺

先由每份候选的12区及原通道包络重现原Footprint，再求纯几何叠加并集。原建筑面积、周长、转折与凹角及新并集指标保存在JSON；正式九/十二指标比较器未调用或修改。B房间新增面积与净Footprint新增面积不同，是因为其中一部分覆盖原通道。即使并集周长减少，也不能称为工程质量改善。拓扑并集单连通/零孔洞仅是几何诊断，不能替代Site、通道和独立验收。七条原MUST共享边均按原图复查，不创建新工艺关系。

## 缺失与未验证

Truck Envelope在两份原候选中均为空且原Truck状态BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED，不把空数组当作Truck空间清晰证据，保留NOT_EVALUATED。未归档设备/其他占用不推断为空。未运行外部Access重规划或整厂工程复验。缺少某项几何时返回NOT_EVALUATED，篡改或跨项目来源则拒绝。

## 条件与Owner输入

C/B使用20mm完成面、20mm安装输入；3850mm使用30/40mm。三者保留原R10/R11建议Hash、条件与完整双班见证Hash，不作跨参数安全性或全局最优排序。实际功能保持INPUT_REQUIRED。复用R11原确认清单；参数模板的未知值为null，不创建Owner审批记录。已确认的两班各53人、53人同时在室、五层柜、柜前站立、无坐凳继续保留。

- 实际五层柜型号、实体柜分组、外形及格口净尺寸：INPUT_REQUIRED
- 工作服与私人衣物采用何种实际分隔，卫生工艺是否认可：INPUT_REQUIRED
- 柜门铰链、开启角度、分层扫掠及取放操作方式：INPUT_REQUIRED
- 实际完成面尺寸、安装间隙、公差和柜体固定要求：INPUT_REQUIRED
- 站立更衣、运输和转身的人体活动包络及五层可达性：INPUT_REQUIRED
- 已知53人同时在室条件下的柜前并发、等候本位和换位组织：INPUT_REQUIRED
- 洁污工艺、房门开向、门前停留与连续人员通行条件：INPUT_REQUIRED
- 真实取放、更衣和步行时间及允许的换班时间窗口：INPUT_REQUIRED
- 扩建后的Site、Footprint、外部Access、相邻房间及工艺关系：INPUT_REQUIRED

本轮新增功能不调用Native、MAIN、Grant/Claim或正式完整CI。继承自动快速CI的既有合成Native测试单独记录，不宣称所有CI测试都无Native。原R9异常、R10及R11来源和远端JUnit证据保留。
