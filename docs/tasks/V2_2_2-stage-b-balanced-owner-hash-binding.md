# Balanced validation R1 — Owner byte binding, not execution

Task: V2_2_2_STAGE_B_BALANCED_LAYOUT_REAL_VALIDATION_R1_OWNER_HASH_BINDING.
Base: baa85cad4ffa943fef40a833504e52e5576ecc18. Supersedes only the unpinned
state described by the earlier wiring delivery; historical evidence is unchanged.

The private normalized UTF-8/LF instruction has actual byte SHA256:
`83ef14b7f0c62e685cbf3cc8556348616d1645207d027bc16042dd88dc7bb055`.
The original file remains in the authorized local evidence directory, not Git.
No new hash algorithm, caller digest, approval flag or signature system is added.

The instruction retains the fixed experiment identity, one MAIN, no replay,
retry, additional pool or budget extension. Shared caps remain Native49.9s,
elapsed85s, work600000, RSS512MiB, calls100, checked assignments20, with existing
fair reservations and per-requirement host work20000. It includes existing
authority, source, dependency, schedule, baseline-preservation and comparison
requirements. The base reference identifies development lineage, not permission
to execute a successor commit. Neither the file nor its own digest embeds the
future final commit SHA, avoiding a source/hash self-reference.

## Separate gates remain mandatory

This delivery pins bytes only. It does **not** issue or consume a Grant/Claim or
authorize MAIN. After this commit's exact-head formal PR CI succeeds, Owner must
separately reconfirm that final HEAD and authorize the existing trusted issuance
operation. The actual final source/runtime/Plan/P1/Site/schedule/policy binding
belongs in that existing durable decision. An old HEAD's CI or an old task's
decision is not transferable.

The operator now only reads and consumes an already issued, unclaimed decision
from the existing fixed trusted registry. It never calls `approve` itself. The
existing original decision verifier checks Owner bytes, source HEAD and files,
dependencies and resource caps; the adapter additionally validates fixed task,
policies and fresh server-derived binding. Filesystem administrators remain
outside the original trust boundary: SHA proves bytes, not a new professional
approval or external signature. No external signing credential is required by
this repository's existing protocol, and none is invented here.

Absent Grant fails before server inputs/output creation. Any execution residue
(Claim, ledger, lock, journal or unexpected file) requires inspection; no reset,
replacement slot or automatic retry exists. The production bootstrap, solver,
Minimax policy, budget, engineering validations and full-CI admission are unchanged.

Tests use only synthetic instructions/temporary registries/mocked pool execution.
They cover correct bytes without a Grant, read-only Grant loading, old identity,
wrong hash, budget/source tamper, consumed/incomplete slots, independent full-CI
admission, shared accounting and unchanged defaults. Local real RSS is not run;
the formal PR CI retains its two independent actual Linux RSS validations.

Only one labeled full PR CI is requested after fast CI succeeds. Full CI pending
is not success. This task stops without Grant issuance or MAIN even if CI passes.
