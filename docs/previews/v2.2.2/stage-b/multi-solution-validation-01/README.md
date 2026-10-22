# Stage B / REAL_MULTI_SOLUTION_VALIDATION_01 — actual partial-pool previews

Execution source: `4b67e01336b9b2cf73a90e0a91bda7202c73560d`.
One approved real pool and one replay completed. Actual accepted geometry,
Portal/corridor, engineering and diversity outputs match between the two pools.
Replay is not counted as additional construction.

| Preview | Independent engineering | Different physical geometry | Construction counting |
| --- | --- | --- | --- |
| [candidate-01](candidate-01/layout.svg) | 12 zones / 7 MUST / 11 non-Truck Access / coexistence / Footprint and Site PASS | Same as historical candidate-01 | Counted once in this pool; **not a new cross-run construction** |
| [candidate-02](candidate-02/layout.svg) | 12 zones / 7 MUST / 11 non-Truck Access / coexistence / Footprint and Site PASS | Different actual room geometry, including Changing | Same major process organization; **not counted as another construction** |

Both buildings are single-component, hole-free. No historical room coordinates
were injected. Geometry is from each candidate's actual JSON and application
corridors. The existing drawing projection is reused without moving any room,
dimension, route or polygon. Status captions correctly say construction-only,
11/11 non-Truck, and Truck BLOCKED; this is not a construction drawing or final P2D
engineering acceptance. Original native-renderer files and caption changes are
preserved in the experiment archive. Historical candidate-01 files are unchanged.

Per pool: 18 complete final physical assignments, 16 topology/hole rejections,
2 engineering-valid geometries, 1 counted construction / 1 major family, one
terminal UNKNOWN, 23 native calls. Both pools shared 99.806919916 charged native
seconds, 116.046543167 elapsed seconds, 444,962 observable work, 194,297,856-byte
peak RSS and 46 native calls. Resource accounting is complete. Each pool reused
one final model, stopped at the existing replay-reservation guard, and remained
below the unchanged 50-second per-pool native hard limit. The 49.9-second soft
target is not substituted for the slightly larger actually charged wall time.

Only CENTRAL X NEGATIVE was admitted. The next LINEAR X admission was denied by
the existing solver reserve guard; the remaining handoffs were not executed.
No new UNSAT conclusion is claimed for those unexecuted domains. Repeated
topology-rejected witnesses consumed most of the finite enumeration allowance.

Cross-run totals, including the old baseline: **2 different geometries, but still
1 construction / 1 major family**. The five-construction / three-family target is
not met. `STAGE_B_COMPLETE=false`, `P2D_FULL_PASS_COUNT=0`, `P2_COMPLETE=false`,
`P3_COMPLETE=false`, `VERSION_COMPLETE=false`. Quality ranking, Truck acceptance,
Owner visual approval, Ready/Merge/Deploy are not implied.

SVG SHA256:

* candidate-01: `e28ec6efe882764bf15a5315ca66683ae08e9dde7fab75f32c5f73846bd10de7`
* candidate-02: `4346cbec87de7105369c42288116210bea6659e577ccdcb0eb4a32addfdd8c36`
