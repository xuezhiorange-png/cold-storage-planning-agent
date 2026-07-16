# TASK-011C C-3 invalid_blocked Expected Output — Reviewer Sign-Off
STATUS: APPROVED
CHARLES_VERDICT: APPROVED
## Authority
ISSUE_NUMBER: 20
CANDIDATE_EVIDENCE_AUTHORITY_COMMENT_ID:
`4988511679`
EXPECTED_OUTPUT_REVIEW_SIGN_OFF_COMMENT_ID:
`4992680486`
SOURCE_MAIN_SHA:
`7c9e13965e3481217c683176c767f74229ae0dca`
EXPECTED_OUTPUT_IMPLEMENTATION_HEAD_SHA:
`0d2d6728567ea5b11e74e84b1b4dd10b334f877f`
EXPECTED_OUTPUT_COMMIT_SHA:
`0d2d6728567ea5b11e74e84b1b4dd10b334f877f`
## Approved scope
EXPECTED_OUTPUT_SCOPE: INVALID_BLOCKED_ONLY
EXPECTED_OUTPUT_SCENARIO:
`invalid_blocked`
EXPECTED_OUTPUT_FILE:
`backend/tests/evaluation/data/expected/invalid_blocked.v1.json`
`high_throughput_review` is not part of TASK-011C V1 and is not
authorized or materialized by this sign-off.
Multilingual report verification, pilot runbook work, Issue #20
closure, and Task 12 are not authorized by this sign-off.
## Approved expected-output identity
EXPECTED_OUTPUT_FILE_SHA256:
`936da1c497fdc3e23794d3392e0f7005f2fd74b0285b7562ce9d53140b132ab9`
EXPECTED_OUTPUT_FILE_BYTES:
`235`
FINAL_NEWLINE:
`ABSENT`
D3_V1_EXCLUDED_JSON_PATHS:
`[]`
## Approved D10 classification
- `scenario_id = invalid_blocked`
- `actual_outcome = INVALID_INPUT`
- `evaluation_result = pass`
- `reason_code = PROJ_INPUT_INVALID`
- `field = total_area_m2`
- `stage = PRE_ADAPTER_PRE_PERSISTENCE_PROJECTION`
- `persistence_side_effects = NONE`
## Review findings
The approved expected output:
- was captured from the merged C-2 runner on exact
`main@7c9e13965e3481217c683176c767f74229ae0dca`;
- was produced through the D1 canonicalization authority;
- is byte-identical across SQLite and PostgreSQL;
- preserves `D3_V1_EXCLUDED_JSON_PATHS=[]`;
- uses the typed D10 exception code and field;
- has zero production-side persistence deltas;
- contains no message-text classification;
- contains no scenario-ID or correlation-ID special case;
- does not modify the frozen baseline golden;
- contains no `high_throughput_review` expected output.
## Governance
Review sign-off authority is Issue #20 comment `4992680486`.
This document records approval only for the exact file and SHA-256
listed above.
PR Ready remains subject to independent review, exact-head CI success,
correct PR metadata, and separate Charles authorization.
Merge is not authorized.
Issue #20 remains open.
Task 12 is not authorized.