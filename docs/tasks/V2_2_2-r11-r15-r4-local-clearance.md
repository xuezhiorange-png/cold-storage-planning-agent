# R11 R15 R4｜局部柜门间隙与支廊协调

TASK_ID=V2_2_2_R11_R15_R4_LOCAL_CLEARANCE_IMPROVEMENT

BASE_HEAD=b8e6e19f83a44b0bbba76ced2538372a8cb23763

Owner授权：在独立分支实施不超过6个局部调整检查、原非Native两班流程、定向测试、提交推送和独立Draft PR，允许既有自动快速CI。PR #335及所有历史证据不改。照片R15 R2暂停NOT_EVALUATED，不搜索、不读取、不重新验证照片，不提交照片。

固定26331×3850mm、11台850×390×1800mm完整十门柜、22列110格、两班各53人、53人初始在室、本人柜前站立、450×650×1800mm人体、600×900×1800mm活动、1300mm有效通道、200mm等候间隔、原两个1500mm Portal。柜体/格口班次身份不变。

只新增独立条件评审适配器，不接入生产。柜前站距及支廊位置为未批准局部变量；改变候选输入后重新由原快照、排班、连续运动、柜门和余量校核生成证据。不手工编辑成功动作的坐标或状态。

预声明六项：

|编号|柜前位移mm|支廊位移mm|北侧本位|范围|
|---|---:|---:|---|---|
|R4-00|0|0|原样|原65mm完整控制|
|R4-01|35|0|原样|仅必要断面负对照，无新布局/完整流程声称|
|R4-02|35|35|原样|原完整流程|
|R4-03|50|50|原样|原完整流程，保留85mm北侧余量不足|
|R4-04|50|50|按支廊+100mm及相邻本位200mm公式生成|原完整流程|
|R4-05|80|80|同公式|原完整流程|

R4-01单项断面虽门距达到100mm，更衣至通道只有65mm，必要目标条件已失败，不制造一套所谓已验收新布局。其余五套物理几何均重新执行两班53人连续进入、到柜、两次取存开柜、关门更衣及离室；两种既有90°门假设各212次开柜独立校核。未完成或未达目标的证据保留，不能当作全局不可行。

100mm仅为原未批准敏感性目标。实物门扇、人体动作、可达性、内净格和衣物卫生仍INPUT_REQUIRED。条件几何/完整流程/实际工程批准分别记录。最小调整结论只适用于有限测试集合，不是正式规范或全局最优。

报告：`docs/previews/v2.2.2/r11-r15-r4-local-clearance/`。

定向验证（输出目录必须不存在）：

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r15_r4_clearance_review.py --output ../artifacts/r15-r4-fresh-review
PYTHONPATH=src:scripts uv run python scripts/validate_r11_r15_r4_whitelist.py --evidence ../artifacts/r15-r4-directed-validation
```

两条命令均使用既有启动级Native禁用重新执行。父子进程禁止两种Solve API，不运行Stage B/历史Native目录。自动快速CI只追加R4测试文件，全部原测试和继承合成Native保留，并核对精确HEAD JUnit，不能把整条继承CI说成零Native。

禁止：MAIN、Native求解、真实Grant/Claim、正式完整CI、Ready、Merge、Deploy。原P1、Stage B、九/十二比较器、MCP、生产默认、R9历史异常及既有PR全部保留。完成后停止，等待独立工程审核。
