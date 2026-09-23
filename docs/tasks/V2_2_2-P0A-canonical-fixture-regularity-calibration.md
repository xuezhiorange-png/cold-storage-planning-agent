# V2.2.2 P0A — Canonical Fixture and Regularity Calibration Evidence

## Governance snapshot

```ini
TASK_ID=V2_2_2_P0A_CANONICAL_FIXTURE_AND_REGULARITY_CALIBRATION_R1
BASE_MAIN_SHA=3b90126fc4215460b93d6fd72b619dc507602669
P0_MERGE_SHA=3b90126fc4215460b93d6fd72b619dc507602669
P0_EXACT_MAIN_CI_RUN_ID=35860132763
P0_EXACT_MAIN_CI_STATUS=SUCCESS
EVIDENCE_AND_CALIBRATION_ONLY=true
P1_RUNTIME_IMPLEMENTATION=false
CANONICAL_FIXTURE_ACQUIRED=false
P1_IMPLEMENTATION_ENTRY_READY=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

## Result: blocked before threshold calibration

The owner-reported source is `./artifacts/site_layout_input_v3.json`. The raw
JSON bytes were not present in the repository, the P1G checkout, the local
workspace, the Codex attachments, or the local temporary work area searched for
this task. The owner-reported digest is abbreviated (`d03ecae9...03901e`), so
the full raw SHA-256 cannot be verified or recorded here:

```ini
XINZHAO_CANONICAL_INPUT_FILE=NOT_ACQUIRED
XINZHAO_CANONICAL_INPUT_RAW_SHA256=NOT_COMPUTED
XINZHAO_V221_REPLAY_RESULT=NOT_RUN
XINZHAO_V221_CANONICAL_RESULT_HASH=NOT_REPLAYED
MISSING_CANONICAL_FIXTURE=true
```

No input was reconstructed from a screenshot, SVG, Tool 7 result, conversation,
or hash. The source file was not edited, redacted, or normalized. Because the
canonical input could not be acquired and validated against the v2.2.1 Tool 7
contract, the required historical replay was not run and threshold freezing is
stopped.

## Existing full-chain fixture inventory

The repository's P1F acceptance evidence identifies three reproducible,
full-chain fixtures. They are useful existing regression samples, but the
repository does not attach Owner-accepted regularity labels to them. The third
fixture's result hash matches the owner-reported historical Xinzhao result
hash; that output-hash match does not establish that its generated test input
is byte-identical to the missing source JSON.

| fixture_id | site_shape_class | project_layout_validated | owner_known_quality | source result hash | regularity calibration |
| --- | --- | --- | --- | --- | --- |
| `P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE` | RECTANGLE | true | UNAVAILABLE | `sha256:872044da8b2ea985a9059f483d222568b451587f1f0e6740406823407c2e37d8` | NOT_RUN |
| `P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT` | CONCAVE_SITE | true | UNAVAILABLE | `sha256:c8b855adf2e3a09179af0cecce1d79672d3477679370118463c59a02ee2c5da6` | NOT_RUN |
| `P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES` | RECTANGLE_WITH_NO_BUILD | true | UNAVAILABLE | `sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30` | NOT_RUN; input identity unproven |

P1F also has two composition-only scenarios. They are not full-chain layout
fixtures and are excluded from any layout-regularity calibration count.

The full-chain inventory alone is not a calibration matrix: it lacks verified
Owner quality labels and computed values for the new process-flow, grouping,
alignment, and compactness atomics. Those values are `UNAVAILABLE`, not zero.

## Calibration and entry status

```ini
CALIBRATION_FIXTURE_COUNT=0
EXISTING_FULL_CHAIN_FIXTURE_COUNT=3
OWNER_LABELLED_REGULARITY_FIXTURE_COUNT=0
DEPTH_ALIGNMENT_FIXTURE_COUNT=0
DEPTH_ALIGNMENT_APPLICABLE_FIXTURE_COUNT=0
DEPTH_ALIGNMENT_DISTRIBUTION=UNAVAILABLE
XINZHAO_DEPTH_ALIGNMENT_RATE=UNAVAILABLE
DEPTH_ALIGNMENT_THRESHOLD_STATUS=NOT_READY
PROPOSED_DEPTH_ALIGNMENT_PASS_THRESHOLD=NOT_READY
COMPACTNESS_CLASSIFIER_STATUS=NOT_READY
PROPOSED_BOUNDING_RECTANGLE_OCCUPANCY_FLOOR=NOT_READY
PROPOSED_MAX_EXTERIOR_NOTCH_COUNT=NOT_READY
PROPOSED_MAX_ISOLATED_APPENDAGE_COUNT=NOT_READY
P1_ENTRY_CANONICAL_FIXTURE_READY=false
P1_ENTRY_DEPTH_THRESHOLD_READY=false
P1_ENTRY_COMPACTNESS_CLASSIFIER_READY=false
P1_ENTRY_CALIBRATION_MATRIX_READY=false
P1_IMPLEMENTATION_ENTRY_READY=false
```

No numerical grid/depth, process-flow, backtrack/turn, compactness, notch, or
appendage measurement is asserted by this blocked evidence record. The existing
P1F rendering metrics are not substitutes for the new layout-regularity
definitions. `GD-005_PANLONG` remains an organization reference only;
`ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false`, so no numerical golden-drawing
measurement is claimed.

## Exact-main CI evidence

P0 PR #300 was merged with a normal merge commit. `origin/main` was fetched and
verified at `3b90126fc4215460b93d6fd72b619dc507602669`. Exact-main push run
`35860132763` completed successfully for that head, event `push`, branch
`main`; `lightweight` and `ci-gate` succeeded. `backend-sqlite` and
`backend-postgresql` were skipped by the path-aware classifier and are not
reported as passing.

## Required next evidence to unblock

Provide the original `site_layout_input_v3.json` bytes from the owner acceptance
environment or authorize a specific read-only retrieval path. If that source
contains secrets or environment-specific connection details, stop and obtain
an Owner decision on canonical fixture storage; do not redact and relabel it as
the original canonical input. After acquisition, verify its full raw digest,
validate the unchanged input contract, replay against v2.2.1, then calibrate
thresholds using Owner-labelled positive and negative full-chain samples.
