# Balanced feedback correction R2

Optional search orchestration only. No real MAIN, grant, replay, production
default activation, full-CI request or engineering-authority change.

## Mechanism

The fixed two-second/half-remaining slice is removed. The original
FairNativeSolver and cumulative StageALedger again bound each call by the
requested, remaining Handoff, elapsed and global Native allowances.

The shared `_solve_with_feedback` hook defaults to the identical one-argument
`solver.solve(model)` call. First-stage feasibility search, warmups and other
solver implementations receive no callback or extra attempt metadata. The
existing `_run` still owns configuration, admission, exception handling,
counter accumulation, checkpoints and resource guards. The enumeration loop
and all geometry/Access/topology/footprint/site validators are unchanged.

Only `_BalancedNative`'s improvement stage attaches `_FirstImprovingWitness`,
an OR-Tools `CpSolverSolutionCallback`. At transition it captures the original
persisted baseline's worst `ceil(1000 * long_side / short_side)` from the
current solved physical variables. This is the existing Minimax proxy, not a
new score or engineering threshold. It remains fixed for the Handoff; an
invalid or merely examined witness cannot tighten it.

The callback ignores baseline/equal/worse proxies **as stop conditions** and
continues within the SAME Solve. On the first strictly better proxy it calls
normal `stop_search()`. This returns a witness through ordinary accounting and
independent engineering validation, not an accepted layout. Each observation
is charged to existing Work; baseline capture costs six charged observations.
First-solution and feedback wall times, observation count, baseline/proposed
proxy and stop request are recorded in the existing Native attempt. These
timestamps describe search observations, not engineering acceptance times.

## Semantics and failure paths

- FEASIBLE/OPTIMAL/UNKNOWN are the actual OR-Tools return statuses, unmodified.
  A normal stop may return FEASIBLE; a model that genuinely proved optimum may
  return OPTIMAL. Neither proves the exported building is engineering valid.
- Baseline/equal/worse solutions are not cut, hidden or declared infeasible by
  the callback. If no strict proxy gain exists, normal Solve termination can
  still return a non-improving candidate to the original enumeration protocol.
  Proxy ties may conceal small exact-aspect gains; this affects early stopping,
  not admissibility or the unchanged exact nine-metric comparator.
- No feasible witness before the original allowance ends: UNKNOWN remains
  unknown and ends the current stream, without a cut or automatic retry.
- A strict proxy gain with a hole is still rejected. The original exact
  exported-witness cut is added to the SAME CpModel; another Solve is allowed
  only within remaining original resources/checked/call limits. No room-wide
  or aspect-wide exclusion is introduced.
- A callback resource exception takes the original interrupted-Native path:
  history is unverified, no success is fabricated, and no fresh allowance can
  be obtained. No production guard is modified.
- The first independently validated baseline remains saved regardless of
  continuation status, duplicate geometry, topology rejection or exhaustion.

## Risks and validation scope

This removes the artificial two-second deadline before the first useful
witness. It does not guarantee a witness: an original budget can still expire
before any solution or proxy improvement. If no suitable solution appears,
one Solve can still use its original remaining share. The callback is an
event-triggered opportunity, not a promise to reserve time after every solve.

Within a Solve, native learning continues while duplicate/non-improving
incumbents are ignored for stopping. Across separate Solves, learning is NOT
retained; the same model/hints/exact cuts are retained. Restart, callback and
guard overhead remain real costs. There is no new cross-solve learning
dependency or extra budget. Factory-scale efficiency/quality are NOT_EVALUATED.

Synthetic checks include actual single-worker fixed-search callback stopping
at the first gain with FEASIBLE (not a false OPTIMAL); original Minimax on a
tiny finite domain; callback work and single-call Native accounting; no-solution
UNKNOWN; no-gain termination; unchanged first-stage signature; original real
union hole cuts; same-model continuation and baseline protection. The prior
two-second cap is reproduced only in a TEST fixture for comparison. A delayed
three-second-witness scenario uses an explicitly simulated kernel, NOT a
measured real solution latency or evidence of a factory performance gain.

## Identity

Continuation policy is versioned to `@2.1.0` and binds the feedback policy
instead of the old quanta policy. Shape definitions, Minimax objective and
exact geometric Pareto criteria are unchanged. Both old R1 and fixed-quanta
R2 policy bindings are rejected. Historical instruction hashes, consumed
slots, grants and ledgers remain unchanged. Future real execution requires
separate Owner approval, fresh legitimate identity and exact-head formal CI;
automatic fast CI cannot authorize MAIN. This task creates no grant or claim.

Continuation hash: `sha256:201bf90a47095fe6831ca7ea6c41b42c24fc82006cb9683a6508b3ac9d1cb06e`.
Feedback hash: `sha256:78b6566b21568cba14b4f8ef574bb6db30e3d7e381aefbdd6bf0139c8792155e`.
