# V0.3 P5 Controlled Acceptance and Release

This runbook defines the independent controlled-acceptance harness for V0.3
P5. It does not modify historical TASK011/TASK012 authority, the P1 controlled
acceptance workflow, or the ordinary regression suite.

## Stage boundaries

Implementation R1 adds only the harness, pilot runner, this runbook, and a
dispatch-only workflow. Fixture source-definition R1 binds Scenario A/B/C
fixture JSON and records SHA-256 evidence. Scenario execution engine R1 adds
the bound A/B/C execution path behind explicit authorization gates while
controlled acceptance dispatch, tag publication, and GitHub Release remain
separately authorized later stages. Controlled acceptance matrix runner R1
expands the authorized `execution_authorized=YES` workflow path to execute
Scenario A/B/C on sqlite and postgresql with fresh isolated databases per run
while the default `execution_authorized=NO` path continues to fail closed.

Implementation R1 PASS does not authorize controlled acceptance execution.
Fixture source-definition R1 PASS does not authorize scenario execution or
workflow dispatch. Scenario execution engine R1 PASS does not authorize
workflow dispatch, tag publication, or GitHub Release. Controlled acceptance
matrix runner R1 PASS does not authorize workflow dispatch, tag publication,
or GitHub Release. The workflow must not
be dispatched from a pull request or from a feature branch.

**Ordinary PR CI != Controlled Acceptance.** Ordinary CI validates the code;
it is not evidence that the controlled workflow has run.

## Frozen harness posture

```text
HARNESS_SCHEMA_VERSION=v0.3-p5-controlled-acceptance-harness.v1
CONTRACT_PATH=docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md
WORKFLOW_PATH=.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml
CONTROLLED_ACCEPTANCE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTED=NO
SCENARIO_EXECUTION_ENGINE_ROUND=SCENARIO_EXECUTION_ENGINE_R1
SCENARIO_EXECUTION_IMPLEMENTED=YES
CONTROLLED_ACCEPTANCE_MATRIX_RUNNER_ROUND=CONTROLLED_ACCEPTANCE_MATRIX_RUNNER_R1
RELEASE_EVIDENCE_ASSEMBLY_ROUND=RELEASE_EVIDENCE_ASSEMBLY_R1
SCENARIO_A_RUN_AUTHORIZED=NO
SCENARIO_B_RUN_AUTHORIZED=NO
SCENARIO_C_RUN_AUTHORIZED=NO
FIXTURE_JSON_CREATE_AUTHORIZED=NO
FIXTURE_SOURCE_DEFINITION_BOUND=YES
FIXTURE_SOURCE_DEFINITION_ROUND=FIXTURE_SOURCE_DEFINITION_R1
V0_3_TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
PRODUCTION_ENABLEMENT_AUTHORIZED=NO
P2_LIVE_PROVIDER_ACCEPTANCE_REQUIRED_FOR_P5_MAINLINE=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Authorized operator

The workflow requires an explicit `trusted_operator` input. It is not derived
from `github.actor`, an HTTP request, a model, a calculator, or a retry worker.
Empty values and the reserved actors `system`, `api`, `background`, and `llm`
are rejected.

## Execution authorization gate

Scenario execution requires all of the following:

1. `workflow_dispatch` on `refs/heads/main` only;
2. exact `source_sha` and `source_tree_sha` matching the checked-out commit;
3. non-empty `authorization_record_id`;
4. explicit execution authorization via either:
   - workflow input `execution_authorized=YES`, plus CLI `--execution-authorized`, or
   - environment variable `V03_P5_CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=YES`.

Harness R1 still fails closed without explicit execution authorization.
Scenario execution engine R1 executes the bound fixture only after explicit
execution authorization, authorization record id, trusted operator, and exact
source SHA/tree gates pass. Controlled acceptance dispatch, tag publication,
and GitHub Release remain separately unauthorized.

## Fixture source-definition evidence

The following fixture files are bound at
`FIXTURE_SOURCE_DEFINITION_ROUND=FIXTURE_SOURCE_DEFINITION_R1`. Each SHA-256
is computed from the committed file bytes using SHA-256 over the exact file
contents.

```text
SCENARIO_A_FIXTURE_PATH=backend/tests/pilot/data/v03-scenario-a-normal-formal-report.v1.json
SCENARIO_A_FIXTURE_SHA256=b4227ea107c12571681d29ad7746175e73e05b0ffeb9e6d7fa5e61e0b9877d15
SCENARIO_A_REVIEW_REQUIRED=false
SCENARIO_A_UPSTREAM_MANIFEST=backend/tests/evaluation/data/task011-pilot-sqlite.v1.json
SCENARIO_A_UPSTREAM_EXPECTED_OUTPUT=backend/tests/evaluation/data/expected/baseline_feasible.v1.json

SCENARIO_B_FIXTURE_PATH=backend/tests/pilot/data/v03-scenario-b-review-required-formal-report.v1.json
SCENARIO_B_FIXTURE_SHA256=ff462cbaff0fadc77c809cd0a28917dd09ba0cea1ed73066d6fa1100f8552bbb
SCENARIO_B_REVIEW_REQUIRED=true
SCENARIO_B_UPSTREAM_SOURCE=backend/tests/pilot/data/task011-followup-high-throughput-source.v1.json
SCENARIO_B_FORMAL_EXPORT_BLOCKED_UNTIL_REVIEW_APPROVAL=YES

SCENARIO_C_FIXTURE_PATH=backend/tests/pilot/data/v03-scenario-c-agent-knowledge-deterministic.v1.json
SCENARIO_C_FIXTURE_SHA256=9ac8a43020bd6876909265e2e0e8286053bfb17c7152039d32b406f78fa9233a
SCENARIO_C_AGENT_TRANSPORT=fake_or_mocked_gateway
SCENARIO_C_LIVE_MIMO_REQUIRED=NO
SCENARIO_C_AGENT_UNAVAILABLE_BLOCKS_CORE_WORKFLOW=NO
SCENARIO_C_PAGE_LEVEL_PROVENANCE_REQUIRED=YES
```

Scenario A reuses the governed `baseline_feasible` pilot manifest and expected
output with `review_required=false`. Scenario B reuses the governed P1
high-throughput source fixture with structured review-required semantics.
Scenario C reuses governed Agent gateway and knowledge OCR test authorities
with optional Agent transport and page-level provenance requirements.

```text
CONTROLLED_ACCEPTANCE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTED=NO
WORKFLOW_DISPATCH_AUTHORIZED=NO
SCENARIO_A_RUN_AUTHORIZED=NO
SCENARIO_B_RUN_AUTHORIZED=NO
SCENARIO_C_RUN_AUTHORIZED=NO
```

## Local harness commands

Verify gates without executing scenarios:

```bash
cd backend
PYTHONPATH=src uv run python tests/pilot/run_v03_controlled_acceptance.py verify-gates \
  --authorization-record-id "auth-record-example" \
  --trusted-operator controlled.operator \
  --execution-source-sha "$(git rev-parse HEAD)" \
  --execution-source-tree-sha "$(git rev-parse HEAD^{tree})" \
  --output /tmp/v03-p5-verify-gates.json
```

Emit the frozen harness posture:

```bash
cd backend
PYTHONPATH=src uv run python tests/pilot/run_v03_controlled_acceptance.py harness-status \
  --output /tmp/v03-p5-harness-status.json
```

Attempting a scenario without explicit execution authorization fails closed:

```bash
cd backend
PYTHONPATH=src uv run python tests/pilot/run_v03_controlled_acceptance.py run \
  --scenario A \
  --authorization-record-id "auth-record-example" \
  --trusted-operator controlled.operator \
  --execution-source-sha "$(git rev-parse HEAD)" \
  --execution-source-tree-sha "$(git rev-parse HEAD^{tree})" \
  --backend sqlite \
  --run-index 1 \
  --output /tmp/v03-p5-scenario-a-refusal.json
```

With `--execution-authorized` or
`V03_P5_CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=YES`, the runner provisions
a fresh isolated database (sqlite by default; postgresql requires
`--database-url`), executes the bound fixture through persisted production
application services, and records evidence JSON with source SHA/tree, calculator
versions, review flags, and artifact hashes. Controlled acceptance workflow
dispatch, tag publication, and GitHub Release remain separately unauthorized.

When the workflow input `execution_authorized=YES` is explicitly set, the
dispatch-only workflow executes the full Scenario A/B/C matrix on sqlite and
postgresql:

```text
SCENARIO_A_SQLITE=YES
SCENARIO_B_SQLITE=YES
SCENARIO_C_SQLITE=YES
SCENARIO_A_POSTGRESQL=YES
SCENARIO_B_POSTGRESQL=YES
SCENARIO_C_POSTGRESQL=YES
```

Each matrix cell provisions a fresh isolated database. PostgreSQL cells use the
workflow service container (`pgvector/pgvector:pg16`), create a dedicated
`v03_p5_matrix_<scenario>` database, run `alembic upgrade head`, and pass an
explicit `--database-url`. The default `execution_authorized=NO` path still
refuses Scenario A on sqlite without `--execution-authorized`.

## STAGE_10 release evidence assembly

`P5_STAGE_10=RELEASE_EVIDENCE_ASSEMBLY` assembles contract §7 release evidence
from an existing STAGE_9 controlled acceptance artifact root. It does not rerun
scenarios, recompute engineering values, create tags, publish GitHub Releases,
or flip harness authorization flags to `YES`.

Locked STAGE_9 authority for the first release-evidence assembly round:

```text
STAGE9_WORKFLOW_RUN_ID=32627831343
STAGE9_JOB_ID=97165830132
STAGE9_ARTIFACT_ID=9490201526
STAGE9_ARTIFACT_NAME=v03-p5-controlled-acceptance-harness
AUTHORIZATION_RECORD_ID=V03-P5-CA-STAGE8-7029cd9e14b1b6ad50d726772ca114356d3018e7
TRUSTED_OPERATOR=xuezhiorange-png
EXECUTION_SOURCE_SHA=7029cd9e14b1b6ad50d726772ca114356d3018e7
EXECUTION_SOURCE_TREE_SHA=71a5837411da249eb71b7014f4d951d25887f6d6
```

Assemble release evidence locally from a downloaded STAGE_9 artifact directory:

```bash
cd backend
PYTHONPATH=src uv run python tests/pilot/run_v03_controlled_acceptance.py assemble-release-evidence \
  --stage9-evidence-root /path/to/v03-p5-controlled-acceptance-harness \
  --output /tmp/v03-p5-release-evidence.json
```

The assembler verifies all six matrix cells (`A`/`B`/`C` × `sqlite`/`postgresql`)
report `PASS`, frozen harness authorization flags remain `NO`, and
`contract_section_7.10_unresolved_blockers` is empty before emitting
`release_evidence_result=PASS`.

## Workflow constraints

`.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml` is
`workflow_dispatch` only, runs on `main` only, requires explicit source SHA,
source tree SHA, operator, authorization record, and execution authorization
input. When `execution_authorized=YES`, it runs Scenario A/B/C on sqlite and
postgresql with fresh isolated databases per cell. It uploads harness evidence
with short retention.

The workflow performs no deployment, release signing, registry mutation,
production database write, Git push, tag creation, GitHub Release publication,
merge, or Issue update. It does not modify the P1 acceptance workflow.

## Failure diagnostics

Harness failures use machine-readable JSON:

```text
CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED
CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_MISSING
DATABASE_URL_REQUIRED
SCENARIO_DATABASE_URL_REQUIRED
SCENARIO_EXECUTION_NOT_AUTHORIZED
WORKFLOW_DISPATCH_REQUIRED
WORKFLOW_MAIN_REF_REQUIRED
EXECUTION_SOURCE_SHA_MISMATCH
TRUSTED_OPERATOR_NOT_HUMAN
```

No production operation, release, signing, deployment, autonomous approval,
or post-merge action is authorized by harness R1.
