# R11 R9 H5 functional space relayout

TASK_ID: `V2_2_2_R11_R9_H5_FUNCTIONAL_SPACE_RELAYOUT_R1`

Base: PR #328, `9ab3851591b93c0bb0543ba2a96c16d49cfbc166`.
Independent branch: `codex/v222-r11-r9-h5-space-relayout`.

Owner authorized independent spatial-template development, complete deterministic
functional checks, local tests, a normal commit/push and an independent Draft PR
with automatic fast CI. No Native, MAIN, Grant/Claim, formal full CI, Ready, Merge
or Deploy. Preserve all R1–R8 sources, results, P1, Stage B and production defaults.

This task changes cabinet/waiting spatial organization. It reuses R8's group
scheduler unchanged and adds no concurrency optimizer. The R8 reviewed source
and project scope remain the fact basis; new dimensions and motion assumptions
are `source_type=demo`, `validity_status=unverified`, `requires_review=true`.

Three distinct original-H5 templates:

- Mixed eastern normal waiting positions with six northwest rotated positions.
- Waiting along the north wall with a separate southeast waiting zone.
- Two cabinet banks separated by 1200mm, with north/southeast waiting zones.

Each keeps 53 initial occupants per shift, 22 columns/110 compartments, no bench
or separate changing station, and the archived 26331×3250 rectangle/1500mm Portals.
The same 450×650mm body can wait with a 90-degree yaw (650×450 in plan). Its
translation, all-angle conservative yaw sweep in the original aisle, and restored
transport pose are checked explicitly against actual remaining occupants. It is
not a smaller body or a proof of human ergonomics. Static positions maintain the
100mm assumed waiting gap; no claim of a 100mm dynamic clearance is made.

Cabinet end clearance derives from the 600mm activity width and 450mm body:
right overhang `(600+450)/2-400=125mm`. The original 100mm corner leaves a 25mm
activity/turn-bay conflict and remains a rejected regression. None of these
hypothetical dimensions is written to Authority.

The original R8 47-position template and a 30mm finish sensitivity failure remain
negative controls. A necessary 3440mm counterfactual width is a cross-section
calculation only; it is not an approved expansion or a new historical room.

Functional verdict: **INPUT_REQUIRED**, including successful conditional traces.
The default north strip has only 10mm spare depth. Real cabinet dimensions,
finish tolerances, human activity/reach/yaw, room-door movement, hygiene and
operating procedure still need review. Timing is illustrative and unoptimized.

Reproduce (locked Python 3.12 environment):

```bash
cd backend
uv sync --locked --python 3.12
PYTHONPATH=src:scripts uv run pytest tests/unit/test_v222_r11_r9_space_relayout.py -q
PYTHONPATH=src:scripts uv run python scripts/build_r11_r9_space_relayout_review.py \
  --output ../artifacts/r11-r9-new-review
```

The report output must not exist. Both OR-Tools solve APIs are blocked by the
report generator. It verifies archived source hashes, writes raw results first,
then creates the page/SVGs from persisted results. Historical files are read only.

Delivery: `docs/previews/v2.2.2/r11-r9-h5-space-relayout-r1/` contains the full raw
trace, 3 original-H5 spatial comparisons, negative controls, exact dimension
chains, waiting/service/yaw drawings, and source provenance. All existing source
files remain unchanged except adding this round's test module to automatic fast
CI; new implementation is confined to named R9 domain/application/view modules.

## Validation scope exception

An overbroad local regression mistakenly executed existing tiny Stage B Native
tests in isolated child processes. The parent-only API prohibition did not carry
into those children. That run was interrupted, retained and not counted as a
completed regression; exact Native call count was not instrumented. No 20t
solve, MAIN or real Grant/Claim occurred. Later local verification is restricted
to functional, architecture and CI-contract tests. The delivered exception note
records the deviation; the task-wide zero-Native boundary cannot be claimed met.
