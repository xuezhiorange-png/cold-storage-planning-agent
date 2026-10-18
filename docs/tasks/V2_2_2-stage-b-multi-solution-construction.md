# REVIEW-MULTI-CANDIDATE / Stage B: bounded single-handoff enumeration

Owner scope: `STRUCTURAL_MULTI_SOLUTION_GENERATION`, baseline
`865bb697b463174520927ddbfbaa90ab4f9cf402`. This is a feature extension of the
delivered Stage-A construction architecture, not a reset of D04 recovery rounds.
No real Owner-bound solve, quota, quality ranking, Selector/Tool7 wiring, Truck
acceptance or deployment is authorized by this implementation.

## Previous limitation and new execution path

Previously a handoff prepared three room hints, one Access hint, then a final
joint model, returning its first topology-valid physical witness. The pool called
that single-result port once for each approved handoff. A feasible handoff could
therefore contribute at most one exported candidate. `stop_after_first_solution`
remains true **per native call**; changing it alone would not expose independently
validated layouts to the application.

The new explicit internal entry is
`bootstrap.global_composition.generate_multi_solution_global_layout_pool`.
The old Stage-A, original pool and soft-guided pool entries remain unchanged.
The new entry uses the existing server-derived six-handoff round-robin schedule.
Within each handoff it performs the original source/context validation and lease
`begin()` once, prepares the existing models once, then resumes the same final
CpModel through bounded native calls. It does not preserve learned SAT clauses
between CpSolver calls; the reused state is the model, hints and explicit cuts.
This entry does not implicitly enable the separate soft-guidance policy.

Each yielded proposal traverses the same extracted
`validate_generated_global_proposal` implementation as Stage A: independent hard
geometry, original native application Access, independent checks of its actual
corridors, coexistence and original Footprint/Site. No validation result is shared
between candidates. Results are deep-copied before later ledger growth. The pool
checks source hashes, canonical result hash, all eleven exact requirement identities
and complete engineering eligibility before counting any construction.

After a fully engineering-accepted room geometry, an enumeration cut excludes
exactly its twelve physical `(x,y,width,depth)` tuples, irrespective of redundant
nominal-rotation or corridor encodings. It means “already represented geometry”,
**not** “engineering infeasible”. Rejected complete witnesses exclude only the
exact room assignment plus selected physical Portal/corridor variables. A different
Portal/path with the same rooms remains available. Hole rejection retains the
existing exact-witness cut with an exact union certificate. UNKNOWN, missing native
accounting and resource interruption never justify an infeasibility cut.

Every cut records its variable indices, names, values, scope and certificate where
applicable. The durable PoolLease records final-model preparation and complete
candidate validation results inside the same active approved composition. Its
source checks and counters cannot be rolled back; no second begin or refill is
introduced. Native calls, checked physical solutions and candidate validations
are different counters. Cut and audit work is charged to the original ledger.

The unchanged shared maximum of twenty checked final-model assignments bounds
duplicates and rejected witnesses as well as accepted ones. A handoff stops after
five newly counted organizations; duplicates do not consume that accepted target
but do consume their actual native/work/time allowance. Cross-handoff geometry,
organization and major-family comparison uses the unchanged versioned
`construction_diversity` D4/translation policy. Micro-shifts, rotations, mirrors,
nominal dimensions, labels and support-only rearrangements do not inflate coverage.
The pool retains collected candidates on interruption and reports a bounded
model's exhausted remainder, never global engineering infeasibility.

## Three bounded UNSAT domains: findings and limits

The sealed real pool/replay evidence records LINEAR X NEGATIVE, SPINE X NEGATIVE
and CENTRAL Y POSITIVE as final joint-model INFEASIBLE, each without a prior hole
cut. This is different from LINEAR Y POSITIVE: a complete model witness with a
0.01883 square-metre hole was rejected, followed by UNKNOWN. SPINE Y POSITIVE was
not admitted before the reservation limit. Ten admissions and 52 native calls
across both pools remain unchanged. No new factory solve or UNSAT-core search was
performed here.

The actual constraint layers are:

* **A, engineering Authority**: original twelve dimensions/areas/rotation, seven
  MUST, Site/obstacles/non-overlap, Portal/net widths/Packaging constraints. The
  existing CENTRAL X accepted candidate disproves any inference that these
  Authorities alone make the entire project infeasible.
* **B, finite P1A intent**: server axis/direction/group ownership and domain faces
  from `domain/composition_placement.py::_domain_faces`. For LINEAR X NEGATIVE,
  Raw/Primary lie east of Sorting, Finished/Shipping west; three auxiliary rooms
  are north and Changing/Office south (`bank=1`). SPINE X NEGATIVE has those same
  sides plus non-increasing X centres along all seven process rooms. CENTRAL Y
  POSITIVE places Raw/Primary/Changing/Office south, Finished/Shipping/Packaging
  north, Secondary Buffer east and Frozen west.
* **C, concrete model restrictions**: `GlobalModel` translates those side inputs
  into integer centre inequalities of at least one millimetre. LINEAR additionally
  orders raw/core/finished group means; CENTRAL orders raw mean / Sorting /
  finished mean; SPINE enforces each consecutive process centre along the axis.
  These are real restrictions, not family labels or product-level global
  impossibility proofs. Their compatibility with room rectangles, fixed MUST
  edges and Site is exactly what a bounded final model decides. No frozen side
  rule or ownership mapping is relaxed by this feature.
* **D, template coverage**: integer-mm rectangular geometry scope, finite native
  Portal candidates, bounded five-segment orthogonal routes and separate corridor
  envelopes further restrict coverage. This is not a completeness proof for all
  engineering-valid routes or structures.

Historical logs contain no assumption-labelled UNSAT core. Consequently the exact
minimal conflicting subset, and which restriction would be sufficient to relax
for each of these three real domains, remain **UNAVAILABLE**. Naming one particular
room or obstacle as the proven cause would invent evidence. Enumeration cannot
make an UNSAT domain feasible; no source error that safely warrants weakening a
frozen family rule has been proven. A proposal to relax these side/mean/ordering
predicates requires a separate Owner decision, D04 review where applicable and
new bounded evidence. This implementation needs no such contract amendment.

## Verification and remaining real work

Small synthetic models exercise real CP-SAT enumeration/cuts, two physically
different main organizations from one prepared model, actual ring-hole rejection,
same-room alternate Portal preservation, Stage-A first-result compatibility,
determinism, UNKNOWN and interruption. Synthetic validation ports are explicitly
marked and do not create business candidates. Existing resource, Access security,
MCP, P1A and architecture regressions independently protect the production oracle.

No real pool runs in this task. Actual counts remain construction **1**, major
family **1**, P2D full-pass **0**. `REAL_MULTI_SOLUTION_VERIFIED=false` and Stage B
remains incomplete. Historical 262 UNKNOWN, P3/P2/version incomplete, D03 ownership
and uncalibrated 0.90 product target, D04 MAX=2 and all old evidence remain intact.

The next real execution request is a proposal only: pin the final committed source
and strategy hashes, allocate one main pool and one exact replay, at most six
approved compositions per pool, at most five counted organizations per handoff,
at most twenty checked final assignments per pool and at most 100 native calls
including all preparations/terminal solves across both pools. The existing shared
100 native seconds / 180 elapsed seconds / 1,200,000 observable work / 512 MiB /
20,000 Host per requirement ceilings remain unchanged; their reserve policy may
stop substantially earlier. Preserve half the native/work reservation for replay
using the existing PoolLease, and all wall/memory protection for both. Do not create
the new grant or execute it until explicitly approved. Existing UNSAT domains may
still consume part of that fixed schedule and cannot be silently replaced.
This removes a one-result interface cap, not a guarantee of five candidates,
three families, shorter routes, better room shapes or any new P2D PASS.
