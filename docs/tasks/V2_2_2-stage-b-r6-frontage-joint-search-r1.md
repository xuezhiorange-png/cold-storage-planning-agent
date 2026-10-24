# R6 functional frontage, physical hints and independent search frontier

Task: `V2_2_2_STAGE_B_R6_FRONTAGE_JOINT_SEARCH_R1`.
Base: `f38f98c3a36346bc0837939558ee2d9936b5687b` (PR #311, unchanged).
This is an independent optional strategy, with synthetic Native tests only.
No frozen 20t MAIN, real Grant/Claim or formal CI is requested by this change.

## Implementation and activation boundary

`StageBFrontageJointSearchFairSolver` in
`stage_b_frontage_joint_search.py` extends the existing R5 solver. Its optional
final-model factory, decision prefix, hint hook and validated-feedback hook are
the only R6 activation paths. R5 keeps its existing full-scan preparation,
full-assignment hints, twelve-metric Pareto rule and policy identity. Production
bootstrap and all real execution scripts are unchanged.

| Policy | Hash |
| --- | --- |
| Existing R5 combined | `sha256:ddccb804958e52c169ad1d1c0c2c6ecc259271e350e23207dba0b1a5e71db0a4` |
| R6 reference preparation | `sha256:31d228d6995aa7d2d71fd5a5fe740868aecda89b2526ff88081efb41f4fb80df` |
| R6 frontage decision prefix | `sha256:ac9ce2d9b8f6d196705c12f91d28bb113b31ab31eebb4cf79aa319a030e38923` |
| R6 combined | `sha256:5584fd5bb8a833905bc0f441bcdc1da8d9876f619d75b7d9fd948c843a2fd95d` |

The inherited bound-policy check rejects missing, R5 and older policy identities.
There is no R6 real runner or new authorization system here. A later separately
authorized experiment would need its own task/Owner/Grant/Claim/ledger binding
and exact-head formal CI; existing consumed slots cannot activate this strategy.
This PR creates none of those execution credentials.

## Reference preparation: replace repeated reads, preserve the arithmetic

`ReferenceCpModel` records supplied interval bounds once at variable creation
and maintains the original global magnitude bound. It does not build a global
name index. `apply_reference_area_guidance` uses the six existing
`model.rooms[role][w/d]` references, checks their ownership, original index/name,
positive domain, P1 area source and unchanged interval, then reuses R5's exact
P1 rounding, global/derived int64 checks and total proxy definitions. The whole
27-definition/13-creation-record batch is admitted before model mutation.

Native-created unnamed constants are read only from the unrecorded tail. Their
real reads and creation facts are charged. Duplicated reserved names, unsupported
creation paths, cloned/copied metadata, foreign references, wrong ledger and
selected-domain changes fail closed. The supported construction contract is the
private source-owned append-only AccessModel builder. Six field checks cannot
detect arbitrary edits to unrelated auxiliary proto domains: raw-proto domain
rewrites by callers are unsupported, rather than presented as a tamper-proof
certificate. Full CP-SAT model validation remains in the original execution path.

The shared extraction of `_area_specs`, `_define_area_proxy` and `_area_receipt`
does not change the R5 arithmetic or its charge labels. The six complete Handoff
models match the untouched base source exactly for variables, domains, indices,
constraints and objective. R6 adds only decision strategies after that point.

## Physical hints and two independent states

`install_physical_hint` reads current accepted room x/y/physical w/d, Packaging
case and selected portal, active route points/faces or selected direct portal.
It omits unrelated auxiliaries and definitional values. Reference discovery,
selector reads and actual hint writes are all charged. The values are read
before clearing previous hints, so a budget failure cannot partially replace
them. Hints originate from the current model's accepted invocation, never from
historical coordinates. They are soft hints and introduce no constraint or Solve.

The initial independently accepted baseline is retained. Formal quality and
formal hint updates still use the exact original twelve-metric comparison.
Separately, accepted geometry may lower the monotone integer search-proxy
frontier even if it is a formal Tradeoff. The continuation checks the same model,
solver value and ledger before changing this scalar callback threshold. Equal
proxy values, invalid topology, engineering rejection and UNKNOWN never advance
it. A search-frontier event explicitly does not claim formal quality improvement.
The additional nine physical-fact reads and maximum reduction are charged as
10 Work per accepted snapshot; applying a changed frontier costs one further Work.

For example, sealed R5 proposal 01→02 reduces the proxy 5772→5469, but increases
Coating area by **0.000714 m²**. It remains nine-metric Pareto / twelve-metric
Tradeoff. R6 can acknowledge that accepted proxy progress without promoting it
to twelve-metric Pareto or replacing the original baseline. The unchanged
comparison functions recompute the sealed original decisions exactly.

## Joint frontage/seam search without new engineering rules

`apply_frontage_joint_search` places a deterministic prefix on existing Boolean
choices, before the existing generic corridor strategy:

1. Try the Changing ingress face toward the actual boundary personnel entrance.
2. For existing Changing→Sorting, Secondary→Coating and Coating→Finished Access
   requirements, try existing direct/domain-side choices before other legal cases.
3. Try the existing Packaging→Sorting direct interface and Authority-supported side.
4. Coordinate existing process MUST literals and portal offsets. Office uses only
   its existing Office↔Shipping MUST; no Office door/Access Authority is invented.

The shape objective remains R5's P1-normalized maximum semiperimeter-square
proxy. There are no new weights, width/area/aspect limits, historical coordinates,
Native calls or budgets. The prefix is a search preference, not a predicted
engineering result. CP-SAT automatic search/presolve may behave differently from
the fixed-search synthetic witness used to demonstrate the prefix.

The original exact union-input cut, single-connectivity/zero-hole test,
Footprint/Site, MUST, Access and Packaging validators remain unchanged. The
shared model edits expose already-created literals; they add no CP variables or
constraints. R3 whole-Work admission and all existing resource guards are untouched.

## Measured preparation and hint cost

Three fixed paired construction measurements on the same complete LINEAR_BANDED
Y-positive model include the final-model builder, all reference bookkeeping,
inactive-route normalization, R6 prefix and unchanged area definitions. Input
binding and the equally performed final model validation are outside the timing.
Every result has 27,400 variables / 38,760 constraints. No Native Solve was run.

| Measure | Original R5 | R6 |
| --- | ---: | ---: |
| Final-model build + preparation Work | 104,383 | 49,975 |
| Paired wall-time samples, seconds | 0.268563 / 0.258436 / 0.260091 | 0.325704 / 0.315208 / 0.320074 |
| Wall-time median, seconds | 0.260091 | 0.320074 |
| Full proto name/domain scan | 27,387 variables | none |
| New creation facts, including proxy vars | none | 27,400 |
| Physical fact reads | included in global scan | 21 |
| Frontage reference reads / decision writes | none | 166 / 166 |

Work falls because the repeated name/bounds scan and name index are removed,
not because the same scan receives a cheaper coefficient. The new real
creation-record updates are included. **Preparation wall time increases by about
60 ms in this measurement** because Python creation/ledger hooks add overhead.
This establishes fewer charged preparation operations, not a CPU latency win.

On the same tiny physical model with 1,000 unused auxiliary variables and a real
synthetic accepted CP-SAT assignment, full hints write 1,007 values (Work 1,007;
5.98 ms). R6 writes 7 deduplicated physical values (12 reference reads + 7 writes,
Work 19; 0.073 ms). This is one local hint measurement, not real factory timing.

The four original warmup phases and three base-model clones are retained. A
construction-only observation found a 600-variable base model, three clones of
roughly 0.22–0.33 ms each, and an Access hint-model build of 22,192 Work / 0.191 s.
Their Native cost was not remeasured. Removing warmups or their independent
constraint/validation paths is not justified by this evidence. Original clone
accounting is unchanged; no fictitious clone saving is claimed.

## Offline and synthetic evidence

All 14 sealed R2/R4/R5 candidate files and original SVGs were read back by SHA256.
Their recomputed snapshots, geometric topology and formal comparisons agree.
All four original hole witnesses remain invalid (hole counts 2, 2, 1, 2).
The old R2 Work=600003 remains a historical overrun. No evidence is rewritten.
223 source-file hashes and 60 historical registry-file hashes were checked.
Primitive topology scan counts depend on rectangle iteration order; the offline
comparison checks every topology geometry field and does not replace historical
Work values with a recount.

An exhaustive six-variable domain retains all **729** physical assignments with
one exact definitional extension each. Construction comparison against the base
source covers all six complete Handoffs without solving them. These tests and
unchanged hard constraints support domain preservation; they do not claim an
exhaustive enumeration of the full plant domain.

The eight-room synthetic scene uses native portals, MUST contacts, route
envelopes, room/site separation and exact union checks. Both alternatives remain
feasible. With identical one-worker/seed-3/fixed-search/no-presolve/2-second
test-only settings, original order chooses the north Changing portal (12 m,
3 turns); R6 chooses the east portal (9 m, 2 turns). Proxy stays 1125, and both
unions are connected with zero holes. This demonstrates an actual portal/path
choice difference, not a real factory quality or efficiency improvement.

[Actual synthetic layout comparison](../previews/v2.2.2/stage-b-r6-frontage-joint-search-r1/synthetic-layout-comparison.svg)

Local raw measurements, readback, JUnit and PNG preview live in
`artifacts/stage-b-r6-frontage-joint-search-r1/` in the local evidence workspace.
Private historical candidate coordinates/Owner records are not added to Git.

## Verification and stopping boundary

The focused R6 suite covers domain/overflow/ownership failures, whole-batch Work
admission, physical hints, frontier/Tradeoff separation, UNKNOWN and baseline
retention, same model/ledger, old-policy rejection, deterministic native synthetic
choices and all six model constructions. Existing R5, balanced, fair-search,
enumeration, resource, architecture, partition and CI contract regressions run
alongside it. Linux physical RSS is explicitly excluded on macOS and recorded
`NOT_RUN_ENVIRONMENT_SPECIFIC`; it is not counted as a local PASS.

Local results: fast-workflow test selection 615 PASS / 1 Linux-RSS deselected;
additional fair/enumeration/worker regression 116 PASS / 2 Linux-RSS deselected;
architecture plus selected partition contracts 778 PASS / 16 existing skips;
CI contracts 64 PASS. The final R6 suite separately passed all 53 cases after
the explicit frontier-fact accounting check. Ruff, Format, Mypy and diff checks
pass. An initial architecture subprocess used system Python without pytest;
the unchanged tests pass with the existing test virtual environment on PATH.

Only automatic fast CI is requested. Formal full CI, real MAIN, Grant/Claim,
production activation, Ready/Merge and deployment remain outside this task.
