# 原验证器复用与尚未闭合的输入边界

本轮不修改以下任何验证器，不另建Truck审批系统。测试仅调用纯合同和静态必要条件，搜索入口一旦被调用即由测试保护报错。

| 现有实现 | 复用内容 | 边界与本轮结论 |
|---|---|---|
| P1F `validate_project_truck_input` | 项目引用完整性、车辆宽长、正数、毫米grid、同项目及摘要格式 | `COMPLETE`仍恒定`evidence_contents_verified=false`；没有原件不能形成完整几何输入。测试验证完整引用而模板缺失仍阻断 |
| P2B1 `validate_truck_maneuver_project_binding` | 原同项目/同车辆、模板集合与requirement、Hash、版本、姿态、dock reference | canonical模板Hash不是源文件字节Hash；项目所需类别可为子集，不能统一强制三类。测试覆盖缺类别、错项目/车长、版本及Hash |
| P2D immutable result reader / loading-face谓词 | 原应用结果Hash、实际Shipping长边和所选侧 | 不生成Portal、不搜索、不重新验证11项Access；历史原始结果逐套回读，错误面或跨候选复制被拒绝 |
| R13 `_evidence` | 原Base64、大小限制、引用一致性、实际字节SHA核验 | 字节相同不证明项目适用或人类审批；未创建本地平行审批字段或新Owner Grant |
| R13 `_vehicle_body / _verify_body_envelopes` | 显式车身参考点、车身宽长及模板若干姿态的必要覆盖 | 不证明连续车辆动力学/完整扫掠充分性；仍需原项目工程资料确认 |
| R13完整preview / P2D route入口 | **本轮不调用** | 完整preview在`truck_parameter_input.py:270`启动原生Option C搜索，没有独立公开的完整输入-only入口；审批记录匹配与完整验证留给另行授权的原流程 |

## 具体缺口与证据

1. **资料引用完整但内容未验证**不是P1F Bug，而是原合同明示边界。实际冻结P1正好处于此状态；本预检单独列出来源原件及审批缺失。
2. **软件schema版本不等于图纸/车型资料修订**。P1F/P2B1没有独立的图纸修订字段；来源reference、content_sha256仅能标识提交者声明。新资料必须保留制造商、型号、项目适用性、实际修订及可读原件，由既有专业审查核实，不由预检发明正式Authority。
3. **完整输入验证与搜索耦合**。本轮没有拆分生产代码，只复用纯谓词并在输出中标明 `NECESSARY_STATIC_SUBSET_NOT_FULL_R13_OR_P2D_VALIDATION`。它不是完整R13验证的替代。将来若希望无搜索完成所有原输入校核，可另行批准抽取原函数前半部为等价输入校验端口，并证明原preview行为/错误码不变；本轮只提出，不实施。
4. **R13提交审批记录匹配不认证签署身份**是原合同明示边界。其`REAL_PROJECT_APPROVED=false`不变。本预检也不通过`verified=true`、`APPROVED`、重算Hash或测试身份提升项目状态。
5. **候选专属上下文不可省略**：相同Site、同车和同模板不能跨不同Shipping面、房间、Portal、人员通道和建筑几何复用Truck PASS。8套精确装卸面和Truck上下文均不同；每套需原P2D链独立复验。

## 下一次正式验证的必要条件

取得带项目身份/版本的真实车辆、Gate开口及净空/方向、实际需要的Option C模板和完整包络、装卸接口、人员车辆冲突处理及审批来源；按原合同绑定业务输入、P1、typed Site、候选所选装卸面和原件字节；如资料引起Authority变化先获得修订授权并保留旧记录。之后另行授权原R13/P2D执行及必要资源，逐套记录链/扫掠/交互/Footprint与最终状态。没有这些条件时保持 `PROJECT_TRUCK_INPUT_ADMISSION=BLOCKED`，不得把当前0节点解释成不可通行。
