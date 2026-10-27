# R10 R2：入口、Changing 与工艺前缘联动搜索

TASK_ID=`V2_2_2_STAGE_B_R10_ENTRANCE_COUPLED_SPATIAL_SEARCH_R2`

开发基线 PR318 `f7ea97f4cf0c48e287571c4f905af4abee64dd5f`。独立分支；PR317/318、历史证据及生产默认不变。

## 工程结论

**本受限合成工程场景已经取得本轮重点目标：房间比例改善，同时人员路线和建筑面积均不增加。** 共同有效基线的 Changing 为2.774×14.420m、40.001080㎡、比例5.198270；R2 C02为3.637×10.999m、40.003363㎡、比例3.024196。路线9.211→2.751m（−6.460m），建筑547.936073→535.018356㎡（−12.917717㎡），周长204.940→198.098m（−6.842m）；转向1、轮廓转折38、凹角17均不变。Office、Coating未恶化。

这不是用2×20m作为初始解或目标：新场景第一阶段自由得到2.774×14.420m，R2针对其自身基线比较。宽增加0.863m、深减少3.421m，属于米级实体组织改变。

C02与自身基线同Handoff、同V2；**原九项为 GEOMETRIC_PARETO_IMPROVEMENT，原十二项仍为 QUALITY_TRADEOFF**，因为 Changing 面积增加0.002283㎡。未调容差，未把重点目标达成写成十二项整体Pareto。不能据此宣称真实整厂改善、家具布置通过或Truck/P2D通过。

## 为什么原场景有局限，以及本轮改变了什么

PR318原固定场景及原图/报告完整保留：Changing北沿与Sorting南沿固定y=30m，Changing从2×20变6.135×6.520m时南门退后，路线+11.163m、建筑面积+22.326730㎡。这不是“更紧凑必然路线更差”的工程定律，而是该有限空间域和搜索结果的具体代价。

新场景仍由原正式合成Plan/P1、Typed Site和工艺图构造，12角色、7 MUST、12条P1 Access中的11条非货车全部保留。采用已有Sorting x/y作为可移动工艺脊线：x∈[38,48]m、y∈[12,36]m，相关预冷、包装、原料、缓冲、覆膜、成品、发货和Office按原工艺相对关系联动。Changing北沿等于Sorting南沿这个**相对接口**保留，已不固定世界y=30。Office仍与Shipping衔接；Coating仍位于原预冷→覆膜→成品链，未被强行移到人员入口。

有限测试还保留Changing相对Sorting x偏移[-4,+6]m及三功能房间的宽深测试范围，三个对照组完全一致。它只证明这个受限完整工程场景的搜索价值，不能代表所有工厂可行域；这些范围均不进入生产策略。设计几何整体平移0/−12m的两套独立原验收通过，用于验证场景允许真实平移，**从未作为Native Hint/Seed**。

## 最小算法变化

新增 `StageBEntranceCoupledSpatialFairSolver`，显式opt-in，继承原R7首次可行恢复机制。第一阶段、预热、模型构造、R5目标、有效物理Hint、严格改善回调、搜索阈值、几何切除、基线保存、九/十二指标与工程验收均继承不变。

仅在当前Handoff首套候选经原独立工程验收后，第二阶段读取当前已验收Hint中的**实际入口Portal**及Changing/Sorting中心。不是用场地中心或历史P04坐标。软顺序依次考虑：Changing入口侧边界、Sorting入口侧边界、两者朝当前入口的切向位置、Changing宽深、已有三房间P1归一化紧凑度、合法门面及原路线法向变量，随后保留原全部策略后缀。

只改 search_strategy：新增变量0、新增约束0、目标不变、原非空Hint不变。全部引用和Authority先核实，元数据读写成本整笔预收费后才重排。复制的只是小量搜索策略元数据；**不复制完整模型，不额外调用Solve**。没有新的房间宽度/比例/面积上限，旧策略、Owner Scope、Runner/Store与默认均未修改。

独立策略Hash：`sha256:fc0082de49eb1e289c487c2f88c4a873f73b3a553077102dc7dc1aa0e11afcf5`。R1仍为`sha256:cb1e9516708056a8f113319872e57cc643f85cbbbca9a9be8d35200575a27b98`；旧Policy不能自动选择R2。本轮无新Runner、授权体系或实际Grant/Claim。

## 三组同条件完整工程结果

所有记录为实际Native见证，经过原`generate_global_composition_candidates()`、`validate_global_geometry()`、`validate_generated_global_proposal()`、`validate_native_access_geometry()`、原Site/Footprint/Topology、`_eligible()`；没有Mock验收器、手写PASS或虚构ENGINEERING_ACCEPTED。每套有效见证12/12角色、7/7 MUST、11/11非货车Access、单连通、零孔洞。

|场景/臂/有效见证|Changing 宽×深m；面积㎡；比例|Office 宽×深m；比例|Coating 宽×深m；比例|人员m/转向|建筑㎡/周长m|转折/凹角|九项/十二项（相对自身基线）|
|---|---|---|---|---|---|---|---|
|r9/C01|2.774×14.42; 40.00108; 5.198270|8.917×6.729; 1.325160|5×16; 3.200000|9.211/1|547.936073/204.94|38/17|BASELINE|
|r9/C02|2.774×14.42; 40.00108; 5.198270|8.917×6.729; 1.325160|5×16; 3.200000|9.211/1|547.936073/204.94|38/17|NO_MEASURABLE_IMPROVEMENT/NO_MEASURABLE_IMPROVEMENT|
|r10_r1/C01|2.774×14.42; 40.00108; 5.198270|8.917×6.729; 1.325160|5×16; 3.200000|9.211/1|547.936073/204.94|38/17|BASELINE|
|r10_r1/C02|2.858×13.999; 40.009142; 4.898181|9.512×6.308; 1.507926|5×16; 3.200000|9/1|547.521338/204.446|38/17|QUALITY_TRADEOFF/QUALITY_TRADEOFF|
|r10_r1/C03|2.857×14.001; 40.000857; 4.900595|9.509×6.31; 1.506973|5×16; 3.200000|9.001/1|547.515147/204.448|38/17|QUALITY_TRADEOFF/QUALITY_TRADEOFF|
|r10_r2/C01|2.774×14.42; 40.00108; 5.198270|8.917×6.729; 1.325160|5×16; 3.200000|9.211/1|547.936073/204.94|38/17|BASELINE|
|r10_r2/C02|3.637×10.999; 40.003363; 3.024196|8.917×6.729; 1.325160|5×16; 3.200000|2.751/1|535.018356/198.098|38/17|GEOMETRIC_PARETO_IMPROVEMENT/QUALITY_TRADEOFF|
|r10_r2/C03|3.537×11.311; 40.007007; 3.197908|7.516×7.983; 1.062134|8.674×9.223; 1.063293|9.689/3|548.896037/207.752|40/18|NOT_COMPARABLE_STRUCTURE/NOT_COMPARABLE_STRUCTURE|

R9两个有效见证仅nominal宽深/旋转编码不同，实体边界相同，不能算两套实体布局。R1后续比例仅小幅改善，同时Office比例恶化，原九/十二项均Tradeoff。R2 C03把三房变得更紧凑，但路线9.689m、3次转向，建筑548.896037㎡、周长207.752m、轮廓40/18；其人员门面为另一V2，**正式比较为NOT_COMPARABLE_STRUCTURE**，仅可诊断展示形状与路线/轮廓的取舍，不能算第二次正式Pareto。

### C02的真实几何机制

- 实际入口Portal始终(45.750,0)m，Changing始终使用原合法东侧门面，并没有新开门。
- Sorting南沿15.421→12.000m，工艺脊线整体南移3.421m；Changing底边仍y=1.001m，实体宽2.774→3.637m、深14.420→10.999m，右边界始终x=44.750m。
- 已验收基线实际门中心(44.750,8.211)m，C02门中心(44.750,1.751)m。合法门洞偏移与房间组织共同改变，门净宽仍1.5m，入口连接及2m人员廊原规则不变。
- 原通行中心线[(45.750,0),(45.750,8.211),(44.750,8.211)]；新中心线[(45.750,0),(45.750,1.751),(44.750,1.751)]。按真实折线测量缩短6.460m，非直线距离替代。
- Coating仍5×16m；Office仍8.917×6.729m，只随既有工艺脊线平移。建筑面积降低来自实际房间与通道矩形精确并集，不是单纯房间面积总和。

这些事实说明：**让分选包装区和相邻工艺房间与入口相对位置一起移动，能解除原固定y=30场景的代价。** 本轮没有做房间家具/柜体排布权威验收，也没有证明所有空间组织都会得到同样收益。

## 资源、未知状态与复核

Python3.12.13 / OR-Tools9.15.6755 / macOS。同一Plan/P1/Site/Handoff、相同测试空间范围、相同Worker1/Seed3/PARTIAL_FIXED_SEARCH、原Presolve=true。保留原四轮预热及其原Seed0配置，未关闭Presolve。三臂第一完整模型Proto SHA256均为`df04fd286acdeef26064e04766de3808e2452b030555f2abde7664d88fb71dc9`，第一有效实体布局也一致。

各臂独立新内存诊断账本，共享本臂原8s Native/85s Elapsed/600000Work/512MiB/12Native调用/6完整检查/单要求Host20000；每次Solve前后核查，保留80ms余量。没有封存20t求解、生产Grant或真实MAIN。

|联动场景|R9原机制|R10 R1|R10 R2最终版本|
|---|---:|---:|---:|
|Native秒（monotonic）|7.9232213330687955|7.922375375055708|7.682234583015088|
|模型Work|77727|80801|83246|
|Native Host几何校核Work|34762|52163|55213|
|总Work|112489|132964|138459|
|完整赋值检查|2|3|3|
|实际Elapsed秒|9.534203707997221|10.009751750039868|9.934007957985159|
|Native调用|6|7|8|
|工程有效见证|2|3|3|
|实体房间边界去重|1|3|3|
|V2组织|1|1|2|
|实际局部复制Native|0|0|0|
|搜索峰值RSS MiB|222.109375|224.9375|234.78125|

所有臂未越限。R9/R1终止于Handoff份额耗尽；R2末次Native为UNKNOWN。UNKNOWN不是INFEASIBLE，也不能由本轮搜索否定其他合法布局。原九/十二比较、每个Work事件及所有调用记录见[精确JSON](evidence/stage-b-r10-entrance-coupled-spatial-r2/synthetic-comparison.json)。R2的Work高于两个对照，**不声称单位资源有效候选效率普遍提高**。

第一次三臂顺序比较、R2一次重复、实际Portal回读后的最终R2运行均保留。三次R2工程指标序列及实际实体几何一致；实际耗时不同，墙钟预算内的确定性不等于跨机器、跨运行时间逐毫秒一致。最终Portal回读使Work138457→138459，新增2次实际Portal坐标读取；没有少记或改收费。

原固定场景的中段R2负对照保留在本地`fixed-negative/r2`（完成实际Portal回读前的策略403e8b…）：仍只有微小尺寸变化，路线19.252→19.257→19.262m、建筑568.014500→568.034495→568.054480㎡，没有重点目标收益。原R1负面证据仍在[原报告](V2_2_2-stage-b-r10-functional-spatial-organization-r1.md)及其原SVG/JSON，未覆盖。不能把不同场景之间的候选直接当正式Pareto。

最终非空Hint路径的Native实验后，补充了缺失Hint字段在读取前拒绝、Portal变量来源检查与精确入口引用；这些不改变有效模型/顺序/预算，最终契约测试再次核实。没有为了修补负测试而再次调整搜索优先级。

## 图纸、复核与边界

- [同尺度三组实际几何对照 SVG](evidence/stage-b-r10-entrance-coupled-spatial-r2/layout-comparison.svg)
- [共同基线原工程图](evidence/stage-b-r10-entrance-coupled-spatial-r2/baseline.svg)
- [R2 C02入口协同原工程图](evidence/stage-b-r10-entrance-coupled-spatial-r2/entrance-coupled.svg)
- [R1在新联动场景的对照](evidence/stage-b-r10-entrance-coupled-spatial-r2/r10-r1-control.svg)
- [R2 C03不同V2、存在取舍的候选](evidence/stage-b-r10-entrance-coupled-spatial-r2/compact-tradeoff.svg)

所有原工程图直接由实际应用结果调用原绘图器导出；原`.native.svg`在本地保留，评审图仅校正旧模板把Truck/P2D写成VALIDATED的固定文案，元素属性/坐标完全一致。同尺度对照图也只投影实际矩形、门洞、已验收中心线和精确并集轮廓，没有移动布局。

完整本地目录：`artifacts/stage-b-r10-entrance-coupled-spatial-r2/`。每臂有所有原始`call-*.log`、Proto、candidate JSON、result/usage、audit账本与scope；`raw-manifest.json`绑定原件SHA256。衍生SVG和报告生成在搜索结束后进行，不冒充新Native或搜索预算内产物。新、旧场景都可用`python -m tests.r10_entrance_coupled_experiment --arm r9|r1|r2 --scene moving|fixed --output <新目录>`复核；必须用受限合成环境，不能接入真实Store。

本地：R2最终23通过，R1原有27通过；架构771通过/16原有跳过；CI契约65通过；Ruff/Format/Mypy通过。新增测试已加入原独立RSS资源测试Worker与快速CI，不改变正式ci.yml。初次新增契约4项失败（空Hint字段存在性、pybind列表不支持删除、测试新账本未装配历史状态），原失败JUnit保留；修正后完整R2 23项通过，未修改原工程验收或资源保护。

当前只请求独立Draft PR的自动快速CI。正式完整CI=NOT_REQUESTED，真实20t MAIN=false，真实Grant/Claim=false，生产默认不变，PR317/318及原证据不变。本轮重点目标在完整合成工程中有实际支持，**可以交由Owner决定是否进一步工程评审，不能自动转入整厂准备/正式CI/MAIN**。
