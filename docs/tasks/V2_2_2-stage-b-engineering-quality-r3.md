# R3 Work precharge and validated quality guidance

Base: `9c13a134b6008c8960996eedf016dc2b4754a013`.
Task: `V2_2_2_STAGE_B_ENGINEERING_QUALITY_R3`.

## Sealed R2 evidence

The last resource journal entries show model Work 406892 and Native Host Work
193109: 600001 at `NATIVE_OBSERVER_FINISHED`. The Native primitive counter had
been incremented before checking the existing pool ceiling. During unwinding,
`NATIVE_ENVELOPE_COVERAGE_CELL` and `STAGE_B_ENUMERATION_AUDIT_RECORD` each added
one model Work before failing their guards. Final Work was 600003. This is three
rejected charges recorded as consumption, not one legitimate three-unit operation.
The original experiment remains resource-noncompliant; its ledger, Claim, SVGs and
certificates are immutable and are not published with this change.

R2 retained two engineering-valid baselines and four improvement geometries.
The extreme Changing room improved only from 40942/977 to 20471/489, while
perimeter increased 20.1m, outline turns increased two and reflex corners one.
The original nine-metric comparator correctly classified it as a tradeoff.
Another Handoff's first continuation was a genuine local geometric Pareto
improvement. Two subsequent proposals had worse Minimax proxies than that already
accepted proposal, yet the callback still compared against the original baseline.
Both sealed hole-rejection events occurred in the feasibility stage and remained
correctly rejected; the previously observed 16.583 by 2.423m Changing witness was
not an independently accepted building and cannot be promoted to a trusted hint.

## Resource correction

`StageALedger.precharge_work` checks the entire integer nonnegative charge before
changing model counters or event totals. Native primitives use the same admission
before incrementing the requirement or global Native Host counters, and before
entering the primitive body. Rejection changes no Work counter and needs no
rollback, clamping, reset or new allowance. Existing RSS/time guards still run.

The original Pool lease checks its 600000 local allowance and 1200000 shared
allowance prospectively. Dynamic shared totals include other pools/AB arms.
The production replay lease also checks previously consumed task Work before
admitting a charge. No budget constants, Owner digests or engineering rules change.
These checks also cover cleanup and audit charges after a resource interruption.

## Minimal evidence-supported search change

Only balanced second-stage continuation has an additional optional feedback hook.
After application engineering acceptance, the unchanged exact nine-metric
comparator must establish Pareto improvement over the current guidance incumbent,
with the same Handoff, V2 organization and Authority. Only then may the stream
refresh partial physical/union-input hints from its current solver assignment and
advance the callback proxy reference to that validated incumbent. No historical
coordinates, external Seed, unvalidated witness or tradeoff can replace it.

The original baseline and the baseline-relative reporting comparison remain
unchanged. Hints are soft; they add no constraints and do not replace the existing
accepted-geometry cut. The first phase, Minimax objective, shape definitions,
topology oracle and exact hole-witness cuts are unchanged. No new score weights,
room width or aspect threshold are introduced. Hint preparation is itself charged
as a batch before any hint/reference mutation.

This prevents a witness worse than an already known Pareto incumbent from causing
an early callback stop merely because it beats the original baseline. It does
not prove that a much better Changing geometry can be found. In particular, the
first strict proxy gain can still be millimetric. There is no evidence-backed
minimum meaningful aspect gain or safe neighborhood of the rejected witness to
encode. Those broader changes remain unsupported in this task.

A stronger incumbent reference can delay the next callback or exhaust the same
remaining allowance if no further gain is found. CP-SAT learning is not retained
across Solve calls. The existing accepted-geometry cut still excludes the exact
hinted geometry, so CP-SAT must repair the soft hint; that can cost additional work.
No real efficiency improvement or room-fit acceptance is
claimed without a separately authorized experiment. Unknown still ends the stream;
it is not infeasibility and receives no new retry policy or cut.

## Policy identity and validation

Balanced policy: `sha256:3b4e5a23d95238aaa71d21920270469dc317d5dc965b5b13690ad5545f436c0f`.
Feedback policy: `sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2`.
Shape policy remains `sha256:4f03968760711b1ab090fbcabc2d45ea367428065ec23a47d6986671b7c3ddb0`.
Comparator remains `same-handoff-exact-nine-metric-pareto@1.0.0`.

Tests cover atomic batch refusal, exact boundaries, Native primitive entry,
cleanup/audit refusal, cumulative pool/task budgets, negative/non-integer charges,
baseline preservation, unusable evidence, tradeoffs, soft-hint-only changes,
charged hint failure, accepted-feedback ordering and old R2 policy rejection.
Existing 729 physical-assignment parity, topology, UNKNOWN and resource tests are
retained. Tests use temporary registries and tiny synthetic models, never the
consumed production registry or a factory MAIN.

Only fast CI is requested. Formal CI and real MAIN are not authorized here.
No consumed authorization, Claim or resource allowance is reusable. PR307 and
PR308 source heads remain untouched; this work is delivered on an independent
Draft branch based on the requested baseline.
