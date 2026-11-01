# 自主布局 V1.2 · 实际设备物流贯通

`V2_2_2_AUTONOMOUS_PROCESS_FLOW_CONTINUITY_R1`。基线PR #338，精确HEAD `28ee3bef2860fc93f9f1e692ffc8de669b86a709`。独立非Native、opt-in概念设计入口，不接入生产/MCP/MAIN。

[整厂PDF](autonomous-layout-A12.pdf) · [高清PNG](autonomous-layout-A12.png) · [SVG](autonomous-layout-A12.svg) · [工艺局部放大](A12-process-detail.png) · [本地评审页](autonomous-layout-review.html)

[主产品物流图](main-product-logistics.pdf) · [五台折箱机/六线供箱图](six-line-case-supply.pdf) · [端点与路线JSON索引](equipment-endpoints-and-routes.json) · [完整原始候选](autonomous-layout-A12.json)

## 实际生成结果

- 12区、原7条MUST、原固定尺寸和面积来源、房间级非货车Access 11/11；生成占用并集单连通、零孔洞。所有原建筑柱体保留，净面积扣减单列。
- 六条线分别形成原果货位→一级预冷托位→周转筐卸料工作位→包装机入口→包装机出口→线端托位→待冷缓冲→二级预冷→拆托→四段独立纸箱封膜→复托→成品货位→出货工作位的完整条件链。
- 共87条设备/托位路线条件通过，0条有界路线失败。其中6段包装机、4段封膜组件的内部输送为明确声明的机器内部接口，非车辆通道或厂家性能验收。每条产品链经过6个真实原P1物料Access门洞。
- 五台折箱机全部有纸板供给路径；计算30条成箱到六线的实际路径，并在1800个覆盖全部五机、每机最多服务两线的组合中按几何长度选配。没有进行设备产能均衡或证明该分配的小时供箱能力。
- 14个待冷位（N/S服务组各7）与6个包装托盘工作位、1个周转筐卸料位分别计数。14个待冷位均有到二级预冷托位的条件路径。N/S组在本次自主房间北侧工作带重新布置，不等同于B1两个厅的位置。

| 包装线 | 含机内声明输送的条件中心线总长 |
|---|---:|
| PACK-01 | 278.246m |
| PACK-02 | 272.644m |
| PACK-03 | 268.942m |
| PACK-04 | 253.740m |
| PACK-05 | 250.038m |
| PACK-06 | 244.436m |

以上是不同运输/交接方式的几何参考线长度合计，不能当作车辆行驶里程、果实真实轨迹、作业时长或产能。V1.1没有建立设备端到端链，其对应长度和冲突数为NOT_EVALUATED，不虚构改善百分比。

## 具体调整与代价

包材库增放第二台完整折箱机的6个实际位置尝试均只能保留63/最低67位，因此全部否决。保留4台分选间、1台包材库；四台分选间折箱机旋转90°，中部2500mm主通道、两列间1800mm补料操作带。六线原1000mm人员操作带保留，仅压缩非通行的对间空隙。

首次在原7100mm封膜房间深度下纳入完整托盘与600×900mm操作位，操作位会占用预留主通道。程序据断面尺寸链提出柔性房间8300mm深度，再重新生成并验证；这是候选尺寸，不是P1新增硬限制。

| 区域 | A1→V1.2 |
|---|---|
| 独立封膜间 | 16300×7100→16300×8300mm，增加19.56㎡ |
| 成品库 | 原面积及固定尺寸不变，向北1200mm，内部货位由程序重新排布 |
| 出货区、办公室 | 固定/原柔性尺寸不变，向北1200mm |
| 更衣室 | 12600×9700mm及原条件模型保留；人员Portal变化仅由原适配器复核进入/离室 |

[房间坐标差异](a1-a12-room-changes.csv) · [设备坐标差异](a1-a12-equipment-changes.csv) · [实际反馈/失败](iteration-feedback.json) · [完整比较](layout-comparison.md)

包材67/最低67、成品324/最低315、原果45/最低37、次果21/最低19、冻果36/最低34。保留493货位原有序取放见证，不代表每一个货位都已经通过本轮整车包络或任意顺序存取。成品容量仍沿用原P1冻果扣减及126000kg分配，不冒称20t/天全部成品储存7天。分选固定几何45760×13600=622.336㎡、业务显示622.34㎡的原四舍五入口径不变。

## 几何与工程边界

主通道2500mm，包材主通道5000mm；托盘1200×1000mm、整车及载荷1300×1800mm为未批准假设。直角转向采用外接方形2222mm，门洞2400mm仅直线通过；不是叉车/地牛真实转向运动学。400×600mm纸箱投影是两种箱重的共同待审几何假设，不是4.8kg/3.2kg厂家箱型已确认。

设备嘴部与载荷接触、载荷相对搬运参考点偏移、机外短交接、主通道、实际门洞和转向包络分别保存。每条路线均保留其他等待托盘，源托位随载荷移动、目标为该批次预留空位。共享通道及补料/出箱交会需要时间分离；未证明同时交通、缓冲动态容量或20t连续吞吐。包装/封膜机内部嘴部和输送方向仍需厂家接口确认。

B3/B4的20t/天、4.8kg与3.2kg、六线人员10/10/10/8/8/7、换托60s/端且重叠45s、全部二级预冷后独立纸箱覆膜仅作为衔接条件，不重算产能或制冷。Truck、完整P2D、现场功能批准及整厂适用性未成立。H5实际功能仍INPUT_REQUIRED，不把两班53人条件流程升级为工程批准。

## 复算与输入变化

在backend目录、Python3.12锁定依赖下，输出目录必须预先不存在：

```bash
uv sync --locked --python 3.12
PATH="$PWD/.venv/bin:$PATH" \
PYTHONPATH=tests/functional_native_guard:src:scripts \
R11_FUNCTIONAL_GUARD_AUDIT=/tmp/autonomous-v12-guard \
uv run python scripts/generate_autonomous_process_layout.py \
  --input ../docs/previews/v2.2.2/autonomous-factory-layout-v12/inputs/project-input.json \
  --parameters ../docs/previews/v2.2.2/autonomous-factory-layout-v12/inputs/process-parameters.json \
  --output /tmp/autonomous-v12-new-output
```

`--finished-storage-days 8 --no-drawings`实际重算原P1和房间，成品库从原框变为`[86680,33534,107880,64734]`，新候选原预留主通道与3个保留柱体相交，因此整体状态为`INTERRUPTED_PROCESS_CANDIDATE`。即使六条路线可以各自绕行，也没有覆盖该失败或返回旧方案冒充成功；不宣称全局不可行。[实际输入回归](input-change-regression.json)

相同输入结果Hash一致；禁止读取历史布局坐标的回归通过。本入口不签发Stage A/B预算、不建立Work账本，不把房间选项计数伪称600000 Work中的收费。[实测耗时/RSS/操作数](execution-resource-usage.json)

## 软件验证与执行边界

本地显式白名单884通过、16项原有架构跳过；补充几何反例2通过。新模块35项加补充2项共37，原V1.1共36、V1共23，架构790通过。CI契约65通过；Ruff、Format1174文件、Mypy542源码加新入口严格检查通过。

[本地白名单JUnit](local-whitelist.xml) · [新模块JUnit](process-tests-junit.xml) · [补充反例JUnit](geometric-negatives-junit.xml) · [验证摘要](validation-summary.json)

父子进程保留Native禁用；负向测试的solve/Solve请求均在调用底层Native前拒绝。没有MAIN、真实Grant/Claim或正式CI。ci-fast新增本模块并保留全部继承测试及Python3.12锁定；继承自动快速CI会执行既有合成Native测试，不能把整次CI宣称为零Native。精确HEAD自动CI与远端JUnit以本PR Checks最终回执为准。
