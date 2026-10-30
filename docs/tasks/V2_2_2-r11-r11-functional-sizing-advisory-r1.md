# R11 R11 conditional functional sizing advisory handoff

TASK_ID: `V2_2_2_R11_R11_FUNCTIONAL_SIZING_ADVISORY_HANDOFF_R1`.
Base Draft PR #330: `9629019ddd704426b5f7fe72b9a98d2273fca1c4`.
Independent branch: `codex/v222-r11-r11-functional-sizing-advisory`.

Owner authorizes a versioned advisory data contract, read-only applicability
precheck for the existing reviewed H5 project, engineering review artifacts,
explicit functional/architecture whitelist, static checks, normal commit/push,
an independent Draft PR and automatic fast CI. The advisory is not an area
Authority, approval, solver constraint, MAIN credential or production handoff.

Preserve original P1/Stage B/geometry, R1-R10 evidence, nine/twelve comparators,
Owner inputs, production defaults, MCP behavior and all historical records.
No new 20t Native solve, MAIN, real Grant/Claim, formal full CI, Ready, Merge or
Deploy. Local validation uses the inherited child startup Native guard and
explicit R11/architecture file whitelist. Existing synthetic Native tests remain
in automatic fast CI and must not be reported as zero task-wide Native calls.

Source copies are byte-for-byte, hash-checked historical evidence. They retain
their original P1 and candidate references and do not establish new Authority.
Counterfactual dimensions are separate objects; external Site, Footprint,
Access and adjacent process relationships remain unvalidated. Conditions are
grouped for descriptive review only, with no optimality or safety ranking.

## Existing architecture and data flow

`dimension_handoff.py` owns the canonical P1 hybrid result. Its original
`FLEXIBLE_RECTANGLE` authority permits choosing width/depth while forbidding a
change to required area. The new contract carries the existing
`DimensionAuthorityReferenceV1`, original P1 hash, exact original authority row,
and an immutable content reference to the byte-identical P1 snapshot. It is not
another dimension handoff and cannot be passed to the production solver.

`functional_room_review.py::_room()` reads the existing candidate's exact room
and Portal geometry. Its source/role binding and the original `_eligible()`
predicate are reused to read the preserved H5 records. The provenance matching
principle in `composition_candidate_validation.py` remains unchanged. No
composition replay, placement enumeration, Native model or new engineering
acceptance is performed by this reader.

`room_reverse_sizing_review.py` already produced the full archived two-shift
witnesses. This task validates their bytes/hash and original candidate binding;
it does not call that search again. Its C/B base conditions and the 3850mm
sensitivity conditions remain distinct. The archived source files are not
rewritten. New immutable copies of original P1/Plan/Site, source binding,
P01/P02 and R10 remote JUnit make the preview reproducible on CI.

## Interface

`read_functional_sizing_evidence(root)` returns only known file bytes.
`preview_functional_sizing_handoff(files, project_scope_id=..., layout_candidates=...)`
is an in-memory application function with no write/DB/network/execution port.
It verifies caller candidates against the preserved sources and validates any
submitted `FunctionalRoomSizingAdvisoryV1` payload against rebuilt advice from
the fixed evidence. A recomputed user JSON hash cannot approve or rebind it.

The canonical value object exports Schema 1.0.0 and explicit approval boundaries.
Other room codes return `FUNCTIONAL_ADAPTER_REQUIRED`. It supports only this
reviewed H5 project; no generic room-fit capability is claimed.

## Local reproduction

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r11_sizing_advisory_review.py \
  --output ../artifacts/r11-r11-new-review
uv run python scripts/validate_r11_r11_whitelist.py \
  --evidence ../artifacts/r11-r11-new-validation
```

Both tools preserve the existing child startup Native guard. The test launcher
enumerates the new functional/architecture files and the existing explicit R11
and architecture whitelist. It never selects a historical Stage B test directory.
Fast CI adds the new functional file, retains all existing files and JUnit
upload, and discovers the new architecture test through its existing job.

Serve the generated static output on loopback for browser review if desired.
It has display-selection controls only, no approval or production action.
