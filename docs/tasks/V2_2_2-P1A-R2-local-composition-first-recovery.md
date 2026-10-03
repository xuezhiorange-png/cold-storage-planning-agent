# V2.2.2 P1A R2 — local composition first recovery

## Outcome

`RESULT=FAIL` on the canonical, unmocked Xinzhao Tool 7 replay. The recovery
replaced the structured family entry point with local-coordinate composition
followed by rigid whole-building site placement, but none of the three family
synthesizers produced an acceptable seven-zone `RECTANGLE` or `SIMPLE_L`
composition for the authoritative Xinzhao dimensions. Consequently no complete
structured 12-zone candidate, structured truck pass, structured P2D pass, or
local Xinzhao composition image exists. No image was fabricated from a
synthetic test fixture or from the legacy control.

The independent `GENERAL_FALLBACK_PHASE` remains operational. In the same real
Tool 7 replay it supplied two P2D full-pass candidates, and the selected result
remained hard-valid: 12 zones, 12/12 access, truck validation, P2 completion,
and a building footprint. This is compatibility evidence, not structured
generator success.

## Implementation boundary

- Structured construction now enumerates finite local family compositions
  before consulting site coordinates, then translates a complete local
  composition rigidly.
- Local geometry uses authoritative room dimensions, allowed rotations, and
  exact shared-edge MUST interfaces. Site event coordinates are not used to
  construct room positions.
- The derived plan is formed only after a complete local composition exists.
- An unresolved site-derived process direction is normalized to the
  deterministic `POSITIVE` first variant, with `NEGATIVE` also enumerated.
- Each local family/axis/direction attempt is capped at 128 deterministic
  authority-derived room-dimension/orientation combinations. This covers the
  binary 0/90 orientation combinations of the seven main-process zones when
  each has one authoritative dimension shape; flexible-dimension variants are
  a bounded search slice. It is a computational cap, not an engineering or
  placement-budget change.
- Compatibility fallback, P2D rules, truck authority, zone dimensions, and
  `site_geometry.py` were not changed.

## Canonical replay

Machine-readable result: [xinzhao_p1a_r2_local_composition_first.json](../tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_local_composition_first.json).

The final capped replay attempted all three families on X/Y and both
deterministic process directions. Every family/axis/direction row had zero
accepted local main compositions. Full local compositions therefore did not
exist and the three requested local SVG/PNG images were correctly not emitted.
The replay reports the fallback's selected canonical hash and full
hard-validation fields.

This result does not establish that no valid structured geometry exists; it
establishes that this finite local composition implementation did not construct
one. The requested Stage A gate is unmet, so R2 remains failed. No R3 or new
diagnostic task is started here.

## Verification

- New local-composition and prior R2 band-packing unit tests: 22 passed.
- Ruff and mypy on the changed production modules: passed.
- R7/R9/R11/R13/R15 focused unit tests and R7/R9/R11/R13 architecture
  regressions: 39 passed.
- P1F cross-fixture, P4 Tool 7, P1F architecture, and R2 tests: passed in the
  combined run. The R15 closure run retained its hard invariant and failed only
  because the full-pass registry still contained one distinct main skeleton
  (`55589...`), not the required two.
- After the deterministic 128-combination cap, P1F cross-fixture, P1F
  architecture, and P4 Tool 7 tests: 23 passed.
- `site_geometry.py` protected-scope diff: empty.
- Ruff format check and `git diff --check`: passed.
