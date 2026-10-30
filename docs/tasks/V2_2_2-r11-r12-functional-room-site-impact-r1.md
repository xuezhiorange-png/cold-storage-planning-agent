# R11 R12: functional room site-impact review

TASK_ID: `V2_2_2_R11_R12_FUNCTIONAL_ROOM_SITE_IMPACT_REVIEW_R1`.
Base Draft PR #331: `5a652a05afa438bd43631b7ffdaf4b541899c8ca`.
Independent branch: `codex/v222-r11-r12-site-impact-review`.

Owner authorizes reading archived P01/P02, deterministic exact geometry overlays,
read-only source-bound application interfaces, tests, review documents/figures,
normal commit/push, a new Draft PR and inherited automatic fast CI. No layout or
route search, Native solve, MAIN, real Grant/Claim, formal full CI, Ready, Merge
or Deploy is authorized. Preserve all original P1/Stage B/Authority, production
solver/MCP/defaults, comparators and historical evidence.

## Source and scope

The R11 evidence reader and advisory precheck are reused. R11's committed source
manifest and advisory bytes are checked before using the same project, P1,
Site, composition, physical H5 and both distinct archived candidate records.
P01 and P02 must be supplied with their proper identities; neither may replace
the other. Both are inspected independently but count as one physical room.

The new interface `review_functional_site_impact()` accepts immutable source
bytes and the archived candidate records. It has no I/O, persistence, routing,
solver or approval port. A source/hash/candidate/Portal mismatch is rejected.
Missing individual geometry components remain NOT_EVALUATED, distinct from an
explicit archived empty set. Other room types/projects are not supported.

## Geometry and interpretation

Existing integer-mm rectangle intersection/coverage, exact Site containment,
rectangle Footprint union and orthogonal topology primitives are reused. The
added north/east bands are disjoint. Only positive area is an occupancy conflict;
normal room/corridor boundary contact is not. Existing closed hard-obstacle
contact is separately reported without weakening Site authority.

The original Footprint is reproduced from each candidate's 12 rooms and archived
corridor envelopes before the counterfactual union is measured. This union is
diagnostic, never a new approved Footprint or a valid rerouted factory. Overlap
areas are measured as unions; duplicated Hard/No-build representations and
duplicated envelope coverage are not double-counted.

Affected original Access/Portal identities, mappings and source hashes are
retained. No replacement route is generated. Truck evidence is explicitly
blocked/incomplete in these archives; empty Truck envelopes are not proof of
clear space. Unarchived occupancy and final factory applicability remain
NOT_EVALUATED. All Owner functional dimensions still require actual review.

## Reproduction and validation

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r12_site_impact_review.py \
  --output ../artifacts/r11-r12-new-review
uv run python scripts/validate_r11_r12_whitelist.py \
  --evidence ../artifacts/r11-r12-new-validation
```

The inherited R10 child startup guard blocks both solve APIs, including ordinary
Python children. The explicit functional/architecture file whitelist excludes
historical Native directories. Fast CI appends the new functional test file and
retains every prior test and gate, including inherited synthetic Native tests;
do not call all environments zero-Native because local functional checks are.

New output directories only. Original R9 boundary exception, R10/R11 archives,
sources and remote JUnit evidence remain byte-identical. R11 remote evidence is
copied exactly for durable provenance, not treated as engineering approval.
The page provides record/scheme/zoom controls only, no approval or write path.
