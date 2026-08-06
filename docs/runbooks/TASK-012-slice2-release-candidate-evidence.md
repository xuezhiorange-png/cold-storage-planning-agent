# TASK-012 Slice 2 R1: Release Candidate Build and Provenance Evidence Runbook

## Overview

This runbook documents the release-candidate build and provenance evidence
system implemented in V0.2 Slice 2 R1. It covers the five P0 gaps
(S2_GAP_01 through S2_GAP_05), the 20 negative scenario tests, and the
quality gate targets.

## Five P0 Gaps

### S2_GAP_01: Reproducible Build Evidence

Two independent builds from the same commit SHA must produce identical
OCI image digests. The `digest_verifier.verify_reproducible_build`
function compares build input manifests and final image digests.

**Module**: `cold_storage.release.digest_verifier`

### S2_GAP_02: Final Image Digest

The authoritative image identity is `sha256:<64-hex>`, never a mutable
tag. The `digest_verifier.authoritative_image_digest` function resolves
the local OCI manifest digest and optionally the registry manifest digest.

**Module**: `cold_storage.release.digest_verifier`

### S2_GAP_03: Artifact Manifest and Digest

A canonical JSON artifact manifest with deterministic key order, UTF-8
encoding, duplicate key rejection, absolute path rejection, and secret
value rejection. The digest is `sha256(canonical manifest bytes)`.

**Module**: `cold_storage.release.artifact_manifest`

### S2_GAP_04: Release-Candidate Provenance

A machine-verifiable provenance statement binding the image digest and
artifact manifest digest to a build identity. Protected by an attestation
mechanism (GitHub OIDC, cosign, GPG, or write-once integrity).

**Module**: `cold_storage.release.provenance_statement`

### S2_GAP_05: Environment Promotion Provenance

A promotion record schema and verifier enforcing `ci -> staging ->
production` sequence, immutable digest references, no rebuild during
promotion, and approver/promoter separation.

**Module**: `cold_storage.release.promotion_record`

## Negative Scenario Tests

All 20 frozen negative scenarios (NR-01 through NR-20) are implemented as
automated tests with explicit error code assertions:

```
NR-01  RC_SOURCE_COMMIT_MISMATCH
NR-02  RC_BASE_IMAGE_DIGEST_MISMATCH
NR-03  RC_LOCKFILE_DIGEST_MISMATCH
NR-04  RC_BUILD_ARG_MISMATCH
NR-05  RC_FINAL_IMAGE_DIGEST_MISMATCH
NR-06  RC_FINAL_IMAGE_DIGEST_MISSING
NR-07  RC_REGISTRY_DIGEST_MISMATCH
NR-08  RC_ARTIFACT_MANIFEST_MISSING
NR-09  RC_ARTIFACT_DUPLICATE_KEY
NR-10  RC_ARTIFACT_DIGEST_MISMATCH
NR-11  RC_PROVENANCE_UNSIGNED
NR-12  RC_PROVENANCE_REPO_MISMATCH
NR-13  RC_PROVENANCE_WORKFLOW_MISMATCH
NR-14  RC_PROVENANCE_SUBJECT_MISMATCH
NR-15  RC_PROMOTION_MUTABLE_TAG
NR-16  RC_PROMOTION_REBUILD
NR-17  RC_PROMOTION_DIGEST_DRIFT
NR-18  RC_ENV_CONFIG_DIGEST_MISSING
NR-19  RC_APPROVER_MISSING
NR-20  RC_PROMOTION_RECORD_UNVERIFIABLE
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `release-evidence-lint` | Ruff lint + format check on release module |
| `release-evidence-typecheck` | Mypy strict typecheck on release module |
| `release-evidence-test` | All release evidence tests (127 tests) |
| `verify-release-evidence` | Full gate: lint + typecheck + tests |
| `verify-base-image-digests` | Verify Dockerfile and Compose use digest pinning |

## CI

The `release-evidence` job in `.github/workflows/ci.yml` runs the full
evidence verification suite on every push and pull request.

## Live Evidence Execution

This implementation provides code and synthetic verification only. Real
registry push, GitHub OIDC signing, and environment promotion require
separate authorization:

```
LIVE_EVIDENCE_EXECUTION_STATUS=REQUIRES_SEPARATE_AUTHORIZATION
```

## Authorization Boundary

```
IMPLEMENTATION_AUTHORIZED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
TAG_OR_RELEASE_AUTHORIZED=false
```
