# 自主整厂布局生成 V1

任务：`V2_2_2_AUTONOMOUS_FACTORY_LAYOUT_GENERATION_V1`。开发基线为PR #335的
`b8e6e19f83a44b0bbba76ced2538372a8cb23763`。这是独立、显式启用的概念设计入口，
不接入生产MCP或默认规划路径，不是施工图或完整P2D验收结果。

## 输入与坐标

唯一生成输入是[inputs/project-input.json](inputs/project-input.json)。它包含业务输入、
原建筑结构图元、尺寸规格和有限搜索配置，不包含历史房间、设备世界坐标、候选或初始Hint。
生成时不读取Owner PDF、V2/V3图或历史MAIN目录；原PDF仅在本次输入整理时提取结构与测量设备外形。

Owner原PDF为`02、新哨单体融合方案.pdf`，实际字节SHA256：
`a2654279dbdefac8e225d7554e35463902e4abca1b4769418cd83e3a5ff6d139`。
不将原始PDF公开提交。结构输入逐项保留原路径ID与测量转换依据。

- 世界坐标X向东、Y向北；单位整数毫米。
- 原PDF显示坐标原点为`(584,2070.8399963378906)`点；每点
  `108000/2246.16015625`毫米；Y轴反向。
- 1～19轴：0～108000mm，18跨×6000mm；A～G的Y值在输入中逐项列出。
- 主厂房墙内净矩形：`[98,12019,107902,72781]`mm。不是土地Site，也不是轴线外包尺寸。
- 保留原WALL墙线及77个原COLUMN对象。北侧附属/雨棚、南侧装卸范围没有被当成新增房间用地。
- Owner本次明确允许房间内保留柱体。新房间边线不能切柱；设备及通道仍检查柱体。
  房间毛面积、柱占面积、扣柱面积分别输出。毛面积达到P1不证明功能净面积或货位操作满足。
- 原WALL-MOVE功能隔墙没有作为房间生成模板；新概念分区需要后续建筑设计确认。
- 三处南侧开口来自原墙线端点。进料、人员、出货的用途分配是设计建议，未声称门型或实际用途已批准。
- 整数化是计算单位，不是实测精度承诺；原PDF约0.12点的矢量误差约为5.8mm。

## 实际复用与新增范围

复用原`ColdRoomZonePlanner`、P1 handoff、Dimension Authority、Site校核、
`PlacedRectangleV1`、精确面积补足、原7条MUST/不重叠谓词、原Access路由谓词、
零孔洞占用轮廓计算。现有`composition_placement`在真实柱墙输入上进行过有界准备探查，
没有完成候选输出，记录为中断，不解释为工程无解。

新增的事件锚点搜索补充组合缺口：主工艺优先，有限P1尺寸/旋转/柔性尺寸采样、附件接触和入口侧偏好。
它不修改原面积计算或工程硬约束。LINEAR_BANDED、CENTRAL_PROCESS_CORE、
PROCESS_SPINE_WITH_PERIPHERAL_BANKS在此是搜索偏好，不能冒充已通过正式V2组织合同。
不同输出以接触关系图Hash区分；平移、镜像、90度旋转不会改变该签名。

原完整`svg_projection`和候选选择要求完整P2D，故不把条件候选伪装成其输入。
新增投影器只读取同次生成JSON；房间、设备、门洞、路径不能在绘图后手工移动。
PDF/SVG均为A1横版841×594mm，1:200，20m校尺段纸面100mm；PNG长边6623px。

设备世界坐标由房间局部规则重新生成。来源只继承尺寸/数量：6条输送主体、5台折箱机、
4段纸箱封膜线、一级周转筐与二级纸箱托盘预冷、存储货位和11台完整十门柜。
所有设备主体逐一检查房间、柱体与其他主体。冲突项保留在拒绝记录，不能靠减少需求算通过。
柜体布置有横/竖两种有限候选，避让当次生成的Portal预留。柜门、53人运行等不在本轮验收范围。

Access结果分开报告：原房间级11条非货车要求；设备后门前/操作带；扣除设备和柱体的室内段。
完整宽度室内段仍使用原`_find_route`与精确安全谓词，每段最多24节点。
搜索耗尽不是不可行。室内段不自动证明变宽门喉、全货位取放、车辆回转或多人通行。
没有路线见证的地方不画成通过的直线。Truck、土地Site和完整P2D均未取得通过。

原面积规则中的成品10%冻果扣减被保留：20t/天、7天对应126000kg、315最低货位。
这不是20t/天全量成品7天的新增容量承诺。包材库、预冷等实际主体缺口在结果中保留。
所有设计参数、柜型、作业空间和安装条件继续按来源区分，未生成Owner工程批准。

## 复算

从本分支仓库根目录执行：

```bash
cd backend
uv sync --locked --python 3.12
PATH="$PWD/.venv/bin:$PATH" \
PYTHONPATH=tests/functional_native_guard:src:scripts \
R11_FUNCTIONAL_GUARD_AUDIT=/tmp/autonomous-layout-native-guard \
.venv/bin/python scripts/generate_autonomous_factory_layout.py \
  --input ../docs/previews/v2.2.2/autonomous-factory-layout-v1/inputs/project-input.json \
  --output /tmp/autonomous-factory-layout-v1
```

改变有效业务输入的回归B：在上述命令加
`--finished-storage-days 8 --output /tmp/autonomous-factory-layout-v1-days8`。
可用`--no-drawings`只生成新计算JSON/表格，仍重新计算面积与房间。
`--strict-columns`为完全避柱的有限负面对照，不改变原输入文件。

防护复用已有`functional_native_guard/sitecustomize.py`，父子进程均屏蔽两种Solve API。
新增代码没有CP-SAT、MAIN、Store或Claim路径。负测试只验证API请求被阻断，实际Native调用为0。
自动快速CI保留既有合成Native测试，不能将整次继承CI报告成零Native。

## 复用与限制

面积/P1绑定、有限房间搜索、设备局部坐标、碰撞检查和结果投影可以复用于具有相同12区合同的项目。
当前建筑转换和设备适配针对本项目；其他工厂需提供自己的建筑结构与设备规格。
未实现通用设备装配规划、全部货位搬运、Truck或完整工厂适用性验收。
本轮没有Native、MAIN、真实Grant/Claim、正式完整CI、Ready、Merge或Deploy。

详见生成的[方案比较](layout-comparison.md)、[交互评审](autonomous-layout-review.html)、
[生成结果](layout-generation-results.json)和[回归证据](regression-evidence.json)。
