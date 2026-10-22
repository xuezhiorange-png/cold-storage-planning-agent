# Stage B balanced Native quanta R2

Scope: opt-in balanced continuation only; no real MAIN, grant, replay, full-CI
request, production default, engineering authority or resource-limit change.

## Scheduling

`_BalancedNative._run` changes only calls for which `improving` is true and
`phase == ALL_ROOMS_ALL_ACCESS`. Before delegating to the original guarded
solver, the requested seconds become:

```
min(2.0, min(requested_seconds, remaining_handoff_native,
             remaining_handoff_elapsed, remaining_global_native) / 2)
```

Two seconds is a versioned experimental search cap, not a measured optimal
quantum or an engineering standard. The half-remaining rule avoids handing the
entire remaining allowance to the last slice. Actual CP-SAT termination and
host work have overhead: the cap is not a promise of exact wall-clock timing.
Existing cumulative guards remain authoritative before and after every solve.
Work is not converted into guessed seconds: original Work/checked/RSS/call
guards and shared Handoff limits still apply, without allocation or refill.

`_BalancedNative.begin_improvement` records the quanta policy in the existing
transition receipt. No new execution or authorization framework is introduced.
First-stage solving, warmups, hint construction, Minimax objective and exact
nine-metric Pareto comparison are unchanged.

## Feedback and status semantics

The original iterator is unchanged. FEASIBLE and OPTIMAL supply a witness to
the same independent geometry, union topology, footprint/site and application
validators; neither status alone proves engineering validity or global quality
optimality. An invalid topology receives the original exact exported-witness
cut on the same CpModel. A subsequent bounded solve is possible only while the
original share and all guards permit it. No room-dimension-wide cut is added.

UNKNOWN without a witness ends the current stream as UNKNOWN, with no cut,
infeasibility claim or automatic retry. Short slices can therefore reduce the
chance of obtaining any improving witness. Resource exhaustion retains the
persisted first-stage baseline; it does not prove infeasibility. Existing
checked-assignment and call limits remain finite, including for repeated cuts.

## Restart cost and validation limits

Each Solve creates a new CpSolver. Learned search state is **not** retained;
model constraints, hints and exact cuts are retained. Distinct active portal
witnesses can share the same invalid room geometry and legitimately require
separate cuts. Identical forbidden witness assignments cannot recur.

Tests compare unsliced and sliced scheduling on the same tiny finite hole/open
domain using the actual CP-SAT and union checker. They measure Native calls,
cuts, branches and time, and require no more than two invalid portal witnesses
plus one valid solve, with only one final model preparation. Separate protocol
tests check UNKNOWN terminates without retries, baseline preservation, unchanged
status handling, and decreasing cumulative remaining allowances.

This establishes bounded mechanics and detects redundant restarts in that
finite test domain, **not** factory-scale throughput parity. Repeated presolve
and lost learning may outweigh earlier feedback in larger models; real-layout
candidate efficiency and quality remain NOT_EVALUATED. Any real experiment
needs separate authorization and must compare valid candidates per cumulative
Native/Work budget, not merely shorter individual calls.

## Source and authorization binding

Balanced continuation is versioned to `@2.0.0`; its policy hash includes the
new quanta policy hash. The shape objective hash and comparator stay unchanged.
Policy hash: `sha256:c1aed0b63d610538ce0c66f3e6bf88e9811d7f6d7f350b9d77c38e7aa2db6911`.
Quanta hash: `sha256:98e1c9b47eafdc37c0e7d31b49380d8e13283605334a25de21e259bb8479b531`.
An R1 policy binding cannot authorize R2. Historical evidence, consumed slots,
Owner instruction hashes and Grant/Claim ledgers are not migrated or reset.

The existing R1 runner is not rearmed by this development. A future R2 real
execution requires separately approved fresh execution identity/wiring and
Owner instruction/policy/source/dependency bindings, plus exact-head formal CI
and the original one-use Grant/Claim mechanism. Fast CI is not formal MAIN
admission. No such execution authorization is created or consumed here.
