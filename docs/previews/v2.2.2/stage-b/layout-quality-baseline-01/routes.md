# 工艺接口与人员事实

**共享门中心线0m只证明接口，不是房间内搬运距离。**
全部8套均缺Receiving映射、室内运输连接和可比最短可行路径；
主流程顺序、折返、转弯、总距离、效率均为UNAVAILABLE，不能填0/PASS。

## 历史01

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|SHORT_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|58.629|3|2|BOUNDARY_ACCESS / SHORT_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:db6da34efa1161aab3225d6d9bb6949d2783914a98ca8fe34cb70dba288bcf22",
      "EXACT_RATIONAL": "5/2",
      "SOURCE": "multi-solution-validation-01/candidate-01/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "2.5"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:db6da34efa1161aab3225d6d9bb6949d2783914a98ca8fe34cb70dba288bcf22",
      "EXACT_RATIONAL": "49/12",
      "SOURCE": "multi-solution-validation-01/candidate-01/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "4.083333333333333333333333333333333333333"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:db6da34efa1161aab3225d6d9bb6949d2783914a98ca8fe34cb70dba288bcf22",
      "SOURCE": "multi-solution-validation-01/candidate-01",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 历史02

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|SHORT_EDGE / SHORT_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|11.214|3|2|BOUNDARY_ACCESS / LONG_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:6272e8ab1c31e6dd90cf12ceebb1b3fa8f8621a4912c5c926c48aee25496253b",
      "EXACT_RATIONAL": "659/300",
      "SOURCE": "multi-solution-validation-01/candidate-02/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "2.196666666666666666666666666666666666667"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:6272e8ab1c31e6dd90cf12ceebb1b3fa8f8621a4912c5c926c48aee25496253b",
      "EXACT_RATIONAL": "49/12",
      "SOURCE": "multi-solution-validation-01/candidate-02/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "4.083333333333333333333333333333333333333"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:6272e8ab1c31e6dd90cf12ceebb1b3fa8f8621a4912c5c926c48aee25496253b",
      "SOURCE": "multi-solution-validation-01/candidate-02",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 最新01

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|LONG_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|34.679|2|2|BOUNDARY_ACCESS / SHORT_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:42b20791862454a346e51d0fc4237e27824463708159c2b923db616072ca2ba1",
      "EXACT_RATIONAL": "49/8",
      "SOURCE": "guided-fair-validation-02/candidate-01/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "6.125"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:42b20791862454a346e51d0fc4237e27824463708159c2b923db616072ca2ba1",
      "EXACT_RATIONAL": "1633/800",
      "SOURCE": "guided-fair-validation-02/candidate-01/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "2.04125"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:42b20791862454a346e51d0fc4237e27824463708159c2b923db616072ca2ba1",
      "SOURCE": "guided-fair-validation-02/candidate-01",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 最新02

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|LONG_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|39.037|1|2|BOUNDARY_ACCESS / LONG_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:249eebe4410be1fa6f0da11299d57b30101c5f05d04c7c6d119a839448e9c486",
      "EXACT_RATIONAL": "49/8",
      "SOURCE": "guided-fair-validation-02/candidate-02/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "6.125"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:249eebe4410be1fa6f0da11299d57b30101c5f05d04c7c6d119a839448e9c486",
      "EXACT_RATIONAL": "1",
      "SOURCE": "guided-fair-validation-02/candidate-02/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "1"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:249eebe4410be1fa6f0da11299d57b30101c5f05d04c7c6d119a839448e9c486",
      "SOURCE": "guided-fair-validation-02/candidate-02",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 最新03

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|LONG_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|16.502|1|2|BOUNDARY_ACCESS / LONG_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:d52500dd974f7563fba59b0268c504795aac941cbf8e430d70349363f871b77b",
      "EXACT_RATIONAL": "49/8",
      "SOURCE": "guided-fair-validation-02/candidate-03/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "6.125"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:d52500dd974f7563fba59b0268c504795aac941cbf8e430d70349363f871b77b",
      "EXACT_RATIONAL": "1633/800",
      "SOURCE": "guided-fair-validation-02/candidate-03/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "2.04125"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:d52500dd974f7563fba59b0268c504795aac941cbf8e430d70349363f871b77b",
      "SOURCE": "guided-fair-validation-02/candidate-03",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 最新04

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|SHORT_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|47.352|3|2|BOUNDARY_ACCESS / SHORT_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:6efc6aa78c7f85d3a4a8aefb27b02ab2cd4d70d5c2fcd7e2140254186486a434",
      "EXACT_RATIONAL": "49/8",
      "SOURCE": "guided-fair-validation-02/candidate-04/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "6.125"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:6efc6aa78c7f85d3a4a8aefb27b02ab2cd4d70d5c2fcd7e2140254186486a434",
      "EXACT_RATIONAL": "67/16",
      "SOURCE": "guided-fair-validation-02/candidate-04/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "4.1875"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:6efc6aa78c7f85d3a4a8aefb27b02ab2cd4d70d5c2fcd7e2140254186486a434",
      "SOURCE": "guided-fair-validation-02/candidate-04",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 最新05

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|SHORT_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|47.419|3|2|BOUNDARY_ACCESS / SHORT_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:72cfe4dbc42a20b26885be0cfb927a1b976b49b0b307e807394055896937d769",
      "EXACT_RATIONAL": "49/8",
      "SOURCE": "guided-fair-validation-02/candidate-05/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "6.125"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:72cfe4dbc42a20b26885be0cfb927a1b976b49b0b307e807394055896937d769",
      "EXACT_RATIONAL": "67/16",
      "SOURCE": "guided-fair-validation-02/candidate-05/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "4.1875"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:72cfe4dbc42a20b26885be0cfb927a1b976b49b0b307e807394055896937d769",
      "SOURCE": "guided-fair-validation-02/candidate-05",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```

## 最新06

|从→至|拓扑|实际接口/走廊距离 m|转向|门净宽 m|起点/终点边类|
|---|---|---|---|---|---|
|changing_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|1.5|SHORT_EDGE / LONG_EDGE|
|coating_room→finished_goods_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|finished_goods_room→shipping_channel|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|main_entrance→changing_room|CORRIDOR_MEDIATED|47.947|3|2|BOUNDARY_ACCESS / SHORT_EDGE|
|packaging_material_storage→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|primary_precooling_room→sorting_packaging_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|raw_fruit_buffer→primary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / SHORT_EDGE|
|secondary_precooling_room→coating_room|DIRECT_SHARED_EDGE|0|0|2.4|SHORT_EDGE / LONG_EDGE|
|sorting_packaging_room→frozen_fruit_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|
|sorting_packaging_room→secondary_fruit_buffer|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / SHORT_EDGE|
|sorting_packaging_room→secondary_precooling_room|DIRECT_SHARED_EDGE|0|0|2.4|LONG_EDGE / LONG_EDGE|

人员与物流**已记录**中心线及Corridor逐对精确接触见facts.json。
物流均为无外部Envelope的共享门接口，不能据此宣布室内人货分离。
Office仅有与Shipping的空间MUST，不存在Office人员通行路线权威。

共享边质量（非门槛、逐对、不聚合）：
```json
[
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:865258d6bdcc2a67a5c4947be9956b9cbfac701cd88b369d51ec7fe0094ecab0",
      "EXACT_RATIONAL": "49/8",
      "SOURCE": "guided-fair-validation-02/candidate-06/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "6.125"
    },
    "pair": [
      "primary_precooling_room",
      "sorting_packaging_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "shared-positive-edge length / actual portal width; pair-specific",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:865258d6bdcc2a67a5c4947be9956b9cbfac701cd88b369d51ec7fe0094ecab0",
      "EXACT_RATIONAL": "67/16",
      "SOURCE": "guided-fair-validation-02/candidate-06/application",
      "STATUS": "DERIVED",
      "UNAVAILABLE_REASON": null,
      "UNIT": "ratio",
      "VALUE": "4.1875"
    },
    "pair": [
      "sorting_packaging_room",
      "secondary_precooling_room"
    ]
  },
  {
    "metric": {
      "CALCULATION_METHOD": "No authoritative direct interface for this pair (Coating remains a main stage); do not invent an adjacency",
      "DEFINITION_VERSION": "offline-layout-quality-facts@1.0.0",
      "EVIDENCE_HASH": "sha256:865258d6bdcc2a67a5c4947be9956b9cbfac701cd88b369d51ec7fe0094ecab0",
      "SOURCE": "guided-fair-validation-02/candidate-06",
      "STATUS": "NOT_APPLICABLE",
      "UNAVAILABLE_REASON": "NO_APPLICABLE_DIRECT_PORTAL",
      "UNIT": "ratio",
      "VALUE": null
    },
    "pair": [
      "secondary_precooling_room",
      "finished_goods_room"
    ]
  }
]
```
