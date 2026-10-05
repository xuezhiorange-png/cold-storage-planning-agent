# V2.2.2 P1A — Whole-Building Composition Core (P1-S1)

```ini
TASK_ID=V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S1
MODE=WHOLE_BUILDING_COMPOSITION_CORE_IMPLEMENTATION
BASE_MAIN_SHA=a781398cf483320327d23e2f942b5762dc18d845
BRANCH=codex/v2.2.2-p1a-whole-building-composition-p1-s1
SELECTED_ARCHITECTURE=WHOLE_BUILDING_GROUP_BAND_COMPOSITION_WITH_RESERVED_PERIPHERAL_DOMAINS
MAIN_FIRST_TAIL_ATTACHMENT_PRIMARY_PATH=false
ROUTE_REPAIR_IS_PRIMARY_GENERATION_STRATEGY=false
MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2
```

## Scope and version goal

V2.2.2 aims to generate a visually recognizable, coherent whole factory, not
merely twelve rectangles that pass hard constraints. The organization should
show directional production, Sorting/Packaging as a process core, a continuous
raw-to-shipping structure, grouped cold/storage functions, subordinate support
branches, a separate personnel domain, a considered shipping/truck interface,
a limited orthogonal axis family, and a coherent principal composition.
Golden references remain qualitative organization references; this slice does
not ingest their geometry or use them as runtime authority.

P1-S1 implements only the whole-building structural-composition domain. It
creates complete group/band/domain topology before any exact room placement.
It does not claim site feasibility, engineering validity, or a completed P1.

## Implemented core

`backend/src/cold_storage/modules/layout/domain/structural_composition.py`
defines the immutable, versioned `StructuralCompositionPlanV2` value object,
the topology-only `StructuralCompositionSignatureV1`, coordinate-free
validated site-orientation facts, completeness gates, deterministic family
enumeration, and a JSON-compatible evidence projection.

Every plan assigns the canonical twelve roles exactly once across five
functional groups:

| Group | Roles |
| --- | --- |
| `RAW_SIDE_GROUP` | `raw_fruit_buffer`, `primary_precooling_room` |
| `PROCESSING_CORE_GROUP` | `sorting_packaging_room`, `secondary_precooling_room`, `coating_room` |
| `FINISHED_SIDE_GROUP` | `finished_goods_room`, `shipping_channel` |
| `SUPPORT_GROUP` | `packaging_material_storage`, `secondary_fruit_buffer`, `frozen_fruit_room` |
| `PERSONNEL_GROUP` | `changing_room`, `office` |

Each plan creates all five peripheral domains in the same composition:
`PERSONNEL_INGRESS_DOMAIN`, `PACKAGING_SUPPORT_DOMAIN`,
`SECONDARY_BRANCH_DOMAIN`, `FROZEN_BRANCH_DOMAIN`, and
`SHIPPING_TRUCK_INTERFACE_DOMAIN`. Each domain records only relative side,
group/band relationship, and topology intent. It is not a zone, area,
rectangle, route, engineering authority, or final footprint.

The finite family topologies differ structurally:

1. `LINEAR_BANDED`: ordered raw, process-core, and finished-terminal bands,
   with a subordinate support branch and personnel outside the product bands.
2. `CENTRAL_PROCESS_CORE`: Sorting is the organizing center; raw and finished
   groups attach to distinct opposing core faces, support uses other peripheral
   faces, and personnel remains separate.
3. `PROCESS_SPINE_WITH_PERIPHERAL_BANKS`: a longitudinal seven-role process
   spine has a product-support side bank and a separate personnel ingress bank.

The signature compares group ordering, band topology, peripheral topology,
personnel relationship, and shipping/truck relationship; it does not use a
random ID, serialization order, coordinate nudge, or family label alone.

Enumeration is deterministic and family-first: the first round emits one
composition for each family before a second cross-axis round. Xinzhao's
validated site facts select the primary axis and orient the finished terminal
toward a same-axis validated loading/truck side where available. Only
categorical site facts and provenance are retained; no exact site coordinate
enters a composition.

The domain reuses `process_graph()` for the existing directed process flow.
Composition relationships are separately typed, marked non-authoritative, and
cannot add or upgrade MUST adjacency. Personnel remains outside raw, process,
finished, and support groups. Frozen, Secondary, and Packaging roles and
domains are present at object construction; none is deferred as a later tail.

## Xinzhao evidence and acceptance

The representative `xinzhao_20t_site_layout_input_v3` fixture was passed
through the existing site-geometry foundation only to derive validated
orientation facts. The composition enumerator then produced six plans: two
per family, with family first-round order
`LINEAR_BANDED → CENTRAL_PROCESS_CORE → PROCESS_SPINE_WITH_PERIPHERAL_BANKS`.
The first-round three have pairwise-distinct topology signatures and complete
12-role coverage. Evidence Candidates A–C preserve those first-round plans.

Machine-readable evidence:
[`xinzhao_whole_building_compositions.json`](evidence/v2_2_2_p1a_reset_s1/xinzhao_whole_building_compositions.json)

```ini
FAMILY_COUNT=3
FAMILY_ENUMERATION_COUNT_BY_FAMILY={LINEAR_BANDED:2,CENTRAL_PROCESS_CORE:2,PROCESS_SPINE_WITH_PERIPHERAL_BANKS:2}
FAMILY_FIRST_ROUND_COMPLETE=true
COMPLETE_12_ROLE_COMPOSITION_COUNT=6
DISTINCT_STRUCTURAL_COMPOSITION_COUNT=6
PAIRWISE_FIRST_ROUND_TOPOLOGY_SIGNATURE_DISTINCT=true
FUNCTIONAL_GROUP_COUNT=5
PERIPHERAL_DOMAIN_COUNT=5
FROZEN_ASSIGNED_AT_COMPOSITION_CREATION=true
SECONDARY_ASSIGNED_AT_COMPOSITION_CREATION=true
PACKAGING_ASSIGNED_AT_COMPOSITION_CREATION=true
TAIL_ATTACHMENT_REQUIRED_FOR_ROLE_COVERAGE=false
PERIPHERAL_DOMAIN_IS_ENGINEERING_AUTHORITY=false
AXIS_FAMILY_IS_INTENT_ONLY=true
TRUCK_INTERFACE_IS_COMPOSITION_INTENT_ONLY=true
```

## Non-goals and next-stage boundary

This slice does not implement or connect exact placement, access routing,
Truck validation, P2D, Tool 7, candidate selection, or SVG rendering. It does
not modify the existing placement search or validated-candidate selector.
Composition intent is not a `PROJECT_LAYOUT_VALIDATED` result and cannot
substitute for any current hard authority.

```ini
EXACT_PLACEMENT_IMPLEMENTED=false
ACCESS_ROUTING_IMPLEMENTED=false
TRUCK_VALIDATION_IMPLEMENTED=false
P2D_IMPLEMENTED=false
TOOL7_INTEGRATION_IMPLEMENTED=false
LEGACY_PLACEMENT_RUNTIME_CHANGED=false
VALIDATED_CANDIDATE_SELECTOR_CHANGED=false
TOOL7_BEHAVIOR_CHANGED=false
PROJECT_LAYOUT_VALIDATED_CLAIMED=false
P2D_PASS_CLAIMED=false
NEXT_RUNTIME_IMPLEMENTATION_AUTHORIZED=false
```

Any adapter from a complete composition into exact authoritative placement is
a later, separately authorized implementation stage. Existing zone
dimensions, MUST adjacency, access, Truck, P2D, Tool 7, and `P2_COMPLETE`
authorities remain unchanged.
