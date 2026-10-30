# H5 · Owner选定五层十门柜实物建模

TASK_ID=V2_2_2_R11_R14_OWNER_SELECTED_TEN_DOOR_LOCKER_R1
BASE_HEAD=9501238d7a815957e8bd46831b3f9f24767ce754

Owner选择850×390×1800mm标称整柜。原照片文件不可获取，照片Hash=null，照片证据INPUT_REQUIRED。选型不等于供应商技术审核/采购验收。400×360×320mm只是Owner转述图片中的标称标签，不是内部净尺寸。

11台完整双列五层柜，22列110格；两班各55格，其中各53人分配独立格口、各2格备用。U06两列分属两班，但整柜只有一个实体身份。无单列半柜，无跨班共享格口，未引入12台方案。

所有以下尺寸与流程均为条件模拟：425mm均分前缘非净宽；450×650mm人员、600×900mm活动、1200mm基准通道与余量、柜门400×320mm叶片/15mm厚、100mm底部/20mm层间隙、左铰链或镜像90°均未技术确认。层位100..1780mm，条件参考取放范围100..1800mm及水平600mm不是已批准人体可达性。不能借此认定储物或人体工学满足。

| 同条件案例 | 本位/缺口 | 两班已完成 | 闭门子校核 | 左开/镜像联合流程 | 联合最小余量下界 / 目标 |
|---|---|---|---|---|---|
| R14-20-20-M50-C | 53/53；缺0 | [53, 53] | CLOSED_DOOR_MOVEMENT_PASS_ONLY | CONDITIONAL_COMBINED_FLOW_PASS / CONDITIONAL_COMBINED_FLOW_PASS | 15mm / 50mm；达到目标=False |
| R14-20-20-M50-3850 | 53/53；缺0 | [53, 53] | CLOSED_DOOR_MOVEMENT_PASS_ONLY | CONDITIONAL_COMBINED_FLOW_PASS / CONDITIONAL_COMBINED_FLOW_PASS | 15mm / 50mm；达到目标=False |
| R14-30-40-M100-C | 38/53；缺15 | [] | NOT_EVALUATED_STATIC_REJECTED | NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW / NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW | Nonemm / 100mm；达到目标=False |
| R14-30-40-M100-3850 | 52/53；缺1 | [] | NOT_EVALUATED_STATIC_REJECTED | NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW / NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW | Nonemm / 100mm；达到目标=False |

每组C/3850mm使用相同柜体与人体/完成面/安装输入，全部新算；没有套用R10/R13的旧PASS。新Hash绑定Owner来源、原历史源Hash、当前几何/全部两班事件/逐门开柜子校核。

闭门状态复用原R10柜体/人员/Portal/连续通行子校核；它不是开门通过依据。R14单独检查110个门的独立身份，并在两班106人每人取放两次、共212个人-开柜事件中检查完整三维扇形与真实剩余人员/固定柜体/通道/其他同时打开门的冲突。只有两个子校核均通过才形成指定假设下的联合流程PASS。实际未知门型、内部净格和工艺仍INPUT_REQUIRED。

柜门额外余量采用原解析四分之一圆盘+厚度检查，并单列包围盒间隙下界。联合最小余量包含该新增门扇项，不能用闭门50mm余量掩盖开柜后更小余量。该下界不是人体工学净距或规范限值。

30/40mm组失败保留：C/3850未形成53个本位，因此未进入完整流程；没有减少人数、缩小人体或删除净通道。仅此有限模板失败，不是全局不可行。

## 标称柜体与旧模型的差异

旧22列400×500mm合计外包络面积4.400000㎡、累计列宽8800mm；新11台850×390mm合计3.646500㎡、累计柜宽9350mm。面积减少0.753500㎡、累计宽度增加550mm、外深减少110mm。实际安装排长还包括柜间隙，不能只用面积下降宣称功能改善。

| 案例 | 有效安装间隙 | 有效柜间隙 | 保留通道 | 实际柜排长度 |
|---|---:|---:|---:|---:|
| R14-20-20-M50-C | 70mm | 70mm | 1250mm | 10050mm |
| R14-20-20-M50-3850 | 70mm | 70mm | 1250mm | 10050mm |
| R14-30-40-M100-C | 140mm | 120mm | 1300mm | 10550mm |
| R14-30-40-M100-3850 | 140mm | 120mm | 1300mm | 10550mm |

## 储物与外部工程边界

110>=106仅是容量算术。各层真实净宽/净深/净高尚无证据，不能把360mm或320mm标签当净值。无衣杆/额外层板0为图片转述，不自动增加隔板。工作服/私人衣物分隔、折叠衣物规格与取出空间、最高最低格口可达、固定与维护条件均待确认。

原P01/P02对应一个H5物理房间，面积不重复计算。C=93.475050㎡、3850=101.374350㎡均为独立反事实尺寸，不改原85.575750㎡历史H5。R12原始叠加在构造上下文时独立复核；未重新验证的外部Access、Site/Footprint最终适用及洁污流程不作PASS。B历史3.338㎡通道与0.982㎡禁建区冲突原样保留。

## 待补资料

- Original selected photograph bytes; manufacturer/model and reviewed product drawing
- Verified net width/depth/height of all five tiers and actual panels/base/frame
- Actual hinges, left/right mirroring, opening angle and leaf thickness
- Clothing folded dimensions/volume, work/private segregation and hygiene process
- Actual lowest/highest tier retrieval reach and human activity envelopes
- Fixing/maintenance/installation requirements, finish and construction tolerances
- Room door swings, reviewed operating sequence, external Site/Access and hygiene review

ACTUAL_CALIBRATION=INPUT_REQUIRED
ENGINEERING_APPROVAL=NOT_EVALUATED
FACTORY_APPLICABILITY=NOT_EVALUATED

本轮无Native/MAIN/真实Grant/Claim/正式完整CI。既有自动快速CI保留原合成Native测试，不能将继承CI虚报为全程零Native。原R3～R13源码、证据、P1、Stage B、九/十二指标、MCP与生产默认未改。
