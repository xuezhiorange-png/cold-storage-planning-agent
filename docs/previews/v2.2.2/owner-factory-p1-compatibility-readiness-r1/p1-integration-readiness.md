# 正式P1实施准入与版本隔离（设计，不实施）

## A/B/C边界

**A BUSINESS_RULES_READY=true**：OwnerFactoryFunctionalInputsV1规则已确认，可离线计算。
这不表示任何实际项目的质量来源、设备、家具、工厂分级已齐全。

**B P1_INTEGRATION_IMPLEMENTATION_READY=false**：本轮产出了兼容矩阵与草案，但以下阻断尚未解除。

- BLOCKING_INPUTS：实际项目/产品/期间、包装质量及来源、两个班次分配、规模选择与定义、
  工位/柜体/设备和净空间参考、状态Envelope、设备有效运行时长、适用卫生/隐私审查。
- BLOCKING_AUTHORITY_DECISIONS：原3人/台是否适用，包装台是否跨班共用、是否有额外工况；
  新面积计算与Dimension profile的来源及批准；新旧策略的适用项目与supersession。
- BLOCKING_IMPLEMENTATION_ITEMS：可信来源接入、显式版本选择、业务别名迁移、
  新Canonical身份和下游绑定、测试矩阵、可逆切换与Owner独立实施授权。

有的缺项是运行时项目输入，有的是先于实施的政策/合同决定。不能因接口草案写完或测试通过，
就把B改为true；须逐项由具名审核确认哪些前置已满足、哪些应由新入口在运行时拒绝缺失。

**C P1_PRODUCTION_ACTIVATED=false**：只有独立授权实现、完整工程回归、exact-head CI及版本验收后
才可启用；不因A/B进度自动继承。无新求解Grant，不执行真实工厂求解。

## 提议的消费边界

1. 既有输入默认继续走LEGACY_CANONICAL，不注册Owner新输入到现有MCP/Tool7。
   旧336、25/50吨档、结果JSON/Hash、公式版本和原P1/P2行为保持。
2. 独立评审Owner业务扩展契约及策略身份，禁止把version字符串改一下就复用旧Authority。
   未来新模式需同时绑定Owner规则版本、真实来源字节、批准记录、Canonical输入及策略版本。
   不接受调用方provided verified=true作为合法来源；Hash是完整性，不是审批。
3. 上游先建立原果/包装产品质量口径，缺转换或显式分班则Fail-closed。
   生产入口应由可信服务取得/校验资料与审查角色，不依赖离线目录名称或一个字符串引用。
4. 在已批准台位并发/共用政策下计算候选台数，再独立批准排布模块、面积及精确/报告精度链。
   不在新分支直接调用旧plan并偷偷把raw输入改成产品量，也不伪造新面积后改Hash凑绑定。
5. 新office/changing/coating功能面积未校准时，整体新P1不得宣布完整。
   不隐式套旧吨位档或按无来源人均面积/设备尺寸填空。是否允许明确标注混合Authority的
   过渡模式必须另行审查，不能在本轮默认启用。
6. 正式P1消费者须检查新身份及source/profile批准，重建Dimension Handoff；排序间格位/面积
   改变会影响长短边、Packaging接口和下游几何，必须独立复验。旧结果只读归档而非“升级”。
7. 保留当前未建模尺度的UNMODELED_FLEXIBLE_DIMENSION_RULE。未来只有明确授权的新增消费者
   才能支持新净宽等Hard；不利用本次输入人数绕过Fail-closed或改工程可行域而不披露。

## 兼容与回退测试设计

旧分支金样字节与canonical Hash、Authority/profile和12角色/7MUST不变；旧336和吨位边界不变；
新分支缺包装源/班次/审批拒绝；新旧身份不能互相冒充；来源重放/篡改/跨项目拒绝；
总员工与并发/柜位分离；3人/台及共用必须有明确政策；旧浮点报告与精确面积链不混；
未校准面积不成Canonical；Owner业务别名映射经批准再迁移；专业合规状态不随布尔值放行。

回退设计：新模式在正式启用前保持显式开关关闭，旧默认路径不变；未来启用记录策略版本及输入来源。
禁用新模式只能恢复旧请求的旧模式，不能把新产品质量请求自动降级成旧原果输入。
新项目若缺准入，返回明确阻断；保留已生成结果原始身份、Hash及审计，不原地改写历史。
不执行数据库迁移、部署或生产切流。

本次只读生产区域计算及P1尺寸投影，无CP-SAT/Placement搜索；不改D01/D03/D04或P3历史262UNKNOWN。
