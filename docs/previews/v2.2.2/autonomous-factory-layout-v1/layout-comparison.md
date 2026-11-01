# 自主整厂布局生成 V1

本轮仅输入原建筑结构、业务参数及设备规格，没有读取V2/V3功能分区或历史候选坐标。

Owner已确认允许室内保留柱体；新墙线、设备和通道仍避让，柱体损失从净面积单列。原尺寸Authority未修改。

|候选|独立房间|原MUST|非货车Access|包装线|折箱机|十门柜|原P2房间检查|
|---|---:|---:|---:|---:|---:|---:|---|
|A|12|7/7|11/11|6/6|5/5|11/11|PASS|

## 方案A

结构接触图Hash：sha256:9a0abc67ab0a0879a5a5dc3fa002be3aa606ebdc92bbe5881cfae9444e2a257e。占用房间毛面积2230.825205m²，室内柱投影0.8415m²；不能以毛面积自动证明货位取放或功能可用。

|功能区|X/Y mm|宽×深mm|毛面积m²|扣柱面积m²|
|---|---|---|---:|---:|

设备布置后的室内通道复核（与原室间Access分别报告）：

- changing_room：INTERIOR_FULL_WIDTH_PATH_VERIFIED，净宽2500mm；已核实完整宽度的室内段。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- coating_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- finished_goods_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- primary_precooling_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- secondary_precooling_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
|更衣室|71837 / 14518|6325×6325|40.005625|40.005625|
|覆膜间|86680 / 23171|8945×8944|80.00408|80.00408|
|成品间|86680 / 32115|18600×32400|602.64|602.2797|
|冻果间|58200 / 12643|10800×8200|88.56|88.56|
|办公室|95625 / 15615|6000×10000|60|60|
|包材库|16620 / 18993|14500×17300|250.85|250.6682|
|一级预冷间|31120 / 34443|14700×10050|147.735|147.6138|
|原果暂存间|45820 / 34443|15200×8700|132.24|132.0618|
|次果暂存间|49800 / 13943|8400×6900|57.96|57.96|
|二级预冷间|76880 / 22618|9800×10050|98.49|98.49|
|出货通道|95625 / 25615|7693×6500|50.0045|50.0045|
|分选包装间|31120 / 20843|45760×13600|622.336|622.336|

设备拒绝记录（未将冲突设备画成通过）：

- finished_goods_room-PAL-003：COLUMN-41487
- finished_goods_room-PAL-004：COLUMN-41487
- finished_goods_room-PAL-019：COLUMN-41977
- finished_goods_room-PAL-111：COLUMN-41486
- finished_goods_room-PAL-112：COLUMN-41486
- finished_goods_room-PAL-154：COLUMN-41976
- finished_goods_room-PAL-246：COLUMN-41485
- finished_goods_room-PAL-247：COLUMN-41485
- finished_goods_room-PAL-262：COLUMN-41502
- packaging_material_storage-PAL-017：COLUMN-41475

|存储区|原计算最低货位|实际主体位置|缺口|取放验证|
|---|---:|---:|---:|---|
|raw_fruit_buffer|37|45|0|未验证全货位取放|
|finished_goods_room|315|315|0|未验证全货位取放|
|secondary_fruit_buffer|19|21|0|未验证全货位取放|
|frozen_fruit_room|34|36|0|未验证全货位取放|
|packaging_material_storage|67|66|1|未验证全货位取放|

设备后门前预留/操作带冲突：

- portal:access:raw_fruit_buffer->primary_precooling_room@1.0.0:raw_fruit_buffer@1.0.0：raw_fruit_buffer-PAL-001, raw_fruit_buffer-PAL-010, raw_fruit_buffer-PAL-019
- portal:access:raw_fruit_buffer->primary_precooling_room@1.0.0:primary_precooling_room@1.0.0：PRI-C3-P4, PRI-C3-P5
- portal:access:primary_precooling_room->sorting_packaging_room@1.0.0:sorting_packaging_room@1.0.0：PACK-05, PACK-06
- portal:access:sorting_packaging_room->secondary_precooling_room@1.0.0:sorting_packaging_room@1.0.0：ERECT-03
- portal:access:sorting_packaging_room->secondary_precooling_room@1.0.0:secondary_precooling_room@1.0.0：SEC-C1-P2
- portal:access:secondary_precooling_room->coating_room@1.0.0:secondary_precooling_room@1.0.0：SEC-C2-P5
- portal:access:coating_room->finished_goods_room@1.0.0:coating_room@1.0.0：FILM-FILM, FILM-OUTFEED
- portal:access:coating_room->finished_goods_room@1.0.0:finished_goods_room@1.0.0：finished_goods_room-PAL-190, finished_goods_room-PAL-191, finished_goods_room-PAL-192, finished_goods_room-PAL-217, finished_goods_room-PAL-218, finished_goods_room-PAL-219, finished_goods_room-PAL-244, finished_goods_room-PAL-245
- portal:access:finished_goods_room->shipping_channel@1.0.0:finished_goods_room@1.0.0：finished_goods_room-PAL-028, finished_goods_room-PAL-029, finished_goods_room-PAL-030, finished_goods_room-PAL-055, finished_goods_room-PAL-056, finished_goods_room-PAL-057, finished_goods_room-PAL-082, finished_goods_room-PAL-083, finished_goods_room-PAL-084
- portal:access:packaging_material_storage->sorting_packaging_room@1.0.0:packaging_material_storage@1.0.0：packaging_material_storage-PAL-008, packaging_material_storage-PAL-009, packaging_material_storage-PAL-010
- portal:access:sorting_packaging_room->secondary_fruit_buffer@1.0.0:secondary_fruit_buffer@1.0.0：secondary_fruit_buffer-PAL-010, secondary_fruit_buffer-PAL-011, secondary_fruit_buffer-PAL-012, secondary_fruit_buffer-PAL-017, secondary_fruit_buffer-PAL-018, secondary_fruit_buffer-PAL-019
- portal:access:sorting_packaging_room->frozen_fruit_room@1.0.0:frozen_fruit_room@1.0.0：frozen_fruit_room-PAL-022, frozen_fruit_room-PAL-023, frozen_fruit_room-PAL-024, frozen_fruit_room-PAL-031, frozen_fruit_room-PAL-032, frozen_fruit_room-PAL-033
|B|12|7/7|10/11|6/6|5/5|11/11|PASS|

## 方案B

结构接触图Hash：sha256:9f2d5bd248467bb14f383d4984b12df0c374350b7780a850316c0f008bb8f714。占用房间毛面积2230.825721m²，室内柱投影0.7203m²；不能以毛面积自动证明货位取放或功能可用。

|功能区|X/Y mm|宽×深mm|毛面积m²|扣柱面积m²|
|---|---|---|---:|---:|

设备布置后的室内通道复核（与原室间Access分别报告）：

- coating_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- finished_goods_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- primary_precooling_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- secondary_precooling_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
- sorting_packaging_room：BOUNDED_PATH_NOT_FOUND，净宽2500mm；ROUTE_SEARCH_EXHAUSTED。门洞变宽连接段、车辆回转和全货位取放尚未验证。
|更衣室|70470 / 14518|6325×6325|40.005625|40.005625|
|覆膜间|59025 / 34443|8945×8944|80.00408|79.88648|
|成品间|67970 / 36293|32400×18600|602.64|602.3385|
|冻果间|58200 / 12643|10800×8200|88.56|88.56|
|办公室|97880 / 25234|7746×7746|60.000516|60.000516|
|包材库|76880 / 18993|14500×17300|250.85|250.6682|
|一级预冷间|16420 / 22618|14700×10050|147.735|147.735|
|原果暂存间|1220 / 23293|15200×8700|132.24|132.24|
|次果暂存间|49800 / 13943|8400×6900|57.96|57.96|
|二级预冷间|48975 / 34443|10050×9800|98.49|98.4312|
|出货通道|91380 / 28600|6500×7693|50.0045|49.9439|
|分选包装间|31120 / 20843|45760×13600|622.336|622.336|

设备拒绝记录（未将冲突设备画成通过）：

- SEC-C1-P2：COLUMN-41479
- finished_goods_room-PAL-301：COLUMN-41499
- finished_goods_room-PAL-306：COLUMN-41500
- finished_goods_room-PAL-311：COLUMN-41501
- finished_goods_room-PAL-316：COLUMN-41502
- finished_goods_room-PAL-320：COLUMN-41976
- packaging_material_storage-PAL-017：COLUMN-41485
- DEPALLETIZE：COLUMN-41480
- REPALLETIZE：COLUMN-41481

|存储区|原计算最低货位|实际主体位置|缺口|取放验证|
|---|---:|---:|---:|---|
|raw_fruit_buffer|37|45|0|未验证全货位取放|
|finished_goods_room|315|319|0|未验证全货位取放|
|secondary_fruit_buffer|19|21|0|未验证全货位取放|
|frozen_fruit_room|34|36|0|未验证全货位取放|
|packaging_material_storage|67|66|1|未验证全货位取放|

设备后门前预留/操作带冲突：

- SEC-CELL-1-AISLE：COLUMN-41479
- portal:access:raw_fruit_buffer->primary_precooling_room@1.0.0:raw_fruit_buffer@1.0.0：raw_fruit_buffer-PAL-009, raw_fruit_buffer-PAL-018, raw_fruit_buffer-PAL-027
- portal:access:raw_fruit_buffer->primary_precooling_room@1.0.0:primary_precooling_room@1.0.0：PRI-C1-P2
- portal:access:primary_precooling_room->sorting_packaging_room@1.0.0:primary_precooling_room@1.0.0：PRI-C3-P5
- portal:access:sorting_packaging_room->secondary_precooling_room@1.0.0:sorting_packaging_room@1.0.0：PACK-05, PACK-06
- portal:access:sorting_packaging_room->secondary_precooling_room@1.0.0:secondary_precooling_room@1.0.0：COLUMN-41479
- portal:access:coating_room->finished_goods_room@1.0.0:finished_goods_room@1.0.0：finished_goods_room-PAL-001, finished_goods_room-PAL-002, finished_goods_room-PAL-003, finished_goods_room-PAL-028, finished_goods_room-PAL-029, finished_goods_room-PAL-030
- portal:access:packaging_material_storage->sorting_packaging_room@1.0.0:packaging_material_storage@1.0.0：packaging_material_storage-PAL-059, packaging_material_storage-PAL-060, packaging_material_storage-PAL-061
- portal:access:packaging_material_storage->sorting_packaging_room@1.0.0:sorting_packaging_room@1.0.0：ERECT-03
- portal:access:sorting_packaging_room->secondary_fruit_buffer@1.0.0:secondary_fruit_buffer@1.0.0：secondary_fruit_buffer-PAL-010, secondary_fruit_buffer-PAL-011, secondary_fruit_buffer-PAL-012, secondary_fruit_buffer-PAL-017, secondary_fruit_buffer-PAL-018, secondary_fruit_buffer-PAL-019
- portal:access:sorting_packaging_room->frozen_fruit_room@1.0.0:frozen_fruit_room@1.0.0：frozen_fruit_room-PAL-022, frozen_fruit_room-PAL-023, frozen_fruit_room-PAL-024, frozen_fruit_room-PAL-031, frozen_fruit_room-PAL-032, frozen_fruit_room-PAL-033

所有图纸为同次计算结果的投影；不能将候选占用Footprint当作Owner原建筑外轮廓。
Truck缺少真实车辆/场地输入，完整P2D、冷却能力、设备维修、全货位取放及53人更衣流程均没有被本轮证明。
原成品规则保留10%冻果扣减（20t/天、7天对应126000kg和315最低货位）；没有将其悄悄改成20t/天全量成品7天的容量承诺。包材货位缺口及柱体影响须另行处理。
原建筑3处南侧开口的几何来自墙线端点；人员、进料及出货的用途分配为本轮设计建议，门型未批准。
新增代码仅显式入口启用，生产默认/MCP/历史P1及比较器保持不变。Native=0；MAIN=false；Grant/Claim=false。
