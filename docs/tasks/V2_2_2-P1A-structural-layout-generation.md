# V2.2.2 P1A — Structural Layout Generation and Selection

## Governance

```ini
TASK_ID=V2_2_2_P1A_STRUCTURAL_LAYOUT_GENERATION_AND_SELECTION_R1
BASE_MAIN_SHA=955e5e532236fb6c33a80709e90362b12124fb72
TARGET_VERSION=v2.2.2
ACTIVE_GOVERNANCE_LANE=V2.2.2_P1A
P1A_RUNTIME_IMPLEMENTATION_AUTHORIZED=true
P1B_NUMERIC_THRESHOLD_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
OWNER_XINZHAO_P1A_VISUAL_REVIEW=PENDING
```

P1A adds an internal, deterministic group/band/zone placement policy and a
lexicographic structural comparator for candidates that have already passed
the existing P2D hard-validation gate. It does not modify Tool 7's input
schema or the meaning of `PROJECT_LAYOUT_VALIDATED` / `P2_COMPLETE`.

## Implemented structural policy

- Existing canonical zones are assigned to the five frozen functional groups;
  unknown zone roles fail closed. No raw-receiving role is invented.
- Candidate placement order starts with the raw/process/finished chain, then
  places personnel at the main-entrance side, then adds support branches.
- `LINEAR_PROCESS_BAND` and `CENTRAL_PROCESS_HUB` are versioned families.
  The dominant site axis and family selection use existing site/area facts;
  the selected family is a search policy, not a project template.
- Support zones are generated as a subordinate branch rooted at packaging
  storage, while all existing hard relationships remain authoritative.
- Personnel zones are kept out of the main-process rank and changing-room
  options prefer contact with the already-authoritative personnel entrance.
- Structural facts are compared lexicographically only among P2D full-pass
  candidates. P2B2 SHOULD-adjacency then loading-side preference remains the
  final tie-break, followed by canonical JSON ordering. There is no weighted
  score and no P1B numeric pass threshold.
- Main-flow turns/backtracking and route efficiency remain `UNAVAILABLE`;
  centroid, Manhattan, straight-line, or other proxy values are not emitted.

## Xinzhao negative-fixture evidence

The canonical input bytes remain unchanged at SHA-256
`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`. The
v2.2.1 Owner-fail result and SVG hashes are retained as historical baseline
evidence. P1A Tool 7 output is allowed to have new canonical hashes.

The unmocked Tool 7 replay remains engineering-hard-valid: 12 zones, 12/12
access requirements, truck route validated, building footprint present, and
P2 complete. The bounded P4 placement budget remains 15 nodes. The explored
stream emitted three P2C candidates; one passed P2D. The node budget was
exhausted, so this is not a global optimum or infeasibility result.

Compared with the v2.2.1 Owner-fail baseline:

| Fact | v2.2.1 | P1A | Interpretation |
| --- | ---: | ---: | --- |
| Support-group positive shared edges | 0 | 2 | Support rooms form a contiguous branch. |
| Major-zone grid alignment rate | 0.4 | 0.4 | No measured improvement. |
| Process-core direct edges | 2/2 | 2/2 | Existing core connectivity is preserved, not improved. |
| Footprint reflex corners | 16 | 15 | One fewer reflex corner; no threshold is inferred. |
| Bounding-rectangle occupancy | 0.5792454589543597 | 0.5818081984351934 | Small fixture-only improvement, not a gate. |

Thus the candidate geometry changes and support grouping improves, but the
current evidence does **not** demonstrate a clearer main-process geometry or
improved process-core legibility. P1A is therefore implementation/evidence
`PARTIAL`; the owner-facing visual review remains an independent pending gate.
The bounded search may not be described as globally optimal.

The before/after structured layout, SVG, and 1800×1800 PNG renderings are in
[`evidence/v2_2_2_p1a/`](evidence/v2_2_2_p1a/xinzhao_p1a_comparison.md).
The PNGs are direct macOS Quick Look SVG render outputs; no manual image or SVG
editing was applied. Browser capture of local files was blocked by the
computer-use browser URL policy, so the PNG evidence is identified as a local
SVG render rather than a browser screenshot.

## Frozen non-goals

```ini
GRID_THRESHOLD_ACTIVATED=false
DEPTH_THRESHOLD_ACTIVATED=false
OCCUPANCY_THRESHOLD_ACTIVATED=false
NOTCH_THRESHOLD_ACTIVATED=false
APPENDAGE_THRESHOLD_ACTIVATED=false
WEIGHTED_SCORE_USED=false
ROUTE_QUALITY_PROXY_USED=false
P2D_RULES_CHANGED=false
TOOL7_INPUT_CONTRACT_CHANGED=false
P1B_NUMERIC_THRESHOLD_IMPLEMENTATION_AUTHORIZED=false
```
