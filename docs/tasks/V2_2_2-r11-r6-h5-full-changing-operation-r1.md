# R11 R6 H5 full changing operation

Task: `V2_2_2_R11_R6_H5_FULL_CHANGING_OPERATION_R1`

Base: PR #325, `73e5ab0a12f8851298da9b8222321327e46edabb`.
Independent development branch: `codex/v222-r11-r6-full-changing-operation`.

Owner authorized deterministic functional development, local tests, an independent
Draft PR and automatic fast CI. No Native solve, MAIN, Grant/Claim, full CI,
Ready, merge or deployment. Existing project facts, geometry, P1, Stage B,
comparators, production defaults and R1–R5 remain untouched.

## Implementation

- `changing_operation_motion.py`: continuous physical-body transport; explicit
  sit/rise upper-body and forward-leg volumes, with benches retained as collision
  bodies; original east/south Portal crossings and all-person identity accounting.
- `full_changing_operation.py`: all 28 adjacent pairs at default four-front-user
  configuration, independent entry/exit audits, and a separate continuous full
  service protocol. Rejecting a step preserves state and blocks dependent steps.
- `full_changing_operation_review.py`: binds the original R4/R5 source-verified
  H5 catalogue, evaluates nine explicit hypothetical configurations.
- `full_changing_operation_page.py`: reads persisted results; no engineering
  formulas in browser code. Timeline, all batch routes, body sweeps, seat motions,
  conflict coordinates, comparison and input boundaries.
- `build_r11_r6_operation_review.py`: fresh output only, original source hash
  check, both OR-Tools Native APIs disabled, raw gzipped JSON before presentation.

## Engineering result

Default H5 retains 53 simultaneous occupants, 22 columns/110 cells and both
1500mm Portals. All 30 snapshots and 28 independent adjacent pairs pass the
stated hypothetical volume checks, including later seated participants.

Two explicit protocols are retained. Waiting for everyone before any departure
blocks after three service cycles per shift: a service-area occupant cannot
relocate to a free reviewed standing home. That negative protocol remains intact.

Departing immediately after each person's complete locker/changing/bench chain
allows both shifts to finish 53 users, 15 batches and 14 batch boundaries in the
hypothetical continuous model. All 53 must first be inside; each later departure
is recorded only after a verified service chain and actual south-Portal crossing.
No uncompleted user is removed. Remaining occupants still block movement.

Default serial timing is about 229.95 / 216.64 minutes. This is an explicit
hypothetical plan, not measured throughput or functional approval. A 90-second
single changing operation alone has a 4770-second ideal workload lower bound.
The negative protocol retains a null complete duration. Both protocols remain
INPUT_REQUIRED for actual engineering use.

Fixed-position body envelopes expanded by 10mm already expose aisle/support-model
conflicts; 25mm also exposes adjacent-user overlap. Repacking larger bodies or
100mm home gaps fails the 53-home requirement in this template. No missing user
is silently removed. Alternative protocols/layouts are not proven impossible.

## Scope and actual inputs

All practical functional results stay `INPUT_REQUIRED`. Actual human dimensions,
articulation, time parameters, cabinet construction/reach, doors, finishes,
hygiene, cleaning/maintenance and approved shift duration are not supplied by this
software task. No `CONDITIONAL_FIT` or capacity compliance is claimed.

To reproduce with Python 3.12 and locked dependencies:

```sh
cd backend
PYTHONPATH=src:scripts uv run --frozen python scripts/build_r11_r6_operation_review.py \
  --output ../artifacts/r11-r6-new-review
PYTHONPATH=src:scripts uv run --frozen pytest tests/unit/test_v222_r11_r6_full_changing_operation.py -q
```

Use a new output directory; never overwrite frozen reports. The final delivery
is under `docs/previews/v2.2.2/r11-r6-h5-full-operation-review-r1/`.
