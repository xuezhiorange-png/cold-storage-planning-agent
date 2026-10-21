# Balanced quality — explicit Linux RSS delivery gate

Owner-authorized mode: `LINUX_RSS_CI_GATE_AND_DELIVERY`, existing Draft PR #307,
reference HEAD `2c5b8d6a6c033267e306da494c25fe45748a3a75`.

The pending balanced Minimax strategy and its policy hashes are unchanged.
This change separates synthetic resource-state assertions from actual physical
resident-memory assertions; neither replaces the other. No factory MAIN,
replay, real Truck search, grant, default activation or engineering authority
change is authorized. The consumed MAIN slot remains consumed.

## Local selection

On macOS run the required functional, resource, architecture, Access, MCP and
P1A tests with the explicit `-m "not physical_rss_linux"` selection. Registering
the marker does **not** change global pytest addopts. The physical tests must
be reported as `NOT_RUN_ENVIRONMENT_SPECIFIC`, never as PASS or skip/xfail.

Three nodes require actual physical memory pressure: the original durable-pool
guard rejection, worker-owned memory rejection, and the live-parent isolation
test. All three receive the marker because all three already allocate real
random memory until actual RSS exceeds 512 MiB. No memory preparation, cap,
measurement, guard or original assertion in those tests is weakened.

Synthetic over-budget ledger states are explicitly identified as
`SYNTHETIC_RESOURCE_STATE_TEST`; these do not establish actual RSS overlimit.
Consumed-identity, monotonic-counter, UNKNOWN/fail-closed and time/work tests
continue through the ordinary functional regression selection.

## Required Linux gate

The existing required `backend-sqlite` Ubuntu job performs, in order:

1. One original physical RSS node in an independent existing resource worker.
2. A second fixed invocation in a second independent worker, even if run 1
   failed (unless cancelled). This is not a retry-until-green loop.
3. Verification of both single-PASS JUnit files, original node identity,
   Linux platform, distinct PIDs, same-process measurements and guard call,
   raw KiB-to-byte conversion, actual pre-guard RSS strictly above 536870912,
   retained data within the original 600–768 MiB range, original guard exception
   and ledger peak strictly above the unchanged limit.
4. Both additional physical worker-isolation regressions.
5. Complete functional regression excluding only the physical marker, followed
   by the existing architecture/lint/typecheck gates.

Raw worker output and original JUnit are uploaded on success or failure.
Any failed physical test, missing report, below-threshold measurement, skipped
test, repeated PID, or failed receipt validation fails the job. No
`continue-on-error` or shell failure suppression is used for these gates.
The final `ci-gate` already requires this job for backend changes. PostgreSQL
retains its functional tests, explicitly excluding the physical marker to avoid
uncontrolled duplicate pressure runs. Thus each workflow has exactly the two
predeclared invocations of the original pressure node, not retries.

The small receipt verifier is a test-only consumer of existing worker evidence,
not a new resource authority. Synthetic parser tests never count as actual
Linux pressure validation. Both exact-head PR and Push workflow conclusions
and their actual physical-step results must be verified before delivery PASS.

## Limits and evidence

StageALedger, PoolLease protection, 512 MiB, native/work/Host/time limits and
production defaults are unchanged. There is no unapproved memory enlargement,
RSS mock, skip, xfail, or factory solve. Local private logs, original pressure
failure, current regression results and downloaded Linux receipts remain in
the task artifact directory, not in the public source commit.

Code delivery does not establish real layout quality improvement. Stage B,
P3 and version completion remain false; P2D full-pass remains zero.
