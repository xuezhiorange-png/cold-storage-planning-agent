# V2.2.2 P0A — Canonical Fixture and Regularity Calibration Evidence

## Governance snapshot

```ini
TASK_ID=V2_2_2_P0A_XINZHAO_CANONICAL_FIXTURE_INGEST_AND_REPLAY_R2
PR_NUMBER=301
BASE_MAIN_SHA=3b90126fc4215460b93d6fd72b619dc507602669
PREVIOUS_HEAD_SHA=8181b51edfb7918f9054f4aba8e14a7470d964eb
P0_MERGE_SHA=3b90126fc4215460b93d6fd72b619dc507602669
EVIDENCE_AND_CALIBRATION_ONLY=true
P1_RUNTIME_IMPLEMENTATION=false
CANONICAL_FIXTURE_ACQUIRED=true
CANONICAL_FIXTURE_VERIFIED=true
P1_ENTRY_CANONICAL_FIXTURE_READY=true
OWNER_LABELLED_REGULARITY_POSITIVE_SAMPLES_UNAVAILABLE=true
P1_IMPLEMENTATION_ENTRY_READY=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

## Canonical Xinzhao source and v2.2.1 replay

The Owner-provided original bytes were copied without JSON normalization to
`backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`. The
repository fixture layout follows the existing versioned `vXX` fixture
convention. Provenance is recorded beside the input, and the complete replay
details are in
[`regularity-calibration-matrix.json`](evidence/v2_2_2_p0a/regularity-calibration-matrix.json).

```ini
SOURCE_FILE_NAME=site_layout_input_v3_original.json
RAW_SIZE_BYTES=9552
RAW_SHA256=d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e
JSON_PARSE=PASS
SENSITIVE_SCAN=PASS
TOOL7_INPUT_SCHEMA_ACCEPTANCE=PASS
RELEASE=v2.2.1
RELEASE_SHA=64f335bbfbbaf061b9ba08c18f2068db411f8922
PROJECT_LAYOUT_VALIDATED=true
P2_COMPLETE=true
ZONE_COUNT=12
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=12
TRUCK_ROUTE_VALIDATED=true
BUILDING_FOOTPRINT_PRESENT=true
EXPECTED_CANONICAL_RESULT_HASH=sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30
ACTUAL_CANONICAL_RESULT_HASH=sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30
CANONICAL_RESULT_HASH_MATCH=true
EXPECTED_V221_SVG_SHA256=sha256:db63fa7a6954820dd21dc0a7c70aba6f2cbfa7de6c5d2299027176100b109973
ACTUAL_SVG_SHA256=sha256:db63fa7a6954820dd21dc0a7c70aba6f2cbfa7de6c5d2299027176100b109973
SVG_HASH_MATCH=true
XINZHAO_V221_REPLAY_RESULT=PASS
OWNER_LAYOUT_REGULARITY_LABEL=FAIL
ENGINEERING_VALIDITY_AT_V221=true
```

The exact release runtime source under `backend/src/` is unchanged between
`64f335bbfbbaf061b9ba08c18f2068db411f8922` and the P0A branch base. Replay used
that release source identity. The raw fixture remains the canonical source;
there is no normalized replacement file.

## Calibration matrix and limits

The matrix contains the canonical Owner-labelled Xinzhao negative sample and
the three existing reproducible P1F full-chain fixtures. Two fixture pairs
share a canonical layout result hash, so the four rows represent only two
unique layout geometries, not four independent geometries. The three earlier
fixtures have no Owner regularity labels; Xinzhao is the only Owner-labelled
sample and it is negative. No Owner-labelled positive regularity sample is
available.

The matrix calculates only facts supported by the frozen P0 definition and
the structured result: exact major-zone grid-axis incidence rate, building
footprint bounding-rectangle occupancy, exterior reflex-corner count, and
single-polygon component count. Metrics requiring semantic band/orientation
mapping, process-route aggregation, or an uncalibrated outline classifier are
`UNAVAILABLE`; they are not treated as zero or pass.

For Xinzhao the exact grid alignment rate is `0.4`, bounding-rectangle
occupancy is approximately `0.5792454589543597`, reflex-corner count is `16`,
and the authoritative building footprint is represented as one polygon.
These measurements are evidence, not newly frozen acceptance thresholds.
The 0.90 grid-alignment target remains the P0 contract target; this sample is
below it. No occupancy, notch, or appendage threshold is inferred from one
negative sample.

```ini
CALIBRATION_FIXTURE_COUNT=4
FULL_CHAIN_FIXTURE_COUNT=4
OWNER_LABELLED_REGULARITY_FIXTURE_COUNT=1
OWNER_LABELLED_REGULARITY_POSITIVE_SAMPLES=0
DEPTH_ALIGNMENT_FIXTURE_COUNT=0
DEPTH_ALIGNMENT_APPLICABLE_FIXTURE_COUNT=UNAVAILABLE
DEPTH_ALIGNMENT_DISTRIBUTION=UNAVAILABLE
XINZHAO_DEPTH_ALIGNMENT_RATE=UNAVAILABLE
DEPTH_ALIGNMENT_THRESHOLD_STATUS=NOT_READY
PROPOSED_DEPTH_ALIGNMENT_PASS_THRESHOLD=NOT_READY
COMPACTNESS_CLASSIFIER_STATUS=NOT_READY
PROPOSED_BOUNDING_RECTANGLE_OCCUPANCY_FLOOR=NOT_READY
PROPOSED_MAX_EXTERIOR_NOTCH_COUNT=NOT_READY
PROPOSED_MAX_ISOLATED_APPENDAGE_COUNT=NOT_READY
P1_ENTRY_CANONICAL_FIXTURE_READY=true
P1_ENTRY_DEPTH_THRESHOLD_READY=false
P1_ENTRY_COMPACTNESS_CLASSIFIER_READY=false
P1_ENTRY_CALIBRATION_MATRIX_READY=false
P1_IMPLEMENTATION_ENTRY_READY=false
```

`EXTERIOR_NOTCH_COUNT` and `ISOLATED_APPENDAGE_COUNT` remain unavailable until
their deterministic classifiers are versioned and calibrated against suitable
Owner-labelled samples. Depth-alignment eligibility remains unavailable until
compatible band orientation can be established without guessing. Main-flow
backtracking/turn, functional grouping, branch crossing, personnel/logistics
separation, and route efficiency are also unavailable in this v2.2.1 evidence
contract; no centroid or straight-line proxy was substituted.

`GD-005_PANLONG` remains an abstract organization reference only.
`ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false`; no numerical measurement of its
original drawing is claimed. Xinzhao's historical result hash is baseline
evidence; future layout algorithm work may change it:
`FUTURE_CANONICAL_HASH_CHANGE_ALLOWED=true`.

## P1 entry decision

At P0A completion, the missing canonical-input blocker was cleared while P1
implementation entry remained **not ready** because Owner-labelled positive
samples were unavailable, depth alignment could not yet be evaluated under a
stable eligibility policy, and compactness thresholds were not calibrated.
The Owner later separately authorized structural P1A without activating those
numeric thresholds; see the [P1A implementation/evidence report](V2_2_2-P1A-structural-layout-generation.md).
