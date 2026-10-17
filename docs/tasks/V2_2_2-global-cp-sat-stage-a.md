# v2.2.2 controlled global CP-SAT integration — stage A

Task: `V2_2_2_MULTI_CANDIDATE_STAGE_A_PRODUCTION_INTEGRATION`.
Owner-authorized scope: one bounded main integration attempt, its necessary
integration/CI corrections and deterministic replay. No automatic recovery task.

## Stage-A decisions (not a blanket contract amendment)

* D01: safe pruning, joint positive-capacity evidence and complete engineering
  validation remain three distinct responsibilities. Historical P3 has 262
  UNKNOWN results; `P3_COMPLETE=false`. A CP-SAT assignment is not a negative
  certificate and does not close the historical P3 proof chain.
* D03: this implementation consumes the current server-replayed P1A handoff:
  Secondary is in `PROCESSING_CORE_GROUP`. Historical P0 `FINISHED_SIDE_GROUP`
  reports are not rewritten. Grid alignment 0.90 is an uncalibrated product
  target, not a new acceptance threshold. Dimensions and areas are unchanged.
* D04: `WHOLE_BUILDING_COMPOSITION + GLOBAL_CP_SAT_JOINT_PLACEMENT` is an
  opt-in internal generator, not the existing production selector replacement.
  Historical tail-first, P1A/P3 and recovery authorizations remain preserved;
  `MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2` is not reset by this task.

## Authority and search boundary

`bootstrap.global_composition.generate_controlled_global_layout` wires the
application-owned solver port to OR-Tools. It accepts canonical business plan,
P1 and authoritative typed Site; the application rebuilds compositions and
validates their complete hash/role references. It accepts neither supplied
composition bodies nor coordinates/hints. No historical candidate or S4 file
is read. The existing selector, MCP and Truck flows are untouched.

All 12 room variables, seven positive-edge MUSTs and 11 non-Truck access
geometries are in the final joint model. B0 geometry-only/MUST/packaging warmups
provide fresh invocation-local hints, never an accepted solution. Flexible
nominal dimensions remain variables with their original minimum area.

The initial bounded backend supports exact rectangular Site/obstacles,
integer-mm rooms/portals, five-segment orthogonal corridors and separate route
envelopes. Unsupported geometry fails closed; it is never replaced by a bbox.
Conservative separate corridors and finite path templates restrict the search
domain, not the Owner Authority. INFEASIBLE is scoped to this model; UNKNOWN is
not proof of project infeasibility. No geometric/quality standard is invented.

## Resources and outstanding contract work

The controlled entry retains B0 ceilings: 100 cumulative native solver seconds,
180 experiment seconds, one worker, CP-SAT memory parameter 512 MiB, observable
construction-work safety ceiling 1,200,000. Native branches/conflicts/response
statistics are recorded separately; model work is not a DFS-node measure.
These research ceilings are **not an approved conversion** to P3 DFS/RS work.
Formal selector/resource contract closure is still required before routing
normal production candidate selection to this backend.

Existing formal values are unchanged: placement 60,000; access 20,000; truck
20,000; joint evaluations 256; origin events 1,024; joint work protection 8,192.
Native engineering validation uses unchanged Access/Footprint/Site code. Real
Truck inputs remain missing; `P2_COMPLETE=false`, `SERVER_REPLAY_ACCEPTED=false`.
Concept previews are not construction drawings or final engineering approval.

## Reproduction

From `backend`, use locked Python 3.12+ dependencies:

```sh
uv sync --frozen --group dev
PYTHONPATH=src uv run python scripts/run_stage_a_global_layout.py --output NEW_PERSISTENT_DIRECTORY
uv run pytest tests/unit/test_v222_global_cp_sat_stage_a.py
```

The output directory must be new. Inputs are the five real business parameters
in the repository fixture and its current server-bound authorities. Legacy
candidate geometry is neither an input nor a solution hint. Final acceptance
is native Access plus native footprint/typed-Site, not a solver status flag.

## C1 bounded engineering correction (not accepted production integration)

C1 continues the existing R16 attempt; it does not reset D04 recovery rounds
or grant a fresh solver allowance. The original two-round ceiling remains
unchanged, and missing historical accounting is not interpreted as zero work.

Portal variables now match the native finite centered/lower/upper candidate
positions. This is a search-domain mapping, not a new continuous-geometry
Authority. Exact integer endpoint decomposition detects disconnected unions,
holes and singular boundary contacts. A topology rejection excludes only the
verified complete room-and-selected-route assignment, retaining alternative
routes for the same rooms. Native footprint and Site validation remain required.

The internal entry requires a shared, verified cumulative execution ledger.
Unknown historical usage or an unresolved active native solve blocks before
CP-SAT starts. No caller may fabricate ledger verification to obtain a fresh
allowance. Interrupted final counters must remain unavailable, not zero.

In C1 the historical interrupted replay lacks final native statistics. Source
replay therefore ended with `CP_SAT_CUMULATIVE_HISTORY_UNVERIFIED`; no new real
layout solve, candidate or deterministic project replay was completed. Synthetic
unit solver checks are not project generation. Formal resource mapping remains
unapproved; commit/push and default production selection gates remain unmet.

## Owner-approved independent execution V1 (resource scope only)

`V2_2_2_R16_INDEPENDENT_EXECUTION_AND_ENGINEERING_VALIDATION_R1` separately
authorizes exactly one NEW main generation invocation, with the existing C1
algorithm and all its bounded internal phases unchanged. Its pinned Owner
instruction digest is bound at bootstrap; the trusted durable registry is not
selected by a caller's output path or UUID. NEW binds current source/input/P1/
Site/composition/version hashes and consumes an exclusive one-allocation claim.
RESUME requires the same approved scope, a complete PAUSED checkpoint and all
prior counters. R16/C1's incomplete legacy continuation remains denied.

The existing 100-second cumulative native solver, 180-second experiment,
one-worker, 512-MiB, 1,200,000 observable-work and 20,000 requirement-Host ceilings
are unchanged. A verified boolean alone cannot grant admission. Durable
STARTED/RETURNED checkpoints retain actual native statistics and interruptions;
Route Nodes are measured separately from returned corridor polygons. A second
main invocation is not implicitly authorized by remaining numerical allowance.

This resource authorization does not change D04 rounds, P3's 262 UNKNOWN,
engineering authorities, the C1 layout/Portal/topology algorithms, or the default
selector. Native CP-SAT measurement in this independent experiment is approved;
the production numerical-budget mapping remains NOT_APPROVED. Failure stops
this instance without a second NEW or automatic layout correction.
