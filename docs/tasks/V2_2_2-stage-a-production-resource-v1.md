# Stage A CP-SAT production execution resource contract V1

Owner task: `V2_2_2_STAGE_A_FINAL_PRODUCTION_CLOSURE_R2`.
Policy: `V2_2_2_STAGE_A_CP_SAT_PRODUCTION_RESOURCE_V1`.
This approves the controlled source entry, not the public/default selector.

## Ceilings and scopes

* Formal request ceiling: 100 cumulative native solver seconds. Warmups,
  topology screening/refinement and final solve all share it; individual native
  calls never allocate another budget.
* This acceptance uses a stricter predeclared 90 seconds per replay, one worker
  and the existing fixed seed configuration. At most two NEW main invocations
  share 180 cumulative solver seconds and 1,200,000 original observable work.
* Existing per-request experiment wall protection 180 seconds, process memory
  protection 512 MiB, and per-requirement Host protection 20,000 remain intact.
* Original numerical contracts stay placement 60,000, Access 20,000, Truck
  20,000, joint evaluation 256, origin events 1,024, joint work 8,192.

## Executable accounting (not a new unit)

The work gate uses the existing `StageALedger.guard` counter expression,
`model_work + native_host_work`, without changing its increments. `charge`
retains explicit model construction/interval geometry events and multiplicities;
`observe_native` retains the original selected Domain-call primitive counter.
The same expression is accumulated across the task's requests, with both
components separately exposed. CP-SAT branches, conflicts, wall time and
deterministic time are **not** added to this counter or converted to DFS nodes.
The original 20,000 requirement Host counter and actual route-grid BFS visited
nodes remain separate. This does not measure all Python CPU operations.

Every native call's imposed deadline is bounded by its existing phase limit,
remaining request/replay allowance and remaining task allowance. A monotonic
timer covers the actual native invocation; both elapsed and solver-native wall
are saved, and the greater is charged. Native deterministic time, branches,
conflicts, status and call ordinal are recorded without redefining their units.
Existing construction/Host checks stop before downstream acceptance when limits
are exceeded. External worker supervision retains the existing wall/RSS limits.

## Identity, durability and interruption

Trusted bootstrap pins the Owner instruction SHA256 and task identity. Approval
binds exact source/dependency/input/P1/Site/composition/solver identities. A
durable task slot, exclusive allocation claims and active lock prevent output
directories or new UUIDs granting allowance. A second NEW requires the first
request to have completed; a third is denied. Source changes invalidate admission.

Native STARTED marks accounting incomplete before the solver starts. RETURNED
saves all counters. Unknown interrupted consumption is never zero; NEW/RESUME
remain denied. A verified PAUSED checkpoint restores elapsed/work/native usage
without refill. Legacy R16/C1 continuation stays denied. Filesystem administrators
remain outside the local in-process trust model.

The two real replays must match actual engineering geometry, authority and
native application outputs; timing and execution identities are not geometry.
All commit/push gates, D04 history, P3 UNKNOWN262, Truck/P2D and deployment
restrictions remain unchanged. No resource approval extends to another service.
