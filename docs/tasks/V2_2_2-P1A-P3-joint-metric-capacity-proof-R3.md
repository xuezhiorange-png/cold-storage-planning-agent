# P3-R3 — connected HARD component capacity proof

Task: `V2_2_2_P1A_P3_JOINT_METRIC_CAPACITY_PROOF_R3`.
Start: `8c921b0f654d5d00e8664cf19650a278d558a7a0`; same Draft PR #307.
PR #306 remains diagnostic-only; no code or geometry is inherited.

## Isolated checkout recovery

Owner separately authorized `V2_2_2_P1A_P3_R3_ISOLATED_CHECKOUT_RECOVERY_R1`.
Original PID 3066 was absent at the initial system-only observation. This is not
a claim that the original worktree is clean or healthy. No original-repository
status/diff, metadata operation, signal or lock recovery is performed.

Available Data-volume capacity before clone: 9,061,088 KiB (approximately 8.6 GiB).
No separate suitable writable disk was mounted. GitHub reported repository size
19,443 KiB; planning allowance was 3 GiB for clone/environment/test artifacts,
with at least 4 GiB retained as headroom. No user files were cleaned.

Complete non-shallow GitHub clone:
`/Users/charles/codex-r3-isolated.m45h1H/repo`.
Its independent `.git` is 20 MiB; checked-out repository initially 47 MiB.
No shared index, alternates, local clone or original-object hard links. HEAD,
branch and HTTPS origin matched; status/diff/cached-diff/add-dry-run completed
normally; required historical commits are readable; no new index.lock.
No configured hooksPath or executable non-sample hooks.

Before business edits, archive backup:
`/Users/charles/codex-r3-isolated.m45h1H/r2-start-backup.tar`.
SHA256: `aa0283b7459b29c3bb762082f2a23b9729bc500005e2e59e859bb07694c4d04e`.
Python 3.12 environment is installed independently using locked dependencies and
copy mode. An initial environment selected 3.14; it was replaced by explicit
3.12 before canonical or acceptance execution. No dependency files changed.

R2 exact-head CI was independently confirmed SUCCESS, attempt 1:
PR 37729555390 and Push 37729552299. They are baseline evidence, not R3 CI.

## Stage 1 — UNKNOWN attribution before production integration

Committed R2 evidence contains 354 UNKNOWN edge checks (195 Coating/Finished,
75 Finished/Shipping, 42 Office/Shipping, 30 Secondary/Coating, 12 Raw/Primary).
These are not 213 accepted partials: multiple edges can be unknown per partial,
and rejected candidates also contribute edge queries. R2 evidence does not
persist per-query depth/reasons, so a real unchanged-R2 targeted replay is used
to supply them rather than inventing a breakdown.

Only observational monkeypatches are applied in an external analysis runner;
no authoritative predicate, probe cap, anchor, schedule or placement order changes.
Primary reason is probe exhaustion when the measured dynamic-origin/pair count
reaches the frozen 256 cap; otherwise it is incomplete dynamic witness coverage.
Static fixed-endpoint index misses are orthogonal flags, not negative proofs.
Multi-fixed-neighbor constraints are separately marked. Shared-role or component
joint contradictions were not tested by R2 and cannot be retrospectively claimed
as demonstrated causes of those UNKNOWN results.

The real unchanged-R2 replay reproduced every committed placement field exactly
(1 complete candidate, 50,260 nodes, 11 attempts). Measured primary UNKNOWN
reasons: 346 POSITIVE_PROBE_CAP_EXHAUSTED and 8 DYNAMIC_ORIGIN_DOMAIN_INCOMPLETE.
28 queries had one fixed endpoint; 326 had neither endpoint fixed. Orthogonal
static-domain misses: 24; fixed-endpoint multi-neighbor cases: 0. Depths 1–6:
7 / 11 / 11 / 266 / 22 / 37. Composition totals, banks combined:
LINEAR X-negative 106, CENTRAL X-negative 18, SPINE X-negative 158;
LINEAR Y-positive 2, CENTRAL Y-positive 12, SPINE Y-positive 58.
These explain checker uncertainty, not engineering infeasibility.

## Proof contract and scope

ADR-050 distinguishes pairwise positive facts, shared-variable compatibility,
and a complete assignment to a connected HARD component. Only the last discharges
joint capacity. Every role has one authority shape and rectangle. Each actual
edge, all component overlaps, all fixed blockers, physical authority and current
composition intent are checked together. No site-exact full-12-room claim follows.

Natural joins of existing positives are attempted only when common variables
agree, followed by complete hard revalidation. Otherwise bounded deterministic
shared-variable witness construction uses existing dynamic origins and necessary
multi-neighbor interval intersections. Every query failure/exhaustion is UNKNOWN.
Allowed negatives are freshly checked R2 necessary-origin-space proofs, minimum
component area exceeding the site bounding-box area, or an empty conservative
MUST arc projection over all integer origins for canonical footprints. Arc
projection enlarges neighbor spaces and discards the negative attempt on resource
guards. All proofs bind actual placed geometry; speculative branch failures never
authorize pruning.

Joint witnesses are advisory proof objects, not hard reservations or new placement
seeds. The ordinary R2 pairwise support hints and normal fallback remain unchanged.
Immutable states and positive-only fresh revalidation protect backtracking.
All state stays runtime-only; Plan/Handoff/P2 schemas and results are frozen.

Schema audit: no new public placement input or Plan/Handoff/P2 field is added.
Joint state is internal; only existing open-ended search diagnostics gain fields.
The old accepted-UNKNOWN counter now explicitly means component UNKNOWN; a new
`accepted_partial_with_pairwise_unknown` preserves the separately named R2 metric.
Repository consumers are diagnostic/evidence tests, not external strict contracts.
Historical evidence is immutable. Reservation references are the unique P1
source-edge identities, bound to the exact handoff through authority provenance.

## Acceptance reporting

Canonical replay, UNKNOWN before/after, certificate coverage, tests and exact-head
CI are recorded in the evidence and final handoff when completed. Pending stages
are not PASS. If any accepted partial lacks a connected-component certificate,
the result remains PARTIAL and P3_COMPLETE=false even with a complete candidate.
If no complete candidate is produced, business result is FAIL.

No standalone canonical Access/Truck/P2D acceptance, Ready, Merge, force push,
tag, release, deployment or subsequent phase is authorized. Existing CI tests
are reported separately from new business authorization.

## Validation development record

The initial integrated focused run found a legacy mock graph without identity;
its fixture now supplies explicit graph provenance. Root joint impossibility is
also checked before recursion, and recorded as a prune. The existing zero-capacity
test still requires a real negative proof, but accepts the stronger root joint
area proof as well as the older placed-endpoint proof. No hard predicate or
negative-safety assertion was removed.

A wrong architecture-test filename caused one collection-only failure. One
runner launch lacked PYTHONPATH and failed before execution. Three early local
capture attempts were explicitly interrupted during static-domain construction
to finalize root-gate accounting and its typing; none are acceptance evidence.
Final focused rerun: 35 passed. Mypy: 404 source files pass. Ruff check and normal
repository-discovery format check pass (914 files). A wider explicit src/tests
format check additionally discovered two pre-existing excluded pilot files;
they are not reformatted or changed.

The new independent integer-exhaustion fixture also checks a four-role MUST
chain with actual fixed endpoints: an empty relaxed arc space has no reference
witness, while feasible endpoint controls never receive an erroneous negative.
The R2 static-miss regression now separately asserts that its pairwise UNKNOWN
is preserved and that R3 recovers a verified joint certificate; it still checks
normal recursion, no capacity prune, and the unchanged lack of a complete result.
This diagnostic distinction is intentional, not UNKNOWN relabeling.

Full architecture suite initially reported 765 passed / 1 environment failure /
16 skipped because a nested `python3` resolved outside the virtual environment.
After putting the locked environment on PATH, the unchanged suite passed:
766 passed / 16 skipped. No architecture assertion was bypassed.

Reproduction helpers are committed under `backend/tests/evaluation/` (explicit
force-add is needed because this directory is ignored). Run
`v222_p1a_r2_unknown_attribution.py` against a separate exact R2 checkout to
produce the baseline input; then run `v222_p1a_joint_metric_capacity_r3_evidence.py`
against R3 with `PYTHONPATH=src:.`, `--baseline-audit`, `--output`, and
`--regressions`. No baseline geometry becomes a production seed.

## Canonical observations

The observations below initially came from two fully matching pre-delivery
captures. A positive state's reason annotation still used the probe's default
unproven label even when its certificate verified. The annotation is corrected
to JOINT_WITNESS_VERIFIED and explicitly regression-tested; no support decision
or geometry predicate changes. That exploratory capture was stopped during P2
replay, and fresh final-code captures replace its evidence. To avoid serially
duplicating long domain builds, the final evidence runner runs an independent
public P2 invocation in a separate process alongside placement. It shares no
runtime cache and does not modify any production scheduler or query budget.

The first full R3 replay retains one complete candidate, 50,260 placement nodes,
11 attempts, and the R2 candidate hash
`sha256:554e77dd6e5b0da7bdecb97558bc4f16a8b1bd5c073ff18b080714a6462375ab`.
Every final HARD edge has a direct certificate, and the complete HARD component
also has one common geometry assignment. All final claims are construction-hard,
not Access/Truck/P2D acceptance.

An additional exact comparison independently confirmed all 12 role/bounds pairs
from the live unchanged-R2 START replay equal the historical control used for
the 13-prefix check (`LIVE_R2_START_CONTROL_GEOMETRY_MATCH=true`). Thus that
prefix regression is for the real START candidate geometry, not a different
historical sample. The geometry is used only as an audit/test input.

R3 does **not** meet the zero-UNKNOWN business gate. Across 317 accepted partials,
52 have a component certificate and 265 remain joint UNKNOWN. The old pairwise
metric is retained separately: 243 accepted partials have a pairwise UNKNOWN.
R2's 213 unknown accepted partials and R3's 265 joint-unknown partials are different
proof scopes and different explored partial sets, not evidence of convergence.
Sound joint negatives alter earlier backtracking while allocated/visited nodes
and the eventual complete candidate happen to remain unchanged.

Across root/child joint queries: 866 assessments = 53 SUPPORTED + 538 covered
negative proofs + 275 UNKNOWN (10 root, 265 accepted child). All 53 positives are
independently rechecked with the exact site, hard-obstacle, overlap, shared-edge
and composition predicates; all 538 negatives are regenerated by the proof
verifier. This is not an independent exhaustive canonical geometric oracle;
independent exhaustive reference comparisons are limited to the small fixtures.
UNKNOWN reasons: 216 positive-probe-cap exhaustion and 59 joint assignment
unproven. There is no UNKNOWN-to-positive conversion without a certificate.
Only two Coating/Finished pairwise-UNKNOWN queries gain a joint certificate.
673 witness disagreements are observed proposals, **not** proofs of infeasibility.

Joint query work: 51,025 candidate evaluations, 168,628 origin events,
4,536,004 necessary arc intersections. 308 necessary-space resource guards
discard that negative attempt (they do not prune). Per-edge joint counters
repeat common component work for provenance and must not be summed as seven
independent searches. Cold replay: 1,383.33 s; static domain build 1,055.59 s;
joint queries 80.86 s; peak process RSS 351,944,704 bytes. Warm replay, P2 parity,
full regressions and exact-head CI must be completed before delivery closure.

`positive_certificates` counts verified positive assessment events, including
rebindings/reuse. The lower `certificates_created` diagnostic counts initial
positive-cache creation with no old certificate; it is not a count of every
new immutable certificate object or unique digest. Likewise overlap, fixed-
neighbor and intent conflict counters count rejected witness proposals, not
proved component infeasibility. Final performance timings must be interpreted
with the independent P2 process running concurrently during the cold build.
The observational verifier regenerates each negative proof once more and that
necessary-arc work is included in the query ledger; it changes no support status,
candidate ordering or placement node. Joint-query timers stop before the extra
observer verification, while total replay timers include it. These audited
timings/counters are not a zero-overhead standalone production benchmark.

Pending final validation does not change the business classification:
`RESULT=PARTIAL`, `P3_COMPLETE=false`,
`JOINT_UNPLACED_ROLE_CAPACITY_PROVEN=false`.

## Proof-test coverage

All cases below are in `test_v222_p1a_joint_metric_capacity_r3.py` and pass.
P0/P1/P2/R1, existing conditional-support and placement tests are separate
regressions, not replaced by these fixtures.

| Obligation | Independent fixture / assertion |
| --- | --- |
| Shared-role certificate and identity | One rectangle per role, all edges revalidated |
| Pairwise support is not joint proof | Individually positive conflicting common variables yield UNKNOWN |
| Connected component and graph extension | Added edge extends scope; disconnected components remain separately scoped |
| Unrelated blocker | Covered negative binds actual fixed blocker |
| Domain revision and backtracking | Parent immutable; sibling revalidated; stale identities rejected |
| UNKNOWN never pruned | Zero positive-probe cap cannot invent a negative |
| Non-static actual final pair | Actual common assignment certifies outside static origins |
| Negative soundness | Independent integer enumeration never finds a rejected valid assignment |
| No role-specific recovery | Generic source has no Office/Shipping branch or static-exclusive domain |
| Joint area contradiction | Three rooms cannot fit a two-cell site despite pairwise positives |
| Non-neighbor overlap | Joining edge facts cannot certify overlapping non-neighbors |
| Relaxed MUST arc contradiction | Exhaustive fixed-endpoint controls check empty-arc soundness |
| Authority and event revision | Forged graph/edge/authority/partial identities fail; changed revision revalidates |
| Positive cache migration | A child uses another witness without changing parent or sibling proof |

## Final-code replay closure

Both actual final-code canonical replays match in their complete placement bodies
and observed joint-query sequence. Comparison digest:
`sha256:5270689b6816f85de19168274273058bb1cd6e9bb81cb6809bf67675f9da49ec`.
The final proof annotations now distinguish verified witnesses from UNKNOWN.
Candidate, node, attempt, accepted-UNKNOWN and certificate counts remain as above.
Every one of the 538 joint negatives has reason EMPTY_RELAXED_MUST_ARC_SPACE.

| Measurement | Cold final-code replay | Warm final-code replay |
| --- | ---: | ---: |
| Total audited seconds | 1553.294 | 321.428 |
| Static runtime build seconds | 1223.355 | 0.0177 |
| Unique runtime domain builds | 7 | 0 |
| Joint query seconds (excluding extra observer verification) | 82.061 | 79.571 |
| Peak process RSS bytes | 336658432 | 336658432 |

The independent public P2 process completed in 1228.332 s, peak RSS 146407424
bytes. Its 6 compositions / 42 realizations exactly retain public result hash
`sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`.
All seven runtime count/digest comparisons pass; total valid slots 642,482.
There is one fresh public P2 invocation, matching the previously deterministic
frozen public result; the two fresh full replays in this task are placement.

The real START control passes all 13 prefix checks without erroneous NONE.
The empty prefix remains joint UNKNOWN; depths 1–12 all have a component
certificate, including the two depths whose pairwise Coating/Finished check
remains UNKNOWN. The complete control has 7 direct final certificates and a
verified common assignment for its 8-role connected HARD component.

This is subset proof progress, not zero-UNKNOWN acceptance. R3 remains PARTIAL,
P3_COMPLETE=false. Existing regression completion and exact-head CI are separate
delivery gates and cannot upgrade that business result.

Related regressions completed: **238 passed**, covering P0/P1/P2/R1, composition
placement and architecture boundaries. The unchanged candidate-validation file
is deliberately not invoked as standalone local Access/Truck/P2D acceptance;
normal exact-head CI retains its full existing integration-test scope.
Final evidence size: 343,993 bytes, not a persisted runtime slot domain.

### UNKNOWN comparison (different proof layers are explicit)

Edge counts below are pairwise query events, including candidates later pruned.
They are not accepted-partial counts. Joint UNKNOWN covers the entire component,
so attributing its 275 events independently to each of seven edges would be wrong.

| HARD edge | R2 pairwise UNKNOWN | R3 pairwise UNKNOWN |
| --- | ---: | ---: |
| Raw / Primary | 12 | 12 |
| Primary / Sorting | 0 | 0 |
| Sorting / Secondary precooling | 0 | 0 |
| Secondary precooling / Coating | 30 | 66 |
| Coating / Finished | 195 | 762 |
| Finished / Shipping | 75 | 250 |
| Office / Shipping | 42 | 1115 |

Banks combined; composition query counts and joint-unknown accepted partials
have explicitly different scopes:

| Composition | R2 pairwise UNKNOWN queries | R3 pairwise UNKNOWN queries | R3 accepted joint UNKNOWN |
| --- | ---: | ---: | ---: |
| LINEAR X-negative r0 | 106 | 662 | 106 |
| CENTRAL X-negative r0 | 18 | 78 | 10 |
| SPINE X-negative r0 | 158 | 216 | 101 |
| LINEAR Y-positive r1 | 2 | 2 | 0 |
| CENTRAL Y-positive r1 | 12 | 12 | 10 |
| SPINE Y-positive r1 | 58 | 1235 | 38 |

### Full actual placement attempts

All attempts retain the frozen scheduler and 5,000-node allocation. Total visited
nodes = 10 × 5,000 + 260 = 50,260. Propagation work is separately counted.

| # | Family / variant | Bank | Nodes visited | Max placed | Reservation prunes | Accepted joint UNKNOWN | Complete |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LINEAR X-negative r0 | 1 | 5000 | 6 | 45 | 36 | no |
| 2 | CENTRAL X-negative r0 | 1 | 5000 | 5 | 10 | 5 | no |
| 3 | SPINE X-negative r0 | 1 | 5000 | 5 | 284 | 9 | no |
| 4 | LINEAR X-negative r0 | -1 | 5000 | 4 | 457 | 70 | no |
| 5 | CENTRAL X-negative r0 | -1 | 5000 | 5 | 10 | 5 | no |
| 6 | SPINE X-negative r0 | -1 | 5000 | 4 | 32 | 92 | no |
| 7 | LINEAR Y-positive r1 | 1 | 260 | 12 | 2 | 0 | yes |
| 8 | CENTRAL Y-positive r1 | 1 | 5000 | 5 | 0 | 5 | no |
| 9 | SPINE Y-positive r1 | 1 | 5000 | 6 | 197 | 33 | no |
| 10 | CENTRAL Y-positive r1 | -1 | 5000 | 5 | 0 | 5 | no |
| 11 | SPINE Y-positive r1 | -1 | 5000 | 5 | 952 | 5 | no |

Exact-head CI and literal containing commit are recorded in the PR delivery
closure and Owner report, avoiding a self-referential evidence commit hash.
Historical original P3 failures and R2 PARTIAL/CI records remain in PR #307.

Final focused rerun: **38 passed** (including 14 new joint-proof unit cases).
Full final-source architecture rerun: **766 passed, 16 skipped**. Related full
regressions: **238 passed**. Ruff/normal-discovery format, explicit evaluation
runner lint/format, mypy (404 source files) and diff whitespace checks all pass.
The two evaluation runners are explicitly included despite the pre-existing
ignore rule; no .gitignore or CI scope is changed.
