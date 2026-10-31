# R11 R15 R4｜3850mm房间的柜前站位与支廊协调

TASK_ID=V2_2_2_R11_R15_R4_LOCAL_CLEARANCE_IMPROVEMENT
BASE_HEAD=b8e6e19f83a44b0bbba76ced2538372a8cb23763

## 结论与范围

六项预声明检查中，满足原完整条件流程和所有已声明100mm余量家族的最小位移方案为 **R4-02**。这是测试集合内最小站距位移，不是全局最优，也不是现场工程批准。
R4-02：柜前站距480→515mm，柜前支廊中心线2440→2475mm；房间26331×3850mm、11台完整850×390×1800mm十门柜、22列110格、两班各53人、53人初始同时在室、450×650×1800行走人体、600×900×1800更衣体积、1300mm通道、200mm等待间隔、原两处1500mm Portal与所有53本位均不动。没有新增建筑面积。
两班分别重新完成全部53人进入—到本人柜位—开柜取衣—关柜—站立更衣—开柜存物—关柜—离室。两种原90°门扇假设分别检查212次人员开柜，原碰撞校核全部保留。
**条件距离100mm不是实测操作净距。100mm为未批准敏感性目标，不是规范下限。** 实际铰链/厚度/把手、弯腰伸手携衣、格口净尺寸、五层取放与卫生分隔仍INPUT_REQUIRED；外部Site/Access和扩大后3850mm房间的整厂适用性没有因本轮室内改进升级。

## 局部尺寸链

基准S1/E110/OPEN_FOR_RETRIEVE，U01-L-T1-DOOR与S1-P001。柜前缘y560mm，条件门扇最北边560+400+15=975mm；原人体y1040..1690mm，原关柜更衣体积y790..1690mm。
只退人35mm：人体y1075..1725mm，门距1075−975=100mm；支廊南缘不变1790mm，更衣/静态人体至支廊只剩1790−1725=65mm。该项是必要断面负对照，未生成完整布局或成功见证；不把未达100目标称为碰撞或全局不可行。
同步移支廊35mm：支廊y1825..3125mm，更衣至廊1825−1725=100mm；北侧本位下缘3225mm，本位至廊3225−3125=100mm；北侧本位上缘3675mm至完成面3820mm仍145mm。
在保持原北侧本位的这个截面中，门距要求给出人员位移≥35，活动至廊要求支廊位移≥人员位移，北侧本位至廊要求支廊位移≤35；因此该截面下35/35是同时满足目标的边界值。它不替代完整路径和事件校核。

## 六项对照（含原基线及一个断面负对照）

|编号|人员/支廊/北侧本位位移mm|本人门距 / 全对象最小解析距离mm|更衣至廊 / 北侧本位至廊mm|两班完成|完整流程与全部已声明100mm目标|
|---|---|---|---|---|---|
|R4-00|0 / 0 / 0|[65.0, 65.0] / [65.0, 65.0]|100 / 135|[53, 53]|CONDITIONAL_FULL_FLOW_COMPLETE；100目标=False|
|R4-01|35 / 0 / 0|None / None|65 / 135|[]|NOT_EVALUATED_SECTION_NEGATIVE_CONTROL；100目标=False|
|R4-02|35 / 35 / 0|[100.0, 100.0] / [100.0, 100.0]|100 / 100|[53, 53]|CONDITIONAL_FULL_FLOW_COMPLETE；100目标=True|
|R4-03|50 / 50 / 0|[115.0, 115.0] / [115.0, 115.0]|100 / 85|[53, 53]|CONDITIONAL_FULL_FLOW_COMPLETE；100目标=False|
|R4-04|50 / 50 / 15|[115.0, 115.0] / [115.0, 115.0]|100 / 100|[53, 53]|CONDITIONAL_FULL_FLOW_COMPLETE；100目标=True|
|R4-05|80 / 80 / 45|[145.0, 145.0] / [117.0, 117.0]|100 / 100|[53, 53]|CONDITIONAL_FULL_FLOW_COMPLETE；100目标=True|

R4-03实际两班流程仍完成，但北侧至廊仅85mm，不能以门距115mm宣称全部达标。R4-04将北侧行按新支廊边界+100mm并与东侧行保持200mm间隔的公式生成，北移15mm；R4-05北移45mm。它们没有修改既有成功事件坐标，而是先改变候选输入和布局，再重新生成快照、路径、动作与证明。
R4-05本人门距145mm，但所有对象的真正保守模型最小解析距离是117mm（邻柜限制），不能把145mm写成全局最小。较大位移还减少了未批准的600mm水平可达参考差值，且消耗北侧余量；因此不作为最小调整推荐。

## 原有流程、通道与距离复核

五套实际几何（含零位移控制）均通过原validate_use与activity_proof静态检查，并调用原closed_door_flow/simulate_sizing_shift、relayout_transfer、portal_crossing。_schedule保留原完整柜列/人员绑定及交错排序，快照由原sizing_snapshot按新站距生成，支廊由相同参数自动联动。没有修改上述历史代码或工程判据。
所有未完成人员在连续运动证明里始终作为碰撞对象保留。每班初始53人；完成/服务身份集合均为53，全部进入、两次取存开柜、更衣、离室记录保留。关门后才移动或更衣；没有将静态不重叠升级为真实人体动作验证。
每种门假设、每套实际几何对原事件重新执行check_flow_doors：110个独立门身份、106个独立人员格口、212次必要开柜；另对每次开门的现场人员与其他柜体逐体积运行原certified_sweep_distance，共8148次距离核对/配置。距离是原保守四分之一圆盘加厚度模型的解析值，不依赖简化扫掠盒对任意位置都准确。原door_hits_box碰撞器没有替换。
原闭门余量、人员至通道、更衣至通道、转身方形至通道、等待间距和门扇距离分别保存。R4-02最小已声明空间余量100mm；人员运动时进入通道是预期通行，不声称每种运动都具有统一100mm人体膨胀缓冲。原Portal宽减通道宽为200mm，左右各100mm。

## 证据和复现

- review-summary.json：六项状态、两班人数、余量家族、逐门最小值和见证Hash。
- full-witnesses.json.gz：所有新几何、完整事件、连续路径扫掠、原校核输出、目标未达记录。
- coordinate-difference.json：房间/柜体/Portal、本位、站位、支廊、路线和活动区变化。
- R4-02-plan.svg / R4-02-difference.svg / R4-02-section.svg：完整平面、柜区叠加和最不利事件断面，均取实际输出坐标。
- source-manifest.json：原157个来源/衍生文件与新增计算代码Hash；R15-03原见证单独绑定。
- ../r11-r15-ten-door-local-relayout-r1/：原12组及失败轨迹原样保留，不重跑原生成器。

复现（输出目录必须不存在）：

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r15_r4_clearance_review.py --output ../artifacts/r15-r4-fresh-review
```

生成器在运行前通过既有启动级保护重新执行，父子Python均禁用两种Native API；只接受固定六项目录，无照片参数、无MAIN、Store或Claim入口。定向测试见docs/evidence/v2.2.2/r11-r15-r4-local-clearance-validation/。自动快速CI继续包含原有合成Native测试，不能把整条继承CI虚报为零Native。

## 待确认条件与执行状态

实际柜门铰链/角度/厚度/把手、内净格口与衣物分隔、人体取放和穿脱动作、员工适配、固定维护和施工公差、洁污流程、实际房门与外部Access均待工程确认。站距515mm仅在既有600mm参考以内，不等于真实伸入柜内可达。
照片R15 R2暂停NOT_EVALUATED；不搜索或验证图片，不改变旧不匹配记录。原P1、Stage B、九/十二比较器、生产默认、历史MAIN与R9边界异常均不改。

ACTUAL_CALIBRATION=INPUT_REQUIRED
ENGINEERING_APPROVAL=NOT_EVALUATED
FACTORY_APPLICABILITY=NOT_EVALUATED
NEW_NATIVE_SOLVES=0
NEW_MAIN=false
NEW_REAL_GRANT_CLAIM=false
FULL_CI=NOT_REQUESTED
READY=false
MERGE=false
DEPLOY=false
