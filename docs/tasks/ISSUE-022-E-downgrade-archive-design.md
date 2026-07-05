# ISSUE-022-E Design Contract — Downgrade Archive and Historical-Read Integrity

> **Frozen contract scope:** Issue #22 §10 (Downgrade and historical-read
> integrity) and §11 SQLite/PostgreSQL parity.
>
> **Status:** FROZEN
> **Frozen in this PR:** `codex/issue-22e-downgrade-archive` (pending)
> **Issue:** #22 (Open — §10 to be closed by merge of the implementation PR)
> **Parent design contract:** #22 + PR #23 at `b30ccf8ffde54eb40081b514a1d7eaa1615417ae`

## Goal

Production `SchemeRunRecord` rows persist with full source identity
(`source_binding_id`, `combined_source_hash`, 5× slot ids, weight-set
identity, etc.) at the time the SourceBinding is committed.  This contract
guarantees that, **at any later time**:

1. If the online `SourceBindingRecord` is still queryable, the
   historical-read resolver verifies the online source and returns it.
2. Otherwise, a verified `production_source_archives` row preserves a
   canonical snapshot and the resolver verifies against the archive.
3. If neither online binding nor verified archive exists, the resolver
   fails closed.
4. If the archive payload or its hash has been tampered with, the
   resolver fails closed.
5. Alembic downgrade past the archive migration is blocked while any
   production `SchemeRunRecord` exists without a verified archive.

This is fail-closed by design.  No silent fallback, no demo path, no
legacy lookup.

## Out of scope

- Resuming Task 11 Phase B / starting Task 12 / Phase C / Phase D.
- Modifying PR #21 (Task 11).
- Closing Issue #22.
- Back-archive flows for pre-existing production `SchemeRunRecord` rows.
- Changes to Scheme scoring / engineering formulas / demo fallback.
- Changes to the frozen `SourceBinding` semantics from PR #28 / PR #30.
- Removing the `SourceBindingRecord` ONLINE path (it stays as the
  primary read source).

## Data model

New table `production_source_archives` (SQLite + PostgreSQL parity):

| Column                                | Type / constraints                                |
|---------------------------------------|--------------------------------------------------|
| `id`                                  | `String(36)`, primary key (uuid)                 |
| `scheme_run_id`                       | `String(36)`, FK → `scheme_runs.id`, **UNIQUE**  |
| `source_binding_id`                   | `String(36)`, FK → `orchestration_source_bindings.id`, nullable (legacy) |
| `source_contract_version`             | `String(50)` (mirrors SchemeRun.source_contract_version) |
| `archive_schema_version`              | `String(50)`, pinned to `"SchemeSourceArchiveV1"` |
| `archive_payload`                     | `JSON` — canonical form                          |
| `archive_hash`                        | `String(128)`, hex SHA-256                       |
| `combined_source_hash`                | `String(128)` (mirrors SchemeRun.combined_source_hash) |
| `weight_set_revision_id`              | `String(36)`, FK → `scheme_weight_set_revisions.id`, nullable (legacy) |
| `weight_set_content_hash`             | `String(128)`, nullable (legacy)                 |
| `binding_schema_version`              | `String(50)`, nullable (legacy)                  |
| `execution_snapshot_id`               | `String(36)`, FK → `project_version_execution_snapshots.id`, nullable |
| `coefficient_context_id`              | `String(36)`, FK → `coefficient_contexts.id`, nullable |
| `orchestration_identity_id`           | `String(36)`, FK → `orchestration_identities.id`, nullable |
| `authoritative_attempt_id`            | `String(36)`, FK → `orchestration_run_attempts.id`, nullable |
| `orchestration_fingerprint`           | `String(128)`, nullable                          |
| `created_at`                          | `DateTime(timezone=True)`, UTC aware             |
| `created_by`                          | `String(120)` — actor id                          |
| `reason`                              | `String(50)`, reserved enum: `'completed'` (this PR only writes this), `'pre_downgrade'` (reserved) |

Constraints:

- `UNIQUE(scheme_run_id)` — exactly one archive per SchemeRun.
- Application-side verification of `archive_hash` (no SQL CHECK that
  recomputes the hash — SQLite and PostgreSQL JSON canonicalisation
  diverge in semantics, so the application owns the hash).
- A `CHECK` ensures `archive_hash` is either NULL or a 64-character
  lowercase hex string — defence in depth at the storage layer.

Indexes:

- `PRIMARY KEY (id)`
- `UNIQUE (scheme_run_id)`
- `INDEX (source_binding_id)` — used by the online fall-back lookup.

Five CalculationRunRecord rows are NOT mirrored as columns; they live
inside `archive_payload["source_slots"]` as an ordered list of
`[[slot_name, {calculation_id, result_hash}], ...]` tuples in the
canonical order
`["zone", "cooling_load", "equipment", "power", "investment"]`.

## Hash contract

```
archive_hash = sha256_hex(canonical_json_v1(archive_payload))
```

Where `canonical_json_v1` is the v1 algorithm frozen in
`backend/alembic/helpers/frozen_scheme_source_archive_v1.py`.  It is
mirrored on the application side at
`backend/src/cold_storage/modules/orchestration/application/canonical_archive_v1.py`
to ensure both the migration preflight (rarely) and the runtime builder
(common path) hash identically.

### Canonical JSON rules

| Aspect | Rule |
|--------|------|
| Key ordering | `sort_keys=True` |
| Nested dict | recursively sorted |
| Top-level slot order | **Frozen**: `["zone", "cooling_load", "equipment", "power", "investment"]`. The payload's ``source_slots`` field is **always** an ordered JSON-safe list: `[["zone", {calculation_id, result_hash}], ["cooling_load", {calculation_id, result_hash}], ["equipment", ...], ["power", ...], ["investment", ...]]`. The hash commits to this exact order. A reverse-order, permuted-set, or dict-shaped ``source_slots`` is rejected at validation time (round 9 P1-1) before the hash recomputation runs. Tests pin: ordered-list emission, reverse-order rejection, swapped-neighbours rejection, missing-slot rejection, extra-slot rejection, dict-shape rejection, per-slot missing-`result_hash` rejection. The validator is `validate_archive_payload_v1(payload)` in `canonical_archive_v1.py` (round 9). |
| Decimal | `str(decimal_value)` (base-10), never `float()` |
| datetime | UTC-aware ISO format (`...isoformat()`); naive datetimes are coerced to UTC via `ensure_utc_aware` |
| UUID | `str(uuid_obj)` |
| `None` | JSON `null`; required keys may carry `None` (legacy rows) |
| **Binary float** | **Recursive reject**: any `float`/`inf`/`nan` anywhere in the value tree → `ValueError` |
| **Unknown object type** | `TypeError("Object of type X is not JSON serializable")` |
| Silent `default=str` fallback | **FORBIDDEN** |

### Schema of `archive_payload`

```python
{
  "schema": "SchemeSourceArchiveV1",   # pinned identity
  "scheme_run_id": str,
  "source_binding_id": str | None,
  "source_contract_version": str,
  "binding_schema_version": str | None,
  "combined_source_hash": str | None,
  "weight_set_revision_id": str | None,
  "weight_set_content_hash": str | None,
  "weight_set_generator_compatibility_version": str | None,
  "execution_snapshot_id": str | None,
  "coefficient_context_id": str | None,
  "orchestration_identity_id": str | None,
  "authoritative_attempt_id": str | None,
  "orchestration_fingerprint": str | None,
  "source_slots": [
    ["zone",         {"calculation_id": str, "result_hash": str}],
    ["cooling_load", {"calculation_id": str, "result_hash": str}],
    ["equipment",    {"calculation_id": str, "result_hash": str}],
    ["power",        {"calculation_id": str, "result_hash": str}],
    ["investment",   {"calculation_id": str, "result_hash": str}],
  ],
  "project_id": str,
  "project_version_id": str,
  "generator_compatibility_version": str,
  "captured_at": "<ISO-8601 UTC string>",
}
```

The 19 keys listed above are required (and no extra keys are
permitted).  Round 9 P1-1 enforces this contract via
``validate_archive_payload_v1(payload)``: missing keys and extra keys
each raise ``SourceArchiveBuildError`` *before* the hash recomputation
runs.  ``source_slots`` is the canonical ordered list above; any
reordering, permutation, dict shape, missing slot, extra slot, or
per-slot payload missing ``result_hash`` is rejected.

### Hash coverage

The hash covers the entire `archive_payload` dict, which includes:

- `combined_source_hash` ✓
- 5 × `source_slots[i][1].calculation_id` and `source_slots[i][1].result_hash` ✓
- `weight_set_revision_id`, `weight_set_content_hash`,
  `weight_set_generator_compatibility_version` ✓
- `binding_schema_version` ✓
- `execution_snapshot_id`, `coefficient_context_id`,
  `orchestration_identity_id`, `authoritative_attempt_id`,
  `orchestration_fingerprint` ✓
- `project_id`, `project_version_id`,
  `generator_compatibility_version` ✓
- `captured_at` ✓

No `signature` / `nonce` / `signing_key` keys appear in the payload.
The hash is self-referential — only the payload itself is hashed; the
`archive_hash` column is computed from the payload and stored beside it.

## Historical-read resolver contract

`resolve_scheme_run_sources_for_history(scheme_run_id: str) -> ResolvedSchemeRunSources`

Lives at:
`backend/src/cold_storage/modules/orchestration/application/historical_source_resolver.py`

Returns one of these result types (new file, same module):

- `LegacySourceBundle` — only for `source_mode='legacy'` SchemeRuns
- `VerifiedOnlineSourceBundle` — verified online
- `VerifiedArchiveSourceBundle` — verified archive
- raises one of the structured errors below

### Decision tree

```text
input: scheme_run_id

1. Load SchemeRunRecord by id.  If absent → raise SchemeRunNotFoundError
   (existing error class; not added by this contract).

2. If SchemeRunRecord.source_mode == "legacy":
     → return LegacySourceBundle
     (legacy is not required to have a binding or archive)

3. If SchemeRunRecord.source_mode == "production":
   a. Try:
      i.   Load SourceBindingRecord by SchemeRunRecord.source_binding_id.
      ii.  Load its 5 CalculationRunRecord rows and verify each
           result_hash matches the binding's slot map.
      iii. Verify SchemeRunRecord.source_binding_id / source_contract_version /
           binding_schema_version / weight_set_revision_id /
           weight_set_content_hash / weight_set_generator_compatibility_version /
           combined_source_hash / orchestration_identity_id /
           authoritative_attempt_id / orchestration_fingerprint /
           execution_snapshot_id / coefficient_context_id / 5 ×
           *_calculation_id / 5 × *_result_hash match the loaded
           binding and its slot records.
      iv.  SUCCESS → return VerifiedOnlineSourceBundle
   b. If any i–iii step fails or records are missing → fall through to (c).
   c. Load ProductionSourceArchiveRecord by SchemeRunRecord.id.
      i.   If missing → raise SchemeRunHistoricalSourceUnavailableError.
      ii.  If archive_payload is missing required keys or has extra
           forbidden keys → raise SchemeSourceArchiveIntegrityError.
      iii. Recompute canonical_json_v1(loaded archive_payload).hexdigest().
           Compare to stored archive_hash.  Mismatch →
           SchemeSourceArchiveIntegrityError.
      iv.  If archive_schema_version != "SchemeSourceArchiveV1"
           → raise SchemeRunHistoricalSourceTamperedError with
              field="archive_schema_version".
      v.   Verify SchemeRunRecord.5 × *_result_hash columns match
           archive payload's source_slots[*][1].result_hash (each
           ordered list entry is `[slot_name, {calculation_id,
           result_hash}]`).  Mismatch →
           SchemeRunHistoricalSourceTamperedError with field
           = one of "zone_result_hash" / "cooling_load_result_hash" /
                  "equipment_result_hash" / "power_result_hash" /
                  "investment_result_hash".
      vi.  Verify SchemeRunRecord.combined_source_hash matches
           archive_payload["combined_source_hash"].  Mismatch →
           SchemeRunHistoricalSourceTamperedError with field
           = "combined_source_hash".
      vii. Verify SchemeRunRecord.weight_set_content_hash matches
           archive_payload["weight_set_content_hash"].  Mismatch →
           SchemeRunHistoricalSourceTamperedError with field
           = "weight_set_content_hash".
      viii. SUCCESS → return VerifiedArchiveSourceBundle.
```

### Structured errors

| Class | code | field | notes |
|-------|------|-------|-------|
| `SchemeRunHistoricalSourceUnavailableError` (new, in `domain/errors.py`) | `SCHEME_RUN_HISTORICAL_SOURCE_UNAVAILABLE` | `scheme_run_source_identity` | Path 3.c.i — neither online nor archive |
| `SchemeRunHistoricalSourceTamperedError` (new, in `domain/errors.py`) | `SCHEME_RUN_HISTORICAL_SOURCE_TAMPERED` | one of: `archive_hash`, `combined_source_hash`, `weight_set_content_hash`, `archive_schema_version`, `zone_result_hash`, `cooling_load_result_hash`, `equipment_result_hash`, `power_result_hash`, `investment_result_hash` | Path 3.c.iv-vii |
| `SchemeSourceArchiveIntegrityError` (existing — `errors.py:358`) | `SCHEME_SOURCE_ARCHIVE_INVALID` | `archive_hash` | Path 3.c.ii-iii — payload↔stored hash disagree |

All three inherit `OrchestrationDomainError`.  Errors raise during the
resolve step **fail closed**; the production UoW is not affected because
`resolve_*` is a read-side operation.

## Alembic 0034 downgrade guard

Migration:
`backend/alembic/versions/0034_add_production_source_archives.py`

- `revision = "0034_add_production_source_archives"`
- `down_revision = "0033_extend_outbox_envelope"`

### Upgrade

- SQLite path: `CREATE TABLE`, FK pragma deferred (SQLite FK is honoured
  per-connection via `PRAGMA foreign_keys=ON` in the test runner).
- PostgreSQL path: `CREATE TABLE` with FK constraints; the FK on
  `scheme_run_id` is `UNIQUE` to enforce 1:1.

### Downgrade

Before dropping the table, `downgrade()` runs this preflight:

```python
# Step 1 — Count production SchemeRuns without verified archive
unverified = bind.execute(text("""
  SELECT COUNT(*) FROM scheme_runs sr
  WHERE sr.source_mode = 'production'
    AND sr.source_binding_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM production_source_archives psa
      WHERE psa.scheme_run_id = sr.id
    )
""")).scalar()

if unverified > 0:
    raise RuntimeError(
        f"alembic 0034 downgrade blocked: {unverified} production "
        f"SchemeRun(s) lack verified archive in production_source_archives. "
        f"Run maintainer back-archive manually before downgrading."
    )

# Step 2 — Defence in depth: every archive row must have a 64-char hex hash
bad = bind.execute(text("""
  SELECT scheme_run_id FROM production_source_archives
  WHERE archive_hash IS NULL
     OR length(archive_hash) != 64
     OR archive_hash GLOB '*[^0-9a-f]*'
""")).fetchall()

if bad:
    raise RuntimeError(
        f"alembic 0034 downgrade blocked: archive rows with malformed "
        f"archive_hash: {[row[0] for row in bad]}"
    )

# Step 3 — Drop the table + index + unique constraint
if dialect == "sqlite":
    _sqlite_downgrade()
else:
    _pg_downgrade()
```

The two SELECTs are written so they execute identically against SQLite
and PostgreSQL — only the drop step differs.  When the guard fires, the
table is **still present** (nothing was dropped yet) so the maintainer
can back-archive and retry.

## Generation path

In the production SchemeRun completion UoW:

```text
SourceBinding insert
→ 5 CalculationRunRecord inserts
→ SchemeRunRecord UPDATE status=completed + persist column values
→ ProductionSourceArchiveRecord INSERT (computed from the persisted columns
  AND the in-memory binding/slots/weight-set/snapshot/context/identity)
→ UoW.commit()
```

The archive insert is co-committed with the SchemeRun.  If the archive
insert fails (e.g. duplicate `scheme_run_id`, malformed payload, hash
mismatch), the entire UoW rolls back and the SchemeRun is left
uncompleted.

## Tests

### Cross-backend parity coverage

| Test | SQLite | PostgreSQL | File |
|------|--------|------------|------|
| Online historical read returns verified bundle | ✓ | ✓ | `tests/integration/test_historical_source_resolver_{sqlite,postgresql}.py` |
| Archive fallback read returns verified bundle | ✓ | ✓ | same |
| Missing online + missing archive → UnavailableError | ✓ | ✓ | same |
| Payload tampered, hash unchanged → IntegrityError on read | ✓ | ✓ | `tests/integration/test_scheme_source_archive_{sqlite,postgresql}.py` |
| archive_hash column tampered → IntegrityError | ✓ | ✓ | same |
| combined_source_hash mismatch → TamperedError(field=combined_source_hash) | ✓ | ✓ | same |
| weight_set_content_hash mismatch → TamperedError(field=weight_set_content_hash) | ✓ | ✓ | same |
| 5× *_result_hash mismatch → TamperedError(field=<slot>_result_hash) | ✓ | ✓ | same |
| archive_schema_version mismatch → TamperedError(field=archive_schema_version) | ✓ | ✓ | same |
| Slot dict order frozen (zone→cooling_load→equipment→power→investment) | ✓ | ✓ | `tests/unit/test_canonical_archive_v1.py` (unit) |
| Decimal payload serialised as base-10 string | ✓ | ✓ | same unit suite |
| Binary float in payload → fail at build time | ✓ | ✓ | same unit suite |
| Unknown object in payload → fail at build time | ✓ | ✓ | same unit suite |
| Downgrade guard: empty schema roundtrip | ✓ | ✓ | `tests/integration/test_migration_0034_downgrade_guard_{sqlite,postgresql}.py` |
| Downgrade guard: production SchemeRun without archive → abort, table remains | ✓ | ✓ | same |
| Downgrade guard: production SchemeRun with verified archive → allowed | ✓ | ✓ | same |
| Downgrade guard: archive_hash malformed → abort | ✓ | ✓ | same |
| Downgrade guard: legacy-only → allowed | ✓ | ✓ | same |
| Upgrade → downgrade -1 → re-upgrade head → parity | ✓ | ✓ | same + existing `test_orchestration_migration_*` smoke |
| Existing production E2E still passes (with new archive persistence) | ✓ | N/A | existing `test_production_scheme_sqlite.py` |

Each migration test file also asserts:

- After successful downgrade, `production_source_archives` no longer exists.
- After failed downgrade, `production_source_archives` still exists and
  contains the rows it contained before `alembic downgrade -1`.
- After successful re-upgrade, the table is recreated with all its
  constraints.

## Round 9 — production wiring + payload validator

Two follow-up closures were required after independent engineering
review of this contract:

1. **Production archive wiring must reach production code via a
   single canonical composition root.**  The repository
   ``SqlAlchemyProductionSchemeRunRepository`` accepts
   ``build_archive_callable=None`` (so unit tests can opt out),
   which means *any* production-side caller could silently bypass
   the archive INSERT.  Round 9 closes that gap with
   ``bootstrap.production_composition.compose_production_scheme_service(session_factory)``
   — the **single** production-mode factory.  ``bootstrap.dependencies.init_dependencies``
   now also wires a ``production_scheme_service`` singleton + getter.
   An architecture test
   (``tests/architecture/test_production_archive_wiring_boundary.py``)
   AST-scans the production tree for naked
   ``SqlAlchemyProductionSchemeRunRepository(...)`` constructions
   and fails if any construction is missing
   ``build_archive_callable=`` *outside* the composition root.

2. **Archive payload schema must be validated before the hash is
   recomputed.**  A persistent ``archive_payload`` whose keys
   drift away from the agreed contract (or whose ``source_slots``
   shape regresses to a dict / wrong order / missing slot) would
   otherwise produce a hash mismatch instead of a structural
   integrity error.  Round 9 adds
   ``validate_archive_payload_v1(payload)`` in
   ``canonical_archive_v1.py`` enforcing:
   - exactly the 19 required keys (no missing, no extras)
   - ``source_slots`` is the canonical ordered list
     `[["zone", …], ["cooling_load", …], …]`
   The validator is wired into
   ``historical_source_resolver.resolve_scheme_run_sources_for_history``
   *before* ``compute_archive_hash_v1``; any violation raises
   ``SchemeSourceArchiveIntegrityError(detail=…)`` instead of an
   opaque hash mismatch.  Fail-closed tests cover both the
   validator function (32 cases) and the resolver wire-up (3 cases).

## Maintainer governance

This PR remains Draft / Open / Not merged until:

1. All four CI jobs green on the head SHA.
2. `backend-postgresql` inner steps (Alembic upgrade, downgrade/re-upgrade
   roundtrip, integration tests, Backend tests PG) all success.
3. A separate, independent engineering review of this contract (per
   Issue #22 review pattern) approves the implementation.

After independent review, the maintainer will:

- Convert the PR to Ready.
- Merge with `gh pr merge --merge --match-head-commit <head>`.
- Refresh Issue #22 body to mark §10 closed, then close Issue #22.

That is NOT done by this implementation PR.

## References

- Parent issue: #22
- Approved design contract (`PR #23 at b30ccf8ffde54eb40081b514a1d7eaa1615417ae`)
- Previous PR #32 merge commit: `e3320dfd209e6044f199e0177ec8ce8511ef17f0`
- Frozen baseline: `3654d00a739ccd8027930ef3bf853fda70afd734`
- Existing precedent for a frozen migration helper: `backend/alembic/helpers/frozen_outbox_envelope_v1.py`
