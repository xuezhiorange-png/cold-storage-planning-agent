# 功能房间可用性离线校核 R2

TASK=`V2_2_2_STAGE_B_FLEXIBLE_ROOM_FUNCTIONAL_FIT_R2`。
基线 `a34dff1f45dcbc930b3ca3d4e0a07117dbf8d592`；本目录仅新增离线工具、合同、测试和审图。

## 交付结论

`FunctionalRoomFitEvaluatorV1` 已实现：三类功能输入、四工况组件组合、精确整数毫米变换、
正面积碰撞、并集、给定完整宽度路径与 Portal 连接检查、指定布置的必要不满足证明、确定性 SVG。
没有开发第二套候选加载或项目审批系统。

8 套真实候选的 24 间房逐一回读，全部 **INPUT_REQUIRED**。真实家具、柜型、包装箱封膜机、
装修净尺寸、操作/室内通行/门扇/清洁检修依据均未在现有项目证据中齐备。
**狭长外形不直接判违规；原面积满足也不等于功能可用。**

- [24 间逐项矩阵](functional-fit-review-matrix.md)
- [完整房间及状态 JSON](eight-layout-functional-fit.json)
- [实际几何索引](existing-room-geometry-index.json) / [原 Portal 索引](existing-room-portal-index.json)
- [功能缺项](missing-project-inputs.json) / [来源边界](source-provenance-matrix.json)
- [已运行测试和质量检查](validation.json) / [旧源码与 Canonical/P1 完整性](historical-integrity.json)

## 直接审图

所有真实图使用相同世界坐标原点及 **0.01 px/mm**，不移动房间，不补画设备或门。
1/2 为历史候选，3–8 对应 guided 01–06。只画三个目标房间，空白不代表室外可用区域。
红色线段仅是封存 Portal；室内路线及门扇未知。小号圆点编号与侧栏对应。

|实际来源|审图|
|---|---|
|multi-solution-validation-01/candidate-01|[真实01](previews/candidate-01.svg)|
|multi-solution-validation-01/candidate-02|[真实02](previews/candidate-02.svg)|
|guided-fair-validation-02/candidate-01|[真实03](previews/candidate-03.svg)|
|guided-fair-validation-02/candidate-02|[真实04](previews/candidate-04.svg)|
|guided-fair-validation-02/candidate-03|[真实05](previews/candidate-05.svg)|
|guided-fair-validation-02/candidate-04|[真实06](previews/candidate-06.svg)|
|guided-fair-validation-02/candidate-05|[真实07](previews/candidate-07.svg)|
|guided-fair-validation-02/candidate-06|[真实08](previews/candidate-08.svg)|

三张合成图分别包含正例、反例及正常/检修状态，统一 **0.05 px/mm**。
红色虚线是明确输入的装修净边界，红框突出冲突组件。
尺寸仅为软件夹具，不是推荐尺寸、采购选型、人体工学判断或施工图。

- [办公室：12 个合成桌位、人员与座椅，净宽不足反例](previews/office-synthetic.svg)
- [更衣：单排柜正例、指定双排柜重叠反例](previews/changing-synthetic.svg)
- [包装箱封膜：供出料、同室非封膜通道与检修空间不足](previews/film-sealing-synthetic.svg)
- [全部六个实际软件结果](synthetic-scenario-results.json)

## 几何与语义边界

三类草案分别为 `OfficeFunctionalModuleV1`、`ChangingRoomFunctionalModuleV1`、
`FilmSealingRoomFunctionalModuleV1`。[统一输入合同](functional-fit-input-contract.json)列出字段与状态。
矩形、路径宽度、位移是整数毫米；内部奇数宽度保持精确半毫米 Fraction，不作浮点容差。
支持四分之一圈旋转，不用外接矩形冒充任意多边形。

原房间由既有 `_rectangle_from_row` 消费名义旋转，再获取物理边界；
本工具的房间局部坐标始于**物理左下角**，轴向平行世界 XY，不再对 Portal 二次旋转。
装修净边界必须显式给出，不从建筑轮廓减一个猜测墙厚。

各状态分别计算同时活动集合。实体始终存在；站立与实体碰撞、实体挡门/通道为
`HARD_GEOMETRY_CONFLICT`；动作、椅退、检修及供出料交互保留
`INTERACTION_REVIEW_REQUIRED`，不自动同意共用。不同工况不同时活动不等于时序共享获批。
没有规定的门操作、有效运行时间、清洁检修或完整宽度路径时保持 `INPUT_REQUIRED`。

路径是**给定路径的全宽占用校核，不是搜索**。端点完整宽度匹配绑定 Portal 后，
仅允许该开口的方形端帽跨越室内边界；不推导外部道路、开门可用性或室内所有位置可达。
Portal 连接事实与 `PORTAL_FUNCTIONAL_ACCESS=NOT_EVALUATED` 分开。
办公室与 Shipping 的空间 MUST 不创建人员门；更衣、封膜原接口也不证明柜前或设备流线可达。

反例只证明**这一给定配置和朝向**几何不满足，不搜索其他摆法，不证明整个房间不可用。
指定相对两排 500 mm 柜体对 875/977 mm 净宽的必要下界另见
[条件证明](conditional-width-proofs.json)；500 mm 只是假设，不是项目选型或新 Hard。
几何并集面积、矩形外包络、房间几何面积与功能面积不同；`FUNCTIONAL_ROOM_AREA=null`。
即使返回 `GEOMETRY_CHECK_ONLY`，也不证明工作容量、消防、卫生、隐私、人体工学或工程批准。

## 业务数量与来源复用

原 Owner V2 代码只读复用；[业务条件示例](owner-v2-business-examples.json)含显式 SMALL/MEDIUM/LARGE
12/20/30 人及未知规模拒绝推断。20 吨**包装成品量**条件示例重算为 53/53 人、106 独立柜位、
53 同时更衣、18 张跨班共台；不绑定八套旧布局的真实项目人数，也不从原果质量推断成品量。
柜内衣物分隔不翻倍柜位，无默认男女独立分区，保留专业卫生和隐私审查。

覆膜唯一适用工艺为 `PACKAGING_BOX_FILM_SEALING`。果品打蜡、涂膜、托盘缠绕资料均不适用。
工序、独立房间、100%设计能力及非封膜产品同室绕设备通过政策不变。
有效设备时长为独立缺项，不默认包装安排的16小时。

候选由前一任务固定目录及 Hash 的 `load_sealed` 加载，原始 JSON、投影子树、Canonical Hash、
旧 SVG 和 authority 字节逐项验证。R1 的 `transform_rect/intersection/covered/union_area/path_envelope`
直接复用；此前 R2 的 `verify_document/extracted/normalize_value` 负责项目来源及尺寸。
旧目录均经过固定 manifest SHA 和逐文件检查后导入，不调用旧生成脚本写入旧目录。

合成模式使用 R1 的完整记录—来源文件字节绑定，仅能得软件诊断。
项目候选模式需由可信离线启动端传入已有 R2 `ReviewContext`；调用方请求不能提供该上下文，
每个 CONFIGURATION、COMPONENT、ROUTE、PORTAL 都须通过原 `verify_document` 并与明确提取记录相等。
`PROJECT_RECORD_REFERENCES` 逐 key 携带既有完整 `DOCUMENT` 与 `LOCATION`；项目/工厂身份、版本、
原件 SHA 及人工提取复核均沿用 R2。软件上下文、公开参考和自行填写 APPROVED 不获项目准入。
当前没有实际家具/柜体/封膜资料，不创建新的项目审批记录，不升级 PROJECT_SELECTED 或批准状态。

## 复现

仓库根目录、已锁定 Python 环境，不安装依赖：

```sh
PYTHONPATH=backend/src:backend backend/.venv/bin/python3 \
  docs/previews/v2.2.2/stage-b-flexible-room-functional-fit-r2/offline_functional_fit.py \
  --artifact-root /path/to/authorized/project/artifacts

PYTHONPATH=backend/src:backend backend/.venv/bin/python3 \
  docs/previews/v2.2.2/stage-b-flexible-room-functional-fit-r2/offline_functional_fit.py \
  --input docs/previews/v2.2.2/stage-b-flexible-room-functional-fit-r2/examples/office-positive-input.json \
  --evidence-root docs/previews/v2.2.2/stage-b-flexible-room-functional-fit-r2/examples

PYTHONPATH=backend/src:backend STAGE_B_PREFLIGHT_ARTIFACT_ROOT=/path/to/authorized/project/artifacts \
  backend/.venv/bin/python3 -m pytest \
  docs/previews/v2.2.2/stage-b-flexible-room-functional-fit-r2/test_functional_fit.py
```

`build_review.py --artifact-root ...`只重建本目录报告和示例；不生成真实候选。
可调用 `evaluate(document,evidence_root,context=existing_review_context)` 接入已有来源复核资料。
本次没有运行真实项目资料诊断，因为输入尚不齐备。

## 不变项及下一步

原 60/40/80m²代表性面积、旧 Canonical/P1 Hash、八套候选及 SVG、P0/P1/P2/Access/Truck、
`UNMODELED_FLEXIBLE_DIMENSION_RULE`、预算、D01/D03/D04和262 UNKNOWN全部保持。
没有运行新的工厂求解、Truck路径搜索、CP-SAT或 Owner Grant，没有修改正式 Selector、Tool7、MCP。

下一步须补实际工厂规模/人数及质量来源，项目家具与柜型/门扇，包装箱封膜选型、设备能力和有效时长，
真实装修净边界、人员与物流通道、操作/清洁/检修及专业复核，再另行授权正式工程消费。
本次条件测试不能变成正式 P1 Hard 或面积切换。

FUNCTIONAL_FIT_CALIBRATION_READY=false；PROJECT_FUNCTIONAL_FIT_APPROVED=false；
P1_PRODUCTION_ACTIVATED=false；P2D_FULL_PASS_COUNT=0；STAGE_B_COMPLETE=false；VERSION_COMPLETE=false。
不 Ready/Merge/Tag/Release/Deploy；完成后 STOP。
