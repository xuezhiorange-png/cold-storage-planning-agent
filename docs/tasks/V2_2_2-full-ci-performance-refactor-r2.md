# Full CI execution restructuring R2

Base: `9c13a134b6008c8960996eedf016dc2b4754a013`. This independent branch
does not update PR #307, production algorithms, engineering authorities, execution
authorization or historical ledgers.

## Measured baseline

GitHub run `39633254144` reports SQLite pytest 8810.17 seconds and PostgreSQL
pytest 7654.67 seconds. Workflow started 2026-10-21 16:16:18 UTC; its last
job completed at 18:45:01 UTC: 8923 seconds wall time. Run updatedAt is not
used as the test completion timestamp.

SQLite log progress intervals around candidate-validation and exact-placement
files are 3824.968 and 1861.473 seconds. PostgreSQL intervals are 3861.735 and
1884.477 seconds. These are NOT individual test/fixture timings. The old run
does not provide such timings; this change records them explicitly.

## Preserved assertions, reduced setup

The S3 and S4 modules previously created separate identical baseline placement
fixtures. They now reference one session fixture registered once as a pytest
plugin. The S3 determinism test still performs a fresh full enumeration. The S4
validation fixture still calls the real validation entry, including its independent
server-side enumeration and real Access/Truck/P2D chain. No production function
is replaced by a cached result, and the original 60000-node budget is unchanged.

The two modules' computation/import closure has no database dependency. Database
fixtures are not requested; global SQLAlchemy imports and the CJK font prerequisite
remain. The composition fixtures actively reject database connections and SQL;
guard tests exercise that rejection. Only these exact two modules are shared
between the backend matrices. All other original PostgreSQL selection remains.

Default-budget enumerations in these two modules: previously four per backend,
eight per full workflow; now three in the single composition lane. This is a
source-derived count; observed runtime and fixture timing receipts must be used
for performance claims. Small bounded test enumerations remain unchanged.

## Execution graph and completeness

SQLite has four general partitions, one composition fixture-affinity lane, and
one architecture lane. PostgreSQL has four general partitions with an independent
PostgreSQL service for every runner, plus its original integration and ten-round
race acceptance job. General partitions preserve module fixtures rather than
multiplying setup per test. Lint and mypy run independently.

Each partition records the full original collection AFTER the original marker/
keyword selectors, its selected nodes, fixture dependencies, actual setup/call/
teardown outcomes, durations and process exit status. The mandatory coverage job
requires identical original collections across shards, an exact disjoint union,
and an execution report for every selected node. Only the two named modules may
be delegated from PostgreSQL, and their nodes must have actually run in SQLite.
Existing skip reports stay visible and are not counted as passes.

`backend-sqlite`, `backend-postgresql`, `ci-gate`, and `fast-ci-gate` names remain.
All required parallel dependencies must succeed; missing/skipped/cancelled/failed
jobs reject acceptance. The original two Linux RSS workers and verifier remain
in backend-sqlite, preserving the existing admission consumer. No admission code
changes are necessary. Specialized manual jobs and their authorization remain.

## Performance boundary

The target is under 30 minutes, not an acceptance shortcut. Real candidate
validation remains an indivisible expensive call with engineering checks intact.
If it dominates after duplicate removal, report its measured fixture duration and
the missed target; do not silently reduce its budget or replace it with a mock.
No guarantee of a 30-minute result is made before the single full CI measurement.

Two pre-existing pilot test files have mechanical import/format repairs solely
because the baseline fails the existing global Ruff/format gates. Their assertions
and execution logic are unchanged.
