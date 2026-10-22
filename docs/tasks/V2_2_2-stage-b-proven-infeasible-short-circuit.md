# REVIEW-MULTI-CANDIDATE / Stage B: proven base INFEASIBLE propagation

Owner scope: `STAGE_B_PROVEN_INFEASIBLE_SHORT_CIRCUIT_01`, reference HEAD
`e95b56502b9fd66bcb74f7e09d4e4d493f826d8b`. This change is status propagation,
not a new architecture, D04 recovery round, execution grant, real factory run,
layout strategy, topology rule or resource-contract amendment.

## Model containment proof

`GlobalModel(context, handoff)` contains the complete room dimensions, rotation,
site/obstacle/non-overlap and MUST constraints, Packaging interfaces and finite
composition predicates. The `COMPOSITION_PACKAGING_HINT` phase clones that
complete model with `cut=None`; earlier hint phases instead remove later
constraints. Solution hints do not constrain the solution set.

For the same bound context and handoff, `AccessModel.__init__` first invokes
`GlobalModel.__init__` and retains its variables and constraint prefix, then adds
Access variables/constraints. The final model adds further normalization/search
configuration, not a relaxation. Therefore `UNSAT(M)` implies `UNSAT(M AND A)`.
Production-builder inspection tests compare the base variable/constraint prefix
against AccessModel for all six server-derived handoffs, without solving them.

## Exact trigger and compatibility

The shared native enumerator exposes a default-disabled internal option,
`propagate_base_infeasible`. Only the two Stage-B streaming ports explicitly
enable it. Stage A's original `solve()` path and default enumeration behavior
are unchanged, as are the older single-result entry and optional guidance path.

Only an actual native `cp_model.INFEASIBLE` from the complete base phase enters
the branch. The original `_run()` finishes recording native counters and applies
its existing post-native resource guard **before** status propagation. Exceptions
remain exceptions. UNKNOWN, MODEL_INVALID, incomplete hint statuses, local share
exhaustion and interrupted history never become proof of infeasibility.

On this strict trigger, no AccessModel is constructed or solved for that handoff.
The terminal proposal retains the original native attempt/response statistics,
lists the skipped Access hint/final phases, identifies the complete-base scope
and keeps `global_infeasibility_claimed=false`. A source-bound enumeration event
and ordinary checkpoint preserve the reason and all consumed counters. The
existing pool treats this as finite-model UNSAT, never as an accepted candidate
or a global factory-impossibility proof, and proceeds under its unchanged shared
schedule. No cross-run/source cache of UNSAT is introduced.

## Evidence, tests and limits

The sealed fair MAIN/REPLAY evidence records three complete-base UNSAT domains
per pool. Their subsequent six native calls per pool consumed approximately
8.913 and 8.834 seconds respectively. These are historical observed costs, not
a measured new performance improvement or a guarantee of five constructions /
three major families. Historical candidates, SVGs, hashes and ledgers remain
unchanged; construction baseline stays two meaningful candidates / one family,
P2D full-pass zero. P3 historical 262 UNKNOWN and D04 state remain unchanged.

Synthetic native tests cover complete-base UNSAT, default Stage-A compatibility,
FEASIBLE/OPTIMAL/UNKNOWN continuation, MODEL_INVALID, incomplete hint statuses,
exceptions and post-native resource rejection. Port tests require explicit
Stage-B opt-in. Existing Stage B, resource, Access security, MCP, P1A and
architecture regressions remain required. Status-injection tests are explicitly
synthetic control-flow checks, not engineering or performance evidence.

No real factory solve, MAIN/REPLAY, existing/new Owner grant, quality ranking,
Tool7, Ready, Merge or deployment is authorized by this implementation task.
Any future real execution needs separate authorization bound to its new source.

## Local implementation validation

New targeted tests: 16 passed. Stage B: 109 passed; resource: 44;
Access security: 43; MCP: 98; P1A: 74; architecture: 771 passed with
16 existing skips. Ruff, formatting, Mypy and diff checks passed.

The initial admission run had 36 passes and one real-memory pressure-test
failure: measured lifetime RSS was 486866944 bytes, below the unchanged
536870912-byte rejection threshold. After the other groups ended, one unchanged
serial run of the same 37 tests passed, including the memory rejection assertion.
The initial failure/log is retained in the delivery evidence, not hidden or
converted to a skip. Neither the resource test nor production guard was modified.
No local full-Backend run or new real factory performance result is claimed;
exact-head GitHub CI is recorded separately in the delivery receipt.
