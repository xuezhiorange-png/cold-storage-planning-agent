# TASK-012 V0.2 Slice 6 Package 3: Final Release Evidence

This runbook defines S6-06 as a read/verify/bind/assemble boundary. It
combines already-closed V0.2 authorities into one small, deterministic,
machine-verifiable release evidence bundle. It does not build, deploy,
backup, restore, roll back, migrate, sign, promote, or execute S6-07.

## Scope and dependency direction

S6-06 proves that the required V0.2 production-readiness authorities are
closed under one exact current release identity. It reuses the existing
Slice 2, Package 1, Package 2, runtime, environment, and observability
authorities by reference and digest.

The dependency direction is intentionally one-way:

```text
S6-06 evidence closure
        |
        v
S6-07 separately authorized controlled end-to-end acceptance
```

`S6_07_IS_REQUIRED_FOR_S6_06_PASS=NO`.
`S6_06_PASS_DOES_NOT_IMPLY_S6_07_PASS=YES`.
`S6_06_PASS_DOES_NOT_AUTHORIZE_S6_07=YES`.

An S6-07 status of `NOT_AUTHORIZED` is recorded as the next stage and does
not make an otherwise complete S6-06 bundle fail.

## Exact bundle contract

The final bundle contains exactly these eight regular files. Extra files,
missing files, symlinks, and temporary files are rejected:

```text
release-evidence-summary.json
source-identity.json
authority-index.json
runtime-readiness-summary.json
recovery-authority-summary.json
release-provenance-summary.json
SHA256SUMS
SHA256SUMS.sha256
```

`SHA256SUMS` covers the six JSON files. `SHA256SUMS.sha256` covers only
`SHA256SUMS`; neither manifest self-references.

Every JSON document carries the TASK-012/V0.2/Slice 6/S6-06/Package 3
scope, exact current source SHA and tree SHA, a UTC `generated_at`, the
controlled-evidence and no-production-operation markers, authority counts,
and its verification result.

## Upstream authority model

The authority index contains exactly 17 required entries. Each entry binds:

```text
authority_id
authority_type
domain
required
canonical_repository_path
canonical_pr_number
canonical_merge_sha
workflow_name
workflow_run_id
workflow_run_attempt
workflow_event
workflow_head_sha
workflow_conclusion
artifact_id
artifact_name
artifact_digest
receipt_name
receipt_sha256
source_environment_class
controlled_synthetic
production
verification_result
```

An inapplicable value is JSON `null`, never an empty string or an invented
placeholder. The assembler compares the complete entry to the frozen
authority table and can additionally verify deterministic synthetic GitHub
run/artifact metadata fixtures. A missing, failed, ambiguous, expired,
head-mismatched, digest-mismatched, or lineage-unverified authority fails
closed.

The final bundle references, rather than copies, upstream payloads. It does
not contain database dumps, artifact archives, production data, credentials,
or secret-bearing logs.

### Package 1 binding

Package 1 is the final successful controlled recovery authority for S6-01,
S6-02, and S6-03:

```text
run_id=31469678479
head_sha=658c993040d93371ee3286fc91c8f4abeb5da7b1
artifact_id=9092865725
artifact_digest=sha256:345841c71d21239753758749f3f02b17925bb73dc2d4b72071c6389e3b481699
```

Earlier failed attempts remain historical lineage only and are not final
authority. Package 1 is reused and never rerun by S6-06.

### Package 2 binding

Package 2 is the final successful controlled failure-recovery authority for
S6-04 and S6-05:

```text
run_id=31493144331
head_sha=7b36d68afb94577db401b8825013cc14ab0943d7
artifact_id=9101883140
artifact_digest=sha256:ab859a42afc7e6459dd053fa1aaf5d7ddd4ce9968f11093904f1f513c0b1ea18
controlled_synthetic=true
production=false
automatic_downgrade_performed=false
```

The summary binds actual transactional and partial Alembic failure evidence,
mutation rollback/persistence classification, backup/restore/verify reuse,
previous-release recovery, live/ready observations, and both recovery
receipts. Package 2 is reused and never rerun by S6-06.

### Slice 2 provenance binding

The release provenance summary reuses the closed Slice 2 chain by reference:

```text
D0 capture:      run 31342745646, artifact 9046325555
D1 transport:    run 31352302807, artifact 9049370270
attestation:     run 31371998864, artifact 9056423295
assembly:        run 31394393604, artifact 9064992469
```

Each reference includes its historical authority source SHA, current release
source SHA, lineage binding result, artifact digest, and receipt/manifest
digest where applicable. Historical run heads are not rewritten as the
current main SHA, and Slice 2 is not reopened.

## Deterministic gates

The assembler and independent verifier require all applicable gates to pass:

```text
SOURCE_SHA_GATE
SOURCE_TREE_GATE
ENVIRONMENT_SECURITY_GATE
RUNTIME_READINESS_GATE
OBSERVABILITY_GATE
RELEASE_PROVENANCE_GATE
RECOVERY_PACKAGE1_GATE
RECOVERY_PACKAGE2_GATE
UPSTREAM_RUN_CONCLUSION_GATE
UPSTREAM_ARTIFACT_EXISTENCE_GATE
ARTIFACT_DIGEST_GATE
RECEIPT_BINDING_GATE
NO_SECRET_MATERIAL_GATE
NO_PRODUCTION_OPERATION_GATE
BUNDLE_SHAPE_GATE
BUNDLE_CHECKSUM_GATE
```

`release_evidence_result=PASS` is valid only after all 17 required
authorities and all required gates pass. The verifier independently derives
the six JSON documents and does not trust the summary's PASS field. It
rejects source/tree mismatch, unsuccessful or mismatched runs, missing or
expired artifacts, digest or receipt mismatch, unverified lineage, secrets,
production-operation markers, bundle shape changes, and checksum failures.

## Local operator commands

Use an empty temporary directory outside the repository for all output:

```bash
PYTHONPATH=backend/src uv run --project backend python \
  -m cold_storage.release.final_release_evidence \
  write-frozen-authority-index \
  --output /tmp/task012-s6-06/authority-index.json

PYTHONPATH=backend/src uv run --project backend python \
  -m cold_storage.release.final_release_evidence \
  assemble-final-release-evidence \
  --authority-index /tmp/task012-s6-06/authority-index.json \
  --output-dir /tmp/task012-s6-06/bundle \
  --source-sha 7b36d68afb94577db401b8825013cc14ab0943d7 \
  --source-tree-sha a43c2686a5f2c91aae1b4966f31923648c5eff03 \
  --generated-at 2026-08-11T00:00:00Z

PYTHONPATH=backend/src uv run --project backend python \
  -m cold_storage.release.final_release_evidence \
  verify-final-release-evidence \
  --bundle-dir /tmp/task012-s6-06/bundle \
  --source-sha 7b36d68afb94577db401b8825013cc14ab0943d7 \
  --source-tree-sha a43c2686a5f2c91aae1b4966f31923648c5eff03
```

The final command must independently report `S6_06_VERIFICATION_RESULT=PASS`.
Do not point these commands at a tracked directory.

## Controlled GitHub workflow

The implementation-only workflow is:

```text
.github/workflows/task012-slice6-package3-release-evidence.yml
```

It is `workflow_dispatch` only, requires
`execute_final_release_evidence_assembly=true`, requires the exact frozen
main SHA, and requires `refs/heads/main`. It has `contents: read` and
`actions: read` permissions, writes the bundle under `RUNNER_TEMP`, verifies
both checksum files, uploads the exact bundle, and records the upload-time
artifact identity. It cannot dispatch Slice 2, Package 1, Package 2, or
S6-07 and performs no production operation.

This PR does not dispatch that workflow. A later execution requires separate
authorization after independent review and merge.

## Explicit non-goals

S6-06 does not:

- execute S6-07;
- rerun Slice 2, Package 1, or Package 2;
- build images or access production secrets;
- perform backup, restore, rollback, migration, deployment, promotion,
  registry push, signing, or attestation creation;
- alter recovery core semantics or Slice 2 provenance semantics.
