# REVIEW-MULTI-CANDIDATE — Stage B scoped construction

Owner instruction: `STAGE_B_MULTI_STRUCTURAL_CONSTRUCTION`, 2026-10-17.
Baseline PR #307: `9d6d6c054295f589075441bbd75d71b9eb54a470`.
This is a delivery slice of the original work package, not a new version task,
architecture identity or recovery allowance. No quality ranking, Tool7 wiring,
Truck acceptance, deployment, Ready or Merge is authorized.

## One-time opening applicability review

* D01: safe capacity pruning, joint positive-capacity proof and actual engineering
  validation remain separate. Construction cannot close the old P3 proof. Its
  262 UNKNOWN and zero-UNKNOWN strong gate remain unchanged; P3_COMPLETE=false.
* D03: consume the current server P1A handoff, including Secondary in
  PROCESSING_CORE_GROUP. Preserve P0's historical FINISHED_SIDE_GROUP. The 0.90
  product grid target is not a calibrated numeric acceptance gate.
* D04: the stage-A main implementation has succeeded and been delivered. PR CI
  39014412638 and Push CI 39014409166 both succeeded at the baseline SHA. Stage B
  adds collection/deduplication around that SAME successful construction chain;
  it is not another attempt to recover a failed 12-zone architecture. The current
  Owner instruction explicitly authorizes this new-feature implementation.
  Consequently this scoped feature does not require inventing a historical
  recovery-round classification, a new architecture, or a reset of MAX=2.
  Historical unresolved classifications in version-plan sections 8.1/8.5/12.5
  remain unresolved; this review neither signs an Owner decision nor waives them.
  The original reset contract's recovery stop rule (main attempt plus at most two
  bounded corrections) still applies to any future actual recovery. No further
  implementation/recovery task is implied by this one. If execution later needs
  a historical-round ruling or exception, obtain that decision before proceeding.

This review applies the existing Stage-A D01/D03/D04 scope and ADR-051. It does
not amend their historical contracts or retroactively approve R1–R15 rounds.

## Implementation and conservative coverage

`bootstrap.global_composition.generate_controlled_global_layout_pool` is an
internal entry accepting the existing business Plan/P1/typed Site, not supplied
coordinates. It builds the server's six handoffs and searches them in a stable
round-robin across source family intents. Every attempt uses the unchanged
Stage-A global solver and complete per-candidate independent/native Access and
Footprint/Site validation. It never fixes a historical room or reuses another
candidate's PASS. Candidate results are copied at the boundary so later ledger
mutations cannot rewrite earlier candidate evidence or invalidate its hash.

Two separate geometric facts are exposed:

1. Integer-mm physical rectangles, role-labelled and canonicalized across
   translation, rotations and reflections; nominal rotation/serialization is
   not a new geometry.
2. Ordered positive-edge attachment directions along the seven-room main process
   chain, canonicalized under the same eight symmetries. These come from actual
   geometry, not family labels. Different direction sequences require different
   main production organization. Their canonical sequences are reviewable.
3. Major family further collapses consecutive equal directions into physical main
   bands. Moving the turn along the same L-shaped band organization is not another
   major family. Source family labels remain separate scheduling intent.

For now only one candidate per main organization is counted. This is deliberately
conservative: genuinely different auxiliary branches within one main organization
may be undercounted. Resizing, tiny offsets, changing labels or support-only swaps
cannot inflate the construction count. This is a versioned diversity policy, not
a new engineering constraint or calibrated quality threshold. More permissive
branch-sensitive counting would need additional evidence, not invented tolerances.
Five counted candidates therefore require five observed role-to-band organizations
and at least three collapsed main-band families in this first implementation;
the product minimum remains five candidates / three major organizations, not
reduced to three JSON files. Neither target is guaranteed
by the bounded six-handoff search.

Incomplete, UNKNOWN, rejected and duplicate proposals remain recorded separately.
A finite-model INFEASIBLE is not project infeasibility. Resource interruption stops
the pool; it does not restart per family. Construction results are never P2D
full-pass, even if the native application produces eleven non-Truck PASS results.

## Resource admission and concrete request — NOT an execution approval

Stage A's exhausted grants are not Stage B grants. The new entry returns
OWNER_POOL_EXECUTION_QUOTA_REQUIRED before any solve unless a separately approved
durable pool authorization implements the application-owned validate_pool port.
This task provides no concrete lease issuer, registry allocation or fabricated
Owner signature. A UUID, directory or boolean cannot create a lease. The future
issuer must bind exact source/dependency/Plan/P1/Site/schedule identities and
enforce NEW/RESUME, complete history, exclusive claims and all shared counters.
Admission returns a durable authorization receipt for the output's provenance;
the issuer must include Owner instruction, exact source/dependency identities and
allocation/checkpoint references in that receipt, not merely a verified boolean.
Old Stage-A authorizations do not implement that port and are denied.

Requested next execution, subject to Owner approval and durable issuer wiring:

* One separately identified Owner task, one construction pool and one exact replay.
* At most six server-derived composition invocations per pool, twelve total;
  all native warmup/refinement/final calls charged, with no per-family refill.
* Both pools and validation/replay costs share **100 native solver seconds total**,
  **180 elapsed seconds total**, **1,200,000 model+native Host work total** and
  **512 MiB process peak**. These are not additional allowances for each pool.
  Each requirement retains Host 20,000 and the unchanged route-node budget.
* Reserve the replay within those same ceilings before starting; stop and retain
  partial results when the remaining shared allowance is insufficient. Do not
  promise five/three under this finite resource proposal.
* Unknown interrupted native consumption prohibits continuation without a complete
  durable ledger. A fresh run ID is never a replacement. Replay compares actual
  geometry/authority/native outputs; elapsed statistics need not be identical.

Original budgets remain placement 60,000, Access 20,000, Truck 20,000, joint
evaluations 256, origin events 1,024 and joint work 8,192. Branch/conflict/time/Host
units are kept separate. No Owner-bound real factory solve or replay was started
by this implementation task. Synthetic orchestration tests are not construction
candidates and never enter the real five/three or full-pass counts.

## Verification boundary

Run the new diversity/pool tests and the existing Access 43, resource 44, MCP 98
and Architecture regressions, plus Ruff/format/Mypy/diff checks. Pool tests use
synthetic solver/authorization ports and also exercise the real server input and
validation entry on UNKNOWN-only proposals without invoking CP-SAT. The existing
process-isolation test harness also covers pool tests using the real RSS guard;
no resource threshold, profiler or business assertion is modified.

Real candidate comparison/gallery and real deterministic replay remain pending
the separate execution approval. P3_COMPLETE=false, P2_COMPLETE=false and
VERSION_COMPLETE=false. The original final five distinct structured P2D full-pass
and three-family product acceptance, quality and Owner visual gates remain intact.
