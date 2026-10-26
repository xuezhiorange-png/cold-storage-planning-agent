# R9 R7 路线择优资源控制

基线 PR #316：`c52b51c7866ee439f1513780003f31b23501aedb`。新策略只控制局部准备资源和复制次数，不改人员路线算法。

## 结论

完整 20t 模型的一次复制本身需要 66,255–66,259 Work。最初六等份每份 100,000 Work，完成已知模型准备后只剩 49,579，无法承担复制、定长定义及局部固定。旧策略仅在操作之间检查 Handoff 份额，可能先复制、耗尽份额，再在下一次检查中停止；全局账本仍保持拒绝超额。

新增显式可选 `StageBResourceBoundRouteRefinementFairSolver`，在复制前检查实际剩余份额和已知操作上界；不足则跳过局部择优，返回原房间枚举。每个 Handoff 最多建立一个局部模型。原 R6 仍保留，旧 Runner、授权、生产默认不选择新策略。

## 六个 Handoff：只构造，无 20t Native

顺序由原服务器 schedule 取得。所有模型均为完整 12 区 / 7 MUST / 11 非货车 Access。两种 Solve API 被禁止。没有伪造工程有效基线、Hint 或验收。Native 时间与工程校核成本均 NOT_EVALUATED。

|顺序 / 组织 / 方向|变量|约束|复制 Work（无未来 Hint）|复制 ms|实测 RSS 增量 MiB|路线定义 Work / ms|
|---|---:|---:|---:|---:|---:|---:|
|1 / CENTRAL_PROCESS_CORE:X:NEGATIVE:r0|27400|38640|66255|5.361|11.453|942 / 4.011|
|2 / LINEAR_BANDED:X:NEGATIVE:r0|27400|38640|66255|5.278|11.312|942 / 3.917|
|3 / PROCESS_SPINE_WITH_PERIPHERAL_BANKS:X:NEGATIVE:r0|27400|38644|66259|6.226|11.422|942 / 3.745|
|4 / CENTRAL_PROCESS_CORE:Y:POSITIVE:r1|27400|38640|66255|5.609|11.453|942 / 3.611|
|5 / LINEAR_BANDED:Y:POSITIVE:r1|27400|38640|66255|5.617|11.531|942 / 3.789|
|6 / PROCESS_SPINE_WITH_PERIPHERAL_BANKS:Y:POSITIVE:r1|27400|38644|66259|6.444|15.953|942 / 3.745|

第一阶段：1 个 strategy / 10 references；阶段后元数据：19 / 196。真实 Hint 数为 0；未来可能物理 Hint 引用上界 371，仅作为成本上界，不是假装已接受 Hint。原第一阶段准备 Work 49,643；含原 R7 后阶段元数据重排及 R9 引导为 50,421。原始首次测量遗漏了 189 次元数据重排计费，已保留原 JSON，并单独执行零复制、零 Native 的正确计费构造回读；未改写任何历史账本。

每个局部准备上界 68,000（两种模型 68,004）=复制 66,255/66,259 +作用域参考/固定上界802 +原精确路线定义942 +目标写入1。规划读实际计费135。另列原房间键48和未来 Hint371，合计保守准备上界68,554/68,558。原精确路线定义为12次引用读取、336变量、594约束。预估不当作实际操作计费，原构造器逐项计费不变。

最初统一六等份：Native 49.9/6=8.3167s，Elapsed≤85/6=14.1667s，Work100,000，完整检查3。六个 Handoff 在此共同情景均为 SKIP_INSUFFICIENT_RESOURCES：单次已知准备缺口18,975/18,979；两次缺口87,529/87,537。预热、Native、验收、未来 Hint/切除尚未计入，不能把这些值冒充实际剩余额度。

下表另列仅扣前序构造、假设尚无 Native/验收消耗的回流上界，不能作为运行准入。后四项只可 NOT_EVALUATED。实际执行从来没有获得新额度。

|顺序|剩余 Handoff|Work 份额上界|Native 份额上界 s|Elapsed 份额上界 s|检查上界|扣本次准备余量|一次 / 两次准备后 Work 差额|结论|
|---|---:|---:|---:|---:|---:|---:|---:|---|
|1|6|100000.0|8.3167|14.1667|3|49579.0|-18975.0 / -87529.0|SKIP_INSUFFICIENT_RESOURCES|
|2|5|109915.8|9.9800|16.9366|4|59494.8|-9059.2 / -77613.2|SKIP_INSUFFICIENT_RESOURCES|
|3|4|124789.5|12.4750|21.0941|5|74368.5|5810.5 / -62747.5|NOT_EVALUATED|
|4|3|149579.0|16.6333|28.0142|6|99158.0|30604.0 / -37950.0|NOT_EVALUATED|
|5|2|199158.0|24.9500|41.8667|10|148737.0|80183.0 / 11629.0|NOT_EVALUATED|
|6|1|347895.0|49.9000|83.4297|20|297474.0|228916.0 / 160358.0|NOT_EVALUATED|

复制计时只含 proto.copy_from；942 Work 定义单列。RSS 为真实构造进程观测，不能代表求解器峰值。完整准备、未来 Native Host、独立 Access/Topology/Site/Footprint 验收成本分别保留，不省略或估为零。六个原始测量进程及纠正构造回读为独立只读分析计数，不是一次 MAIN 的资源额度，不得与合成 8s 实验预算混用。

## 实现及失败语义

原 `_RouteRefinementNative` 只增加默认原样的 `_build_local_model` 扩展点。新模块通过元数据和已存在引用计算复制/已知定义上界；不扫描全部变量、不读取全模型赋值。规划读取本身按实际操作计费，资源不足可以停止规划。复制前检查 Handoff/global Work、Native、Elapsed、完整检查余量；沿用原 guard、remaining_solver_seconds 和可信 precharge（含调用额度、RSS及外层合同保护）。Elapsed另留0.1s准备窗口；它是准入保留，不是延长预算。

只把预判不足转换为带原因的 LOCAL_REFINEMENT_SKIPPED。真实 guard/precharge/计费异常继续抛出，不得冒充成功。开始第一次复制即消费该 Handoff 的本地会话次数；一次会话仍复用原模型和最多两次局部 Solve，原本地时间/份额规则不变。计费、工程反馈、UNKNOWN及拒绝见证语义均继承原实现。

原父模型、Hint、目标、切除均不修改；局部对象丢弃后继续原房间枚举。全局合法物理域保持不变，改变的是可选局部搜索机会。原真实执行授权仍须绑定新的策略身份；本轮不提供 Runner、Owner Scope、Grant 或 Claim。

## 完整工程合成回归

复用 PR316 的同一独立合成 Plan/P1/Typed Site/Handoff（非20t真实输入），Worker1、Seed3、Presolve、PARTIAL_FIXED_SEARCH、原首次可行和130项物理Hint不变。旧对照只读回读，没有重跑。两个新场景分别共享各自原8s Native /600,000 Work /85s /512MiB /12调用 /6检查上限。

|实际场景|复制次数 / Work|总 Work|保守 Native s|调用 / 检查|有效路线见证 / 房间几何|
|---|---:|---:|---:|---:|---:|
|old-two-copy|2 / 129281|357531|7.893648251|10 / 6|6 / 3|
|admitted-one-copy|1 / 64640|268032|7.532170666|10 / 5|5 / 3|
|skip-copy-continue-rooms|0 / 0|149015|5.542111167|7 / 3|3 / 2|

一次复制保留26.750m→22.500m、同房间/同V2/代理1225的真实合成见证。原九、十二指标均 GEOMETRIC_PARETO_IMPROVEMENT，12区/7MUST/11非货车Access及独立几何、原生Access、Site/Footprint、单连通零孔洞、_eligible均通过。路线来自实际导出中心线，并逐段等于原CP长度定义。全程保留原第一阶段基线。

低Work负对照仅把当前 Handoff 份额缩小到已耗+65,000，未增加任何额度。复制前 SKIP、无局部 Native，随后原枚举取得不同且工程有效的房间几何；最终149,015 Work低于缩小后的186,706份额。

前五个 Native 模型及所有重叠全局续跑模型 hash 与旧对照相同，原130 Hint不变；临时局部约束无泄漏。一次复制节省的总89,499 Work包括少一次64,641复制和相关定义/校核的实际消耗差异，不是少记账。

取舍：不再尝试旧第二次32.749m→22.499m跨V2见证；有效路线见证由6降5，房间几何仍为3。新增最后一次原枚举返回UNKNOWN（不算第六套有效布局）。旧对照预算结束错误CP_SAT_CUMULATIVE_ALLOWANCE_EXHAUSTED原样保留，旧R4约8.015s超额记录未修改。两次新场景均未越限，不能由此推断真实20t提速或质量收益。

## 策略、验证与后续边界

新资源策略 `sha256:ce8c264012510d9655e9d28ca283a98c99775c913df8e976b4ad3e2d5ac17272`。父路线算法hash保持原值；资源审计另带 resource_policy_hash。旧授权不自动选中新类。

本地策略回归114 PASS；架构/资源回归801 PASS + 修正子进程PATH后的单项1 PASS，共802 PASS，16项既有skip、3项physical_rss_linux显式排除（不计PASS）。初次架构子进程误用缺pytest的系统python3，该环境失败日志保留，未改测试或业务源码。CI契约64 PASS（含50次清理循环）；Ruff/Format/Mypy454源文件、YAML、diff PASS。自动快速CI单独报告，FULL_CI=NOT_REQUESTED；正式CI与真实MAIN未执行。

值得由Owner审核后安排后续准备，但不能称已完成真实MAIN准入。关键限制：早期Handoff通常安全跳过全复制，后期能否有足够余量需真实运行时判定；未测得20t路线收益。源码冻结、精确HEAD正式CI及独立授权仍为后续必需门禁，本任务到Draft交付即停止。

[六Handoff成本JSON](../previews/v2.2.2/r9-route-resource-scaling-r7/six-handoff-resources.json) · [原指标与Work回读](../previews/v2.2.2/r9-route-resource-scaling-r7/measurement.json) · [真实合成几何SVG](../previews/v2.2.2/r9-route-resource-scaling-r7/route-resource-comparison.svg)
