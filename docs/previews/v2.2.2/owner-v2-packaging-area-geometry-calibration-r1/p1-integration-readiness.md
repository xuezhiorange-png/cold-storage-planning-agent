# P1接入准备与回退边界

BUSINESS_POLICY_READY=true：OwnerFactoryFunctionalInputsV2的人数、峰值台数和柜位可以有来源地独立精确计算。

PACKAGING_AREA_CALIBRATION_READY=false：本项目设备/三人工位、物流、独立通行、清洁检修及外围余量尚缺审核依据。参数矩阵所列待定项不因离线测试通过而成为正式Authority。

P1_INTEGRATION_IMPLEMENTATION_READY=false：需要先完成上述校准，再审核新版排布、质量来源、默认/覆盖版本选择、精确面积与报告投影、下游尺寸和空间验证及失败回退合同。现有旧台数算法/1.1不直接复制为新版正式面积。

P1_PRODUCTION_ACTIVATED=false：本轮不改生产计算器、Canonical、Dimension Handoff、Global/Access模型、Selector、Tool7/MCP。离线结果拥有独立版本和Hash，既有V1/V2原件和Legacy Canonical/P1 Hash保持不变。

未来若获独立授权，应采用显式版本路由而非更改旧默认值；旧Canonical与封存结果原样可重放，新版输入缺失或验证失败时拒绝新版计算，不静默切回旧质量口径制造新结果。回退是选择原Legacy版本与原输入/Authority，不覆盖已生成项目版本。

本轮没有新面积、整厂总面积或功能合格结论；正式P2D full-pass仍为0，Stage B/P3/版本不因本研究完成而完成。旧8套布局仅是接口边界证据，不是新版P1验收结果。
