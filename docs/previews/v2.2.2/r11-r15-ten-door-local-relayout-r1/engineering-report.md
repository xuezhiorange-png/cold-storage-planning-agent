# R11 R15 · 11台十门柜有限重排和柜门距离复核

TASK_ID=V2_2_2_R11_R15_TEN_DOOR_LOCKER_LOCAL_RELAYOUT_R1
BASE_HEAD=784e87e1e1307b6379214903da6b2fcc393a244d

## 结论

有限检查12组（硬上限12，不超过36）；完成两班各53人联合条件流程的组合：['R15-03', 'R15-05', 'R15-07', 'R15-09', 'R15-11']。选作坐标变化较少的评审对象：R15-03。
静态本位、闭门运动、逐门开启与100mm目标分别报告。新完成组的柜门条件下界为65mm，仍小于100mm目标；没有降低目标、人体尺寸、53人设计基准或1300mm有效通道。不能宣称全部严格空间余量满足或实际功能获批。

## 照片来源

Owner提供文件名 IMG_0875.jpeg 及期望SHA256 `833c674259d29129d75703c37c6eb532b360d09647f3e221f6cce3951b41ccaa`；原始字节独立核对状态：`INPUT_REQUIRED_ORIGINAL_PHOTO_FILE_MISSING`，实际字节Hash=`None`。
原件未取得时保持照片INPUT_REQUIRED，不把文字Hash写成原图已验证。不公开、嵌入或复制原照片。独立补充记录关联R14选型来源，不覆盖R14。图片标称400×360×320mm不是内部净格尺寸；照片即使核对成功也不证明铰链、门厚、开启角度或储物卫生。

## 有限几何与真实流程

只检查南侧网格相位（旧网格/按南门通道边对齐/额外目标退让）、北侧本位行（旧位置/对齐东侧等待行间隔）、两种行填充顺序的3×2×2组合。柜体、柜列、格口分配、原两处Portal、全部参数及建筑边界保持不变。53静态本位成立的每组都重新调用原连续运动与完整两班流程，不因动态失败跳过或重写结果。
北侧行的对齐由实际东侧本位上边界加200mm等待间隔得到，不使用历史人员坐标作为强制解。所有本位和路由都由本次候选生成。不同填充顺序会改变真实人员对应本位；3个NORTH_FIRST组合静态53通过却在进入/旋转接近路径碰到仍在场的人员，原错误及具体扫掠体积保留。

|组合|本位|两班完成|联合条件流程|最低下界/目标|
|---|---:|---|---|---|
|R15-01|52|[]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|
|R15-02|48|[]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|
|R15-03|53|[53, 53]|CONDITIONAL_COMBINED_FLOW_PASS|65/100mm；满足=False|
|R15-04|53|[0, 0]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|
|R15-05|53|[53, 53]|CONDITIONAL_COMBINED_FLOW_PASS|65/100mm；满足=False|
|R15-06|49|[]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|
|R15-07|53|[53, 53]|CONDITIONAL_COMBINED_FLOW_PASS|65/100mm；满足=False|
|R15-08|53|[0, 0]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|
|R15-09|53|[53, 53]|CONDITIONAL_COMBINED_FLOW_PASS|65/100mm；满足=False|
|R15-10|49|[]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|
|R15-11|53|[53, 53]|CONDITIONAL_COMBINED_FLOW_PASS|65/100mm；满足=False|
|R15-12|53|[0, 0]|NOT_EVALUATED_INCOMPLETE_GEOMETRY_OR_FLOW|None/100mm；满足=False|

每个完成方案均保留11台完整850×390×1800mm柜、22列110格、每班55格（53人+2备用），U06左右列分配不同班次且柜体不拆。两班分别初始53人、完成53人；每人取放各一次，共212个人开门事件；ALL_LEFT与MIRRORED分别新算。使用原始人员连续路径/全高旋转方形包络、净通道、柜体与其他剩余人员碰撞、Portal及独立三维柜门校核。柜门关闭后才移动，更衣600×900活动与开柜450×650运输人体是不同工序，不能声称任意动作/同时开柜均成立。

## 15mm独立解析审查

R14最不利：第一班E110、S1-B01、OPEN_FOR_RETRIEVE，U01-L-T1-DOOR（第一层z100..420mm），对应S1-P001（人体[795,910,0,1245,1560,1800]mm），假设左铰链[807,480]mm、叶宽400mm、保守厚度15mm、90°。同期开门还包括U02/U03/U04的左列第一层；实际通道和其他人员在原事件中逐项保留。
新距离函数不改原碰撞器。原模型是四分之一圆盘与[-厚度,+厚度]方形的Minkowski和；把厚度方形移到目标矩形后，求目标至两条半径线段和圆弧的最小距离。整数平方根提供0.001mm包络，绘图折线不参与证明。在最不利事件中，原15mm包围盒下界与这个保守厚度模型的解析距离恰好相等（[15000,15000]×0.001mm），原解析碰撞为false；因此不能借更紧算法把它提升到50mm。该距离也不等于真实五金或真实人体动作的可用净距。50mm仍是未批准敏感性目标，不是规范。
完整事件、门层/铰链/扫掠、人体体积、更衣阶段、保留通道及同时打开门在clearance-analysis.json和局部比例图中提供。实际铰链、厚度、角度与人体活动未批准，真实柜门功能保持INPUT_REQUIRED。

## 保留历史与外部边界

R14原20/20目标50的C、3850均53人条件流程完成、柜门15mm下界；30/40目标100的C38本位、385052本位原样保留。新R15见证及Hash独立保存。有限12组不是全局搜索，不能由模板失败推出房间全局不可行。
本任务不扩大原反事实3850mm房间、不改原封存H5、R3～R14、P01/P02、P1、Stage B、九/十二比较器、MCP或生产默认。外部工程不从本次室内功能模拟升级为PASS。

## 待确认输入

- Original IMG_0875.jpeg bytes if unavailable
- Actual net compartment dimensions and clothing volume/separation/hygiene
- Reviewed hinges, mirroring, door thickness and opening angle
- Reviewed human activity/reach and simultaneous-opening sequence
- Actual fixing/maintenance/installation, finish and construction tolerances
- External Site/Access and room door hardware

ACTUAL_CALIBRATION=INPUT_REQUIRED
ENGINEERING_APPROVAL=NOT_EVALUATED
FACTORY_APPLICABILITY=NOT_EVALUATED

本地显式白名单与生成器使用父子Python启动级Native禁用。自动快速CI保留原合成Native，不能声称整个继承CI零Native。没有新增20t Native、MAIN、真实Grant/Claim或正式完整CI，不Ready/Merge/Deploy。
