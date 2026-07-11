# TASK-011B Path A Expected Outputs — Reviewer Sign-Off

STATUS: APPROVED
CHARLES_VERDICT: APPROVED

## Approved scope

EXPECTED_OUTPUT_SCOPE: BASELINE_ONLY
EXPECTED_OUTPUT_SCENARIO: baseline_feasible

The current expected-output set contains exactly one scenario:
`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`

`high_throughput_review` is not part of the current expected-output
set and is not authorized or materialized in this scope.

## Reviewed implementation identity

EXPECTED_OUTPUT_IMPLEMENTATION_HEAD_SHA:
`f274db66fe4bb2de206d12c2d561d1b3549ab6c0`

The reviewed implementation Head is Commit E:
`fix(task-011b): remove redundant expected-output policy summary`

The contaminated temporary-branch commit
`dcf03434693282f39397d6b8ebde92f61a093133` is not approved and is
not part of this sign-off lineage.

## Approved expected-output file

EXPECTED_OUTPUT_FILE:
`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`

EXPECTED_OUTPUT_FILE_SHA256:
`2d45ea2291c726460d80b0cbca0a771edda9812aa3a6cb017328af458b65ca73`

PRODUCTION_CONTENT_HASH:
`ea4ab8cd7f73b50c8cd83865adc9ec90428d8d60a9fc2e7d823a0c8fdb16fe46`

## Review findings

The approved baseline golden:
- is generated from the real SQLite and PostgreSQL production paths;
- directly compares `SchemeRunRecord.content_hash`;
- records 12 passed constraints and 1 failed constraint;
- records `compressor_operating_adequacy` as the failed constraint;
- derives `expected_outcome` from runtime `ScenarioOutcome`;
- has pairwise-disjoint comparison classes;
- assigns every canonical leaf to exactly one comparison class;
- rejects and excludes redundant `leaf_coverage_summary`;
- contains no high-throughput golden.

## Governance

Charles approved Commit E and the baseline golden.

Commit `dcf03434693282f39397d6b8ebde92f61a093133` is explicitly
excluded from the approved lineage.

PR Ready remains conditional on clean PR-branch publication,
current-head CI success, correct PR metadata, and independent remote
verification.

Merge is not authorized.
