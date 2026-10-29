# R11 R10 CI覆盖与方案一致性复核

TASK_ID=V2_2_2_R11_R10_CI_COVERAGE_R2
BASE_HEAD=58590723f45d8a773fc30ad551ff9f19f7456043

本轮只增加远端测试覆盖和封存数据一致性检查，不重新生成布局或更改规划算法。原R10报告、完整流程、图纸和R9执行边界异常均逐文件SHA256核对，保持原样。

| 方案 | 长×宽mm | 完成面假设mm | 安装间隙输入基值mm | 实际柜到完成面mm | 模板加量目标mm | 实测最小已定义余量mm | 北侧余量mm | 两班完成 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C | 26331×3550 | 20 | 20 | 70 | 50 | 50 | 60 | 53/53 |
| B | 28000×4350 | 20 | 20 | 170 | 150 | 150 | 160 | 53/53 |
| 3850mm sensitivity | 26331×3850 | 30 | 40 | 140 | 100 | 70 | 70 | 53/53 |

安装间隙输入基值与实际柜到完成面距离不同：模板还包含明确的假设余量加量。表中余量来自原完整几何及流程的实测结果，不是将输入目标当作PASS。

B必须采用NORTH_NORMAL_SOUTH_ROTATED本位组织；同长宽的MIXED方案不能代替B。C采用MIXED。3850mm图纸为独立的30mm完成面/40mm安装基值敏感性方案，不是默认20/20条件；其70mm达到单独50mm稳健评审目标，但没有达到100mm模板加量目标。实际功能和工程批准均保持INPUT_REQUIRED。

C的50mm余量不能直接沿用到30/40组合假设：原敏感性证据中C只余20mm。3600mm宽组合对照只余40mm，仍低于50mm目标；两条原失败对照均未修改。

每个选定原始见证的geometry/shifts/margins重算SHA256与原记录一致；保存的plot-data与原始几何一致；纯展示渲染器输出与原SVG逐字节一致。此处没有执行新的功能布局搜索或Native。

## 原图与原报告

- [C：完成面20mm / 安装输入20mm](../r11-r10-functional-room-reverse-sizing-r1/C_less_building_change.svg)
- [B：完成面20mm / 安装输入20mm](../r11-r10-functional-room-reverse-sizing-r1/B_larger_margin.svg)
- [3850mm sensitivity：完成面30mm / 安装输入40mm](../r11-r10-functional-room-reverse-sizing-r1/width-only-robust-sensitivity.svg)
- [原R10完整报告](../r11-r10-functional-room-reverse-sizing-r1/reverse-sizing-report.md)

## 远端执行证据

原32个测试文件及其顺序/选项全部保留，仅新增R10文件。既有合成Native测试保留，不在本地运行。原fast-ci-gate未改变。pytest将保存JUnit，由独立Artifact保留，失败和缺失报告不会被当作通过。提交后核对新精确HEAD的远端JUnit中R10的实际41项结果，最终状态另行回执，避免为回填CI结果再改变HEAD。

## 本地验证

R10明确白名单41项通过，CI契约65项通过（包含原分类器50次清理回归）。YAML语法及原32个文件/选项/fast-ci-gate等价性检查通过。只运行功能测试、CI契约与只读数据核对，没有本地历史Stage B/Native测试或新Native执行。
