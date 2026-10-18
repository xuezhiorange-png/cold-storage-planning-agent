# Stage B fair-search real validation 01

Execution source: `388a60d69469ec4a18b7db112470e76d71462292`. One approved MAIN and one REPLAY only.

MAIN: 3 complete assignments; 3 hole rejections; 0 engineering-valid geometries; V1=0, V2=0, accepted major families=0.
Native-started handoffs: 6/6; final-joint-model-started handoffs: 6/6.
Replay: `NOT_ESTABLISHED_NO_ACCEPTED_CANDIDATES`. Cross-run (historical01/02 + MAIN, replay excluded): 2 meaningful constructions, 1 major families. Historical evidence unchanged.

| Handoff | Native calls | Final started | Assignments | Holes | V2 accepted | Stop/result |
|---|---:|---|---:|---:|---:|---|
| whole-building-structural-composition@2.0.0:CENTRAL_PROCESS_CORE:X:NEGATIVE:r0 | 6 | True | 1 | 1 | 0 | ['UNKNOWN'] |
| whole-building-structural-composition@2.0.0:LINEAR_BANDED:X:NEGATIVE:r0 | 5 | True | 0 | 0 | 0 | ['INFEASIBLE'] |
| whole-building-structural-composition@2.0.0:PROCESS_SPINE_WITH_PERIPHERAL_BANKS:X:NEGATIVE:r0 | 5 | True | 0 | 0 | 0 | ['INFEASIBLE'] |
| whole-building-structural-composition@2.0.0:CENTRAL_PROCESS_CORE:Y:POSITIVE:r1 | 5 | True | 0 | 0 | 0 | ['INFEASIBLE'] |
| whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1 | 7 | True | 2 | 2 | 0 | ['UNKNOWN'] |
| whole-building-structural-composition@2.0.0:PROCESS_SPINE_WITH_PERIPHERAL_BANKS:Y:POSITIVE:r1 | 5 | True | 0 | 0 | 0 | ['UNKNOWN'] |

Shared charged native 99.781791s; elapsed 116.870916s; observable work 574666; peak RSS 218677248; actual native calls 66. Resource compliance: True.

MAIN and REPLAY each rejected all three complete assignments for enclosed holes:
**3/3 = 100%**, compared with historical **16/18 = 88.89%**. These small,
differently scheduled samples do not establish a general quality trend or a
reduced hole rate. Exact rejected room/route/cut traces match across replay.
No accepted-candidate determinism is established. Native application candidate
validation calls were **0**: hole rejection occurred before that acceptance layer.

All four warmup calls returned for every handoff. UNKNOWN is a return from the
locally bounded search, not INFEASIBLE. No explicit global hard-resource guard
exception was raised; both schedules completed inside shared hard ceilings.
The three INFEASIBLE outcomes describe the unchanged finite domains, not global
factory impossibility. Full per-phase statuses, shared/local shares and exact
hole boundaries/cut values are retained in the sealed execution evidence.

The export path would retain each valid geometry with its own actual native
application corridors, validation and Footprint, including explicitly uncounted
geometry. None was eligible here. Real Truck remains BLOCKED; P2D full-pass=0.
P3 historical262 UNKNOWN is retained. P3/P2/version remain incomplete.
No further grant, quality ranking, Tool7, Ready/Merge or deployment is authorized.

No new engineering-valid geometry was obtained; no SVG or historical layout is copied to pretend otherwise.
