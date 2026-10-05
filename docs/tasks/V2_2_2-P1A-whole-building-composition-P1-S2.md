# V2.2.2 P1A — Composition authority binding and placement handoff (P1-S2)

```ini
TASK_ID=V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S2
MODE=COMPOSITION_AUTHORITY_BINDING_AND_PLACEMENT_HANDOFF_CONTRACT
PR_NUMBER=304
PR_STATE=DRAFT
COMPOSITION_APPLICATION_BOUNDARY_IMPLEMENTED=true
COMPOSITION_PLACEMENT_HANDOFF_CONTRACT_IMPLEMENTED=true
STRUCTURAL_COMPOSITION_COUNT=6
FAMILY_COUNT=3
COMPOSITION_HANDOFF_COUNT=6
HANDOFF_COMPLETE_12_ROLE_COUNT=6
EXACT_PLACEMENT_IMPLEMENTED=false
ACCESS_ROUTING_IMPLEMENTED=false
TRUCK_VALIDATION_IMPLEMENTED=false
P2D_IMPLEMENTED=false
TOOL7_INTEGRATION_IMPLEMENTED=false
EXACT_PLACEMENT_IMPLEMENTATION_AUTHORIZED=false
```

## Scope

P1-S2 adds two seams after the P1-S1 structural composition core: a server-side
application boundary that binds composition inputs to current zone-plan, P1,
and validated-site authorities, and a versioned, geometry-free contract for
handing each composition to a future exact-placement implementation. It does
not produce or validate a room layout and does not connect to the legacy
placement runtime, selector, or Tool 7.

## Authority binding

`application.structural_composition.build_structural_compositions()` accepts
the canonical zone plan, the P1 handoff, and a `ValidatedSiteGeometryV1`.
It does not accept `SiteOrientationFactsV1` from callers. P1 identity, schema,
completion flags, blockers, dimension/access/Truck completeness, source zone
plan hash, historical handoff integrity, dimension authority, graph, and
access requirements are checked by the existing P2C `_validate_p1_authority`
integrity utility. The boundary additionally checks the canonical zone-plan
identity/version/success and P2 authorization state, then verifies that the
validated site's source P1 hash matches the supplied handoff.

Site facts are derived only from the authenticated
`ValidatedSiteGeometryV1.to_dict()` projection. Its identity, schema,
validation status, canonical payload, and source P1 identity/hash are checked.
Entrance sides use exact integer-millimetre polygon/segment predicates and
outward cardinal normals; invalid or non-boundary segments fail closed, while
ambiguous valid boundary segments become `UNSPECIFIED`. `NEAREST_TRUCK_ENTRANCE`
resolves to the validated Truck entrance side. No project dimension is
recalculated.

The dominant axis policy is frozen as
`EFFECTIVE_BUILDABLE_BOUNDARY_BBOX_LONG_AXIS@1.0.0`: compare the effective
buildable boundary's X/Y bounding-box spans; select X on a tie. Process
direction and family topology remain in the domain enumerator.

## Composition result and placement handoff

The immutable `StructuralCompositionEnumerationResultV1` binds the source
zone-plan, P1 handoff, and site-geometry hashes to the derived site facts,
family-first coverage evidence, six domain compositions, and six handoffs. It
explicitly reports that exact placement, access routing, Truck validation,
P2D, and project-layout validation were not performed.

`StructuralCompositionPlacementHandoffV1` carries composition identity and
signature, family, process axis/direction, all twelve role assignments,
principal-band and peripheral-domain intents, dominant-axis and site
orientation intents, non-authoritative composition relationships, and source
hashes. Each role points to the existing dimension authority by zone code,
dimension-authority identity, and source P1 hash; no width/depth value is
copied. Frozen, Secondary, Packaging, Personnel, and Shipping/Truck domain
memberships remain explicit. Relationship intent is not engineering authority
and cannot create MUST adjacency.

The contract rejects any interpretation as a final layout, P2C candidate, or
engineering-validity result. It contains no room coordinates, dimensions,
portal or corridor geometry, Truck pose, footprint, or P2D claim.

## Xinzhao evidence and validation

The server-owned Xinzhao chain produces six compositions (two per family) and
six complete handoffs. Main entrance resolves EAST, Truck entrance WEST,
effective-boundary dominant axis X, and preferred loading side UNSPECIFIED.
The first-round three topology signatures match the unchanged P1-S1 evidence.

Machine-readable binding and handoff evidence:
[`xinzhao_composition_authority_binding.json`](evidence/v2_2_2_p1a_reset_s2/xinzhao_composition_authority_binding.json)

The focused P1-S1/S2 and architecture-boundary tests, mypy, Ruff, and format
checks protect the contract and the unchanged authority graph. Full repository
and CI state is recorded in the PR's current status.

## Non-goals and next-stage boundary

This slice does not implement exact placement or geometry, access or Truck
routing, P2D, footprint derivation, scoring, selection, SVG, gallery, or Tool 7
integration. P1 remains incomplete. Any composition-constrained exact-placement
MVP is P1-S3 and requires separate Owner authorization.

```ini
LEGACY_PLACEMENT_RUNTIME_CHANGED=false
VALIDATED_CANDIDATE_SELECTOR_CHANGED=false
TOOL7_BEHAVIOR_CHANGED=false
PROJECT_LAYOUT_VALIDATED_CLAIMED=false
PLACEMENT_HANDOFF_IS_FINAL_LAYOUT=false
PLACEMENT_HANDOFF_IS_P2C_CANDIDATE=false
PLACEMENT_HANDOFF_IS_ENGINEERING_VALIDITY_RESULT=false
NEXT_RUNTIME_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```
