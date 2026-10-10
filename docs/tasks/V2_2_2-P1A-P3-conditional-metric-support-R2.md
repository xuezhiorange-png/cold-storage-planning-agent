# V2.2.2 P1A P3-R2 — conditional geometry-aware metric support

Task: `V2_2_2_P1A_P3_CONDITIONAL_METRIC_SUPPORT_R2`.
Start: `ff4626fce1d88f9860b64cd183af3ce1db21a26a`, same Draft PR #307.
PR #306 remains a frozen diagnostic reference; none of its implementation is used.

## Contract decision

ADR-050 supersedes the original P3 static-domain exclusion rule. P2's complete
finite event domain is not a conservative cover of normal exact construction:
the real pre-P3 complete candidate has 0/7 P2 memberships. Keep the public P2
policy and hash; add a separate server-owned conditional proof query.

`SUPPORTED` requires a concrete exact-valid pair certificate under current
authority, current fixed endpoint geometry, all placed MUST neighbors and
composition intent. `UNKNOWN_SUPPORT` means the query cannot prove capacity;
it proceeds without a false positive-capacity claim. `PROVED_NO_SUPPORT` requires
an independently rechecked analytic necessary-origin-space contradiction, never
an event miss or scan-cap exhaustion.

For each unchanged construction footprint, an integer-mm origin-space cover
uses the site bbox, exact overlap exclusions and ALL fixed MUST face intervals.
This is a necessary SUPERSET, independent of future event-anchor introduction.
Ignoring concavity, obstacles and intent only enlarges this negative relaxation.
Empty across every construction footprint is sound for the existing constructor,
not a global continuous/flexible engineering infeasibility claim. Incomplete
authority or box-operation overflow cannot authorize a negative certificate.

Neither endpoint fixed: static-positive or symmetric dynamic pair witness.
One fixed: exact actual endpoint plus normal shared-face/event partner origins.
Both fixed: direct actual-geometry certificate, without static membership.
All complete candidates need seven direct-final certificates in addition to the
unchanged final hard validators. All partials update all reservations, but
UNKNOWN is explicitly tracked; pairwise witnesses for unplaced shared roles do
not prove a jointly compatible assignment or whole-building capacity.

## State, cache and boundary

Identity binds edge, site/obstacles, dimensions/shapes, handoff, full placed
geometry and revision. Only positive geometry is reused after revalidation;
no negative cursor survives a domain change. Immutable parent states protect
siblings. Advisory partner candidates are offered only with exactly one fixed
endpoint; normal fallback and unique-candidate placement accounting remain.

Positive witness probes have explicit per-edge limits: 256 static pairs and 256
dynamic origin/pair events per update. Exhaustion never proves absence. The
analytic relaxation has an 8192-box resource guard; overflow is incomplete, not
an empty cover. Capacity-query work is separately counted, never placement nodes.

Seven immutable static domains use a bounded server-owned pure cache; cache
keys include edge, all shapes, boundary, obstacles and cap. No public API accepts
a caller runtime domain/certificate. No runtime slot set is persisted.

P0/P1 coordinate-free contracts, P2 realization policy, shared shape algorithm,
site/hard obstacles, graph MUST, 12 roles, zone order, families, scheduler and
60000 placement-node budget are unchanged. No role-specific seed is restored.
The legacy V1 static query is diagnostic membership only, not production capacity
authority; its negative label is now explicitly `NO_STATIC_EVENT_DOMAIN_MEMBER`.

## Verification record

Checkout HEAD and PR matched. Standard Git status eventually returned empty;
staging was clean. Initial read-only inspection was delayed by macOS file reads,
not an index lock. No Git metadata repair was performed.

The independent original-source replay at
`112f30115d201dd8ef2daf541f5352b92d2154fe` recovered the genuine control hash
`sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47`:
50621 nodes, 11 attempts, family maxima 12/6/6. Historical coordinates are used
only to inspect its 13 prefixes, never as production seeds.

The initial focused run had two failures because two integration assertions
required the superseded static-exclusion behavior. They were explicitly revised
to require honest UNKNOWN on static absence and a direct certificate for actual
valid final geometry. Final focused plus new architecture run: 45 passed. This
includes independent all-integer-origin enumeration for multiple footprints and
two fixed MUST neighbors, and reconciliation of every query evaluation by source.
Full backend Mypy passes for 403 source files; whole-backend Ruff and formatting
pass (911 Python files). AST comparison preserves every pre-existing top-level
placement function except the explicitly revised support integration in
`_search_one`; zone order, scheduler and ordinary geometry generators are frozen.

Three early captures were interrupted before any placement result: one to
complete per-source query evaluation counters, and two for evidence-runner-only
constructor/signature corrections. They are not acceptance evidence. The fixed
runner's real START geometry preflight verifies all 12 construction prefixes
against unchanged hard geometry, shape authority and composition predicates.
The terminal direct evidence runner captures two full production placements,
START prefix compatibility, static runtime parity, independent public P2 replay,
determinism, per-edge support states, query/build cost and process peak RSS.
Performance observations are excluded from deterministic artifact comparisons.

Terminal canonical, regression and exact-head CI results are recorded in the
task evidence and final handoff; no pending check is implied PASS here.

First completed canonical replay: one complete candidate
`sha256:554e77dd6e5b0da7bdecb97558bc4f16a8b1bd5c073ff18b080714a6462375ab`,
50260 placement nodes, 11 attempts; family maxima Linear/Central/Spine = 12/5/5.
The complete candidate has all seven DIRECT_FINAL certificates. There are 1282
analytically justified candidate prunes and zero accepted proved-zero partials.
However 213 accepted partials contain UNKNOWN; only 39 accepted partials have
pairwise support on every edge, and even those are not a joint unplaced-role
assignment proof. Candidate recovery is not a proof of all-partial capacity.

Two full canonical placement captures are field-for-field equal (including
node accounting, support/prune sequence digests and final certificates).
The 13 real control prefixes have no PROVED_NO result. Prefixes 4 and 5 each
retain one UNKNOWN; all other prefixes have seven SUPPORTED edges. Final direct
certificates are 7/7 and control static membership remains 0/7.

The recovered geometry equals the real control geometry byte-for-byte after
canonical geometry projection (digest
`sha256:e747ced3e1b271e80448b0fcafd7e1e60aa86e3d54982d0d25a7d56b5548f8fd`).
The new candidate hash differs because construction provenance changed, not
because rooms were repaired or historical coordinates were injected.

The first broad regression invocation loaded one obsolete provenance assertion:
Office must have enumerated DOMAIN anchors before acceptance. A successful
verified dynamic partner hint can legitimately return before DOMAIN enumeration.
Only that source assertion is revised to require a DIRECT_FINAL certificate and
an actual accepted hint record when DOMAIN count is zero; all dimension, site,
obstacle, non-overlap, MUST and final intent assertions remain. Seven exact
certificate/actual-room matches are additionally asserted. The actual captured
production candidate passes the revised entire hard-subset test. A fresh broad
regression invocation runs on the final assertion, not the superseded one.

The first broad invocation ended with 958 passed, 16 skipped and two failures
(4438.69 seconds). Besides that superseded provenance assertion, an existing
architecture subprocess selected system `python3` without pytest. The exact
failing architecture check passes with the installed test environment prepended
to PATH (1 passed, 20.05 seconds); no assertion or unrelated code was changed.
Both initial failures are retained as execution history, not hidden as successes.

Final-source broad regression terminal result: 1001 passed, 16 skipped and one
failure (3664.94 seconds), solely the same system-Python subprocess environment
issue. The revised emitted-candidate hard-subset test passes. A separate complete
architecture replay with the installed test environment on PATH terminates with
763 passed, 16 skipped and zero failures (1117.88 seconds). Thus every scoped
regression has a passing result; the original broad command is not relabelled
all-green. Existing optional skips and deprecation warnings remain disclosed.
The ignored evidence-runner path also passes explicit Ruff lint and format checks.

Support accounting: 10815 edge checks = 7897 SUPPORTED + 2564 PROVED_NO + 354
UNKNOWN. Candidate prunes are 1282, not 2564 extra placement nodes. Evaluation
sources reconcile exactly: 426133 static pairs + 355158 dynamic origin events +
394861 dynamic pairs + 2287 reuse checks + 5803 direct checks = 1184242.

The independent public P2 invocation completed with all 42 realizations and
unchanged hash `sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`.
Each of seven runtime counts/digests equals that actual public result; total
runtime slots = 642482. Runtime cache misses are 7 then 0 for the two placement
invocations, with immutable geometry reused across all six compositions.
Source fingerprint remained unchanged throughout the complete capture:
`sha256:e9b1901ca2af9fe245285bb1e1b7ba3e694f751f1112de5ebe47d07c17577d04`.

Observed cost (not deterministic artifact fields): first build 1477.70 seconds,
first capacity queries 165.85 seconds, first whole placement 1674.73 seconds;
warm build 0.024 seconds, second queries 156.24 seconds, second whole placement
185.96 seconds. Independent P2 replay took 1652.37 seconds. Whole-runner peak
RSS was 334348288 bytes on macOS; this is not an exclusive domain-memory claim.

Evidence: `docs/tasks/evidence/v2_2_2_p1a_p3_conditional_metric_support_r2/xinzhao_conditional_metric_support.json`
(approximately 478 KB; counts, digests, actual partial/final proofs, never the
642482-slot runtime set). The containing commit binds the evidence; its literal
HEAD and terminal PR/Push CI are reported in PR #307 and the final handoff,
avoiding a self-referential commit hash inside its own tracked evidence.

## Acceptance and stop

### Git delivery pause

After local verification, normal scoped `git add` failed with exit 128 because
`/Users/charles/Documents/智能agent开发/.git/index.lock` exists. Read-only inspection
reports size 0, mtime `2026-10-08 03:53:59 CST`, and no open holder observed by
lsof. The separately running own `git diff --check` started at 10:38:39 CST and
is still reading an existing file; it did not create a lock dated 03:53:59.
The prior lock-quarantine authorization was timestamp-specific and is not reused.
No lock is moved/deleted, no process is killed, staging remains empty, and no
commit, push, PR edit or R2 CI trigger has occurred. Delivery awaits fresh Owner
authorization and renewed holder/writer checks; exact-head CI is still missing.

### Authorized delivery recovery

Owner subsequently authorized `P3_R2_SINGLE_INDEX_LOCK_QUARANTINE` for this
single lock. Renewed checks confirmed HEAD/branch unchanged, no lock holder or
current-repository Git writer, device `16777232`, inode `118909738`, size zero,
and unchanged mtime `2026-10-08 03:53:59 CST`. An exclusive same-filesystem
atomic `renamex_np(RENAME_EXCL)` preserved the file at
`.git/p3-r2-index-lock-quarantine-zttj7zqz/index.lock.stale-20261008-035359`.
Post-rename device/inode/size/mtime were identical and the original path absent.
No file was deleted, no process killed, and no other Git metadata repaired.
PR #307 still pointed to the expected starting HEAD; PR #306 remained frozen.
Commit, normal push and exact-head CI closure are bound by the containing commit,
PR #307 delivery section and final handoff rather than a self-referential SHA.
Regardless of delivery/CI outcome, Owner requires `RESULT=PARTIAL` and
`P3_COMPLETE=false`: 213 accepted partials have UNKNOWN capacity and joint
capacity for unplaced shared roles is not proven.

### Second-lock recovery and serial delivery

The first recovery did not reach staging: an outstanding ordinary `git diff
--stat` (PID 81771) created a second index lock, and scoped add failed with
exit 128. No commit or push occurred. The active lock was not moved and no
process was signalled. Subsequent read-only audits found the holder exited,
the lock remained, transient background Git processes could not be attributed,
and a later bounded 55-second observation was quiet. Data volume free space
was approximately 8.4 GiB (98% used); the I/O root cause remains unknown.

Owner independently authorized only device `16777232`, inode `119269342`,
size `0`, mtime_ns `1791429893852332803`. Two fresh safety checks approximately
6 seconds apart and an immediate pre-rename check found no Git process,
lock holder or index writer. Exclusive atomic rename preserved this identity at
`.git/p3-r2-second-lock-quarantine-2f242efy/index.lock.inode-119269342`.
Post-check found no new Git process or lock. The first quarantined lock was
not inspected or modified. All 12 expected R2 files were backed up, preserving
relative paths and verifying SHA256, under
`/var/folders/2p/fmk6_mt12l57gnwl95d8nt7c0000gn/T/p3-r2-12-file-backup-39ka52xp`.
Subsequent read-only Git commands use `GIT_OPTIONAL_LOCKS=0`; Git writes are
serial and scoped. Any new lock anomaly or I/O timeout requires stopping,
not another automatic quarantine. Final commit/push/CI results are reported
in PR #307 and the final handoff; PARTIAL acceptance is unchanged.

Mechanism tests do not establish business success. Zero complete candidates is
FAIL. A recovered complete candidate must have seven direct-final certificates.
Accepted UNKNOWN partials must not be called proven positive capacity; if the
stronger all-partial capacity claim remains unresolved, report PARTIAL and do
not claim P3_COMPLETE. No Access/Truck/P2D business run, selection, next phase,
Ready, Merge, tag, release or deployment follows automatically. Existing standard
CI integration tests are regression execution, not next-stage authorization.
