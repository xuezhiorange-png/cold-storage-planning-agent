# Parameterized Truck preview (additive v1)

This concept-planning preview reuses **Option C approved maneuver templates**.
It is not vehicle dynamics, a minimum turning radius calculator, a construction
drawing, or complete P2D/server acceptance. Existing P1F, maneuver V1, Tool 7,
typed-Site and source-binding contracts are unchanged.

## Actual callable entry

From `backend`, with the locked environment:

```sh
uv run --frozen python scripts/preview_truck.py < input.json
```

Application adapters can call `invoke_truck_preview(structured_json)` from
`cold_storage.modules.layout.application.truck_preview`. The CLI reads at most
12 MB; source bytes are submitted in JSON, never arbitrary file paths or URLs.
No old Tool 7 inputs or MCP registration are changed.

## Inputs and units

See `V2_2_2-parameterized-truck-preview-v1.schema.json` and the executable
`example()` in `backend/tests/unit/test_v222_r13_truck_parameter_preview.py`.
All dimensions and coordinates are metres on the existing exact 0.001 m grid.

| Field | Meaning |
| --- | --- |
| `mode` | `SYNTHETIC_TEST` or `OWNER_PROJECT` |
| `vehicle_type` | Classification only, never default dimensions |
| `truck_access` | Original unchanged P1F TruckProjectAccessInputV1 |
| `truck_maneuver` | Original unchanged Option C project/template V1 |
| `vehicle_body` | Axis-aligned body rectangle in template local frame; explicit offsets from reference origin, x span = vehicle length and y span = vehicle width |
| `vehicle_source_reference` | Uploaded vehicle source document reference |
| `entrance.locator_segment` | Reference-point search segment, not clear opening width |
| `entrance.clear_opening_segment` | Actual axis-aligned opening on effective site boundary |
| `entrance.clear_width_m` | Must match opening length and accommodate actual vehicle width |
| `entrance.measurement_reference` | Measurement source document |
| `entrance.clearance_reference` | Project supplied clearance basis; no default safety margin |
| `shipping_loading_face` | Actual full long edge of supplied Shipping rectangle |
| `loading_face_reference` | Loading interface source document |
| `site_geometry` | Boundary, complete hard obstacles, existing zone rectangles and personnel corridor polygons; no layout search |
| `evidence` | List of `{reference,content_sha256,content_base64}` actual source bytes |
| `approval_reference` | Submitted approval record reference |

Every P1F reference and template source digest must match actual uploaded bytes.
Identical references with contradictory digests are rejected. Up to 32 documents,
1 MiB each and 8 MiB total; these are additive input safety caps, not changes to
production placement/routing budgets. No vehicle size, turning radius, safety
clearance or dock spacing defaults are provided.

`OWNER_PROJECT` additionally requires an uploaded UTF-8 approval JSON record:

```json
{"project_id":"your-project","status":"APPROVED","reviewed_by":"reviewer",
 "approved_input_hash":"sha256:<canonical_hash of input excluding evidence>"}
```

Use existing `dimensioning.canonical_hash` on the structured input excluding
`evidence`. The record binds the exact input; changing geometry invalidates it.
This verifies matching supplied documentary approval, **not a human signature or
professional identity**. `owner_approval_record_matches_input` and
`approval_signature_authenticated` remain separate. `REAL_PROJECT_APPROVED`
is deliberately false: this unauthenticated standalone preview cannot grant
real project acceptance. Missing documents return `PROJECT_INPUT_REQUIRED`.
The real Xinzhao project remains blocked without real vehicle/gate/template data.

`SYNTHETIC_TEST` still checks actual bytes and hashes, but does not require an
owner approval JSON. It always returns `SYNTHETIC_TEST_ONLY=true` and
`REAL_PROJECT_APPROVED=false`. Its PASS must never be used as project approval.

## What is actually checked

Original vehicle/template dimensions, identities and binding hashes are checked.
Supplied envelopes must contain the actual body at entry, exit and final dock
poses. This necessary check does not prove the continuous dynamics between poses;
that swept-envelope adequacy must be confirmed by the project engineer.

Exactly one original native Option C search is called with its unchanged 20,000
node budget, anchor domain and rotation semantics. Complete transformed envelopes
are checked against the supplied site, hard obstacles and all zone interiors.
The selected entry body and first envelope's exact gate-plane section must fit
the measured opening, with an inward normal heading. No epsilon is used.
An invalid selected entrance fails closed; other native chains are not declared
infeasible. Exhausted bounded template search is not global physical infeasibility.

The original personnel/truck policy is invoked on actual returned envelopes.
Shared interiors reject; contact returns engineering review, never inferred
`crossing_necessary=true`. No P2D/Authority bypass is introduced.

Output preserves the native search statistics, chain, envelopes and rejection
codes. SVG is only projected for an overall PASS route, with synthetic/review
labels and actual metre coordinates. Invalid or review-required inputs get no
fake successful-route drawing. SVG is a projection, not engineering authority.
