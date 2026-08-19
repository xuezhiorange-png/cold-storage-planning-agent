# V0.3 P3 OCR and Knowledge Provenance Contract

**Status:** Definition freeze only
**Authority:** Issue #108, tracked by Issue #111
**Authorization record:** '5343938195'
**Codex execution directive:** '5343957086'
**Contract definition source SHA:** '4fb3ef7075787d636d573fb21a20bcebe7113d65'
**Contract definition source tree SHA:** 'b33008759b9e4fd40a45a5bc9ed6aea5b082a16e'
**Implementation branch:** 'codex/v03-p3-ocr-knowledge-provenance-contract-r1'

This document freezes the V0.3 P3 OCR and knowledge provenance authority. It
does not implement OCR, change the database, change dependencies, change the
runtime image, expose a new API, or enable production behavior. A later
implementation authorization must cite this exact contract and may not define
new contract semantics during implementation.

## 1. Contract state and hard boundaries

The contract is documentation-only:

~~~
CONTRACT_STATUS=DEFINITION_ONLY
ORIGINAL_SOURCE_ARTIFACT_IS_AUTHORITY=YES
ORIGINAL_CONTENT_SHA256_IS_AUTHORITY=YES
OCR_CONTENT_CLASS=DERIVED_EVIDENCE
LOCAL_OFFLINE_OCR=YES
CLOUD_OCR=NO
ALL_OCR_DERIVED_CONTENT_REQUIRES_REVIEW=YES
OCR_AUTO_APPROVAL=NO
FAIL_CLOSED_ON_PARTIAL_OCR=YES
RE_OCR_MUTATION_ALLOWED_FOR_APPROVED_REVISION=NO
PAGE_NUMBERING=1_BASED
CODE_MUTATION_AUTHORIZED=NO
TEST_MUTATION_AUTHORIZED=NO
MIGRATION_MUTATION_AUTHORIZED=NO
DEPENDENCY_MUTATION_AUTHORIZED=NO
DOCKERFILE_MUTATION_AUTHORIZED=NO
WORKFLOW_MUTATION_AUTHORIZED=NO
FRONTEND_MUTATION_AUTHORIZED=NO
LIVE_EXTERNAL_OCR_AUTHORIZED=NO
PRODUCTION_ENABLEMENT_AUTHORIZED=NO
P4_IMPLEMENTATION_AUTHORIZED=NO
~~~

P3 does not authorize:

- changing deterministic engineering calculation, coefficient, scheme, or
  report authority;
- changing the Planning Agent decision or tool authority;
- replacing an original PDF with an OCR-produced file;
- external OCR upload, OCR SaaS, OCR credentials, or uncontrolled network I/O;
- a migration, Python dependency, lockfile, Dockerfile, workflow, or frontend
  change;
- Ready, Merge, deployment, or production enablement.

## 2. Audited current implementation baseline

The following paths were read at the contract definition source SHA:

~~~
backend/src/cold_storage/modules/knowledge/domain/models.py
backend/src/cold_storage/modules/knowledge/domain/chunking.py
backend/src/cold_storage/modules/knowledge/application/service.py
backend/src/cold_storage/modules/knowledge/application/query.py
backend/src/cold_storage/modules/knowledge/infrastructure/orm.py
backend/src/cold_storage/modules/knowledge/infrastructure/repository.py
backend/src/cold_storage/modules/knowledge/infrastructure/parsers/base.py
backend/src/cold_storage/modules/knowledge/infrastructure/parsers/pdf_parser.py
backend/src/cold_storage/modules/knowledge/api/routes.py
backend/src/cold_storage/modules/planning_agent/infrastructure/tool_adapters/knowledge_adapter.py
backend/tests/unit/test_knowledge_domain.py
backend/tests/unit/test_knowledge_parsers.py
backend/tests/integration/test_knowledge_sqlite.py
backend/tests/integration/test_knowledge_postgresql.py
backend/pyproject.toml
backend/uv.lock
backend/Dockerfile
~~~

The current implementation facts are preserved as the starting boundary:

1. PdfParser uses PyMuPDF page by page. It keeps PDF page identity as
   page_idx + 1, normalizes native text, records page_start, page_end,
   section_path, and page_number metadata, and carries parser_version.
2. An image-only page does not receive a fabricated ParsedBlock. The parser
   records its 1-based number in ParseResult.ocr_page_numbers and emits a
   warning. This is a detection signal, not OCR evidence and not approval.
3. KnowledgeRevision already carries content_sha256, storage_key,
   requires_ocr, requires_review, parser/chunker/embedding versions,
   page_count, metadata_snapshot, and warnings.
4. KnowledgeChunk already carries revision_id, text_sha256, page_start,
   page_end, and source_locator. The current chunker keeps page metadata on
   blocks and does not intentionally cross a PDF page boundary.
5. KnowledgeCitation and the search API projection already carry
   document_id, revision_id, content_sha256, chunk_id, page_start, page_end,
   source_locator, review_status, and requires_review, together with the
   current document and chunk identity. There is currently no standalone
   persisted page-evidence or citation ORM table; the citation is a read
   projection over revision and chunk records.
6. KnowledgeService currently marks a revision as requiring OCR when the
   parser reports OCR pages. It may index native blocks that exist while the
   OCR pages remain unresolved. P3 implementation must close this partial
   publication gap without changing the original artifact authority.
7. The current migration authority was checked with the real command
   alembic heads and is:

   ~~~
   CURRENT_ALEMBIC_HEAD_AT_CONTRACT_DEFINITION=0039_widen_report_export_artifact_mime_type
   ~~~

   The versions directory also contains non-numeric revision files. A future
   implementation must re-run alembic heads; it must not infer a next
   migration from a filename such as 0040.
8. Python already declares pymupdf>=1.24. The current Dockerfile and lock
   file do not provide a Tesseract/tessdata runtime declaration. Future
   implementation must verify the runtime image and language data before
   claiming OCR availability.

These observations define current seams. They do not authorize preserving a
partial-index or unreviewed-OCR outcome as a successful production state.

## 3. Original source and revision authority

The original uploaded artifact remains the only source authority:

~~~
ORIGINAL_SOURCE_ARTIFACT_IS_AUTHORITY=YES
ORIGINAL_CONTENT_SHA256_IS_AUTHORITY=YES
OCR_IS_SOURCE_AUTHORITY=NO
OCR_IS_DERIVED_EVIDENCE=YES
~~~

For every revision, the immutable source identity is the tuple:

~~~
(document_id, revision_id, original_filename, storage_key, content_sha256)
~~~

The original PDF bytes and its content_sha256 must not be overwritten,
replaced, recomputed from OCR output, or silently associated with a new
source file. An OCR-produced PDF is not an original artifact and must not be
registered as one.

Every OCR-derived text value must be traceable in this direction without
inference from a human-readable string:

~~~
OCR derived text
  -> source_page_evidence_id
  -> page_number
  -> revision_id
  -> document_id
  -> original_filename
  -> original storage_key
  -> original content_sha256
~~~

An OCR retry may produce a new text_sha256, but it must never produce a new
original content_sha256 or detach the evidence from its revision.

## 4. Deterministic page extraction policy

P3 keeps the existing native PDF path and adds page-level OCR only for pages
that require it. The page decision is deterministic and is made before OCR
execution:

~~~
PAGE_NUMBERING=1_BASED
NATIVE_TEXT_PATH_PRESERVED=YES
OCR_DECISION_SCOPE=PAGE
WHOLE_DOCUMENT_UNCONDITIONAL_OCR=NO
~~~

The future implementation must apply this decision for every PDF page:

| Page condition | Canonical extraction method | Required behavior |
| --- | --- | --- |
| Native text is sufficient under the parser's deterministic sufficiency policy | native_text | Index native text; do not OCR the page |
| Page is image-only or below the deterministic native sufficiency policy and is in ocr_page_numbers | ocr | Invoke the local OCR adapter for this exact 1-based page |
| Native and OCR candidates both exist for one page | One selected method only | Never index native text plus full OCR text as duplicate page content |
| Mixed PDF | Per-page selection | OCR only the listed pages; keep other pages on native extraction |
| OCR page number is outside 1..page_count | Invalid source/evidence | Fail closed; do not publish the run |

The existing PDF parser's page-level image-only signal is the input to this
policy. The future implementation must make the native-text sufficiency rule
explicit, deterministic, covered by tests, and independent of OCR output. It
must not use a guessed confidence value or model output to decide whether a
page needs OCR.

## 5. Independent OCR adapter boundary

P3 introduces one independent adapter boundary. The adapter is an extraction
mechanism, not a source, approval, retrieval, or Agent authority:

~~~
OcrAdapter.extract_pages(
    original_artifact_or_immutable_reference,
    revision_identity,
    exact_1_based_page_numbers,
) -> list[OcrPageEvidence]
~~~

The input must bind to the original artifact and exact revision. The adapter
must reject an empty, duplicated, non-integer, zero, negative, or out-of-range
page list before attempting OCR.

Each returned page result is structured and must contain at least:

~~~
source_page_evidence_id
document_id
revision_id
page_number
extraction_method              # native_text | ocr
extraction_status              # completed | requires_ocr | unavailable | empty | failed
text
text_sha256
ocr_engine                     # null for native_text
ocr_engine_version             # null for native_text
ocr_languages                  # [] for native_text; explicit for OCR
confidence                     # real numeric value or null
confidence_source              # engine | unavailable | null
requires_review
review_status
warnings
errors
created_at
updated_at
ingestion_provenance
~~~

source_page_evidence_id is a stable machine identity for the page within a
revision. Its minimum identity is (revision_id, page_number). It must not be
replaced with a new random identity on a retry of the same unapproved
revision. An implementation may include a versioned evidence identity only if
the immutable revision/page binding remains explicit and duplicate detection
remains deterministic.

The adapter must not own or decide:

~~~
DOCUMENT_APPROVAL_AUTHORITY=NO
REVISION_APPROVAL_AUTHORITY=NO
RETRIEVAL_RANKING_AUTHORITY=NO
AGENT_ANSWER_AUTHORITY=NO
ENGINEERING_CALCULATION_AUTHORITY=NO
~~~

## 6. Local OCR runtime authority

The only P3 runtime direction is local, offline OCR:

~~~
LOCAL_OFFLINE_OCR=YES
CLOUD_OCR=NO
PREFERRED_NATIVE_ENGINE=PyMuPDF
PREFERRED_OCR_ENGINE=local Tesseract
BASE_OCR_LANGUAGES=eng+chi_sim
EXTERNAL_OCR_SAAS_ALLOWED=NO
OCR_UPLOAD_TO_EXTERNAL_SERVICE_ALLOWED=NO
OCR_API_KEY_ALLOWED=NO
UNCONTROLLED_OCR_NETWORK_ALLOWED=NO
~~~

The future runtime image must explicitly provide a compatible Tesseract
binary and the eng and chi_sim tessdata language data, or fail closed with
an unavailable OCR result. The exact package/version and image digest must be
verified at implementation time. This contract does not authorize a
Dockerfile mutation.

P3 has no requirement for a new Python OCR package. pymupdf>=1.24 remains
the current Python dependency authority. If authoritative verification shows
that a Python dependency is genuinely required, implementation is blocked
pending a separate dependency authorization:

~~~
PYTHON_DEPENDENCY_MUTATION_REQUIRED=NO
IMPLEMENTATION_BLOCKED_PENDING_DEPENDENCY_AUTHORIZATION=YES_IF_A_NEW_PYTHON_PACKAGE_IS_REQUIRED
~~~

## 7. OCR result, confidence, and review semantics

OCR confidence must be evidence, never a fabricated quality signal:

~~~
OCR_CONFIDENCE_FABRICATION_ALLOWED=NO
CONFIDENCE_NUMERIC_VALUE_ALLOWED=ONLY_IF_ENGINE_PROVIDES_MEASURABLE_VALUE
CONFIDENCE_SOURCE_REQUIRED_WHEN_NUMERIC=YES
CONFIDENCE_UNAVAILABLE_REPRESENTATION=null
CONFIDENCE_UNAVAILABLE_SOURCE=unavailable
~~~

If the selected Tesseract transport cannot provide a trustworthy numeric
confidence for the page or returned text, confidence must be null and
confidence_source must be unavailable. The implementation must not use
invented values such as 0.8, 0.85, or 0.9, and must not derive an approval
threshold from them.

All OCR-derived content requires human review:

~~~
ALL_OCR_DERIVED_CONTENT_REQUIRES_REVIEW=YES
OCR_AUTO_APPROVAL=NO
OCR_REVIEW_REQUIRED_WHEN_CONFIDENCE_IS_NULL=YES
OCR_REVIEW_REQUIRED_WHEN_CONFIDENCE_IS_NUMERIC=YES
~~~

Revision approval remains governed by the existing knowledge lifecycle. A
page marked requires_review=true must not be represented as approved merely
because extraction completed. A rejected or unresolved page blocks an
approved searchable revision.

## 8. First-class page evidence persistence

Page extraction/OCR evidence is a first-class persisted object, not a log
message or an opaque field that cannot be queried. Its durable record must
bind:

~~~
source_page_evidence_id
document_id
revision_id
original_filename
original_content_sha256
page_number
extraction_method
extraction_status
extracted_text
text_sha256
ocr_engine
ocr_engine_version
ocr_languages
confidence
confidence_source
requires_review
review_status
warnings
errors
created_at
updated_at
ingestion_run_id_or_equivalent
ingestion_provenance
~~~

The record must be readable after a fresh process/session and must support:

~~~
RESTART_READBACK=REQUIRED
RETRY_AUDIT=REQUIRED
HUMAN_REVIEW_READBACK=REQUIRED
RETRIEVAL_CITATION_READBACK=REQUIRED
PAGE_EVIDENCE_HASH_RECOMPUTATION=REQUIRED
~~~

The evidence record must not contain credentials, external OCR request
headers, uncontrolled provider payloads, or arbitrary local machine paths.
Error and warning fields are bounded, machine-readable, and safe to expose
through the existing redaction policy.

## 9. Ingestion lifecycle, idempotency, and partial publication

The existing revision identity and lifecycle remain authoritative. OCR adds
evidence and review gates; it does not add a parallel revision state machine.

For an unapproved revision, repeated ingestion or OCR of the same original
content must converge on the same page evidence identities and chunk
identities:

~~~
SAME_REVISION_SAME_SOURCE_RETRY_IS_IDEMPOTENT=YES
DUPLICATE_PAGE_EVIDENCE_ON_RETRY=NO
DUPLICATE_CHUNKS_ON_RETRY=NO
SOURCE_CONTENT_HASH_IS_IDEMPOTENCY_INPUT=YES
~~~

Ingestion must be transactional at the publication boundary. The following
state is forbidden:

~~~
pages 1-2 new OCR
+ page 3 old OCR
+ revision status indexed/complete
~~~

If any required page is unavailable, empty, failed, mismatched, or has a
missing hash, the run must not publish a complete indexed revision:

~~~
PARTIAL_OCR_PUBLISH_ALLOWED=NO
EMPTY_OCR_RESULT_IS_COMPLETE=NO
MISSING_REQUIRED_PAGE_BLOCKS_INDEXED_COMPLETE=YES
FAILED_REQUIRED_PAGE_BLOCKS_INDEXED_COMPLETE=NO
FAIL_CLOSED_ON_PARTIAL_OCR=YES
~~~

An approved revision is immutable. Re-OCR must not mutate its page evidence,
chunks, source hash, or citations. New recognition output requires a new
revision and the normal governed review/approval path:

~~~
APPROVED_REVISION_RE_OCR_MUTATION_ALLOWED=NO
NEW_OCR_RESULT_REQUIRES_NEW_REVISION_OR_GOVERNED_PATH=YES
~~~

## 10. Chunk and citation provenance

The canonical lineage is:

~~~
chunk
  -> exact source_page_evidence_id
  -> exact page_number
  -> revision_id
  -> document_id
  -> original artifact and content_sha256
~~~

The existing page_start, page_end, and source_locator fields remain required
and must not be removed. Because a human-readable locator is not a source
authority, the future chunk contract must add either:

~~~
source_page_evidence_id
~~~

or an equivalent stable machine-readable evidence identity. A chunk spanning
multiple PDF pages must carry all exact page evidence identities or be split
so that its lineage is unambiguous. The current no-cross-page chunking policy
is retained as the default to minimize ambiguity.

Future KnowledgeCitation projections must preserve all current fields:

~~~
document_id
revision_id
content_sha256
chunk_id
page_start
page_end
source_locator
review_status
requires_review
~~~

and must be able to carry:

~~~
source_page_evidence_id
extraction_method
ocr_engine
ocr_engine_version
ocr_languages
ocr_confidence
ocr_confidence_source
ocr_review_status
~~~

The citation projection must not silently drop the original filename,
revision identity, original content hash, or page evidence identity. The
Planning Agent, workbench, and report layers may consume these fields but may
not infer, rewrite, repair, or fabricate provenance.

## 11. Planning Agent boundary

knowledge.search may return search text, review state, and structured
citations to the Planning Agent through the existing knowledge tool adapter.
The Agent remains an orchestration and explanation boundary only:

~~~
AGENT_SOURCE_APPROVAL_AUTHORITY=NO
AGENT_OCR_CORRECTION_AUTHORITY=NO
AGENT_PROVENANCE_REWRITE_AUTHORITY=NO
AGENT_ENGINEERING_CALCULATION_AUTHORITY=NO
AGENT_SCHEME_SCORING_AUTHORITY=NO
~~~

When OCR content has requires_review=true, the search result and citation
must make that state visible to the Agent/application boundary. The Agent may
decline to use or may explain an unreviewed source, but it cannot mark the
source reviewed, approve a revision, or alter an evidence hash.

## 12. Migration authority and schema contract

There is no migration in this contract round. Before any implementation
authorization, the implementation owner must run the real command in the
authoritative checkout:

~~~
cd backend
alembic heads
~~~

The exact output must be recorded in the implementation evidence. A future
page-evidence migration must be a legal child of the exact current Alembic
head(s), including all non-numeric revision identifiers. The next migration
must not be selected by assuming a numeric filename or by guessing
down_revision.

The only future schema intent frozen here is:

~~~
PAGE_EVIDENCE_PERSISTENCE_REQUIRED=YES
PAGE_EVIDENCE_IDENTITY_MUST_BE_STABLE=YES
PAGE_EVIDENCE_REVISION_FOREIGN_KEY_REQUIRED=YES
PAGE_EVIDENCE_DOCUMENT_LINEAGE_REQUIRED=YES
PAGE_EVIDENCE_UNIQUE_REVISION_PAGE_REQUIRED=YES
~~~

The final migration filename, revision ID, down revision, column types, and
indexes remain implementation details that must be derived from the
revalidated Alembic authority and a separate implementation authorization.

## 13. Future implementation allowlist

The following is the minimum candidate allowlist for a later P3
implementation. It is not permission to mutate these paths now. A later
authorization must use this list, remove any path proven unnecessary, and
must not add a path merely for convenience.

| Candidate path | Required mutation and reason |
| --- | --- |
| backend/src/cold_storage/modules/knowledge/domain/models.py | Add immutable page-evidence/provenance value types and the stable evidence identity required by the domain boundary. |
| backend/src/cold_storage/modules/knowledge/infrastructure/ocr_adapter.py | New independent OcrAdapter boundary for local Tesseract extraction; keeps OCR transport out of domain/application code. |
| backend/src/cold_storage/modules/knowledge/infrastructure/parsers/pdf_parser.py | Preserve and make explicit deterministic page selection and native/OCR page metadata at the existing PyMuPDF boundary. |
| backend/src/cold_storage/modules/knowledge/application/service.py | Orchestrate page selection, adapter invocation, transactionally safe publication, review gating, and retry/idempotency without changing document authority. |
| backend/src/cold_storage/modules/knowledge/infrastructure/orm.py | Persist first-class page evidence and any required stable lineage columns/relationships. |
| backend/src/cold_storage/modules/knowledge/infrastructure/repository.py | Read/write page evidence, enforce revision/page idempotency, and provide fresh-session readback. |
| backend/src/cold_storage/modules/knowledge/domain/chunking.py | Carry exact page evidence lineage while preserving the existing no-cross-page chunk policy. Remove this path if the evidence identity can be attached without changing chunking. |
| backend/src/cold_storage/modules/knowledge/application/query.py | Extend the read-only query boundary only as needed to expose approved revision/page provenance to workbench and downstream consumers. |
| backend/src/cold_storage/modules/knowledge/api/routes.py | Extend existing revision/chunk/search response models only to project persisted provenance; no new approval or OCR authority and no unreviewed route expansion. |
| backend/alembic/versions/<legal-child-of-current-head>_knowledge_page_evidence.py | One migration only if the revalidated schema requires durable page-evidence columns/tables; exact revision/down revision must come from alembic heads, never from filename guessing. |
| backend/tests/unit/test_knowledge_ocr.py | New deterministic unit coverage for adapter result shape, page selection, confidence, review, failure, and no-network behavior. |
| backend/tests/unit/test_knowledge_domain.py | Extend domain tests for immutable evidence identity and chunk/citation lineage if domain types change. |
| backend/tests/unit/test_knowledge_parsers.py | Extend native/image-only/mixed PDF trigger tests and 1-based page identity tests. |
| backend/tests/integration/test_knowledge_sqlite.py | SQLite persistence, restart, idempotency, partial-publication, and approved-revision immutability evidence. |
| backend/tests/integration/test_knowledge_postgresql.py | PostgreSQL parity, transaction, unique-identity, and fresh-session evidence. |
| backend/tests/unit/test_knowledge_api.py | Add only if existing API projection requires a separate focused contract test; otherwise keep the route tests in the current knowledge test owner. |
| backend/Dockerfile | Conditional only if verified runtime inspection proves Tesseract/tessdata is absent and a runtime-image change is separately authorized. This path is not part of the default Python implementation slice. |

The following paths are explicitly excluded from the default P3
implementation allowlist:

~~~
backend/src/cold_storage/modules/planning_agent/application/**
backend/src/cold_storage/modules/planning_agent/domain/**
backend/src/cold_storage/modules/planning_agent/infrastructure/tool_adapters/knowledge_adapter.py
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/coefficients/**
backend/src/cold_storage/modules/schemes/**
backend/src/cold_storage/modules/reports/**
backend/pyproject.toml
backend/uv.lock
frontend/**
.github/**
~~~

The current Planning Agent knowledge adapter is a consumer of the existing
search projection and does not need mutation merely to pass through fields.
If an implementation audit proves that it drops a frozen provenance field,
that is a separately documented scope decision, not an implicit expansion.

## 14. Frozen test and acceptance matrix for implementation

The later implementation must provide deterministic, offline tests for all of
the following. A skipped, xfailed, uncollected, or network-dependent test is
not evidence of closure.

| # | Required evidence |
| --- | --- |
| 1 | Normal text-only PDF does not invoke OCR. |
| 2 | Image-only scanned PDF invokes OCR for its exact image-only pages. |
| 3 | Mixed PDF OCRs only the selected pages and keeps native pages native. |
| 4 | Page numbers remain the original PDF 1-based identities. |
| 5 | Original content_sha256 is identical before and after OCR. |
| 6 | OCR text hash is independently recomputable and repeatable. |
| 7 | OCR unavailable fails closed and leaves the revision requiring OCR/review. |
| 8 | Empty OCR output cannot be treated as a complete indexed document. |
| 9 | A partial OCR failure cannot publish a partially complete index. |
| 10 | OCR evidence -> chunk -> citation lineage is complete and read back after restart. |
| 11 | Unknown/unavailable confidence is null and is never fabricated. |
| 12 | Every OCR-derived page has requires_review=true; OCR cannot auto-approve. |
| 13 | Approved revisions cannot be silently re-OCRed or mutated. |
| 14 | Retry/reingestion produces no duplicate page evidence or duplicate chunks. |
| 15 | SQLite persistence and lifecycle tests pass. |
| 16 | PostgreSQL persistence and lifecycle tests pass. |
| 17 | Fixtures are deterministic and use no external OCR network. |
| 18 | Planning Agent citations preserve all frozen OCR provenance and review state. |

The implementation evidence must also show:

~~~
NO_EXTERNAL_OCR_NETWORK=YES
NO_REAL_OCR_CREDENTIAL=YES
ORIGINAL_HASH_UNCHANGED=YES
PAGE_EVIDENCE_RESTART_READBACK=PASS
PARTIAL_PUBLISH_FAIL_CLOSED=PASS
APPROVED_REVISION_IMMUTABILITY=PASS
SQLITE=PASS
POSTGRESQL=PASS
~~~

## 15. P4 read-only handoff

P3 exposes a read-only provenance contract for a future workbench. P4 may
display, without rewriting, at least:

~~~
source_file / original_filename
document_id
revision_id / revision_number
original_content_sha256
page_number
extraction_method                 # native_text or ocr
ocr_review_status
requires_review
ocr_confidence                    # real value or null
ocr_confidence_source
source_locator
source_page_evidence_id
citation
~~~

P4 must read this evidence through the approved query/API boundary. It may
not infer OCR status from warnings, re-run OCR, alter hashes, change review
status, approve a revision, or rewrite a citation.

~~~
P4_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_MUTATION_AUTHORIZED=NO
~~~

## 16. Governance gates

This contract must be independently reviewed before any implementation
authorization. The next required gate is:

~~~
NEXT_REQUIRED_STAGE=V03_P3_OCR_KNOWLEDGE_PROVENANCE_CONTRACT_INDEPENDENT_REVIEW_AUTHORIZATION
NEXT_STAGE_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

Implementation authorization may consume this contract but may not define new
provider, OCR, provenance, review, migration, or readiness semantics. Any
required path or behavior outside the frozen boundary requires an explicit
contract amendment before implementation.
