# Guided fair validation 02 — actual construction previews

Task: `REAL_GUIDED_FAIR_MULTI_STRUCTURE_VALIDATION_02`.
Frozen execution source: `953009a9b61cea818b0b9d37b15e2c9951a752a1`.
Source PR CI `39194319468` and push CI `39194316183` both succeeded before the
single MAIN and single REPLAY were admitted. No third pool was run.

## Actual results, not synthetic layouts

MAIN: 10 checked physical assignments, 4 exact hole rejections, 6 engineering-valid
physical geometries, 4 V1 organizations, **4 V2 meaningful constructions / 3 major
families**. REPLAY: 11 assignments, 5 hole rejections, the same six valid geometries
and four counted constructions / three families. Replay is not counted again.
Candidates05/06 are distinct physical geometries but repeat candidate04's V2
functional organization and earn no extra construction/family coverage.

Across immutable historical candidates01/02 and this MAIN, exact symmetry-invariant
and V2 checks give **8 physical geometries / 6 meaningful constructions / 4 major
families**. This is construction-only cross-run coverage, NOT six P2D full-pass
layouts and NOT a rewrite of the historical two-construction/one-family receipt.
The current pool itself stopped with its five-construction target unmet.

Every preview independently passed12 zones,7 MUST,11 native non-Truck Access,
actual application corridor coexistence, original Footprint and typed-Site
validation, one building component and zero holes. Footprints were also rederived
offline from the returned application corridors, not inherited solver flags.

**CONSTRUCTION_ONLY — Truck BLOCKED — P2D NOT_FULL_PASS.** Quality ranking,
process-flow/regularity numeric acceptance and Owner visual acceptance are not
established. A room-edge direction word is not a route-turn or backtrack metric.

## Review all six actual geometries

| Preview | V2 counted | Major family | Actual room-edge directions | Building area m² | Perimeter m | Turns |
| --- | --- | --- | --- | ---: | ---: | ---: |
| [candidate-01](candidate-01/layout.svg) | Yes | F1 | E N W N N W | 2345.750462 | 493.972 | 48 |
| [candidate-02](candidate-02/layout.svg) | Yes | F2 | E N N E N W | 2308.897562 | 482.522 | 44 |
| [candidate-03](candidate-03/layout.svg) | Yes | F3 | E N W E N W | 2263.862517 | 448.986 | 42 |
| [candidate-04](candidate-04/layout.svg) | Yes | F1 | E N N W N W | 2325.531739 | 495.430 | 48 |
| [candidate-05](candidate-05/layout.svg) | **No: repeats organization04** | F1 | E N N W N W | 2325.676474 | 495.562 | 48 |
| [candidate-06](candidate-06/layout.svg) | **No: repeats organization04** | F1 | E N N W N W | 2326.751460 | 483.200 | 46 |

F1 `sha256:f7228d5e977367b6456a7f8b7140f16face50433adc23186c88593bca2fe16f6`

F2 `sha256:ac72b3817bb14de3e43376648e0c2a0e60cb09f30cf20d1e696409a0206c8bf5`

F3 `sha256:a0d221eb79443fd921237a95a34a585de80c3ed13940239c66b06c496a9698fa`

Candidate01 comes from LINEAR Y;02–06 from SPINE Y. Family classification is
derived from physical main-process adjacency, not these source-family labels.
[Candidate provenance and SHA256](candidate-manifest.json) binds each original
candidate JSON, physical geometry, native application result and review SVG.
Only status text, metadata and two legend annotations were added to the existing
projection; all drawing geometry attributes and the viewBox are unchanged.

## Replay qualification

The six engineering-valid room/Portal/corridor geometries and four accepted
constructions reproduce, including native engineering outputs and family hashes.
The original runner reports `PASS_ACTUAL_PARTIAL_POOL` for that compared subset.
Its subset omits rejected-witness cuts. The stricter offline audit finds one
additional CENTRAL X rejected hole/cut in REPLAY; the common cut prefix and all
handoff terminal outcomes match. Thus the overall receipt is
**PARTIAL_ACCEPTED_SET_PASS_REJECTED_TRACE_DIFF**, not exact full-search replay
PASS. Raw runner evidence is retained, not rewritten. No retry was performed.

## Resources and evidence boundary

Both pools together: native99.47605438029859s; elapsed132.2133106669644s;
observable work757304; pool-ledger peak RSS243957760 bytes;69 native calls.
The full execution process, including preflight/export, peaked at258801664 bytes.
Both RSS readings respect the same536870912-byte cap. All original
shared caps were respected. Three proven-base INFEASIBLE handoffs per pool
skipped two subsequent native phases each:12 skipped phase calls across both
pools. Total native calls nevertheless increased from historical66 to69 because
more valid/witness enumeration was performed; no net time-saving claim is made.

Each pool applied guidance to three final models:1740 auxiliary variables and
1740 defining constraints (exact12-room policy formula);3627 tagged guidance
work units per pool,7254 total, already included in757304. Separate guidance-only
elapsed time was not instrumented and is not claimed. No threshold was changed.

MAIN's hole rejection ratio40% versus historical fair MAIN100% is an observed
non-paired cross-version comparison. Short-circuit and guidance changed together;
this is not a causal A/B proof or general layout-quality acceptance.

[Public resource/handoff summary](resource-summary.json). Full JSON candidates,
actual Access/Footprint results, rejected witnesses/certificates/cuts, signed
instruction/source bindings, private claims and complete durable ledgers are
sealed in the local evidence archive, not committed as large/private Git data.
Candidate resource snapshots are cumulative and must not be summed as new quotas.

Stage B is not declared complete; P2D full-pass0, P3/P2/version remain incomplete.
Historical262 UNKNOWN, D01/D03/D04, all engineering Authority and budget contracts
remain unchanged. PR remains Draft. No Ready, Merge, Release or Deploy.
Execution-source CI and this documentation/preview commit's CI are separate;
the latter must be read at its own exact HEAD.
