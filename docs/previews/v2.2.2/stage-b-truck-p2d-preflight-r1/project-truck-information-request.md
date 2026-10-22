# Truck项目工程资料索取清单

当前八套均为输入阻断，不是搜索后不可通行。请提供可核验原件；本清单不签发执行或审批授权。

| FIELD | 当前状态 | 所需资料 | 阻断阶段 |
|---|---|---|---|
| vehicle_width_m | REFERENCE_ONLY | 实测/车型规格书车宽、适用项目及批准选型记录 | P1F |
| vehicle_length_m | REFERENCE_ONLY | 车型规格书车长、版本、参考点与项目适用性 | P1F |
| vehicle_type_model_and_revision | UNAVAILABLE | 制造商、型号、修订和有来源的实际车辆尺寸 | SOURCE_ADMISSION |
| project_vehicle_source_bytes | UNAVAILABLE | 原始设备/车辆资料字节与实际SHA；示例a/b摘要不可替代 | SOURCE_ADMISSION |
| site_truck_entrance_segment | SOURCE_BYTES_VERIFIED | 已有参考点定位线段；与实测开口之间的工程映射仍需确认 | SITE_BINDING |
| measured_gate_clear_opening | UNAVAILABLE | 带坐标、净宽和现场测量依据的有效开口线段 | TRUCK_INPUT |
| gate_clearance_and_inward_direction | UNAVAILABLE | 通行方向、限制及显式安全净空依据；不得默认半径或余量 | TRUCK_INPUT |
| required_maneuver_classes | UNAVAILABLE | 声明本项目需要的类别；P2D靠台要求DOCK_REVERSE，不能无依据强制全部三类 | P2B1 |
| bound_maneuver_project_input | UNAVAILABLE | 与项目和车宽车长一致的完整模板、姿态及绑定Hash | P2D |
| maneuver_source_bytes_and_revision | UNAVAILABLE | 直行/所需转弯/倒靠模板及完整扫掠包络、图号、修订、来源字节 | SOURCE_ADMISSION |
| actual_shipping_loading_face | INPUT_VALIDATED_NOT_ROUTE_PASS | 当前长边几何可复核；实际装卸面确认与候选身份需逐套批准 | P2D_CANDIDATE_BINDING |
| dock_face_project_approval | PROJECT_APPROVAL_REQUIRED | 装卸平台与车辆到达姿态、实际接口设计确认 | ENGINEERING_REVIEW |
| site_obstacles | SOURCE_BYTES_VERIFIED | 冻结场地三块禁建障碍原样保留；不等同于道路可通行批准 | P2D |
| approved_truck_road_use_area | UNAVAILABLE | 道路用途、承载/通行限制及可用区域；buildable不等于批准行车道路 | ENGINEERING_REVIEW |
| personnel_truck_conflict_review | ENGINEERING_REVIEW_REQUIRED | 结合该候选人员通道和实际Truck包络复核，不跨候选复制 | P2D |
| template_approval_and_review_identity | PROJECT_APPROVAL_REQUIRED | 审批记录及专业审核身份；Hash或调用方APPROVED不证明审批有效 | ENGINEERING_REVIEW |

原始图纸和内部运输协议保留获授权的本地证据目录，公开提交前必须取得传播许可并脱敏。不得用旧示例或公共车型填空。
