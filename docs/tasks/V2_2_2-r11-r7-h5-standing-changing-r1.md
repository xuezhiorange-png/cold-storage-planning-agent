# R11 R7 H5 无坐凳站立更衣

TASK_ID=V2_2_2_R11_R7_H5_NO_BENCH_STANDING_CHANGING_R1

Base PR #326 / `b1ca6be49e47d9e0c191205c7cee84ebcc269baf`。

本任务允许独立分支开发、测试、Commit、Push、Draft PR及自动快速CI。禁止Native、MAIN、Grant/Claim、正式完整CI、Ready、Merge、Deploy。不得修改历史证据、P1、Stage B、九/十二指标或生产默认。

## 已审项目事实

Owner在本任务确认实际不设置坐凳、人员站立更衣。原两班各53人、22列110格及53人同时在室设计基准不变。`standing_changing_review.bind_standing_project()`采用原ReviewedProjectDatum模式：先核实原项目Scope和封存目录，再核实已审原文来源，构造BENCH_COUNT=0与CHANGING_POSTURE=STANDING两个项目事实。普通JSON的source_label/status不能进入该接口；Hash用于固定已审来源，不是凭证或Grant。

## 实现边界

新增R7 `standing_changing_layout`与`standing_changing_operation`。复用原柜体层/格/人员分配、三维门扫、通道网络、真实Portal以及碰撞检查。R7没有座凳、座位、坐下、起身或座凳使用计时，也不预留唯一800×900mm操作区。原R5/R6代码与结果保持不变，R7不调用它们强制经过座凳的完整服务链；仅复用纯几何检查和入室路径校核。

柜前直接站立更衣和回本人分散位置站立更衣均为未批准条件。更衣活动包络与400×600mm运输身体分开；包络包含身体，不通过删除等候者或侵入净通道获得通过。先53人全部进入，再按原个人柜格分配进行批次操作。动作可按批次并行，通道移动保守串行，每个移动段以原通行中心线及连续身体扫掠校核。没有建立多方向同时通道流动能力。

R7实际功能始终INPUT_REQUIRED。实际柜型、人体/穿脱动作、净通道、门扇、时间、洁污与清洁维护条件均需审阅。Source确认不批准具体分散/柜前更衣方式。

## 可复核结果

输出目录：`docs/previews/v2.2.2/r11-r7-h5-standing-changing-review-r1/`。

入口：`backend/scripts/build_r11_r7_standing_review.py`，要求新的输出目录；直接阻止两种ORTools Native API，仅调用确定性功能几何代码。先保存结果，再生成HTML/SVG/报告。旧R6源结果Hash保存在新manifest中，旧文件不改写。

8种条件方案保留成功和失败：4人分散、4人柜前、1人柜前、2/6人分散、扩大活动包络、扩大身体及等候间隙、仅静态身体边界负面参考。失败后不计算完整班次时间，不宣称所有其他方案不可行；完成服务但尚未成功离室者不计入完成使用人数。

验证包含R11 R1–R6回归、零座凳及全部人员身份、30批/28边界、并行时间、末位失败、原门洞/通道/门扫拒绝、旧输入与历史结果不变、Ruff/Format/Mypy、CI契约。只在ci-fast增加新测试模块，不触发正式CI。
