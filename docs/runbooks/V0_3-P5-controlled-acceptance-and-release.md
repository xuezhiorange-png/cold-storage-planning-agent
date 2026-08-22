# V0.3 P5 Controlled Acceptance and Release

This runbook defines the independent controlled-acceptance harness for V0.3
P5. It does not modify historical TASK011/TASK012 authority, the P1 controlled
acceptance workflow, or the ordinary regression suite.

## Stage boundaries

Implementation R1 adds only the harness, pilot runner, this runbook, and a
dispatch-only workflow. Scenario A/B/C execution, fixture JSON creation, tag
publication, and GitHub Release remain separately authorized later stages.

Implementation R1 PASS does not authorize controlled acceptance execution. The
workflow must not be dispatched from a pull request or from a feature branch.

**Ordinary PR CI != Controlled Acceptance.** Ordinary CI validates the code;
it is not evidence that the controlled workflow has run.

## Frozen harness posture

```text
HARNESS_SCHEMA_VERSION=v0.3-p5-controlled-acceptance-harness.v1
CONTRACT_PATH=docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md
WORKFLOW_PATH=.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml
CONTROLLED_ACCEPTANCE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTED=NO
SCENARIO_A_RUN_AUTHORIZED=NO
SCENARIO_B_RUN_AUTHORIZED=NO
SCENARIO_C_RUN_AUTHORIZED=NO
FIXTURE_JSON_CREATE_AUTHORIZED=NO
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

Harness R1 still fails closed after these gates because scenario fixtures are
not yet bound and scenario execution is not authorized.

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

Even with `--execution-authorized` or
`V03_P5_CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=YES`, harness R1 refuses
scenario execution with `SCENARIO_EXECUTION_NOT_AUTHORIZED` because fixture
source-definition evidence is not yet bound.

## Workflow constraints

`.github/workflows/v0-3-p5-controlled-acceptance-and-release.yml` is
`workflow_dispatch` only, runs on `main` only, requires explicit source SHA,
source tree SHA, operator, authorization record, and execution authorization
input. It uploads harness evidence with short retention.

The workflow performs no deployment, release signing, registry mutation,
production database write, Git push, tag creation, GitHub Release publication,
merge, or Issue update. It does not modify the P1 acceptance workflow.

## Failure diagnostics

Harness failures use machine-readable JSON:

```text
CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED
CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_MISSING
SCENARIO_EXECUTION_NOT_AUTHORIZED
WORKFLOW_DISPATCH_REQUIRED
WORKFLOW_MAIN_REF_REQUIRED
EXECUTION_SOURCE_SHA_MISMATCH
TRUSTED_OPERATOR_NOT_HUMAN
```

No production operation, release, signing, deployment, autonomous approval,
or post-merge action is authorized by harness R1.
