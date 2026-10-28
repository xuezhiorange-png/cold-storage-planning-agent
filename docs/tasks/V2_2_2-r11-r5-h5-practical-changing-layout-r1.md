# R11 R5 · H5更衣室工程深化

TASK_ID=V2_2_2_R11_R5_H5_PRACTICAL_CHANGING_LAYOUT_R1

基线PR #324：bc031b50edda3a8e142eb2f0a89b850fc2e2811e。独立分支，原R11 R1–R4实现和历史结果保持不变。

## 具体改动

新增可选择的H5条件模板评估。复用R4的柜体、柜列、独立格口和两班分配；增加分段安装、外开铰链门完整角度扫掠、逐层高度、座凳坐姿体积、独立更衣操作包络、全室53人快照以及两班首组相邻批次的连续换位检查。没有Native或布局求解。

- `changing_room_motion.py`：门扇三维扫掠、人体体积、有限通道图和全段运动包络。
- `practical_changing_layout.py`：单侧、相对双侧、分段模板，明示参数，30/60批次占用核验和首组换位。
- `practical_changing_review.py`：复用原项目审阅结果及封存H5身份；冻结原R4目录内容校验只用于证据一致性，不产生任何批准或Grant。
- `practical_changing_review_page.py` / `build_r11_r5_h5_review.py`：原始归档只读回读、报告、真实比例SVG和本机假设预览。报告读取已保存计算结果，浏览器不计算工程公式。
- 快速CI仅追加新测试文件；正式工作流不变。

## 最有深化价值的条件方案

西段单侧22列/110格，按两列组合为12个假设实体柜。柜体总长度8.8m、占地4.4m²。保持两处真实1500mm Portal、1200mm假设净通道、两张座凳六个座位，以及53处在室本位。东段有独立800×900mm假设更衣操作区，与入口候门区分开。

列宽400、深500、总高1800mm；五层参考净高300mm；底座100、层板20mm；完成面内缩20mm。门为外开0–90°左铰链，框20、厚15、扫掠半径360mm；柜前退让380mm。柜前并发4人，通常另有6人坐姿、1人操作更衣、42人等候。所有上述尺寸、人体包络与流程都属于HYPOTHETICAL_NOT_APPROVED。

两班共30个静态快照通过指定占用检查；两班各首组相邻批次共16条连续人员路径通过。移动时仅1人走动，52人不动，柜门关闭。不能将这些有限证据视为全体53人的完整取衣、更衣和离开过程已证明。

相对双侧、44列双格、较大分段间距和较高格口等指定参数方案的失败保持可见。某个模板失败不代表所有其他方案不可行。

## 仍未成立的工程结论

实际项目功能始终INPUT_REQUIRED。未经审阅的柜型、安装锚固/搬运、柜门和房门开向、内部隔断及衣物容积、人体穿脱衣动作、座凳起坐、完整批次转换时间、清洁维护、消防疏散、洁污工艺都不能从矩形通过自动推出。无CONDITIONAL_FIT，无新工程Authority、P1阈值或正式质量比较变更。

## 复核与证据

主页面及完整原始结果：`docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1/`。

- `review-report.md`：条件、失败及限制。
- `hypothetical-results.json`：逐人、逐格、门扇高度、快照冲突、完整运动扫掠及各步52人位置。
- `source-manifest.json`：原档及衍生文件SHA256。
- `validation.json`、`local-tests.junit.xml`、`ci-contracts.txt`：本地验证。
- `h5-best-conditional-plan.svg`、两班立面及16步换位SVG。

Python3.12锁定依赖下，1079通过/16原有跳过，新增55项R5测试；CI契约65通过。Ruff、Format、Mypy与YAML通过。全部测试禁止两个CP-SAT Solve API。初次架构子进程误用系统Python而缺少pytest，修正PATH后完整重验通过；未修改测试规避此环境错误。

原291个历史/任务状态文件校验一致，已追踪原实现仅快速CI测试allowlist追加一行。没有真实Grant/Claim、MAIN、Native、正式CI、Ready、Merge或Deploy。
