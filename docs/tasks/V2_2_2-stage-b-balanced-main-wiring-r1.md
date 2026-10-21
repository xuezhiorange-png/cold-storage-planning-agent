# Balanced validation R1 — trusted wiring only

Task: V2_2_2_STAGE_B_BALANCED_LAYOUT_REAL_VALIDATION_R1_WIRING.
Base: ec324151d02aa45a3cbb555d4a14c3325e021ac7. PR307 remains Draft.

The new opt-in `run_stage_b_balanced_main.py` fixes the experiment identity to
V2_2_2_STAGE_B_BALANCED_LAYOUT_REAL_VALIDATION_R1 and selects the existing
StageBBalancedQualityFairSearchSolver. No production default or algorithm changes.
It reuses github_admission, committed source/runtime byte checks, server inputs,
the fair schedule, sealed PoolLease and original candidate/SVG exports.

## Deliberately not armed

This task authorizes development, NOT a MAIN or Owner Grant. `OWNER_SHA256` is
therefore None. Runner, Store approval, and Store open fail closed with
BALANCED_OWNER_EXECUTION_NOT_PINNED. There is no CLI/environment digest, registry,
budget, task, seed or strategy override. A generic APPROVED flag is not evidence.

After separate Owner approval, the full execution instruction's actual UTF-8
byte SHA256 must be pinned in trusted source. That subsequent source HEAD must
obtain formal exact-head PR ci.yml SUCCESS before execution. This wiring CI is
not reusable as proof for a later source-pin commit. Neither this document nor
the development instruction is a substitute execution authorization.

The actual Store/Grant and Claim must not be created during this delivery.
Constructors perform no registry writes. Tests arm synthetic bytes only under
monkeypatch and use temporary registries; never the real task slot.

## Fixed isolated contract

One MAIN only, no REPLAY/resume/retry. Cumulative Native49.9s, elapsed85s,
observable work600000, RSS536870912 bytes, Native calls100, checked assignments20,
per-Requirement Host work20000, original six Handoffs/fair reservations. Existing
49.8s/84s search margins remain conservative. Original counters account native
solver/monotonic wall time; no new CPU accounting interpretation or quota is added.

The task SHA256 directory is distinct from all historical slots. Reuse the
original durable exclusivity, monotonic checkpoint, source verification and
incomplete-accounting refusal. Specialized lease inherits the existing stricter
one-MAIN resource guards and validates the balanced, not old semiperimeter,
continuation receipt. Complete contract and both policy hashes are persisted.
No allowance is refilled per stage, room or Handoff.

## Evidence and comparison

Keep every independently accepted baseline and continuation, original canonical
hashes, transitions, nine-metric balanced snapshots, Plan/P1/Site/composition/V2
identities, original validations, raw attempts, cumulative ledger and SVGs.
Original exporter accepts an internal task label; this changes no geometry or
validation. Existing callers retain their original default task identity.

The existing balanced comparator requires same Handoff, V2 organization and
Authority plus complete exact metrics: three aspects, worst aspect, personnel
route/turns, actual perimeter/outline turns/reflex corners. Missing evidence is
not zero, score is not engineering PASS, and smaller room area is not automatic
quality benefit. No historical coordinates are seeds. Coating means packaging
box film sealing. Truck remains blocked and P2D full-pass0.

## Acceptance

Synthetic fixture tests cover unarmed entry and direct Store refusal, identity
and policy/source tamper, one-use/no replay, shared cumulative budgets, limits,
incomplete native history, old receipt rejection, current formal CI refusal,
fixed operator interface and unchanged production bootstrap. Existing policy,
export, full-CI admission and architecture regressions remain required.

Fast CI explicitly includes the new wiring tests. Full CI is requested once by
PR labeled event only after fast SUCCESS. No real MAIN, resource consumption,
Grant, Ready, Merge, Release or Deploy is part of this task.
