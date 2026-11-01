# 自主整厂布局 V1.1 · A1

任务：`V2_2_2_AUTONOMOUS_FACTORY_LAYOUT_FUNCTIONAL_CLOSURE_R1`。基线：PR #337，`66baca30f47fe691d7f2d41a379fdf83b2180a76`。独立 opt-in 入口，不接入生产/MCP/MAIN。

[整厂PDF](autonomous-layout-A1.pdf) · [高清PNG](autonomous-layout-A1.png) · [可缩放SVG](autonomous-layout-A1.svg) · [本地评审页面](autonomous-layout-review.html) · [工艺局部](A1-process-detail.png) · [更衣局部](A1-changing-detail.png)

## 实际改善与代价

| 项目 | V1 A | V1.1 A1 |
|---|---:|---:|
| 12区、原7条MUST、原P1尺寸/边界 | 通过 | 通过 |
| 房间级非货车Access | 11/11 | 11/11 |
| 占用并集单连通、零孔洞 | 通过 | 通过 |
| 门前主体冲突 | 12处 | 0处 |
| 已验证设备后室内全宽路径 | 1段 | 10段 |
| 包材库货位 | 66/最低67 | 67/最低67 |
| 成品库货位 | 315/最低315 | 324/最低315 |
| 原果/次果/冻果货位 | 45/21/36 | 45/21/36 |
| 有序取货、反向入库 | 未验证 | 493位逐位有见证 |
| 取放目标到真实门洞 | 未验证 | 5库房、6个接口有见证 |
| 更衣室 | 40.005625㎡，仅柜体主体 | 12600×9700mm、122.22㎡，两班53人条件序列 |
| 覆膜间 | 80.004080㎡ | 16300×7100mm、115.73㎡ |
| 房间毛面积合计 | 2230.825205㎡ | 2348.766016㎡ |

毛面积增加117.940811㎡，主要用于更衣与覆膜操作空间。不是更小面积方案，也不作跨版本正式Pareto结论。原九/十二指标比较器未改动。成品库仍沿用原P1的10%冻果扣减和126000kg分配，不冒充20t/天全部产品储存7天的容量承诺。

固定房间按原P1固定几何保留；例如分选包装45760×13600mm=622.336㎡，原业务报告显示622.34㎡，此处没有改写其Authority。柔性房间的扩大是本次有限候选选择，不是向P1增加最小宽度、面积上限或新硬限制。

## 怎么生成

1. 从原建筑结构、原业务面积/P1、设备尺寸数量生成首套房间；没有历史功能分区坐标输入。
2. 设备排布识别更衣、覆膜操作尺寸不足，计算柔性房间尺寸请求；在原Authority内重新生成房间。
3. 货位按24个有界方向/偏移组合尝试，保留柱体、真实设备、主通道和其他存货。反馈后的房间接触形成封闭空隙时，调整成品/出货/办公的候选排序，再经原零孔洞谓词检查。
4. 门洞从原合法边段选择，使用原Access Profile和工程谓词复核；原旧策略默认行为不变。

保留6条包装线、5台折箱机、11台完整十门柜、一级18位/二级12位预冷和4段纸箱封膜设备。A1将4台折箱机放在分选包装、1台放在包材库，后者为待厂家接口确认的空箱成型设计提案。没有删除设备、货位或通道以取得通过。

[完整同次计算JSON](autonomous-layout-A1.json) · [12区坐标](room-coordinates.csv) · [设备坐标](equipment-placement.csv) · [A→A1坐标差异](A-vs-A1-coordinate-changes.csv) · [定量比较](A-vs-A1-comparison.json) · [三轮实际反馈](iteration-feedback.json)

## 功能验证边界

- 仓储是指定顺序的块状存储。每次取货保留所有其他存货，入库按实际反向顺序重查。证明的是1100×1300mm条件荷载包络到主通道的运动及主通道到真实门洞的2500mm段，不是任意顺序直接存取、叉车转弯或搬运工具批准。包材主通道5000mm、其他仓储主通道3000mm独立保留；窄门喉与室内全宽段分别表达。
- 更衣室原H5有限尺寸适配器对新形状仍明确为 `UNSUPPORTED_NON_HISTORICAL_ROOM_AND_PORTALS`。新增矩形条件适配复用原完整柜体/格口分配、连续三维人体扫掠及解析门扇谓词，未继承历史H5坐标或PASS。
- 两班分别53人、各55格、4备用格；每人进入后有实际本位，初始53人在室。柜前往返保持52名他人在位；分别计算取物/关门、更衣、存物/关门以及离室。每个门扇假设有212次开柜核查。入口/离室阶段按实际在室人数逐步增减，不隐藏等候人员。
- 人体450×650mm、活动600×900mm、等候间隙100mm、完成面20mm、安装100mm、柜间100mm、支廊1200mm及两种90°铰链均为未批准敏感性条件。53人、无坐凳、本人柜前站立及11台整柜来自本项目已有Owner输入。850×390×1800mm只是选定产品标称外包络，425mm均列不等于格口净宽。
- 当前两条Changing Access使用同一几何门口，按串行分时出入验证；不是两处独立洁污门的工程方案。外部排队、真实门扇、人体取放可达性、储物卫生、人员并发和时长仍待确认。`conditional_complete_sequence_verified=true`不等于实际功能批准；实际功能仍为`INPUT_REQUIRED`。
- 原完整P2D、Truck、厂家操作/检修面、制冷性能及整厂工程批准均未成立。不得将门前主体不冲突或路线几何见证解释为这些项目已通过。

[两班逐人运动](functional-movement.json) · [493位取放](storage-pick-put.json) · [资源实测](execution-resource-usage.json)

本入口没有Stage A/B账本或600000 Work授权份额，不签发/复用资源。给出真实生成耗时、进程RSS及实际房间选项/节点数，不编造与Native账本可比的Work数。

## 复算与测试

在backend目录、锁定Python3.12依赖下，使用新的不存在输出目录：

```bash
uv sync --locked --python 3.12
PATH="$PWD/.venv/bin:$PATH" \
PYTHONPATH=tests/functional_native_guard:src:scripts \
R11_FUNCTIONAL_GUARD_AUDIT=/tmp/autonomous-v11-guard \
uv run python scripts/generate_functional_autonomous_layout.py \
  --input ../docs/previews/v2.2.2/autonomous-factory-layout-v11/inputs/project-input.json \
  --output /tmp/autonomous-v11-new-output
```

加`--finished-storage-days 8 --no-drawings`可复算业务变更回归。没有V2/V3/历史候选文件也能独立运行；这些文件只在生成完成后的A/A1比较中只读使用。[8天回归](input-change-regression.json)记录实际新P1、面积、坐标和结果Hash。

显式本地白名单：新增功能模块、原V1、functional_room_fit、R11 R4/R14；263项通过。最终新增模块36项与架构790项合计826通过、16项原有跳过；CI契约65通过；Ruff、Format1168文件、Mypy538源码与入口严格检查通过。父子进程启动防护保留，本次新Native调用0；没有MAIN/真实Grant/Claim或正式完整CI。早期开发轨迹另存本地临时目录，没有改写历史R9越界记录。

[最终JUnit](final-core-architecture.xml) · [相关回归JUnit](local-whitelist.xml) · [验证摘要](validation-summary.json)

新增测试已纳入ci-fast；保留全部继承测试与Python3.12锁定。自动快速CI包含原有合成Native测试，不能将整个远端工作流宣称为零Native。最终精确HEAD结果以新Draft PR Checks和下载的JUnit为准。
