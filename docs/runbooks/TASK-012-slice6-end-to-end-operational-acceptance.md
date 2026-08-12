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

The acceptance observes image/build identity, the exact migration head,
startup, liveness, readiness, canonical PostgreSQL and artifact storage, and
the strict capability audit. It exercises the database-backed coefficient
route and verifies the planning-agent route remains a disabled `503` with
`AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE` and `retryable=false`.

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

The persistence observations must show the existing canonical source-binding
and scheme path when that path is exercised. A missing, partial, demo, or
latest-row fallback is a failure, not a synthetic pass.

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
and checksum gates. It does not trust `acceptance_result=PASS` in the summary.

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
