# CI speed refactor R1

Owner task `V2_2_2_CI_SPEED_REFACTOR_R1`, Draft PR #307; reference
`2839de7862ee5e7d5f106b0ae89b6dfabaa351bf`. No Ready/Merge/Deploy,
factory solve, new Grant or engineering algorithm change is authorized.

## Event and authority separation

| Purpose | Workflow / event | Final check | Authority |
|---|---|---|---|
| Daily feedback | ci-fast.yml / PR opened, synchronize, reopened | fast-ci-gate | Development only |
| Formal PR acceptance | ci.yml / PR labeled | ci-gate | Full acceptance |
| Main verification | ci.yml / push main | ci-gate | Not PR execution admission |
| Existing manual/special checks | ci.yml / workflow_dispatch | ci-gate | Not PR execution admission |

No feature-branch Push workflow remains. Only ci-fast has a PR-number-specific
concurrency group with cancellation. It cannot cancel full/main/manual jobs.
Any label addition triggers full acceptance, as authorized. ci-full-request
is a convention, not a safety override. To request a new full run when this
label is already attached, remove and re-add it; never substitute dispatch.

## Protection before trigger changes

Main classic protection requires PRs, up-to-date ci-gate from GitHub Actions
App 15368, applies to administrators, and prohibits force push and deletion.
No bypass allowance is configured. Preflight found no prior protection or
ruleset. The initial payload containing organization-only empty bypass lists
was rejected (422) on this personal repository; the supported payload omits
those lists and was independently read back. No existing rule was weakened.

After the first actual fast-ci-gate result, add that Actions check to the
existing required-check list without replacing other protection. Both checks
must then be required. Read back rules and actual check providers. No merge
test is authorized. Fast success alone leaves the current-head ci-gate
requirement pending. Manual workflow success is not formal PR proof:
https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks

## Deny-by-default development selection

The existing classifier adds --development. Only complete exact path sets in
STAGE_B_FAST_PATHS receive STAGE_B_FAST: opt-in balanced/wall/construction
preferences and listed tests/document. Shared solver/orchestration, execution
admission, guards, P1/Site/Access/Truck/P2D, dependencies, CI and unknown or
mixed paths are not allowlisted. Deleted and old renamed paths remain in diff.

Safe and unknown/high-risk development submissions receive bounded synthetic
Stage B, geometry, deterministic-resource and CI-admission tests, architecture
boundaries, CI classifier tests, Ruff/Format/Mypy and static checks. Unknown
changes still need formal full acceptance; fast SUCCESS is never sufficient.
No real Owner-bound factory solve occurs. Physical RSS is explicitly excluded
only in this feedback workflow, not globally and not from full acceptance.

## Full means full

ci.yml uses --full, selecting all existing normal full jobs. Its always-run
ci-gate also requires scope FULL and rejects any missing, failed, cancelled
or skipped required job. SQLite, PostgreSQL, ten-round concurrency stress,
Access, P1A, architecture, MCP and engineering tests remain. Both real Linux
RSS workers, original JUnit verification and production guard remain unchanged.
Manual inputs and controlled-specialist job bodies are frozen.

Database test repartition is not implemented in this revised task: existing
complete acceptance jobs are retained. No node is removed without a separate
Node ID / dependency audit. Savings come from event separation, not an
unsupported claim of safe database-test deduplication.

## Shared real-execution admission

The three guided-fair, functional-shape A/B and feasibility-first trusted
entrypoints still share github_admission. Only the obsolete PR+Push CI proof
changes. Original fixed Owner TXT, committed source/dependency/policy binding,
server inputs, one-use Grant/Claim and durable shared ledger remain in their
callers/stores; none is created or reset here.

The shared CI proof requires clean local HEAD equal to the OPEN/DRAFT PR #307
head in the trusted same repository/branch and main base; the ancestor gate
remains. It reads the active ci.yml workflow, selects the newest exact-head
pull_request run bound to this PR, source repository/branch and current base
SHA, and requires COMPLETED/SUCCESS. Fast, push, dispatch, another PR/fork,
stale HEAD/base, and an older success behind a pending run cannot substitute.

Every required full job must appear exactly once and succeed. Original Linux
RSS steps must actually succeed; incomplete job pagination fails closed.
The real ci-gate check must belong to that run's check suite and Actions App
15368. No caller verified flag is read. PR binding and local HEAD are checked
again after reading evidence; mutable unrelated PR counters are not identity.

## Delivery and limits

All new admission tests use synthetic API data, no network/Grant/native solve.
Existing caller tests still require CI admission before approval/Claim. Run
classifier/gate/event/permission tests, source-admission and existing Stage B
regression, YAML syntax, Ruff/Format/Mypy/diff before one scoped Commit/Push.
That push triggers fast feedback only. After actual fast verification and
requiring its check, add ci-full-request once for formal acceptance at the
same final HEAD. Record measured durations only; PENDING is not PASS.

Private evidence remains local. D01/D03/D04, historical UNKNOWN, engineering
authorities, algorithms, source candidates, ledgers and production defaults
are unchanged. Completion does not authorize Ready/Merge/Deploy or MAIN.

The first Linux fast run exposed a missing prerequisite: the shared autouse
pytest font fixture failed on its builtin-font fallback. Fast CI therefore
installs the same fonts-wqy-zenhei package already used by full CI, before any
pytest selection. The failed run is retained, not rerun or relabeled PASS.
This environment-only correction requires one additional scoped commit; it
does not change the renderer, resource guard, test selection or assertions.
