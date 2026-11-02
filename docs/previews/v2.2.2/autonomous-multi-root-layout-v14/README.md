# 自主整厂布局 V1.4 · 多根空间搜索

独立非Native预览入口，基于 PR #340 的 `3b1db476e09f8fa748c512e5ecd8912f2a8f4776`。
不接入生产MCP、默认规划、Stage A/B Runner或授权槽。

## 复算

在backend的锁定Python 3.12环境中运行；输出目录须不存在。

```sh
PYTHONPATH=tests/functional_native_guard:src:scripts \
R11_FUNCTIONAL_GUARD_AUDIT=/tmp/autonomous-v14-native-guard \
uv run python scripts/generate_autonomous_multi_root_layout.py \
  --input ../docs/previews/v2.2.2/autonomous-multi-root-layout-v14/inputs/project-input.json \
  --parameters ../docs/previews/v2.2.2/autonomous-multi-root-layout-v14/inputs/process-parameters.json \
  --search-configuration ../docs/previews/v2.2.2/autonomous-multi-root-layout-v14/inputs/search-configuration.json \
  --finished-storage-days 7 8 --output /tmp/autonomous-v14-fresh-result
```

父子Python继承现有Native禁用防护；未创建或消费Grant/Claim，无MAIN、模型复制或真实Native调用。
自动ci-fast保留全部旧测试，其中包含原有合成Native测试；不能将整条CI描述成零Native。

## 搜索与准入

- 每次调用先由当前输入重新计算V1.3参考，保留7天B原坐标及8天364位见证；不读取历史候选或已有图纸坐标。
- 三种结构偏好分别生成根；初始位置索引来自当前建筑/P1事件锚点，旋转来自当前Authority。
- 不同根独立计算设备、仓储、门面及路线。柱体/保留通道冲突反馈为按实际障碍边缘计算的新根；容量、空洞和接口失败反馈为新的附件组合。
- 合法门面/精确房间通道并集的必要预检查只用于提前淘汰；完整准入重新执行，不能继承其他根的PASS。
- 原全量准入、P1、7MUST、11Access、设备数量、当前仓储网格、六线三支线、57交接、10+6通行和两班53人不变。
- 房间、设备、门面和选中路线用于物理去重；核心功能关系在8个全局正交变换下规范化，镜像、整体平移或只改覆膜间不算新组织。
- 多样性还要求至少两个核心功能区相对位置变化不小于半个现有轴跨；这是候选分类条件，不是工程硬约束。
- 仅完整准入后的候选参与参考段、转弯、交会及面积比较。原九/十二权威比较器不变，不跨不同P1进行正式Pareto比较。

`results/`提供同次计算JSON、图纸及页面。每个根的房间、设备、货位尝试、失败对象和反馈来源保存在台账；未完成12区的搜索记录最深部分状态及代表性拒绝，未假称完整候选。

`search_budget`记录真实附件DFS节点、根调用、完整重验次数及停止原因。
设备/路径已采集的操作计数另列，不把未采集操作推算为Work，不发行或借用历史Stage A/B份额。
有界失败不证明全局不可行。条件性工艺接口、实际设备、人体、车辆运动学、同时交通、吞吐、Truck、完整P2D和工程批准仍待相应证据。

原PR #338–#340、此前7→8天失败和成功、Native边界异常全部保留。
