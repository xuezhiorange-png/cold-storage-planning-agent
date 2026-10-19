# 项目三人包装工位资料准入 R2

TASK=V2_2_2_OWNER_V2_PACKING_STATION_PROJECT_INPUT_ADMISSION_R2

## 交付结论

本目录新增独立离线资料适配器，复用且不修改 `PackingStationModuleV1` 的几何、完整宽度路径校核和 SVG 引擎。资料准入软件可运行，但本次限定检索范围内未发现可用于项目工位准入的设备总图、三人作业布置和全工况资料。

`PROJECT_EQUIPMENT_CANDIDATES=0`、`PROJECT_SELECTED_EQUIPMENT=UNAVAILABLE`、`PROJECT_INPUT_ADMISSION=BLOCKED`。这里的 0 是具备项目身份及尺寸依据的设备候选数量，不是索引文件数。搜索存在范围和命名限制，不能证明 Owner 在其他位置没有资料。

[查看资料缺失预览](previews/project-input-required.svg) · [填写项目输入模板](project-input-template.json) · [供应商/工艺工程师资料索取清单](project-information-request.md)

真实项目工位未验证，尺寸未批准，包装面积未校准。18 台和 28 台适配均 `NOT_EVALUATED`。不生成真实设备尺寸图，也不输出新版 P1 面积。

## 可执行链路

资料发现与索引 → 本地人工来源及提取复核 → 启动端固定复核登记字节 SHA256 → 请求身份、原件字节、图纸修订、尺寸标注和任务/工况结构核对 → 精确整数毫米标准化 → R1 几何及全宽路径诊断 → `ENGINEERING_REVIEW_REQUIRED`。

不得自动进入 `ENGINEERING_APPROVED` 或 `FORMAL_P1_AUTHORITY_APPROVED`。文件 Hash 只证明字节一致，不能证明真实性、选型、适用性或工程批准。当前登记表为空，没有将任何公开厂商参考或合成工位纳入项目来源。

### 可信边界

`local-review-register.json` 是**本地人工资料提取复核登记**，不是 Owner 求解 Grant、设备批准或网络认证凭据。调用方请求不能包含 `verified`、`APPROVED` 或替换登记表的字段。可信本地审核人员须独立核实原件、项目适用性和标注语义；可信启动人员固定登记文件的实际字节 Hash，不得从请求 JSON 取值。

登记中每个来源应固定：完整资料身份 Hash、原件 Hash、格式、复核人员及记录编号、结构引用 Hash、每一尺寸记录 Hash。对于拥有替换本地代码、登记表及其固定 Hash 权限的人员，本工具不声称能够提供来源认证。测试夹具生成器只创建 `SOFTWARE_TEST_ONLY` 登记；其输出只能进入 R1 合成模式，不能作为真实资料。

`PUBLIC_MANUFACTURER_REFERENCE` 不能进入项目几何；`PROJECT_CANDIDATE_EQUIPMENT` 经过来源及提取复核可用于未批准诊断，不等于已选设备。已选/已批准分类需要独立的既有审批核验，本原型尚未实现审批签署验证，遇到这两类输入明确拒绝，而不采信调用方声明。后续接入应由人工复核批准文件并另行授权审批验证能力。

### 填写与运行

1. 原始内部图纸、采购协议放在获授权的本地资料目录，不提交公开仓库。`SOURCE_PATH_OR_URL` 在适配请求中使用该目录内的相对缓存路径，不支持在线下载、绝对路径或目录逃逸。
2. 按 `project-input-admission-contract.json` 填写完整项目、工厂、设备、制造商、型号、图号、修订版、发布日期、页码、来源类别、适用性及审批证据状态。缺失内容不得猜测。
3. `MODULE_TEMPLATE` 采用 R1 原合同结构、显式组件/人员/接口/路径/实例/共享条件；`MODE=OWNER_PROJECT`、`SOURCES={}`。所有几何数值叶子必须是 `null`，后续仅由已复核尺寸记录填入。结构本身也须绑定真实作业及工况资料，不能由未审核请求临时发明。
4. 每个尺寸记录绑定 `RECORD_ID, VALUE, UNIT, SOURCE_ID, SOURCE_LOCATION, DIMENSION_TYPE, COORDINATE_REFERENCE, EXTRACTION_METHOD, MEASUREMENT, TARGET_PATH`；独立设备长宽高记录另带 `COMPONENT_ID`，`TARGET_PATH=null`。参考 [字段模板](dimension-record-template.json)。
5. 支持明确结构化 JSON 标注，或唯一完整文本行 `CALLOUT_KEY = 2400 mm`。PDF 仅提取可识别的明确文本标注，不量测像素、不按草图比例缩放。原生 CAD、图片或未标注资料保留人工复核状态。当前完整模块结构要求有可复核的结构化资料转录，且该转录由人工逐项复核；不是通用 PDF/CAD 自动识别器。
6. 可信启动端加载已审核登记及其固定 Hash，再执行下面的离线入口；输出目录必须不存在，避免覆盖历史。

```sh
python offline_project_diagnostic.py project-input-template.json \
  --source-root /path/to/authorized/local/evidence \
  --review-register local-review-register.json \
  --review-register-sha256 <trusted-launcher-pinned-sha256> \
  --output /path/to/new/private/diagnostic
```

模板中空列表和未绑定结构会如实被拒绝。当前登记 Hash 记录在 `project-input-admission-contract.json`，并由 `source_manifest.json` 封存。请勿将输入模板当作已有设备数据。

## 尺寸、工况与结果语义

使用整数毫米和显式局部/装配坐标，允许 0/90/180/270°旋转。米、厘米用精确有理数转换；非整数毫米拒绝而不舍入。设备本体 L/W/H 与坐标外廓核对；高度只记录来源，不宣称三维净空已验收。旧 5.6/3.0 节距、8.0/7.6 聚合余量和历史房间净宽不得替代设备或内部通道尺寸。

三名人员分别绑定任务、站位、朝向、动作区和入口路径来源；来源齐全仍 `OPERATOR_FIT_APPROVED=false`。材料输入、包材供应、成品、剔除、人员及检修路径分别记录。原引擎校核的是给定宽度的完整扫掠包络，不是自动求出的最大净空；`ACTUAL_GEOMETRIC_CLEARANCE_MM=null`，避免把通过输入宽度校核冒充净宽批准。

正常生产、交班、清洁、维护四状态由原引擎分别检查。实体冲突、动作区交互、供出料冲突和时间共享保持不同诊断类型。两班共用台位政策不变，但交班、清洁时长、缓冲、设备开启和维修通行均不默认为零。非同时空间重叠仍需人工工程复核。

项目尺寸足够时导出 `PROJECT_STATION_DIAGNOSTIC.svg`，保留 `ENGINEERING_REVIEW_REQUIRED / NOT_P1_AUTHORITY`；软件夹具只导出 `synthetic-pipeline-diagnostic.svg`。实际缺资料输出 `project-input-required.svg`。所有 SVG 独立、无脚本和外部资源。真实资料和派生桥接证据应保留本地，公开前需人工脱敏及传播许可审查。

## 历史隔离与下一步

封存的 8 套布局、48 条接口、R1 的 8 张 SVG、Owner V1/V2、旧 Canonical/P1 Hash 和生产源码仅只读复核。历史 45.76×13.6m 房间及 Portal 并不证明新工位或内部物流可放入。未运行 P2/CP-SAT，未注册 MCP/Tool7，未创建或消耗任何 Owner Grant。

测试结果与 Node ID 见 `validation.json`；原件及历史字节核验见 `historical-evidence-integrity.json`、`legacy-canonical-replay.json`。合成夹具只验证准入、拒绝、转换、碰撞、装配和绘图的软件行为，不补写真实项目数据。

下一阶段所需资料、责任和受影响计算见索取清单及 `engineering-review-matrix.json`。仍保持 `REAL_PROJECT_MODULE_VALIDATED=false`、`FORMAL_MODULE_DIMENSIONS_APPROVED=false`、`PACKAGING_AREA_CALIBRATION_READY=false`、`P1_PRODUCTION_ACTIVATED=false`、`STAGE_B_COMPLETE=false`、`P2D_FULL_PASS_COUNT=0`、`VERSION_COMPLETE=false`。D01/D03/D04、资源预算、P3 历史 262 UNKNOWN 不变。
