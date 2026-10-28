# R11 R3 · 已确认成品项目的106柜评审

TASK_ID=`V2_2_2_R11_R3_106_LOCKER_LAYOUT_REVIEW_R1`

基线：PR #322 `93d7d1520052daf2fccdf62e6dd7e61468ef007f`。独立分支与Draft PR。

## 项目事实与计算

本轮Owner明确确认的是实际包装成品20000kg/天，不是从历史进厂量推断。
原确认及其Plan/P1适用范围封存在 `V2_2_2-r11-r3-reviewed-project-fact.txt`；
应用侧 `bind_r3_project()` 将该已审事实构造成已有 `ReviewedProjectDatum`，调用R2绑定函数。
文档摘要仅防止来源或适用范围意外变化，不是MAIN授权或Grant令牌。
普通JSON中的source_label/status不能签发已审输入，本地页面也没有此类入口。

无实际两班人数覆盖时，沿用Owner V2可信默认均分：10000kg/班，按192kg/人班向上取整为53人，
两班分别53柜，总计106柜，同时更衣53人，包装台18张。这是项目设计计算，不是人员花名册。
原Owner V2文件、历史进厂量、R11 R1/R2模块、P1及验收器均不修改。

## 两关必须分开

`changing_locker_screening.screen_locker_rows()` 是整数毫米、指定长墙模板的必要条件与
显式假设排布检查；无Native搜索，也不排除其他未检查模板。基础单侧长度N×柜宽，
相对双侧理想长度max(n1,N-n1)×柜宽（均分时才等于ceil(N/2)）、宽度2×柜深+净通道。随后扣除真实门洞缺口、
假设端部/完成面留空，列出实际可画柜位、两班身份、同时人员与座凳空间冲突。
柜前操作与通道分开保留的规则属于当前假设模板，不能变成房间硬性最小宽度。

真实设计还缺柜型/尺寸、装修完成面、净高、柜门和房门操作、人员空间、座凳、内部通道、
清洁分隔及清洁维护依据，故8组房间均为 `INPUT_REQUIRED`。假设参数永不转为BasisValue。
后续完整设计经应用侧审阅后，用 `evaluate_reviewed_locker_witness()` 调用原R11校核器，
保留106柜精确独立身份、53人、真实两门连接、操作冲突和四状态校核。
修正后需显式提交两班独立见证和已审逐状态操作/柜门计划，详见
`V2_2_2-r11-r3-locker-functional-validation-fix-r1.md`；单份旧witness不能证明两班能力。
`CONDITIONAL_FIT` 仅是完整已审输入下的指定布置条件结果，仍非专业工程批准。

单元测试中的26×8m完整设计是独立合成夹具，不能当作H5或任何历史房间的新有效方案。

## 历史来源

9份历史记录按原8个物理组归并；P01/P02同属G01，只评审一次，两个源Candidate Hash均保留。
房间尺寸及原Portal来自封存R11 JSON，原始Candidate JSON逐字节SHA核对后回读两条Access。
图中外部中心线仅为历史工程证据；不替代新增内部通道、柜体与门扇连接见证。
原Stage B有效状态、九/十二指标、历史MAIN、Grant/Claim、资源账本和生产默认保持不变。

## 浏览及复现

新建只读报告（输出目录须不存在；`--raw-archive` 指向原R10 R2封存执行目录）：

```sh
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r3_locker_review.py \
  --raw-archive /absolute/path/stage-b-r10-r2-real-main-r1 \
  --output ../artifacts/r11-r3-locker-review
```

在生成目录上启动仅限本机的敏感性评审，不会写入设计Authority：

```sh
PYTHONPATH=src:scripts uv run python scripts/build_r11_r3_locker_review.py \
  --output ../artifacts/r11-r3-locker-review --serve --port 52988
```

浏览 `http://127.0.0.1:52988/`。可切8组、单/双侧、柜体/人员/座凳/通道参数及四状态图层；
所有工程计算由Python完成，浏览器只提交假设参数与显示已计算的SVG/结果。
静态HTML可离线切换8组和默认单/双侧；自定义参数需上述Python服务，不会在前端另写工程公式。
HTTP仅支持假设预览，不接受reviewed_basis、witness、Owner标签或项目人数覆盖。

报告含项目绑定、8组房间与原门洞、16种默认假设排布、逐项失败原因、SVG、来源摘要。
独立SVG也带 `HYPOTHETICAL_NOT_APPROVED` 与 `INPUT_REQUIRED` 标识。

本轮零Native/MAIN/真实Grant/Claim，禁止正式完整CI、Ready、Merge、Deploy。
