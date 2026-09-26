# Xinzhao layout comparison — v2.2.1, P1A R3, P1A R5

Source fixture SHA-256:
`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`.
All images below are committed evidence generated from structured layout/SVG
outputs; no room or SVG was manually edited.

| Version | PNG | SVG | Layout JSON | Main-process geometry |
| --- | --- | --- | --- | --- |
| v2.2.1 baseline | [PNG](xinzhao_v221_before.png) | [SVG](xinzhao_v221_before.svg) | [JSON](xinzhao_v221_before_layout.json) | historical Owner-fail baseline |
| P1A R3 | [PNG](xinzhao_p1a_r3_after.png) | [SVG](xinzhao_p1a_r3_after.svg) | [JSON](xinzhao_p1a_r3_after_layout.json) | baseline coordinates retained |
| P1A R5 selected | [PNG](xinzhao_p1a_r5_selected.png) | [SVG](xinzhao_p1a_r5_selected.svg) | [JSON](xinzhao_p1a_r5_selected_layout.json) | identical to R3 for all seven main-process zones |

R5 selected SVG SHA-256 is
`sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981`,
equal to R3. R5's canonical result hash is
`sha256:4c95a88e74c977f9c122d46c09d7f4d3235b4524f842d6e4cdefa3ed8a7e13c8`.
The canonical result differs while the rendered SVG and seven main-process
rectangles do not; the measured regression outcome remains `PARTIAL`.

## Evaluation-only group/topology overlay

[Open the structural debug PNG](xinzhao_p1a_r5_structural_debug.png) or
[its source SVG](xinzhao_p1a_r5_structural_debug.svg). The dashed group boxes
are bounding envelopes over selected room geometry; they are not new placement
authority.

## Distinct runner-up

`DISTINCT_RUNNER_UP_PRESENT=false`. No runner-up image is provided: producing a
second visual would misrepresent multiple tail variants of the same main
skeleton as distinct geometry. Owner visual review remains pending.
