# V1.3 · 当前业务输入驱动的整厂再布局

TASK_ID: `V2_2_2_AUTONOMOUS_ADAPTIVE_LAYOUT_REGENERATION_R1`

基线为PR #339的 `be6076d3cc937e0bf192e27120ee00b8fdfb4ec3`。
本目录仅增加独立预览；原PR与V1.2的8天真实失败证据不修改。

## 实际结果

7天与8天分别从当前Plan/P1、建筑结构、工艺及设备规格重新生成两套条件性候选。
没有读入历史房间或设备世界坐标，也没有把此前北移量写入新策略。

|工况|当前P1成品网格/最低位|保留成品位|保留总储位|合格空间候选|实际节点/上限|重型流水线尝试/上限|
|---|---:|---:|---:|---:|---:|---:|
|7天|324 / 315|324|493|2|6 / 24|4 / 8|
|8天|364 / 360|364|533|2|5 / 24|2 / 8|

每套合格结果均重新计算12区、原7条MUST、11条非货车Access、全部设备与柱体避让、
原仓储有序取放、六条主产品链、三条辅助物料支线、57项交接、10项室内通行、
6项仓储接口及两班53人更衣条件流程。
不以360位最低容量替代8天364网格；14缓冲位与6包装托盘工作位不重复计入储位。

8天成品库由当前P1确定为21200×31200mm（661.440㎡）；
7天为18600×32400mm（602.640㎡），固定房间仍遵守各自原Authority及允许旋转。

|8天候选|空间变化|Footprint面积㎡|选中运输参考段合计m|转弯|潜在中心线交会|
|---|---|---:|---:|---:|---:|
|A13-A|保留覆膜间上游接缝，延伸柔性房间并移位下游|2519.380816|1777.134|284|44|
|A13-B|下游房间组联动移位|2481.630016|1777.780|286|44|

A比B少0.646m参考段和2次转弯，但多37.750800㎡，应按工程取舍审阅。
参考段合计不是单车里程；中心线交会不是已证实的同时交通碰撞。
字典序排序仅作用于全量准入后的候选，不改原九/十二指标比较器，亦不宣称正式Pareto。
7→8天P1不同，禁止跨工况冒充正式质量改善。

生成结束后的独立对照还确认：7天A13-B的12区和全部设备/储位矩形与V1.2已通过方案一致，
选中运输参考段1777.780m、286次转弯、Footprint2422.830016㎡及44处潜在中心线交会均未变化。
该对照仅在生成后读取旧结果，未将其传入生成器；断开历史文件的重复生成测试另行验证。
见`validation/seven-day-independent-baseline-comparison.json`。

## 本轮补齐的能力

- 当前P1网格、最低位、面积来源Hash及预冷位置数直接绑定当前计算结果；无通用324/493硬编码。
- 当前房间搜索提供初始房间，原方案不直接获得工艺成功状态。
- 候选包括允许的固定房间旋转、真实柱边事件位置、柔性连接房间延伸及生产组重定位；
  柱边100/300/600mm为未批准搜索选择，不是新增硬约束。
- 仓储托盘旋转时，原间距1200×1300一同旋转为1300×1200；
  实体仍1000×1200mm、载荷周边50mm、仓储主通道3000mm、工艺主通道2500mm。
- 实际库位端点由当前朝向、门洞和可达前排选择；旋转载荷的参考点按真实法向尺寸重新计算。
  原1300×1800mm整车与2222mm转向假设不缩小。
- 7天实际出现入库/出货物流失败，记录对象坐标与通道需求，尝试更换排列和端点，
  最终从另一空间候选恢复；失败尝试保留，未计入合格候选。
- 全部设备、门洞、路线、交接和通行证据在每个候选内重建；设备移动后旧证据会被拒绝。

搜索有明确节点与重型尝试预算，达到候选数量即停止。
初始房间搜索的各次独立节点统计保留在结果中，不与24个反馈候选节点混淆。
`operation_counts`是选定库存见证计数和逐路线记录的网格节点计数，缓存共用路径可重复出现；
它们不是全部CPU操作、计费Work或Stage A/B资源份额。生成耗时和进程高水位另列。
本轮不发行、消费或复用MAIN预算，不新建授权体系。

## 文件与复算

`results/autonomous-adaptive-review.html`可本地打开，切换7/8天四张图；
各工况目录保存完整原始JSON、全部工艺网络、真实设备CSV、候选失败坐标、源输入及P1需求。
图纸A1横版841×594mm、1:200，PNG6623×4678；房间、设备及线路均投影自同次JSON。

在backend中以Python3.12锁定依赖执行：

```bash
PATH="$PWD/.venv/bin:$PATH" \
PYTHONPATH=tests/functional_native_guard:src:scripts \
R11_FUNCTIONAL_GUARD_AUDIT=/tmp/autonomous-v13-guard \
uv run python scripts/generate_autonomous_adaptive_layout.py \
  --input ../docs/previews/v2.2.2/autonomous-adaptive-layout-v13/inputs/project-input.json \
  --parameters ../docs/previews/v2.2.2/autonomous-adaptive-layout-v13/inputs/process-parameters.json \
  --search-configuration ../docs/previews/v2.2.2/autonomous-adaptive-layout-v13/inputs/search-configuration.json \
  --finished-storage-days 7 8 \
  --output /tmp/autonomous-v13-new-output
```

输出目录须不存在。父子Python防护同时阻止`solve`和`Solve`。
本地只运行明确列出的自主布局、架构及CI契约白名单。
正常自动ci-fast保留原有合成Native测试；不能把整个CI称为零Native。

## 工程边界

状态为`CONDITIONAL_PROCESS_CANDIDATE`；机内输送、人工接触交接与条件接口仍需厂家/工艺资料。
真实搬运工具运动学、共用通道调度、吞吐、H5实际柜门和人体及洁污条件未批准。
Truck、完整P2D、工程批准和整厂最终适用性仍未成立。
这是自主生成能力的条件性概念方案，不是施工图或已批准整厂设计。

Native新执行0；无MAIN、真实Grant/Claim、正式完整CI、Ready、Merge或Deploy。
生产默认、MCP、原P1面积Authority、Stage B及正式九/十二指标未改。
