# REVIEW-MULTI-CANDIDATE / Stage B: hole-free construction guidance

Scope: `STAGE_B_HOLE_FREE_LAYOUT_CONSTRUCTION_01`; reference
`613a48709242aa9b4b2f9f1cb723562cfc563af3`. This is an explicitly authorized
construction-guidance implementation, not merely an audit. It does not create
a new architecture or reset/classify D04 historical recovery rounds. D01/D03/D04,
the 262 historical P3 UNKNOWN and all resource/engineering contracts are retained.

## Evidence and why no new topology pruning is claimed

Three sealed fair-search assignments have holes of 203.212700, 0.018830 and
1.014012 m². All three exist in the room-only union. Historical sixteen rejected
assignments have twenty-seven holes: twenty-five already exist in the room-only
union, while two involve personnel corridors. Exact original coordinates,
millimetre gaps, routes, certificates and hashes are preserved.

Room-only holes alone do not prove infeasibility of the final building union.
A legal 2m-wide synthetic personnel corridor can fill a 2m by 2m cavity between
opposing portals without crossing room interiors. Neither a hole's existence nor
one narrow bbox dimension proves that all legal corridor alternatives fail.
There is no new room-only cut, clearance threshold, snapping, area tolerance,
void filling, forced rectangular building or claimed irreparability certificate.
Repairability not established means **no pruning**, not INFEASIBLE. The existing
complete-union witness cuts, original Footprint and native Access/Site oracles
remain the sole engineering acceptance path. In particular7mm/108mm holes remain
invalid under the exact unchanged predicate.

## One live opt-in construction improvement

The fair Stage-B streaming port supplies a once-per-prepared-final-model callback
using `stage-b-wall-coordinate-coherence-and-span@1.0.0`. For each physical room
it derives its two x-wall and two y-wall coordinates. For each wall it measures
the nearest parallel wall of another room. One soft millimetre proxy minimizes
the sum of these offsets plus the enclosing x/y room spans (unit coefficients,
no gate or calibrated score). This encourages repeated wall axes and compact
room organization. Nearest walls need not be adjacent; this is a proxy, not a
claim of measured shared-edge quality, actual Footprint or verified process flow.

All absolute/min/max variables are total exact definitions. If B is one plus
the sum of absolute domain extrema for original x/y/w/d values, each derived wall
coordinate, coordinate difference and enclosing span is bounded by B (extrema
themselves lie in [-B,B]). Therefore every original physical assignment has an
auxiliary extension; clearing the objective projects onto exactly the original
feasible domain. No new geometric inequality is imposed on the rooms or routes.
This remains true for negative origins, rotations and reflections. Original
hard process direction/side/shape predicates remain authoritative.

The objective changes search preference, not feasibility or formal quality
ranking. Enumeration can still reach worse proxy values after earlier assignments
are excluded. A pre-existing objective is refused, never overwritten. Geometry
input scanning and all generated variables/constraints/objective work are charged
to the original ledger. The original native calls, counters, time/Host/RSS caps,
fair handoff shares/order and V1/V2/family admission are unchanged.

The callback defaults to None in the shared native enumerator. It is enabled only
by the fair Stage-B port, after the proven-base-INFEASIBLE short circuit and before
final native search. Stage A, older Stage-B entries, existing optional guidance,
Selector, Tool7, MCP and Truck APIs remain unchanged. A policy/hash receipt is
included in source-bound events and proposals; future execution must bind the new
source hashes. No previously consumed grant becomes usable.

## Reproducible tests and limits

The checked-in minimal fixture contains exact source-hashed projections of the
three rejected assignments and historical valid01/02. It is test data only,
not a runtime template. Tests recheck all five exact union topologies and preserve
their bytes/coordinates; no historical12-room model is solved.

Synthetic tests cover a large room ring,7mm and108mm gaps, a corridor-fill positive
case, an ordinary hole-free concave layout, irregular-site/obstacle authority,
all six actual model builders without solving, D4/translation invariance,
physical-domain preservation, repeated deterministic search, prepared-model
multi-solution continuation, resource failure and Stage-A compatibility. The
nonrectangular production adapter scope still fails closed; these tests do not
claim new nonrectangular-site solver support.

The comparison uses three finite two-alternative synthetic domains, preserving
per-room side lengths up to allowed90° rotation and total room area. Both modes
use the same1s native limit,512MiB cap,seed3,single worker,partial fixed search and
first-solution termination. Baseline preferences disabled versus this objective
are compared on exact union holes, not a ranking score. Results only establish
the observed effect on those finite benchmarks; no real factory improvement or
native time saving is inferred.

Real new factory solves0; no MAIN/REPLAY or Owner Grant is invoked. Historical
meaningful constructions2 / major families1 / P2D full-pass0 remain unchanged.
The original target is at least five distinct structured P2D full-pass layouts
covering three major families, not merely these synthetic examples. Stage B,
P3, P2 and the version remain incomplete. No next real execution, quality ranking,
Ready, Merge, deployment or public MCP change is authorized here.

## Observed local checks

Targeted hole/guidance cases29 passed; complete Stage B138; prior strict-base
short-circuit cases16; resource44; Access security43; MCP98; P1A74;
architecture771 passed with16 existing skips. Ruff, formatting, Mypy and diff
checks passed. The separate same-limit benchmark repeated each of its three
cases five times: unguided0/15 versus guided15/15 hole-free first solutions.
This remains finite synthetic evidence, not new real construction candidates.

Admission initially had36 passes and one real-memory pressure-test failure:
actual RSS453099520 bytes did not reach the unchanged536870912-byte threshold.
One bounded recheck of that same original test passed with actual RSS611844096.
All37 unique cases therefore have passing records; the initial suite was not
single-run all-green. Initial failure/log and the recheck remain in evidence.
No resource test, assertion, allocation size, RSS value or guard was modified.
Exact-head CI status is tracked separately; no local full-Backend PASS is claimed.
