# Local validation boundary exception

The agent mistakenly included the unchanged Stage B fast-regression modules in local validation. Their resource workers run in child Python processes; the parent-only Native API prohibition did not propagate. Existing tiny synthetic CP-SAT tests executed, including the R4 729-assignment enumeration and witness tests. The broad run was interrupted after 92 passing tests; this partial run is not counted as completed regression. Exact Native-call count was not instrumented and must not be stated as zero.

No frozen 20t solve, MAIN, real Grant/Claim or formal full CI was executed. R9 spatial-template evaluation itself is deterministic and uses no Native API. Subsequent local tests are restricted to R11 functional, architecture and CI contracts. The inherited automatic fast-CI suite remains intact, including its original synthetic tests. This note records a scope deviation; it does not erase or approve it.
