# TASK-012 V0.2 Slice 2: Release Candidate Evidence Runbook

This runbook defines the release-candidate evidence contract and the
non-production execution surface. It does not grant authorization to build,
sign, push, promote, or deploy anything.

## Frozen identities

The release candidate source is an immutable release-instance value:

```text
RC_SOURCE_SHA=043731fea4e60feb6b929c524c4b68e87ed67bd7
RC_SOURCE_TREE_SHA=b456e77f07a0cef801c57d2f089a318c35c145c4
RC_VERSION=v0.2.0
```

The evidence-tooling checkout may be newer than that source. Its
`EVIDENCE_TOOL_HEAD` and `EVIDENCE_TOOL_TREE` are recorded as execution-tool
identity and must not replace the frozen RC source values.

The authoritative verifier remains in:

- `cold_storage.release.digest_verifier`
- `cold_storage.release.evidence_collector`
- `cold_storage.release.provenance_statement`

The external-observation adapter is
`cold_storage.release.live_evidence_runner`. Docker and Git subprocesses must
stay in that adapter; the verifier and collector do not discover external
state themselves.

The canonical future execution environment is the existing `ci` workflow on
`ubuntu-latest`. Its gated job explicitly creates a `docker-container` Buildx
builder with `docker/setup-buildx-action@v4`, bootstraps it, and verifies that
`linux/amd64` is available. The runner repeats that selected-builder check and
fails closed for the `docker` driver or an unavailable target platform. It does
not create or silently select another builder.

## Canonical Live Evidence Execution Surface

The runner is executable with:

```bash
python -m cold_storage.release.live_evidence_runner capture-local \
  --execute-builds \
  --expected-source-sha 043731fea4e60feb6b929c524c4b68e87ed67bd7 \
  --output-dir "$RUNNER_TEMP/task012-live-evidence/$GITHUB_RUN_ID"
```

`capture-local` requires both `--execute-builds` and the exact environment
value `TASK012_BUILD_A_B_AUTHORIZED=YES`. This software guard is not a
substitute for the separate human or workflow authorization required for a
real capture.

The runner creates two fresh detached worktrees from `RC_SOURCE_SHA`. Before
either build it verifies the commit, tree, tracked/untracked status, and
ignored status. Any `!!` ignored artifact blocks the capture. A capture output
directory must be outside the execution checkout, be empty or newly created,
and is non-tracked by default.

## Frozen RC Source vs Evidence Tooling

Build contexts are the fresh RC worktrees, never the evidence-tooling checkout.
The runner records both identities in `metadata.json` and in the observation
bundle. A later correction commit therefore cannot be accidentally presented
as the source used for the image.

## Build A/B Independence

Build A and Build B are separate `docker buildx build` invocations. Each uses:

- a different fresh detached source worktree;
- a different run ID, output path, metadata path, manifest path, and record;
- `--no-cache`;
- `BuildInputs.docker_target_platform=linux/amd64`, forwarded directly to
  `docker buildx build --platform`;
- the frozen source commit and version;
- `SOURCE_DATE_EPOCH` derived from `git show -s --format=%ct RC_SOURCE_SHA`.

`docker_target_platform` is a build-input-manifest field and is distinct from
the execution environment field `build_platform=ubuntu-latest`. The three
actual Dockerfile build arguments are the frozen source commit, release
version, and source-derived timestamp; there is no fake `TARGET_PLATFORM`
build argument.

The runner observes A and B independently and compares their OCI manifest
digests only after both observations complete. It never copies A's digest,
image output, or record into B. A missing B output, output collision, run ID
collision, or digest drift is a fail-closed error.

## Actual OCI Manifest Digest Observation

The build uses a local OCI exporter and does not require a registry. The runner
requires an OCI layout, a schema-version-2 `index.json`, exactly one image
manifest descriptor, and a supported image-manifest media type. It reads the
referenced `blobs/sha256/<digest>` bytes and recomputes SHA-256 before accepting
the descriptor digest.

The Docker image/config ID is not an OCI manifest digest and is never accepted
as `local_oci_manifest_digest`. Image indexes, manifest lists, attestation
indexes, ambiguous descriptors, missing blobs, malformed digests, and digest
tampering fail closed. The implementation is covered by synthetic tests; no
real RC OCI digest is claimed by this repository change.

## Local-only Capture Phase

Capture produces a machine-readable, non-tracked observation package containing
metadata, expected inputs, independent A/B observed inputs, input-manifest
declarations, BuildRunRecords, Buildx metadata, OCI output, and checksums.

The local phase does not push to a registry. `registry_manifest_digest` remains
`None` until a separately authorized registry-binding phase. No `--push`,
registry login, `cosign`, OIDC token request, or promotion command belongs in
the capture command.

The capture package contains `SHA256SUMS` and its `SHA256SUMS.sha256` sidecar.
Before reading `observation-bundle.json` or any business observation field,
`assemble` verifies the sidecar, every checksum entry, regular-file and
symlink constraints, path safety, and exact coverage of all payload files.
An extra, missing, deleted, or modified payload fails closed before the
collector is called.

## Attestation Assembly Phase

The second phase is explicit:

```bash
python -m cold_storage.release.live_evidence_runner assemble \
  --observation-bundle <non-tracked-observation-bundle.json> \
  --attestation-file <explicit-attestation.json> \
  --output-dir <new-non-tracked-output-dir>
```

Missing attestation fails closed. The runner never creates a default
`write_once_integrity`, `github_oidc`, GPG, cosign, or synthetic binding. Test
fixtures may use an explicitly labeled `TEST_ONLY:SYNTHETIC_ONLY` attestation
to verify adapter wiring; that is not live attestation evidence.

`assemble` reconstructs `BuildInputs` and `BuildRunRecord` from the observed
package and calls the existing `collect_release_candidate_evidence()` API.
It does not copy collector or verifier logic. Independent input-manifest
declarations are recomputed and checked before the collector is called.

## Artifact Transport Integrity

The transport adapter is
`cold_storage.release.artifact_transport`. It verifies a capture package after
it has left the ephemeral capture runner. Transport verification is not
assembly, attestation, OCI verification, registry binding, or promotion.

### Upload-time handoff receipt

The capture workflow uses `actions/upload-artifact@v4` with the runtime name:

```text
task012-live-evidence-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}
```

The upload step summary and job outputs record these runtime-derived values:

```text
artifact-id
artifact-digest
artifact-url
artifact-name
capture-run-id
capture-run-attempt
capture-head-sha
capture-head-branch
```

The `artifact-id` and `artifact-digest` are the machine handoff identity. The
URL is retained for human audit only and is never used as the download
authority. The upload-time digest is external to the ZIP payload; putting it
inside the same ZIP would create a recursive self-reference.

### Exact transport verification procedure

The later operator or gated workflow must select the exact numeric Artifact ID
from the upload-time receipt. It must not list artifacts, search by name, or
choose the newest result. The verifier requires both an explicit CLI flag and
an independent environment authorization:

```bash
export GITHUB_TOKEN='provided-by-the-authorized-workflow-environment'
export TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED=YES

PYTHONPATH=backend/src python -m cold_storage.release.artifact_transport \
  verify-download \
  --execute-download \
  --repository xuezhiorange-png/cold-storage-planning-agent \
  --artifact-id '<artifact-id-from-receipt>' \
  --expected-artifact-digest '<artifact-digest-from-receipt>' \
  --expected-capture-run-id '<capture-run-id-from-receipt>' \
  --expected-capture-run-attempt '<capture-run-attempt-from-receipt>' \
  --expected-capture-head-sha '<capture-head-sha-from-receipt>' \
  --output-dir '/absolute/non-tracked/transport-output'
```

The token is read only from the environment and is never passed as a command
argument or written to a receipt. The adapter first calls the exact REST
metadata endpoint:

```text
GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}
```

It requires the response ID, `expired=false`, digest, exact runtime artifact
name, workflow run ID, run attempt when present, `head_sha`, and
`head_branch=main` to match the upload-time receipt. It then calls the exact
ID-based archive endpoint:

```text
GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip
```

The adapter follows the server redirect but never accepts a user-provided
archive URL as authority. It streams the archive response into a temporary
runner-owned file and computes SHA-256 incrementally. The following three
values must normalize to the same `sha256:<64 lower-hex>` value:

```text
recorded upload-time artifact digest
REST metadata digest
SHA-256(downloaded archive bytes)
```

Any HTTP error, malformed metadata, expired artifact, identity mismatch,
empty/partial download, or digest mismatch fails closed. A partial or failed
download is never promoted to `verified-artifact.zip` and no verified receipt
is written.

### Safe extraction and handoff

Only after all three transport digests match does the adapter validate every
ZIP entry and extract to a new `extracted/` directory. It rejects absolute
paths, `..`, backslash ambiguity, duplicate output paths, symlinks, and special
files without using `extractall()`. The extracted root must contain
`observation-bundle.json`, `metadata.json`, `expected-inputs.json`,
`SHA256SUMS`, `SHA256SUMS.sha256`, `build-a/`, and `build-b/`.

The adapter writes `artifact-transport-receipt.json` containing the three
matching digests, exact Artifact ID, capture identities, exact endpoint
identity, verification time, and `transport_verification_status=PASS`. It
does not call `assemble` and does not create attestation or provenance.

The next separately authorized handoff is:

```text
verified transport output
  -> existing live_evidence_runner SHA256SUMS/SHA256SUMS.sha256 verifier
  -> re-observe A/B OCI outputs
  -> explicit attestation assembly
  -> existing collector/verifier
```

The three integrity layers remain distinct:

```text
TRANSPORT:
  recorded upload digest == REST metadata digest
  == SHA256(downloaded archive bytes)

INTERNAL PACKAGE:
  SHA256SUMS.sha256 -> SHA256SUMS -> exact capture payload coverage

OCI:
  OCI descriptor digest == SHA256(manifest bytes)
```

Failure in any layer stops the chain. An internal `SHA256SUMS` file cannot
substitute for the GitHub Artifact transport digest, and a transport receipt
cannot substitute for OCI or provenance verification.

The adapter uses the GitHub Actions Artifact REST contract documented at
`https://docs.github.com/en/rest/actions/artifacts` and the
`actions/upload-artifact` outputs documented at
`https://github.com/actions/upload-artifact`. The future transport job needs
only `contents: read` and `actions: read`.

## Registry Optional Boundary

The local digest chain can be verified without a registry:

```text
observed OCI digest A + observed OCI digest B
  -> reproducible-build verifier
  -> local authoritative digest
  -> artifact manifest
  -> explicit attestation-backed provenance
```

This does not establish registry-bound evidence. Registry push and registry
digest observation require their own authorization and evidence phase.

## Workflow Dispatch Governance Gate

The gated `live-evidence-capture` job lives in the existing `ci` workflow so
the frozen workflow identity remains `ci` and the allowed ref remains
`refs/heads/main`. It is skipped for ordinary `push` and `pull_request` events.

It can only be considered for a manual dispatch when all of the following are
true:

- `execute_live_evidence_capture` is explicitly `true`;
- `upload_live_evidence_artifact` is independently set to `true` only when
  artifact transport is also authorized;
- `verify_live_evidence_artifact_transport` is explicitly `false`;
- `expected_rc_source_sha` exactly equals the frozen RC source SHA;
- the ref is `refs/heads/main`;
- the checked-out source commit and tree match the frozen values.

The separate `live-evidence-artifact-transport-verify` job requires
`verify_live_evidence_artifact_transport=true`,
`execute_live_evidence_capture=false`, the same frozen source assertion, and
`refs/heads/main`. It receives the five transport receipt inputs: exact
Artifact ID, upload digest, capture run ID, capture run attempt, and capture
head SHA. Both jobs are skipped for ordinary `push` and `pull_request` events
and are mutually exclusive for a manual dispatch. All boolean inputs default
to `false`. Adding either job does not execute a workflow
dispatch, build, upload, download, request OIDC, push a registry image, or
promote an environment.

## Non-tracked Evidence Outputs

Capture output includes `metadata.json`, `expected-inputs.json`, independent
`build-a/` and `build-b/` observations, OCI outputs, `observation-bundle.json`,
`SHA256SUMS`, and `SHA256SUMS.sha256`. Capture and assembly outputs must be
written under an operator-selected, non-tracked directory such as
`$RUNNER_TEMP`. The runner rejects output inside
the evidence-tooling checkout and rejects non-empty or colliding output paths.
Only the runner-owned temporary source worktrees and temporary OCI extraction
directories may be cleaned by the runner. It never runs `git clean`, `git
reset`, or `git stash`, and it never recursively deletes an arbitrary user
directory.

## Required Separate Authorizations

The following phases are intentionally separate:

| Phase | Required authorization | Current status |
|---|---|---|
| Build A local capture | `BUILD_A_EXECUTION_AUTHORIZED=YES` | Not authorized in this correction |
| Build B local capture | `BUILD_B_EXECUTION_AUTHORIZED=YES` | Not authorized in this correction |
| GitHub Actions non-tracked artifact upload | `GITHUB_ACTIONS_ARTIFACT_UPLOAD_AUTHORIZED=YES` plus `upload_live_evidence_artifact=true` | Not authorized |
| GitHub Actions artifact download/transport verification | `GITHUB_ACTIONS_ARTIFACT_DOWNLOAD_AUTHORIZED=YES` plus `verify_live_evidence_artifact_transport=true` | Not authorized |
| Attestation/signing | `OIDC_SIGNING_EXECUTION_AUTHORIZED=YES` or separately approved signing mechanism | Not authorized |
| Registry binding | `REGISTRY_PUSH_AUTHORIZED=YES` | Not authorized |
| Staging promotion | `STAGING_PROMOTION_AUTHORIZED=YES` | Not authorized |
| Production promotion | `PRODUCTION_PROMOTION_AUTHORIZED=YES` | Not authorized |
| Deployment | `PRODUCTION_DEPLOYMENT_AUTHORIZED=YES` | Not authorized |

No phase may infer or inherit another phase's authorization. The software
mapping keeps `execute_live_evidence_capture` and
`upload_live_evidence_artifact` independent. The transport mapping keeps
`verify_live_evidence_artifact_transport` and
`TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED` independent from capture and upload.
Correction R3 implements the transport surface and synthetic/mock verification
only. It does not execute a workflow dispatch, real Build A/B, artifact upload
or download, signing, registry push, promotion, or deployment.

## Verification

The ordinary release-evidence CI job runs the runner unit, integration, and
architecture tests in addition to the existing release evidence suite. The
local runner tests use a mock Docker command and synthetic OCI layouts; they do
not require or invoke Docker. The full CI environment installs the CJK font
required by the existing release test fixture.

Useful local commands are:

```bash
make verify-live-evidence-runner
make verify-artifact-transport
make verify-release-evidence
make verify-base-image-digests
```

`LIVE_EVIDENCE_EXECUTION_STATUS=REQUIRES_SEPARATE_AUTHORIZATION` remains the
correct status until an independent execution authorization is granted.

## Authorization Boundary

```text
IMPLEMENTATION_AUTHORIZED=true
REAL_BUILD_A_AUTHORIZED=false
REAL_BUILD_B_AUTHORIZED=false
REGISTRY_PUSH_AUTHORIZED=false
OIDC_SIGNING_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```
