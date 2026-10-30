# R11 R13 H5 physical input calibration

TASK_ID: `V2_2_2_R11_R13_H5_PHYSICAL_INPUT_CALIBRATION_R1`.
Base Draft PR #332: `5b7ec33f258bacc0797148edb70766b47c47298f`.
Independent branch: `codex/v222-r11-r13-physical-input-calibration`.

Owner authorizes scoped physical-input contracts, necessary equipment checks,
fresh deterministic R10/R11/R12 review, an independent Draft PR, local explicit
functional/architecture tests, static checks and inherited automatic fast CI.
No new 20t Native solve, MAIN, real Grant/Claim, formal full CI, Ready, Merge or
Deploy. All original P1/Stage B, comparators, MCP, production defaults and
historical files are immutable. R9's earlier Native boundary exception remains
an exception; neither it nor R10/R11/R12 evidence is rewritten.

## Sources and review boundary

`physical_room_calibration_review` extends the frozen R12 owner-input template.
It binds exact project/H5/template hashes, integer-mm fields, source file bytes,
document scope, date if supplied, and field-level locations. Actual equipment,
net cell dimensions, clothing, reach and process data are currently missing.
Their values remain null and their derived review state is INPUT_REQUIRED.

Supplier/measurement proposals and hypotheses remain distinguishable. Source
byte integrity is not semantic document review or Owner confirmation. Known
R10 regression documents cannot be relabelled as actual supplier sources.
There is no JSON `approved` or status-to-review conversion. The existing
`ReviewedProjectDatum` type is accepted only at the trusted application review
boundary, with matching field/value/unit/project/document/hash/location. The
CLI and editor do not construct this type or issue approvals. No new approval,
signature, registry or credential system is introduced.

Owner facts remain: packaged mass 20000kg/day, two design shifts of 53,
53 initially simultaneously in the room, 106 independent storage places,
22 five-tier columns/110 working capacity, no bench, no separate changing
station, and personal-cabinet-front standing change. P01/P02 count as one H5.
Design slot identities are not an employee roster.

## Reused calculations and explicit adapter limitations

`RoomUseConditions`, `evaluate_sizing_point()`, the original static/3-D door,
full two-shift movement and located margin checks remain unchanged. Every
compared room receives a fresh calculation, never a historical flow PASS.
New source/review fingerprints bind the entire conditions and evidence. Changes
to parameters, sources, scope, review or adapter version invalidate old use.
Checksums establish integrity/matching only, never engineering approval.

The current existing adapter has uniform tiers, representable unit grouping,
left 90-degree reference hinges/frame/leaf dimensions, a conservative continuous
yaw square, four requested operators and explicit door sequence. It cannot
silently express arbitrary equipment, nonuniform layers or room-door motion.
Unsupported parameters are reported as UNSUPPORTED_PHYSICAL_CONFIGURATION.
Reference reach and dimension restrictions are adapter limits, not new norms or
P1/Owner requirements. Unreviewed body/activity/waiting/aisle envelopes cannot
be reduced below the existing reference to manufacture a passing layout.

Per-face adverse construction tolerance is added explicitly to the finish
inset; this is a conditional budget, not an approved construction tolerance.
Panels, compartment clear dimensions, clothing/partition envelopes, operation
heights and clear openings have separate necessary checks. Capacity arithmetic
110 >= 106 never establishes storage usability. Missing review and ergonomics,
hygiene, door hardware or garment evidence retain INPUT_REQUIRED.

The same two parameter sets are used at BOTH 26331x3550 and 26331x3850mm:
20/20mm base finish/installation plus 50mm spatial padding; 30/40mm plus 100mm.
Both are unapproved regression conditions. Effective installation/aisle/standoff
values include the unchanged R10 padding and are exposed separately.
No cross-condition global optimum or safety ranking is claimed.

R12 overlays are freshly reconstructed from both candidate records. They are
independent of interior equipment parameters while these outer bounds remain
fixed; this invariance is explicit, not external Access approval. B retains the
original 3.338m2 corridor and 0.982m2 no-build conflicts and is not recalibrated.

## Reproduce without Native

Use the repository's Python 3.12 locked environment:

```bash
cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r13_physical_calibration.py \
  --output ../artifacts/r13-fresh-review
uv run python scripts/validate_r11_r13_whitelist.py \
  --evidence ../artifacts/r13-fresh-validation
# For a proposed input, also supply --input <json> --source-dir <original-docs>.
# Every output directory must be new; historical preview roots are rejected.
```

The inherited startup guard blocks both CP-SAT Solve aliases in the report
process and ordinary Python children. Only listed R11 functional/architecture
files are used locally, never the broad Stage B/Native directory. Existing
synthetic Native tests remain in automatic fast CI, separately reported from
this task's zero new functional/20t Native execution.

The editor hashes local files, exports an UNREVIEWED draft and marks frozen
witnesses stale on edits. Python performs all engineering calculations. The
editor provides no database, MCP, approval or production write path.
Actual calibration remains INPUT_REQUIRED while data is missing/unreviewed;
even a complete typed parameter recheck is not functional or engineering
approval. Engineering approval and factory applicability remain NOT_EVALUATED.
