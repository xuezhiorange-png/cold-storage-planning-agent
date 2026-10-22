# ADR-051: controlled global CP-SAT candidate generation (stage A)

Status: Owner-authorized stage-A scope only; not approval to replace P3.

The existing structural composition application remains authoritative for Plan,
Handoff, role groups and seven interface reservations. The new application
replays those sources and exposes an application-owned solver port. Bootstrap
wires the OR-Tools infrastructure implementation explicitly. No MCP tool or
official selector is switched to it.

The final solver jointly assigns 12 rooms and 11 non-Truck Access geometries.
Fresh invocation-local feasibility warmups may supply hints; historical layout
coordinates and external handoff bodies are not input. Native engineering
validation follows independent interval checks. Unaccepted candidates remain
diagnostic proposals, never selected engineering-valid results.

This is a bounded rectangular-site/five-segment/separate-corridor search domain.
Unsupported geometry fails closed. Finite-model INFEASIBLE and resource UNKNOWN
are not global engineering infeasibility certificates. CP-SAT native work has
no approved conversion into the existing DFS/RS numerical contract. Therefore
the backend remains controlled/internal until that contract is approved.

D01/D03/D04 scope, historical UNKNOWN262, grouping history, recovery-round
preservation and unchanged formal budgets are recorded in
`docs/tasks/V2_2_2-global-cp-sat-stage-a.md`. No broad historical contract
amendment, P3 completion, Truck/P2D acceptance or deployment is implied.

## Approved controlled production execution resource policy

Owner task `V2_2_2_STAGE_A_FINAL_PRODUCTION_CLOSURE_R2` approves the native
resource contract recorded in `docs/tasks/V2_2_2-stage-a-production-resource-v1.md`:
100 solver seconds per request, acceptance replay configuration 90 seconds,
two replays sharing 180 solver seconds and 1,200,000 existing observable work.
This is a native CP-SAT policy, not a conversion from branches to DFS nodes.
The historical NOT_APPROVED records above remain historical; the controlled
source path can use this separate approved lease. No default selector, MCP,
Truck algorithm or deployment is switched by this decision.
