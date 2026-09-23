# V2.2.1 P1F Context Inset Loading-Face Correction

```ini
TASK_ID=V2_2_1_P1F_CONTEXT_INSET_LOADING_FACE_CORRECTION_R1
BASE_MAIN_SHA=debda749966e7c890e2f8758f468fa582fb3def8
CORRECTION_SCOPE=RENDER_AUTHORITATIVE_LOADING_FACE_IN_EVERY_CONTEXT_INSET
P1F_CROSS_FIXTURE_REVIEW_PR=297
P1F_REVIEW_PR_MODIFIED=false
```

## Correction

The context inset already projected the authoritative site, building, zones,
and shipping loading-face segment through the same deterministic inset
transform. The renderer had an unnecessary profile condition that emitted the
loading-face line only for `ENGINEERING_SHEET`. The condition is removed: when
a context transform exists, the exact selected `shipping_loading_face_segment`
is now rendered in the inset for `PRESENTATION`, `MOBILE_PREVIEW`, and
`ENGINEERING_SHEET`. `ENGINEERING_REVIEW` has no context inset and remains
unchanged.

This is a projection visibility correction only. Loading-face selection,
source geometry, coordinates, placement, routing, truck validation, and the
P1F cross-fixture results are not changed. No geometry is inferred or
recalculated.

## Acceptance evidence

Three existing authoritative full-pass scenarios are exercised in both
`PRESENTATION` and `MOBILE_PREVIEW` (six profile/scenario combinations):

1. The representative 20 t/day rectangular-site P2D full-pass fixture.
2. The existing concave-site validated-layout fixture.
3. The unmocked P4 selector/no-build-site fixture, where the first P2C
   candidate is rejected by P2D and a later full-pass candidate is selected.

Each projected line endpoint is checked against the selected validated
layout's authoritative loading-face segment transformed by the existing
`SvgProjectionTransformV1`. Each case also checks full-pass status, stable
replay bytes/hash, unchanged source result hash, and a zero-error,
zero-warning Drawing Lint report with no unavailable required facts.

| Profile | P1F baseline SVG SHA-256 | Corrected SVG SHA-256 | Result |
|---|---|---|---|
| PRESENTATION | `97e7c9083050dc1e1edd01c8880f4c7aa1d2526d72e8eff809ee792bda8cf59e` | `e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a` | Expected context-line-only projection change |
| MOBILE_PREVIEW | `db6a39e7ad38ca8c0b0fc2063d4189bdd295691d92aaf7a922e59d7c200954c8` | `dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2` | Expected context-line-only projection change |
| ENGINEERING_SHEET | `96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3` | same | Preserved |
| ENGINEERING_REVIEW | `48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d` | same | Preserved; no context inset |

The baseline values are the representative fixture's P1F pre-correction
outputs. The earlier P1E task document retains its historical P1E baseline
snapshot; this correction does not rewrite that history.

## Visual artifacts

The `before_*` and `after_*` SVG/PNG pairs use the same representative
20 t/day validated fixture and renderer inputs. PNGs are direct rasterizations
of their corresponding SVGs. The optional context crops are inspection aids
only; the complete, uncropped SVG and PNG files are retained alongside them.

- [Before Presentation SVG](evidence/v2_2_1_p1f_context_loading_face/before_presentation.svg)
- [Before Presentation PNG](evidence/v2_2_1_p1f_context_loading_face/before_presentation.png)
- [After Presentation SVG](evidence/v2_2_1_p1f_context_loading_face/after_presentation.svg)
- [After Presentation PNG](evidence/v2_2_1_p1f_context_loading_face/after_presentation.png)
- [After Presentation context detail crop](evidence/v2_2_1_p1f_context_loading_face/after_presentation_context_crop.png)
- [Before Mobile Preview SVG](evidence/v2_2_1_p1f_context_loading_face/before_mobile_preview.svg)
- [Before Mobile Preview PNG](evidence/v2_2_1_p1f_context_loading_face/before_mobile_preview.png)
- [After Mobile Preview SVG](evidence/v2_2_1_p1f_context_loading_face/after_mobile_preview.svg)
- [After Mobile Preview PNG](evidence/v2_2_1_p1f_context_loading_face/after_mobile_preview.png)
- [After Mobile context detail crop](evidence/v2_2_1_p1f_context_loading_face/after_mobile_context_crop.png)
- [Machine-readable file hashes](evidence/v2_2_1_p1f_context_loading_face/evidence.json)

The crops do not replace, scale, or edit the full-page evidence and are not
used to claim a composition or occupancy result.

## Scope and governance

```ini
LOADING_FACE_SELECTION_CHANGED=false
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false
P2_CHANGED=false
P2D_CHANGED=false
P4_CHANGED=false
MCP_CHANGED=false
DATABASE_CHANGED=false
P1F_CROSS_FIXTURE_REVIEW_PR_297_MODIFIED=false
P1G_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

Automated evidence in this correction does not replace owner visual review or
authorize a later phase.
