# R10：整体空间组织软搜索，合成工程验证为 Tradeoff

TASK_ID=`V2_2_2_STAGE_B_R10_FUNCTIONAL_SPATIAL_ORGANIZATION_R1`

基线：`8b731d7ab2f7a0ae10f1c58c34a38d763284b271`，PR #317 保持不变。

## 结论

**已证明可以在完整原工程合法性下，显著改变三个房间的实际形状；尚未证明整体空间组织优于真实 P04，也没有取得全面 Pareto 改善。**

R10 在完整合成场景中把 Changing 从 2×20m 改为 6.135×6.520m，同时把 Office 和 Coating 从条带改为近似紧凑矩形。不是 1mm 坐标变化，也不是只降低一个代理分数。但人员路线增长 11.163m，建筑面积增加 22.326730㎡；原九项和十二项均为 `QUALITY_TRADEOFF`。不能把本结果宣传为整厂真实改善。

P04 的真实 20×2m、40㎡仅为问题参照，未注入其坐标、几何 Hint 或目标尺寸。合成输入与 P04 不同，不做跨输入的正式 Pareto 比较。

## 最小实现

新策略：`StageBFunctionalSpatialOrganizationFairSolver`，位于 `stage_b_functional_spatial_organization.py`。

独立 Policy Hash：

`sha256:cb1e9516708056a8f113319872e57cc643f85cbbbca9a9be8d35200575a27b98`

只在本 Handoff 第一阶段候选经过原应用工程链验收并保存后启用：

1. `_organization_plan()` 复核源模型所有权、原 P1 面积来源、三房原有紧凑度定义、Office→Shipping MUST、Coating 前后工艺 MUST 和人员入口引用。
2. 复用已捕获 `r5_area_worst` 索引之前的原 13 项定义，逐项验证名称和正值域；没有全变量扫描或新的尺寸定义。
3. 先对 Changing、Office、Coating 各自原需求归一化紧凑度变量建立软分支顺序，再尝试 Changing 宽深、面向当前入口的实体边、入口切向位置和合法门面。
4. 入口轴线、方向、切向偏好由当前 Site/入口计算。Coating 不使用入口位置偏好，仍由原工艺和 Access/MUST 关系控制；Office→Shipping 原关系保留。
5. 在原模型上仅改 `search_strategy` 元数据，保存原 R7 搜索策略作为后缀。原目标、所有变量/约束/域、当前物理 Hint 均不变。没有局部模型复制、额外 Solve 或新资源份额。

原 R7 首次可行、Reference 构模、物理 Hint、独立搜索阈值、精确几何枚举、九/十二指标和有效基线保留全部继承。旧 R7/R9 策略不自动选择 R10；旧 Policy 无法满足其显式策略绑定。没有新增 Runner、Store、Owner Scope 或授权体系。

`apply_functional_spatial_organization()` 在写入前完成检查和整笔元数据计费。新准备 Work 为 247：需求读取3、定义引用13、MUST引用3、路线引用10、实体变量引用11、搜索元数据207。真实工作记在原 Ledger，没有折扣计费或校核缓存。

### 物理可行域与工程边界

移除新策略的搜索元数据后，完整模型 Proto（含变量域、约束、目标、Hint）逐字相同。因此没有增加面积上限、最小宽度、比例限制、坐标或新门洞；原合法物理赋值集合不变。

柜体、内部更衣通行、消防与施工适用性在现有 Authority 中缺少足以独立证明的输入。本轮没有发明柜宽或3m下限，`furniture_layout_validated=false`；紧凑外形不等于这些项目已经验收。

## 合成场景与执行口径

复用 `tests/r9_full_engineering_synthetic.py`：由原 Plan/P1/Typed Site/Process Graph 正式构建的 1000kg 合成输入，完整12区、7 MUST、12 Access中的11条非货车要求、原包装接口和障碍物。

新测试辅助 `tests/r10_spatial_organization_experiment.py` 只为同条件测试定义有限功能区 bay：Changing 位于 Sorting 南侧、Office 位于 Shipping 南侧，Coating 保持预冷→Coating→成品工艺位置；放开三房宽深与 Changing 横向位置，并联动成品/发货的横向位置。两臂使用完全相同的 bay 约束，未改 P1。bay 的有限外包络是合成场景条件，不是生产最小尺寸/最大面积规则，也不是证明了整个原始模型所有布局的性能。

调用原 `generate_global_composition_candidates()` 和 `_eligible()`；没有 Mock 验收器、伪造 `ENGINEERING_ACCEPTED` 或直接喂已知布局。所有基线和后续几何均由实际 Native 产生，经过原独立几何、原生 Access、Site、Footprint、单连通与零孔洞校核。Truck/P2D 不计完整通过。

每臂上限：Native8s、Elapsed85s、Work600000、RSS512MiB、12次Native、6次完整赋值检查、单要求Host20000。沿用原合成适配器的每次 Solve 前后检查及80ms安全预留；没有延长预算。正式完整模型为 Worker1/Seed3/PARTIAL_FIXED_SEARCH，保留默认 Presolve=true，原日志实际有 `Starting presolve`。四次预热保持原 Seed0/原搜索配置，未改成测试专用无 Presolve。

先进行一组并行探索对照并完整保留，再以相同源码顺序复核，两次精确工程指标序列相同。下表采用顺序复核；不能把并行运行时间当独立性能比较，也不把两组结果当两次真实 MAIN。

## 同条件结果

|实际指标|共同第一阶段基线|R10实际组织候选|变化|
|---|---:|---:|---:|
|Changing 实体X宽×Y深m|2.000×20.000|6.135×6.520|米级形状改变|
|Changing 需求/实际面积㎡|40 / 40|40 / 40.000200|+0.000200|
|Changing 长宽比|10|1.062755|下降|
|Office 实体X宽×Y深m|4.000×15.000|7.983×7.516|米级形状改变|
|Office 需求/实际面积㎡|60 / 60|60 / 60.000228|+0.000228|
|Office 长宽比|3.750000|1.062134|下降|
|Coating 实体X宽×Y深m|5.000×16.000|8.674×9.223|米级形状改变|
|Coating 需求/实际面积㎡|80 / 80|80 / 80.000302|+0.000302|
|Coating 长宽比|3.200000|1.063293|下降|
|人员路线m|19.252|30.415|**+11.163**|
|人员转向|4|4|0|
|建筑面积㎡|568.014500|590.341230|**+22.326730**|
|建筑周长m|248.310|222.986|−25.324|
|轮廓转折 / 凹角|40 / 18|40 / 18|0 / 0|
|原九项 / 十二项|比较基线|**Tradeoff / Tradeoff**|同Handoff、同V2|

精确数值、原比较函数输出、候选 Hash 与工程校核字段见 [合成对照 JSON](evidence/stage-b-r10-functional-spatial-organization-r1/synthetic-comparison.json)。展示小数仅四舍五入，不改变正式比较容差；三房的微小面积增加在十二指标中仍记为恶化。

### 路线增长有具体几何原因

合成 bay 保持 Changing 北沿与 Sorting 南沿 y=30m 接合。原狭长房间向南延伸到 y=10m；紧凑后南门退到 y=23.480m。原实际门中心 x=40.750m，R10门中心 x=43.067m，横向靠近入口2.317m，却在纵向远离入口13.480m；原通道实际净增11.163m。不能将后退的房间深度当免费形状改善。

原路线仍有1mm偏移的合法通道段，本轮没有将其冒充有意义的组织变化。建筑面积主要增加于更长的2m人员廊，不能只看周长下降。Coating 在原工艺链内横向变宽、纵向变短；成品、发货及办公室随原邻接关系横向移动，未被强行拉向人员入口。

这证明“紧凑度优先的软顺序”能改变多房间空间，但入口相对位置及保留 Hint 仍没有保证路线协同。入口偏好目前是轴线/半场地顺序，不是真实最短路目标；此局限如实保留，没有为了报告成功而修改回调或正式质量函数。

### 与R9原机制的资源及产出比较

|顺序复核|R9资源受控路线策略|R10组织策略|
|---|---:|---:|
|第一完整模型 Proto SHA256|`cee516e4…b4f70`|相同|
|第一有效实体布局|相同|相同|
|验收有效见证数|4|3|
|原 geometry_hash 数|3|3|
|实际实体房间边界去重数|3|**2**|
|原V2组织数|1|1|
|Native秒（保守monotonic）|7.719030708|7.924393750|
|Native调用 / 完整检查|9 / 4|7 / 3|
|模型Work / 几何HostWork|156717 / 75214|90150 / 63372|
|总Work|231931|153522|
|局部复制Work / 局部Native调用|64637 / 1|**0 / 0**|
|搜索峰值RSS MiB|244.9375|228.203125|
|Elapsed秒（合成执行）|10.170302|10.138709|
|原始终态|后续UNKNOWN，无全局无解结论|Handoff份额结束，非项目不可行|

R9本合成场景仍保留其已证明的路线优化：15.005→14.504m。不得用R10的结果否认R9已有能力；本轮R10不执行这项复制。两臂的资源独立记账，相同上限，R9的复制没有挤占R10预算。

R10第三个见证只是将 Changing、Coating 的 nominal width/depth 与 rotation重新编码，实际实体边界、路线及质量指标均回到原基线。原 `geometry_hash` 因编码不同而不同，**不把它算第三套新的实体组织**，也不修改原Pool口径。R10只有一套相对基线实质不同的组织候选；没有证明有效几何获取效率提高。Work减少包含少一次验收与取消复制的影响，不宣传为全场景单位收益提升。

## 图纸与证据

三张图均由实际 Native 候选的原工程应用结果调用原绘图器导出；未移动几何。原模板固定的状态文字会错误显示 Truck/P2D 全部通过，评审图仅按既有导出做法校正状态文案，原 `.native.svg` 在本地证据目录保留，JSON状态为权威。

- [共同第一阶段实际基线 SVG](evidence/stage-b-r10-functional-spatial-organization-r1/baseline.svg)
- [R10实际紧凑组织候选 SVG](evidence/stage-b-r10-functional-spatial-organization-r1/organized.svg)
- [R9实际路线择优对照 SVG](evidence/stage-b-r10-functional-spatial-organization-r1/r9-route-control.svg)

本地完整证据位于 `artifacts/stage-b-r10-functional-spatial-organization-r1/`：两个对照组、每次原始日志/模型Proto、完整候选/验收/资源记录、`comparison.json`、`synthetic-inputs.json` 和 `synthetic-comparison.html`。绘图及离线汇总是搜索结束后的报告操作，未冒充Native搜索预算内的新求解。

## 验证与后续边界

新增测试验证完整模型物理Proto/目标/非空Hint不变、R7首次可行模型一致、动态四方向/入口半场地、无效引用及整笔预收费拒绝、旧Policy拒绝、基线与原比较/阈值继承、资源不足不安装偏好。自动快速CI加入该测试文件，沿用原资源测试独立进程。正式 `ci.yml` 未改。

本地：R10最终27项通过，既有关联策略/资源测试256项通过；架构在Python3.12下771通过、16项原有skip；CI契约65项通过；Ruff/Format/Mypy及YAML解析通过。首次组合回归中有一个新增测试的装配错误，修正测试上下文后，R10完整27项重新通过，原日志保留。Python3.14架构的两个历史AST指纹不一致与子进程Python路径错误，在仓库既有Python3.12环境复核消除，没有修改历史断言或生产代码。合成Native实测使用Python3.14.5 / OR-Tools9.15.6755，不能冒充Linux实测。

本次没有真实20t Native/MAIN、实际Grant/Claim、新Owner Scope、正式完整CI、生产默认修改或旧PR修改。冻结代码后提交独立Draft PR，等待工程评审。

**最终工程回答：房间形状实质改善已在完整合成工程链建立；入口路线与总建筑占用没有协同改善，不能认定优于真实P04的整体布局。当前交付为可审查的独立策略和明确Tradeoff证据，不是整厂质量成功证书。**
