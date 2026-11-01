# 自主布局V1.2 · R1工程补正

`V2_2_2_AUTONOMOUS_PROCESS_FLOW_CONTINUITY_R1 / R1_CORRECTION_1`。审核基线 `278fdaaf291eeb05900201977a623c4e2ddaacfe`，计算器 `autonomous-process-continuity@1.2.2`。在原PR #339正常追加，PR #338保持不变。

[整厂PDF](autonomous-layout-A12.pdf) · [PNG](autonomous-layout-A12.png) · [SVG](autonomous-layout-A12.svg) · [局部放大](A12-process-detail.png) · [评审HTML](autonomous-layout-review.html)

[主产品及支线图](main-product-logistics.pdf) · [五机六线供箱图](six-line-case-supply.pdf) · [同次原始A12](autonomous-layout-A12.json) · [工艺明细](process-detail.md)

## 已实现的补正

- **A：次果和冻果**：条件分流口分别绑定PACK-01、PACK-02，食品周转容器送至WORK-PACK-01/02组托，经原2400mm P1门洞、2500mm主通道，交接至实际库位PAL-004/PAL-005。其他库位仍占用，源载荷与该批次预留目标分别处理。分流口、容器、组托及冻果实际工艺仍需厂家/工艺确认；不是设备接口批准。
- **B：57个显式交接**：逐个保存前后载荷/载具、参考点、载荷锚点、接触位置、真实投影连接、操作空间及状态。RAW-UNLOAD的750mm参考点差没有消失，另有950mm载荷锚点差、完整投影连接和操作人员绕托路径；人工可达/取放/卸料方式仍为`CONDITIONAL_OPERATION_ASSUMED / INPUT_REQUIRED`。包装机6段、封膜组件4段、短交接5段的状态均不再冒充厂家内部工艺已验证。
- **C：集中全量验收**：六线全部、三条辅助流、最终选定的五机六线供箱、14缓冲连接、每个载具转换、全部原几何/Authority/Access/货位/条件更衣与16项原通行功能均须通过相应级别。设备或端点移动后，旧证据失效。非选用的备用候选失败不误伤已连接选择。
- **D：重新覆盖10+6项**：按当前房间、设备、全部货位、柱体及人员位置，重新运行原室内全宽和仓储门洞谓词。10项室内路线、6项仓储接口均恢复；原V1.1仅复用需求身份，不继承旧PASS。

状态：`CONDITIONAL_PROCESS_CANDIDATE`，六线6/6，辅助流PACKAGING/SECONDARY/FROZEN三条条件连接。完整P2D、Truck、实际工程批准、车辆运动学、同时交通、20t吞吐和现场功能仍未成立。

## 数量和定位

12区、7 MUST、非货车Access 11/11、单连通零孔洞；六线、五台折箱机、11台十门柜、一级18/二级12预冷位、4段封膜设备全部保留。两班53人原条件模型不变。

包材67、成品324、原果45、次果21、冻果36，合计493货位，未用最低容量替代原实际容量。14待冷位、6线端托位、1卸料托位另计，非仓储货位。

原87条路线：最终选用63条、探索备用24条。新增次果/冻果运输4条，合计91条，选用67条、备用24条。10条机内投影与5条短交接是选用集合的子集，不能与选用/备用数量重复相加。[机器可读分类](route-selection.json)。图中各线长度为运输/机内参考段合计，跨载具交接载荷路径另列，不能拼成单一车辆里程。

为恢复原2500mm闭合障碍通行谓词，四台折箱机各沿Y向外移20mm，中部物理间隔2500→2540mm；仍保留2500mm净通道，外围非通行间隙50→30mm。这是待厂家安装复核的定位条件，不是新安装标准。房间坐标、两级预冷位置、现有封膜扩展及原绕柱路径保留。

[完整交接/载具状态](process-interfaces.json) · [全量门禁](process-admission.json) · [16项对应表](v11-function-coverage.json) · [全部设备坐标](equipment-placement.csv)

## 软件验证

原39项工艺测试扩展至85项，最后一次完整单次运行85/85通过、零跳过。其中覆盖六条线任一失败、两条支线缺失、每条选中供箱失败、交接中断/锚点/载具/路径错误、移动设备后旧证据、旧通行缺失/重复/失败、机内状态冒充几何批准、重复补料/缓冲连接、未选备用失败对照，以及载荷纵向投影和转角包络反例。

[最终85项完整JUnit](r1-final-85-junit.xml) · [既有与架构白名单849通过/16原有跳过](r1-retained-whitelist-junit.xml) · [65项CI契约](r1-ci-contracts.txt) · [完整验证摘要](r1-correction-validation.json)

后续逐项几何复核补正了交接载荷方向：横向600×400、纵向400×600mm，直角转移另保留722mm方包络；这仍是未批准载荷的条件性投影，不是实际车辆或人体运动学。57项交接重新计算仍成立，JSON逐段保存宽深和拐角。早期[77项](r1-process-main-junit.xml)和[4项](r1-strict-levels-junit.xml)观察保留，最终以85项完整运行及同次新候选为准。

首次测试有1项断言把2540mm物理间隔误当2500mm保留通道；修正为分别核对两者，未放宽原障碍谓词。[首轮原始记录](r1-first-test-attempt.txt)

Ruff、Format1176文件、Mypy545文件（含入口）及差异检查通过。三张PDF均实际841×594mm、1:200，PNG6623×4678，完成实际渲染复核。

7→8天依然实际重算并失败：初始成品354位（P1最低360，原新输入候选364），北移尝试只能360/364，且原预留通道与3根柱体冲突；仓储接口未全部闭环。未强行改成成功、不宣称全局不可行。[最终复算真实失败](r1-final-input-change-regression.json)，[本轮前次失败](r1-input-change-regression.json)亦保留。原[历史输入变化证据](input-change-regression.json)、[容量修正](capacity-correction.json)及旧测试文件保留。

## 复算

在backend目录使用Python3.12锁定依赖，输出目录预先不存在：

```bash
PATH="$PWD/.venv/bin:$PATH" \
PYTHONPATH=tests/functional_native_guard:src:scripts \
R11_FUNCTIONAL_GUARD_AUDIT=/tmp/autonomous-v12-r1-guard \
.venv/bin/python scripts/generate_autonomous_process_layout.py \
  --input ../docs/previews/v2.2.2/autonomous-factory-layout-v12/inputs/project-input.json \
  --parameters ../docs/previews/v2.2.2/autonomous-factory-layout-v12/inputs/process-parameters.json \
  --output /tmp/autonomous-v12-r1-new
```

可增加`--finished-storage-days 8 --no-drawings`复算实际失败。生成只读取结构、业务、设备规格，不读取Owner/V2/V3/旧候选坐标；相同输入确定性回归保留。

## 工程条件

食品容器/实际分流口、卸料及原果输送、包装/封膜机内部过程、组托拆托复托、人体动作、搬运载荷和转向、共用通道调度、次果/冻果工艺及H5柜门/洁污条件继续`INPUT_REQUIRED`。本轮仅证明分级条件几何，不作实际生产、厂家、Truck或P2D批准。

本地新增Native执行0，父子防护保留；负向solve/Solve请求在底层调用前拒绝。没有MAIN、真实Grant/Claim、正式CI、Ready/Merge/Deploy。现有自动ci-fast保留全部继承合成Native，不能将整个CI宣称为零Native。新HEAD远端85项和最终门禁由本PR Checks的终态及JUnit回执确认。
