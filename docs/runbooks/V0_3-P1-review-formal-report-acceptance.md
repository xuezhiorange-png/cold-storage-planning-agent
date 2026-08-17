# V0.3 P1 Review/Formal Report Controlled Acceptance

This runbook defines the independent controlled-acceptance surface for V0.3
P1. It does not modify historical TASK011/TASK012 authority, and it does not
replace the ordinary report regression suite.

## Stage boundaries

Stage25 is implementation only. It adds the acceptance verifier, its
deterministic source fixture, the pilot runner, this runbook, and a dispatch
only workflow. Stage26 is the separately authorized controlled run after the
implementation has been reviewed, made ready, and merged.

Stage25 PASS does not authorize Stage26. The workflow must not be dispatched
from a pull request or from a feature branch.

**Ordinary PR CI != Controlled Acceptance.** Ordinary CI validates the code;
it is not evidence that the controlled workflow has run.

## Frozen execution contract

The controlled source is the accepted S6-07 execution snapshot:

```text
SOURCE_CANDIDATE_PATH=backend/src/cold_storage/bootstrap/s6_07_controlled_fixture.py::_EXECUTION_SNAPSHOT
ACCEPTED_SOURCE_DEFINITION_BASE_SHA=c6903d80089291c81bace737f6245da174825b70
ACCEPTED_SOURCE_DEFINITION_BASE_TREE_SHA=5f0239f5804499ca857250a39af38f61c039530b
CONTROLLED_EXECUTION_SOURCE_SHA=<workflow-supplied exact main SHA>
CONTROLLED_EXECUTION_SOURCE_TREE_SHA=<workflow-supplied exact main tree SHA>
CANONICAL_INPUT_SHA256=6a3ccd82852d8aa908a8bedcaab6437fbb68ff8ee3a305f9451c84b738d5f5d4
REVIEW_REQUIRED_VECTOR=true,true,true,false,true
STAGE_ORDER=zone,cooling_load,equipment,power,investment
```

The accepted source-definition base above is historical provenance for the
frozen fixture; it is not the identity of the checkout that executes the
controlled run. The workflow supplies the exact checked-out main commit and
tree as `CONTROLLED_EXECUTION_SOURCE_SHA` and
`CONTROLLED_EXECUTION_SOURCE_TREE_SHA`, and the runner records those values in
the evidence. A missing execution identity fails closed. The runner
re-hashes the fixture with the production `canonical_json_bytes`
implementation. A changed source hash, stage order, or review vector fails
closed. The source module is read-only for this surface.

## Production authority amendment

The controlled acceptance surface consumes the production authority without
changing its formulas, thresholds, coefficients, scoring, status machine, or
source fixture. Scheme generation preserves the authoritative design cooling
total and compressor operating total exactly. When an authoritative
compressor installed total is present, it is preserved exactly as well; when
it is absent, no installed capacity is synthesized. Segmented storage is
allocated independently for each source zone, with the final segment holding
the exact Decimal residual. Existing strict hard-constraint comparisons and
the established area/position split semantics remain unchanged. Genuine
capacity shortfalls therefore remain infeasible.

Report quality validation treats
`throughput_inventory_area.zone_details[*].area_basis` as a polymorphic,
fail-closed authority field.  Classification has strict precedence:

1. Any coefficient discriminator (`code`, `category`, `source_type`,
   `source_reference`, `version`, `validity_status`, `approval_status`,
   `requires_review`, or `notes`) makes the value a coefficient-reference
   candidate.
2. Only a value with no discriminator and both `value` and `unit` is a plain
   measured area value.
3. Any other shape is a blocker; a partial coefficient reference must never
   fall back to measured-value validation.

A coefficient-reference candidate must have the exact production key set,
non-empty `code`, `name`, `unit`, and `notes`, a finite numeric `value`, and
the exact static demo provenance identity emitted by `DemoZoneCoefficient`.
Only these seven code-bound unit pairs are authoritative at `area_basis`:

```text
office_area_per_t_day -> m2/(t/day)
changing_area_per_t_day -> m2/(t/day)
raw_area_loading -> kg/m2
coating_area_loading -> kg/day/m2
storage_area_loading -> kg/m2
secondary_fruit_area_loading -> kg/m2
frozen_area_loading -> kg/m2
```

Unknown or currently unreachable coefficient codes, wrong units, missing or
extra keys, partial provenance, and wrong static provenance identity are
blockers.  A plain measured area value must use canonical unit `m2`; any
other unit is a blocker.  Known refrigeration/electrical/thermal/energy
dimensions remain strict, and a known unit on an otherwise unmapped generic
measured-value path continues to fail closed.

## Authorized operator

The workflow requires an explicit `trusted_operator` input. It is not derived
from `github.actor`, an HTTP request, a model, a calculator, or a retry
worker. Empty values and the reserved actors `system`, `api`, `background`,
and `llm` are rejected. The operator must be non-empty and come from the
existing trusted-operator seam.

## Running the pilot locally

Run against an isolated database that has already been migrated to Alembic
head. The runner does not create a production database or migrate a shared
database on its own.

```bash
cd backend
COLD_STORAGE_DATABASE_BACKEND=sqlite \
COLD_STORAGE_DATABASE_URL=sqlite:////tmp/v03-p1-sqlite-1.db \
COLD_STORAGE_SQLITE_PATH=/tmp/v03-p1-sqlite-1.db \
uv run alembic upgrade head

uv run python tests/pilot/run_task011_followup_acceptance.py run \
  --database-url sqlite:////tmp/v03-p1-sqlite-1.db \
  --source-json tests/pilot/data/task011-followup-high-throughput-source.v1.json \
  --execution-source-sha "$(git rev-parse HEAD)" \
  --execution-source-tree-sha "$(git rev-parse HEAD^{tree})" \
  --operator controlled.operator \
  --backend sqlite \
  --run-index 1 \
  --output /tmp/v03-p1-evidence/sqlite-run-1.json
```

The PostgreSQL run uses the same command and a fresh isolated PostgreSQL
database URL. Repeatability requires two fresh SQLite databases and two fresh
PostgreSQL databases; truncating one database is not a fresh run.

## Evidence and fail-closed checks

The verifier records source hashes, all five persisted CalculationRun
identities and result hashes, SourceBinding and SchemeRun authority, the
typed ReviewReason projection, report transitions, trusted `mark_reviewed`,
approval identity, and the four formal artifacts:

```text
zh-CN DOCX
zh-CN PDF
en-US DOCX
en-US PDF
```

Each artifact is read back from storage and hashed independently. The four
artifacts share the report/revision/content/source/approval identity while
retaining independent locale and format plus persisted template ID/version,
template content hash, template locale, translation catalog version/content
hash, localized template hash, and file hash. Matrix labels must match the
artifact metadata and artifact IDs/storage keys must be unique; any missing
lineage or duplicate is a failure.

Missing or ambiguous source authority, stale review snapshots, wrong-revision
review actions, manual approval without persisted proof, content-hash
mismatch, blocker state, or file-hash mismatch are failures, not warnings.
The runner exits non-zero and emits machine-readable error details.

### Controlled lifecycle failure diagnostics

The successful evidence schema remains
`v0.3-p1-controlled-acceptance-evidence.v1`; successful evidence does not
contain failure-diagnostic fields. The generic failure contract also remains
unchanged: `CONTROLLED_ACCEPTANCE_FAILED` with the existing `backend`,
`run_index`, and `exception_type` details.

Only an `InvalidStatusTransitionError` raised by one of the controlled review
lifecycle actions adds diagnostic details. The closed action set is
`submit_review`, `mark_reviewed`, and `approve`. The boundary sets the action
before calling the production service, reads the report status through a
post-generation `ReportService.get_report(...)` readback, and takes the full
ordered blocker objects from `get_blockers(revision.quality_findings_json)`.
The additional details are:

```text
lifecycle_action
report_status_after_generate_revision
quality_blockers_after_generate_revision
invalid_from_status
invalid_to_status
```

The transition endpoints come directly from
`InvalidStatusTransitionError.from_status` and `.to_status`, normalizing only
Enum values to `.value`; the exception message is never parsed. An empty
blocker set is recorded as `[]`. The CLI runner needs no change: the existing
`ControlledAcceptanceError.to_json()` path writes these details into the
failure artifact, and the workflow needs no change.

The raw canonical input, SourceBinding, and SchemeRun hashes remain in every
evidence file. The normalized comparison retains the canonical input hash,
per-calculation result hashes, reason order, reason code/message, review
vector, status, and artifact semantics. Binding and SchemeRun content hashes
are identity-bound by the production contract, so the comparison records their
presence without comparing values from independent runtime identities; it
never rewrites or recomputes hash input.

## Workflow and evidence retention

`.github/workflows/v0-3-p1-review-formal-report-acceptance.yml` is
`workflow_dispatch` only, runs on `main` only, and requires explicit source
SHA, source tree SHA, operator, and authorization inputs. It provisions an
ephemeral PostgreSQL service, creates fresh database names for each run, and
uploads the resulting evidence bundle with short retention. Credentials and
database URLs are never written to the evidence JSON.

The workflow performs no deployment, release signing, registry mutation,
production database write, Git push, merge, or Issue update. It is an
evidence executor only. Stage25 implementation and Stage26 controlled
acceptance remain separate governance records.

## Failure diagnostics

1. Confirm the workflow ref is `refs/heads/main` and the supplied SHA/tree
   match the checked-out source.
2. Confirm the fixture hash and frozen vector before inspecting application
   behavior.
3. Inspect the first fail-closed code in the runner JSON; do not replace it
   with a warning or bypass it with a direct database update.
4. Confirm each backend used a new isolated database and a fresh session for
   authority, report revision, review action, and artifact readback.
5. Treat ordinary PR CI and a skipped/manual workflow as separate evidence
   states.

No production operation, release, signing, deployment, autonomous approval,
or post-merge action is authorized by this Stage25 implementation.
