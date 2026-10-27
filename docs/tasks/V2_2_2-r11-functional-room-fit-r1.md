# R11 功能房间可用性与尺寸依据

TASK_ID=`V2_2_2_R11_FUNCTIONAL_ROOM_FIT_R1`。独立开发，参考 PR320 精确 HEAD `288a56b768baa859cbcfb41908fbbd5d6155094d`。

## 三种结果独立

1. `original_engineering_status`：原封存 Stage B 几何/Access 的状态，只读观察，绝不由本模块重新批准。原 Access 范围没有办公室门洞时，会额外要求实际办公室出入连接。
2. `p1_area_status`：由原 P1 `dimension_handoff.authorities` 的需求面积与实际旋转后房间矩形计算。满足面积不能推导功能可用。
3. `functional_status`：`INPUT_REQUIRED`、`CONFIGURATION_NOT_FIT` 或 `CONDITIONAL_FIT`。最后一项仅证明同一已审阅输入下的**指定布置**有几何/容量见证，不是卫生、消防、无障碍或项目设计批准。

面积、比例及超配的工程公式只在纯 Python Domain 中计算并持久化。评审模板读取已计算的事实，不在页面/JavaScript中重复计算。没有添加 Native 搜索、P1字段、CP-SAT约束或正式质量指标。

## 实现边界与来源

- `layout/domain/functional_room_fit.py`：确定性整数毫米校核；原 P2 `_path_envelopes()` 保留其全宽和转弯包络语义。
- `layout/application/functional_room_review.py`：核对历史字节清单，使用原物理矩形解码、`_eligible()`和P1面积Authority，按实际矩形去重，不重新求解。
- `layout/infrastructure/functional_room_review_page.py`：本地无网络页面，读取持久化结果；实际房间按原物理比例绘制，原Portal保持实际坐标。
- `functional_room_fit_examples.py`：明确的合成数据，独立于真实记录。不是柜型或设备推荐。
- `build_r11_functional_room_review.py`：只读生成报告；强制禁止两种CP-SAT Solve API，不导入Runner/Store或业务签发入口。

沿用既有离线功能模块的“给定布置、操作状态、来源审阅、无全局不可行声明”边界；复用原几何语义并补入可复用应用模块，没有将旧docs动态加载器或另一套授权机制引入生产。

### 输入引用不是授权

`BasisValue` 是应用侧完成资料/适用范围审阅后传入的普通设计数据，不是令牌或签名。调用请求只提供字段引用，不能凭`OWNER_CONFIRMED`字符串自我确认。每个值包含value、unit、来源标签、原文/型号reference及scope_id；本房间Scope含Plan、P1、候选Hash和房间代码，跨房间/旧几何资料不自动复用。

模块不认证Owner身份。应用应先利用现有资料审阅流程，核对原文、型号版本与项目适用性，再构造catalogue；Hash只锁定字节，不能替代审阅。没有新密钥、证书、Grant或Claim系统。

## 校核内容

Changing：两班独立柜、同时使用人数、柜型三维尺寸、内部分隔能力、单侧或双侧朝向、柜前操作区、人员空间、内部净通道、座凳与操作余量、原门洞及门操作包络。人数不能仅从20t进料量推定。没有“房间必须近似正方形”或3m最小宽度。

Office：实际人数、桌体尺寸/高度、逐桌椅子移动区、明确的储物家具数量和尺寸、出入门洞和全宽通道。明确无储物/座凳可填不适用，不以虚构家具尺寸代替缺失资料。

Coating：已选包装箱覆膜设备、台数和三维安装尺寸、四侧操作/维护净距、进出料面与原Portal对应、进出料/缓冲面积及通道连接。几何可容纳不证明设备产能；能力与物流方向仍需真实设备资料和审阅。

所有实体在正常使用、交接班、清洁和维护状态持续存在；通道不能碰撞实体。使用空间不能重叠计数，不能把离门洞网络隔离的空闲区域当作可用。细小转角接触不能证明全宽通行。门操作包络必须与资料中审阅的包络一致并连接真实Portal，不能直接缩小门扇空间以通过。

若洁污分区适用而没有专门审阅的隔断、门洞与卫生流线设计，返回`INPUT_REQUIRED`。本轮不宣称自动完成这类专业分隔设计、人体工效或法规合规校准；不产生未知的卫生要求或新的MUST。

## 真实记录结果

9份R10记录、8组实际房间矩形、27份房间记录；原工程与面积结论不变，功能全部`INPUT_REQUIRED`。P01/P02属于同一实际矩形组，不能重复算作两个功能布局。

H5：更衣室26.331×3.25m，85.57575㎡。H6：约39.6×1.0m、约40㎡。两者均没有建立实际人员/柜型/净通道/门操作/净高的完整依据。Office与Coating也没有项目家具或已选设备的完整依据。不能据此单凭比例宣判“可用”或“绝对不可用”。

Owner V2规则中两班独立柜等政策已确认，但53人/106柜是未绑定历史布局的条件示例；Office12/20/30人需明确规模选择。没有把这些值注入P1或真实校核。

R9 P04的20×2m、40㎡更衣室作为独立历史参考，功能同样`INPUT_REQUIRED`，不加入R10正式Pareto。见`docs/previews/v2.2.2/r11-functional-room-fit-r1/functional-room-report.md`。

## 后续如何转换为P2尺寸条件

只有已批准的功能数据和模板才能进入下一阶段Authority审阅：

- 单侧模板横向需求来自柜深、柜门/人员操作、通道、座凳及另一侧净距；纵向来自单柜宽×柜数、分隔与端部余量。双侧模板分别计算两排，不预先固定比例。
- 不同模板作为显式备选/析取，保留合法旋转。一个模板失败不代表其他模板被排除。
- 要求长度向上取整至整数mm，可用净长度向下取整；名义P2矩形还必须加上经确认的饰面/墙体关系。面积仍读取原P1 Authority。
- 经原工程Authority版本化审批后，才考虑P2中的选定模板条件、设施不重叠、操作区、门扇及全宽连通表达。不得用本报告生成隐性全局最小宽度、面积上限或比例限制。
- 本轮没有编译或写入任何求解约束。所有历史有效状态、九/十二指标、生产默认及已消费授权记录保持原样。

## 本地复现

在独立Python3.12环境安装锁定依赖。无需任何求解授权：

```sh
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_functional_room_review.py \
  --archive /absolute/path/to/stage-b-r10-r2-real-main-r1 \
  --manifest /absolute/path/to/stage-b-r10-r2-real-main-r1-review/raw-evidence-hashes.json \
  --r9-archive /absolute/path/to/stage-b-r9-resource-bound-real-main-r1 \
  --r9-preservation /absolute/path/to/stage-b-r10-r2-real-main-r1-review/historical-hashes-before.json \
  --output ../docs/previews/v2.2.2/r11-functional-room-fit-r1
```

输出必须独立于历史目录。所有历史输入只读，任何来源、Hash或P1身份冲突即拒绝。打开生成的index.html即可离线浏览，也可只在127.0.0.1启动静态预览。

本轮只有源码、报告、单元回归和快速CI；不触发正式CI，不运行MAIN，不创建真实Grant/Claim。完成后STOP。
