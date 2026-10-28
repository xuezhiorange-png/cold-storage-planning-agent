# R11 R4 — 五层格口与更衣空间独立评审

TASK_ID=V2_2_2_R11_R4_MULTI_TIER_LOCKER_MODEL_R1

基线 PR #323：`aedcbcbe5114f4624a89f61e3fa9305a49a12197`。

本轮新增 opt-in 的功能评审模块，不修改 R3 的实现或历史结论。原项目级成品质量审阅绑定及 Owner V2 规则继续从 R3 读取；本轮确认的“五层五门、每人独立格口”单独绑定到原项目 Scope。普通页面 JSON 不能修改确认事实或创建批准状态。

## 实体和计算

`multi_tier_locker_model.py` 将落地柜体单元、竖向列、独立格口、设计人员分配分开。基本方案每班53格：ceil(53/5)=11列，合计22列、110格，备用格不跨班借用。厂家每柜含几列尚不明确，实体柜体数量不能由列数直接当作事实。

内部分隔方案与每人两格方案分别建模。后者每班106格、22列，合计44列、220格。两种方式都没有取得卫生分隔批准。300mm格高只是近似参考，不能据此宣称柜总高1500mm；假设立面另列底座、层板和柜总高。

53人同时在室保持不变。柜前并发K单独输入，默认缺失。有限操作批次按每列同时最多1人安排，各班的每个已分配格口都有对应服务动作；每个使用批次仍容纳该班全部53人。

## 几何校核边界

`multi_tier_locker_layout.py` 仅构建确定性模板，不调用求解器。使用原R11矩形交叠/覆盖/连通谓词及P2中心线全宽包络，检查柜体、操作区、人员、门扇和座凳是否侵入净通道，以及两处原Portal是否可由实际净宽路线连接。人员必须关联自己的本班格口和柜列，不能利用不同层格口在同一地面重复占位。

运行状态包含两班分别使用、错峰交接、清洁和维护。快照并不证明动态换位、疏散、吞吐、服装体积、可达高度人体工学或清洁规程。缺少实际尺寸/并发/分隔等设计资料时，真实功能状态始终 `INPUT_REQUIRED`；指定模板失败仅为 `CONFIGURATION_NOT_FIT`，不能推广为其他模板均不可行。`SNAPSHOTS_VALID_UNDER_HYPOTHESES` 绝不等于 `CONDITIONAL_FIT`。

## 输入与产物

独立源码：domain `multi_tier_locker_model.py`、`multi_tier_locker_layout.py`；application `multi_tier_locker_review.py`；infrastructure `multi_tier_locker_review_page.py`。

生成器复用 R3 只读原件校验，逐份验证9候选哈希及两处Portal、两个Access原记录，输出8个物理矩形组。新产物位于 `docs/previews/v2.2.2/r11-r4-multi-tier-locker-review-r1/`，旧产物不覆盖。页面不在JavaScript中重新计算工程公式。自定义参数通过本机Python预览，禁止字段越权。

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r4_multi_tier_review.py \
  --archive /absolute/path/to/sealed/stage-b-r10-r2-real-main-r1 \
  --output /absolute/path/to/new/r4-report
PYTHONPATH=src:scripts uv run python scripts/build_r11_r4_multi_tier_review.py \
  --serve-existing ../docs/previews/v2.2.2/r11-r4-multi-tier-locker-review-r1 --port 52990
```

生成器禁止两个CP-SAT Solve API。页面无项目审批、Store或Claim入口。

## 验证与保留项

新单元测试覆盖22/44列和110/220格、制造单元分组、层高溢出、格口重复与跨班复用、两班全部53人、并发批次、通道占用假阳性、门扇、座凳、可达高度、真实Portal以及8组矩形。原R11 R1/R2/R3和架构回归保持通过。

快速CI只追加本模块测试到现有allowlist；正式 `ci.yml` 不变。本轮不触发正式CI，不使用Native、MAIN、真实Grant/Claim，不改变P1、Stage B、比较器、生产默认或已消费历史记录。后续任何已审功能尺寸进入P2须有单独批准和显式版本化接线。
