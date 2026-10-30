# R11 R14 complete ten-door cabinet adapter

TASK_ID: `V2_2_2_R11_R14_OWNER_SELECTED_TEN_DOOR_LOCKER_R1`.
Base PR #333: `9501238d7a815957e8bd46831b3f9f24767ce754`.
Branch: `codex/v222-r11-r14-ten-door-locker`.

This task authorizes only a new read-only physical cabinet adapter, necessary
tests, report/figures, normal commit/push and an independent Draft PR with
automatic fast CI. No existing R3–R13 source/result is edited. The only existing
file change allowed is adding the new functional test to ci-fast.yml.

Owner selection is frozen in the adjacent source text and bound through the
existing reviewed project datum pattern. A checksum is source matching, not a
supplier approval. The photograph is unavailable; no image digest is invented.

The inventory comprises eleven complete 850×390×1800mm cabinets. Allocation of
55 compartments to each shift is a different identity from the physical cabinet.
The central cabinet has one column per shift; all 106 person/compartment bindings
are unique and four compartments remain spare. No half cabinets are used.

425mm pitch, leaf/frame placement, vertical door positions, hinge direction,
90-degree sweep, human reach, finish/installation and motion parameters are
explicit unapproved sensitivity conditions. Nominal 400×360×320mm labels are
never treated as internal clear dimensions. Actual hardware/storage remains
INPUT_REQUIRED. No 12-cabinet option is silently substituted.

The unchanged R10 movement/static checks are reused as a CLOSED-DOOR subproof.
They do not validate actual open doors. A separate required R14 check binds each
independent door and verifies its full 3-D swept sector against live people,
fixed bodies, other active doors, room boundary and reserved aisles in every
open-door event. A combined conditional flow can pass only when both subproofs
pass; unknown real hardware cannot inherit a conditional door PASS. Left-only
and mirrored 90-degree door assumptions are shown separately, not selected as
the actual product. Movement occurs only with cabinet doors closed, as in R10.

Four room/condition cases are rebuilt: C/3850mm at 20/20mm plus 50mm margin and
30/40mm plus 100mm margin. Input changes invalidate all new evidence hashes.
No old full-flow PASS is reused. R12 overlays remain reference-only and all
external Access/ergonomic/hygiene/factory approval requirements remain open.

Local tests use an explicit functional/architecture whitelist with inherited
parent/child Native startup guards. Existing synthetic Native tests in automatic
fast CI are preserved and are not claimed to be task-local zero Native.
