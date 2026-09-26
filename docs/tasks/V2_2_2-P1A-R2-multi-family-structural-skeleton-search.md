# V2.2.2 P1A-R2 — Multi-family structural skeleton search

```ini
TASK_ID=V2_2_2_P1A_R2_MULTI_FAMILY_STRUCTURAL_SKELETON_SEARCH_R1
BASE_MAIN_SHA=955e5e532236fb6c33a80709e90362b12124fb72
PREVIOUS_HEAD_SHA=8f1195ef093b1d54ba302e4b5d8a2d6e89abc9dd
ACTIVE_GOVERNANCE_LANE=V2.2.2_P1A
OWNER_P1A_R1_VISUAL_REVIEW=FAIL
OWNER_XINZHAO_P1A_R2_VISUAL_REVIEW=PENDING
P1B_NUMERIC_THRESHOLD_ACTIVATED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

## Scope and implementation

This correction adds three deterministic search lanes—`LINEAR_PROCESS_BAND`
positive, `LINEAR_PROCESS_BAND` negative, and `CENTRAL_PROCESS_HUB`—with a
preferred family affecting ordering only. Each lane carries a versioned
structural skeleton, exact group-envelope facts, a structured-only phase, and
a separate general fallback. P2D full-pass remains a hard prerequisite; the
selector then compares atomic structural facts lexicographically and retains
the existing P2B2 comparator as the final tie-break. No weighted score or
uncalibrated P1B threshold is activated.

The evidence-supported Tool 7 placement node budget is 120, the smallest
tested value that produced two P2D full-pass candidates. The 240-node run
raised selector latency from about 12.6 s to 56.3 s and added two rejected
candidates but no additional full-pass result. This remains bounded search;
budget exhaustion is neither global optimality nor mathematical
infeasibility.

## Acceptance evidence and unresolved visual result

The canonical Xinzhao input SHA remains
`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`.
The unmocked Tool 7 chain is hard-valid, returns 12 zones, 12/12 access, a
validated truck route, and a building footprint. Two P2D full-pass candidates
exist, but both are from `CENTRAL_PROCESS_HUB`; the two linear lanes produced
no complete P2C candidates in the tested bounded searches, so no infeasibility
claim is made. The selector explanation reports a real runner-up but its
first decisive comparison is the existing `P2B2_FINAL_TIE_BREAK`, because the
structural facts tie.

The selected R2 main-process zone geometries are coordinate-identical to the
v2.2.1 Owner-fail baseline and P1A R1. Support-group shared edges improve
from 0 to 2, while major-zone grid alignment remains 0.4 and support touches
three sides of the core. The comparison therefore does not show the requested
visible primary-skeleton transformation. **P1A-R2 implementation evidence
is partial and Owner visual acceptance remains pending; this PR must stay
Draft.**

See the [same-canvas three-way visual comparison](evidence/v2_2_2_p1a/xinzhao_p1a_r2_comparison.md),
[budget sensitivity matrix](evidence/v2_2_2_p1a/xinzhao_p1a_r2_budget_sensitivity.json),
and [R2 metrics](evidence/v2_2_2_p1a/xinzhao_p1a_r2_metrics.json).

```ini
STRUCTURAL_FAMILY_LANES_ENUMERATED=true
STRUCTURED_PHASE_SEPARATED_FROM_GENERAL_FALLBACK=true
P2D_HARD_VALIDATION_PRESERVED=true
P2B2_FINAL_TIE_BREAK_PRESERVED=true
WEIGHTED_SCORE_USED=false
P1B_NUMERIC_THRESHOLD_ACTIVATED=false
TOOL7_INPUT_CONTRACT_CHANGED=false
EXISTING_SIX_TOOL_CONTRACT_CHANGED=false
PRODUCTION_CHANGED=false
OWNER_VISUAL_ACCEPTANCE_COMPLETE=false
```

## Local verification

The focused R2 selector, architecture, and unmocked Tool 7 evaluation tests
pass (`27 passed`). The selected P1A/P1A2/P1B/P1C/P1D/P1E/P1F, P2A–P2D,
P3, Tool 7, existing six-tool, HTTP protocol, and cross-fixture regression
set passes (`568 passed`). Full backend architecture passes (`747 passed,
16 skipped`); full-source mypy, repository Ruff, repository Ruff format check,
and `git diff --check` pass. The Xinzhao fixture SHA remains unchanged.

The broad local SQLite backend suite was started but deliberately interrupted
at approximately 36% after 13 minutes while running unrelated report/PDF
integration cases; no failure had been observed before interruption. This is
not reported as a full-suite pass. Local PostgreSQL execution was unavailable
because Docker is not available in this environment. Exact-head GitHub CI is
the required backend SQLite/PostgreSQL gate and remains pending until the
correction is pushed.
