# TASK-012 V0.2 Slice 6 S6-07

## Purpose

S6-07 is a controlled end-to-end operational acceptance for the exact V0.2
release source. It exercises the already implemented strict runtime surfaces in
a temporary synthetic environment. It is not a production deployment,
promotion, publication, disaster-recovery rerun, or model-backed agent launch.

The controlled workflow is `.github/workflows/task012-slice6-s7-e2e-operational-acceptance.yml`.
It is `workflow_dispatch` only, requires `main`, an explicit boolean, and an
exact `expected_source_sha`. Ordinary pull-request and push CI never runs the
controlled acceptance.

## Prerequisite authority

The workflow consumes a refreshed S6-06 Package 3 artifact. Its run and artifact
metadata are fetched from the GitHub Actions API on every controlled execution.
The run must be a successful `workflow_dispatch` on `main`, its head SHA must be
the exact S6-07 source SHA, and its artifact must be unexpired, uniquely named,
and have the supplied upload-time digest. The downloaded S6-06 archive is safely
extracted, checked for exactly eight files, checked from its bundle root, and
verified with the existing `verify-final-release-evidence` implementation.

S6-06 must be refreshed after the S6-07 implementation is merged because this
workflow requires the S6-06 source SHA and tree SHA to equal the current S6-07
source. The historical predecessor is an input authority only; S6-07 does not
rerun S6-06, Slice 2, Package 1, or Package 2.

## Controlled environment

The workflow uses `docker-compose.production.yml` with a temporary PostgreSQL
service, temporary Docker network, temporary volumes, a synthetic credential,
and a temporary runtime. It does not connect to production databases, storage,
Redis/queue, cloud resources, secret managers, or real production secrets.
The existing `production` strict mode is used unchanged. The backend process
does not run Alembic; the dedicated migration service owns `alembic upgrade
head`.

The workflow writes raw observations only: build identity JSON, Alembic output,
HTTP status/body pairs, container state, PostgreSQL-backed coefficient IDs,
restart readbacks, persisted run/source-binding facts, artifact probe hashes,
correlation IDs, structured-log counters, and redaction counters. These are
facts, not precomputed `PASS` assertions. The assembler derives the acceptance
results from those facts, and the independent verifier derives them again from
the raw observation documents. A missing persisted fact fails closed.

The runtime dependency evidence is the strict PostgreSQL configuration plus the
observed `DatabaseCoefficientService` authority from an active application
lifespan. The controlled probe reads `get_engine()`,
`get_production_coefficient_service()`, and the existing composition-manifest
provider while that lifespan is active; importing the class by name is not
evidence. The planning-agent evidence is an actual HTTP `503` response with
`AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE` and `retryable=false`, together with
the readiness capability projection showing the capability disabled. The
workflow does not claim a negative construction fact that the runtime does not
expose as machine-readable evidence.

The workflow uses a runner-temporary Compose override only to declare the
synthetic `ci-strict` database, secret, artifact, and artifact-storage
identities required by unchanged strict settings. The tracked production
Compose contract is not modified by S6-07.

The workflow's synthetic setup is implemented by the formal non-production
support module
`backend/src/cold_storage/bootstrap/s6_07_controlled_fixture.py`. The application
bootstrap does not import this module, and the workflow does not import
pytest modules or test-only seed helpers. After migration and before the strict
backend starts, the workflow uses the canonical coefficient approval service to
seed and verify all five required readiness stages. A missing, stale, demo, or
uncited stage fails before backend startup; the readiness seed is not a bypass
of the production startup contract.

The coefficient authorities deliberately distinguish provenance from persistence.
The run-scoped HTTP-created coefficient definition and approved revision prove the
PostgreSQL-backed coefficient lifecycle and restart persistence boundary. The
canonical five-stage production attempt separately resolves its `CoefficientContext`
from the approved catalog through the production resolver. That resolver emits
`source_type="catalog"`, and Transaction A persists that content without rewriting
its provenance. Persistence is proved by the durable `CoefficientContextRecord`,
the exact `SourceBinding.coefficient_context_id`, the same context id on all five
persisted calculation runs, `selection_strategy="source_binding_exact_id"`, the
matching SourceBinding id, and fresh-engine readback after restart. S6-07 must not
invent a `production_persisted_context` provenance value merely to signal that a
catalog context was persisted.

V0.2 S6-07 does not claim a registry-to-engineering-input mapping for the five
calculators. `coefficient_execution_continuity.result` therefore remains
`NOT_REQUIRED_BY_V0_2_OPERATIONAL_ACCEPTANCE` with `available=false`. This scope
marker is distinct from persistence authority: the production path, five
CalculationRuns, SourceBinding, SchemeRun, and source archive are still required
and independently read back. After the initial readback, a fresh database engine
reads the same run through the canonical production read ports and re-hashes the
source archive; this is the restart persistence authority.

## Acceptance sequence

1. Validate the dispatch, exact source SHA, checked-out tree SHA, and refreshed
   S6-06 authority.
2. Build the existing backend image with the exact source identity.
3. Start PostgreSQL, run the canonical migration service, then start the
   backend.
4. Verify liveness/readiness and strict runtime identity.
5. Exercise the existing HTTP project/calculation and coefficient boundaries;
   do not add a product endpoint or change calculation semantics.
6. Verify the disabled planning-agent boundary, correlation ID, structured
   logs, and redaction.
7. Restart the backend while retaining database and artifact volumes, then
   verify readiness and persisted state.
8. Assemble and independently verify the nine-file S6-07 evidence bundle.

The focused PostgreSQL path executes the coefficient persistence, strict
composition, controlled HTTP authority, and fresh-engine reload checks as
independent acceptance steps. A local environment without PostgreSQL may skip
those integration cases, but the controlled workflow must execute them and
fails closed on any missing step.

The persistence observations must show the existing canonical production
scheme-service action followed by independent persisted readback. The legacy
HTTP scheme route is used only for the exact GET readback; its create response
is never treated as persistence proof. Five-stage facts come from the existing
`ProductionSchemeService`, `SchemeRunRecord`, `SourceBindingRecord`,
`CalculationRunRecord`, and production source-archive read ports. The five
stage names and completed statuses, run identity, binding slot set/hash,
coefficient context provenance (`source_type="catalog"`), exact context and
SourceBinding identities, power authority, and source archive identity/hash are
checked independently before and after backend restart. A missing, partial,
demo, non-catalog context, or latest-row fallback is a failure, not a synthetic
pass. HTTP 200 alone never implies five-stage success.

## Evidence bundle

The final artifact contains exactly these nine regular files:

```text
acceptance-summary.json
source-identity.json
s6-06-authority.json
runtime-lifecycle-observations.json
production-http-scope-observations.json
persistence-e2e-observations.json
observability-security-observations.json
SHA256SUMS
SHA256SUMS.sha256
```

`SHA256SUMS` covers the seven JSON files. `SHA256SUMS.sha256` covers only
`SHA256SUMS`. Both are verified from the bundle root. Logs, database dumps,
credentials, DSNs, tokens, and temporary GitHub metadata are never bundle
members.

The independent verifier recomputes source, S6-06, observation, strict-agent,
database-coefficient, persistence, production-operation, secret-scan, shape,
and checksum gates from the raw documents. It does not trust
`acceptance_result=PASS` or any other recorded derived result in the summary.

The final bundle must continue to distinguish:

```text
OBSERVATIONS_ARE_FACTS_NOT_PASS_ASSERTIONS=YES
ASSEMBLER_DERIVES_RESULTS=YES
INDEPENDENT_VERIFIER_RECOMPUTES_RESULTS=YES
HTTP_200_IMPLIES_FIVE_STAGE_PASS=NO
```

The focused PostgreSQL persistence test uses the same CI PostgreSQL service and
performs canonical production create, independent readback, source-archive
re-hash, and fresh-session reload after restart. The strict-agent integration
test declares all required resource identities, starts the existing production
composition, and calls the real disabled route; it does not mock a response
body. The controlled workflow fails closed if the active composition token is
missing or if a process-local coefficient or fake-agent token is present.

## Failure and governance

Any missing or mismatched source, S6-06 run, artifact, digest, observation,
runtime, readiness, persistence, security marker, or checksum fails closed with
an S6-07 failure code. A failed controlled run is not automatically rerun.
Correction, rerun, and any later stage require separate authorization.

S6_07_PASS_DOES_NOT_AUTHORIZE_PRODUCTION_DEPLOYMENT=YES

S6_07_PASS_DOES_NOT_AUTHORIZE_PRODUCTION_PROMOTION=YES

S6_07_PASS_DOES_NOT_AUTHORIZE_RELEASE_PUBLICATION=YES

S6-07 remains separate from S6-06 evidence assembly. S6-07 success does not
enable the model-backed planning agent in strict modes and does not authorize
registry push, signing, attestation, deployment, rollback, migration, backup,
or restore against production.
