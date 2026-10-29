# R11 R10 functional room reverse sizing

TASK_ID: `V2_2_2_R11_R10_FUNCTIONAL_ROOM_REVERSE_SIZING_R1`.
Base PR #329: `6b47d04d5835ef6a6068a15ab33b371ff94baa2c`.
Independent branch: `codex/v222-r11-r10-room-reverse-sizing`.

This task authorizes finite deterministic functional sizing, a preview interface,
explicit local test whitelist, static checks, a normal commit/push and independent
Draft PR with inherited automatic fast CI. No 20t Native, MAIN, Grant/Claim, formal
full CI, Ready, Merge or Deploy. No R1–R9 source/results, P1, Stage B, nine/twelve
metrics, production defaults or engineering Authority changes.

## Input and approval boundary

The existing byte-verified R8 Owner source already contains the 53/53 design
counts, 53 initial occupants, 22 columns and 110 compartments. The existing
ReviewedProjectDatum interface records those as confirmed design requirements;
it retains the old calculation provenance separately. Actual employee rosters,
cabinet dimensions, human envelopes, door operation, finish/install sizes,
hygiene and time are not approved by arithmetic or JSON labels.

`RoomUseConditions` and `SizingSearch` expose integer-mm hypotheses, finite points
and declared bounds. The H5 full-flow adapter currently supports the frozen
53/53, 22-column profile; other room uses can reuse the input/search/margin
structure but require their own independently verified functional adapter.
West/south stay fixed, east/north may expand in this adapter. Mapped Portal
positions and external Site/Footprint/Access revalidation are explicit.

`preview_request()` accepts only numerical/finite conditions and search inputs.
It cannot replace Owner facts or approve a design. `preview_room_sizing()` is a
versioned application preview interface, not a production layout solver.

## Evaluation stages

1. Review a necessary section condition for this finite template.
2. Construct actual cabinets, 53 homes, aisles and Portal connections; run the
   unchanged R11 physical/door/person validators.
3. Rebuild every proposed R8 group on the actual R10 aisle network. Run complete
   entry, assigned locker retrieval, door closure, cabinet-front change, reopening,
   storage, closure and packaging departure for each shift of 53.
4. Independently measure the declared spatial margin families and exact limiting
   locations. A completed flow may still miss its margin target.
5. Keep actual engineering approval `INPUT_REQUIRED`.

No total-area shortcut, new hard room limits, Native search or changed formal
Pareto comparison is introduced. The independent R10 executor preserves R9's
protocol and movement checks but adapts its baseline snapshot factory to explicit
front/aisle padding. R9's executor and original files remain untouched.

The default finite set has 396 combinations. A is the smallest complete witness
within this tested set and is only an area comparison. B maximizes the minimum
explicitly defined planar allowance. C minimizes boundary displacement among
complete witnesses meeting a configurable 50mm hypothetical review target.
Additional finish/install sensitivities may satisfy the flow while failing the
margin goal. No global minimum area or infeasibility is claimed.

## Local execution boundary

The R9 Native exception remains unchanged in its original directory and is
referenced by hash in this delivery. R10 uses a test-only `sitecustomize` startup
guard on both OR-Tools Solve APIs. The explicit whitelist launcher supplies the
guard to its pytest process and inheriting Python children, and tests both child
API denials. A guard bootstrap failure exits rather than running unprotected.
Intentional denied API requests are not Native executions.

```bash
cd backend
uv sync --locked --python 3.12
uv run python scripts/validate_r11_r10_whitelist.py \
  --evidence ../artifacts/r11-r10-whitelist-new
```

The complete concrete file list is saved as `whitelist.json`. It includes the
R10 test, explicitly named R11 functional tests and explicitly enumerated
architecture files, with no historical Stage B/Native test directory. The
existing automatic fast workflow is unchanged and may run its original synthetic
Native tests; those are separate from R10's new calculation/local whitelist.
Do not report task-total Native execution as zero merely because R10 is zero.

## Reports and local preview

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r10_reverse_sizing_review.py \
  --output ../artifacts/r11-r10-new-review
PYTHONPATH=src:scripts uv run python scripts/serve_r11_r10_sizing_preview.py \
  --review ../docs/previews/v2.2.2/r11-r10-functional-room-reverse-sizing-r1 \
  --port 8765
```

The generator requires a new output directory and reexecutes under the startup
guard. It writes raw geometry/full-flow evidence before presentation. An internal
`--computed` option can compose an already-generated evidence set after checking
its collection, witness hashes and reproducing selected designs from current
immutable inputs; it never turns cached labels into engineering approval.

The optional server binds only `127.0.0.1`. It is a standalone preview tool, not a
production service or deployment. It accepts bounded conditions/search JSON,
serves calculated plans and exports the latest actual per-candidate witness.
No database, P1, Stage B, Owner store or historical file is written. Static HTML
can inspect saved results and export requests; all engineering calculations
remain in Python.
