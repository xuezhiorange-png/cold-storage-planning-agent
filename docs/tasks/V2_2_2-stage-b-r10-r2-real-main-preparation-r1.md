# R10 R2 独立 MAIN 接线准备

TASK_ID=`V2_2_2_STAGE_B_R10_R2_REAL_MAIN_PREPARATION_R1`

开发基线：PR319，`0cf97f6d4a4ba48947bc9bfdef25e97968eb9832`。

本独立 Draft PR 仅准备既有 `StageBEntranceCoupledSpatialFairSolver` 的独立单次真实 MAIN 入口；策略保持 `sha256:fc0082de49eb1e289c487c2f88c4a873f73b3a553077102dc7dc1aa0e11afcf5`。不修改算法、P1、工程约束、九/十二项比较或生产默认。

先建立本 PR 以确定真实 PR 编号，再一次冻结规范化 Owner Scope、Hash、分支/Base 身份与源码接线，不猜测编号、不将未来提交 SHA 写入自引用 Scope。准备本身不签发 Grant，也不允许 MAIN。

后续接线复用原 Runner、可信 Store、PoolLease、精确 HEAD 正式 CI 准入与累计资源保护：49.9s Native、85s Elapsed、600000 Work、512MiB、100 Native Calls、20 完整检查、单要求20000 Host Work，六 Handoff及两阶段共用，不执行 R9 局部复制。

本轮仅合成登记簿准入/资源测试和封存20t零 Native 构模、正常提交及自动快速 CI。不得正式完整 CI、真实 Grant/Claim、MAIN、Ready、Merge 或 Deploy；PR317/318/319及已消费历史记录保持不变。
