# R11 R10 remote fast-CI coverage closure

TASK_ID: `V2_2_2_R11_R10_CI_COVERAGE_R2`.
Base: Draft PR #330, `58590723f45d8a773fc30ad551ff9f19f7456043`.
Continue `codex/v222-r11-r10-room-reverse-sizing`; update the existing Draft PR.

Owner authorizes adding the existing 41-test R10 module to the existing fast-CI
file list, preserving all prior tests, and checking C/B/3850mm saved conditions,
margins and drawings. Save remote pytest JUnit evidence to establish actual test
execution. Local validation is restricted to R10, CI contracts and static checks;
do not run the inherited synthetic Native tests locally. Those existing tests
remain unchanged in automatic fast CI and are accounted separately.

No algorithm, original R10 report/evidence, R9 boundary-exception record, P1,
Stage B, quality comparator, Authority or production default changes. No new
Native solve, MAIN, Grant/Claim, formal full CI, Ready, Merge or Deploy.

Change scope: `.github/workflows/ci-fast.yml`, this task record, and the independent
`docs/previews/v2.2.2/r11-r10-ci-coverage-r2/` evidence-consistency report. An
execution-report upload preserves evidence only; no test is skipped, replaced,
repeated or relaxed.
