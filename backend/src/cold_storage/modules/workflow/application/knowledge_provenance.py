"""Knowledge provenance assessment for workflow aggregation (consumer-only)."""

from __future__ import annotations

import json
from typing import Any


def content_depends_on_knowledge_source(content_json: dict[str, Any]) -> bool:
    """Return True when governed content embeds a knowledge revision dependency."""
    return _contains_knowledge_source_reference(content_json)


def assess_knowledge_provenance(
    *,
    depends_on_knowledge: bool,
    knowledge_revisions: list[dict[str, Any]],
    page_evidence_by_revision: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Assess read-only provenance without defining OCR producer semantics."""
    if not depends_on_knowledge:
        return {
            "required": False,
            "available": False,
            "status": "NOT_REQUIRED",
            "blockers": [],
            "source_references": [],
        }

    blockers: list[dict[str, Any]] = []
    source_references: list[dict[str, Any]] = []

    for revision in knowledge_revisions:
        revision_id = str(revision.get("id", ""))
        source_references.append(
            {
                "revision_id": revision_id,
                "document_id": revision.get("document_id", ""),
                "content_sha256": revision.get("content_sha256", ""),
                "requires_review": revision.get("requires_review", True),
                "requires_ocr": revision.get("requires_ocr", False),
                "ingestion_status": revision.get("ingestion_status", ""),
            }
        )

        if revision.get("requires_review"):
            blockers.append(
                {
                    "code": "KNOWLEDGE_PROVENANCE_PENDING",
                    "message": "Knowledge revision requires review before provenance is complete",
                    "stage": "KNOWLEDGE_PROVENANCE",
                    "source_type": "knowledge_revision",
                    "source_id": revision_id,
                    "severity": "blocking",
                }
            )

        requires_ocr = bool(revision.get("requires_ocr"))
        ingestion_status = str(revision.get("ingestion_status", ""))
        page_evidence = page_evidence_by_revision.get(revision_id, [])

        if requires_ocr and ingestion_status == "requires_ocr" and not page_evidence:
            blockers.append(
                {
                    "code": "KNOWLEDGE_PROVENANCE_UNAVAILABLE",
                    "message": "OCR detection is not OCR evidence; page evidence is missing",
                    "stage": "KNOWLEDGE_PROVENANCE",
                    "source_type": "knowledge_revision",
                    "source_id": revision_id,
                    "severity": "blocking",
                }
            )

        incomplete_pages = [
            evidence
            for evidence in page_evidence
            if not evidence.get("is_complete", False)
            or evidence.get("extraction_status") in {"failed", "unavailable", "empty"}
        ]
        if incomplete_pages:
            blockers.append(
                {
                    "code": "KNOWLEDGE_PROVENANCE_PENDING",
                    "message": "Partial OCR is not complete provenance",
                    "stage": "KNOWLEDGE_PROVENANCE",
                    "source_type": "knowledge_revision",
                    "source_id": revision_id,
                    "severity": "blocking",
                }
            )

        for evidence in page_evidence:
            if evidence.get("is_ocr_derived") and not evidence.get("source_page_evidence_id"):
                blockers.append(
                    {
                        "code": "KNOWLEDGE_PROVENANCE_UNAVAILABLE",
                        "message": "OCR-derived content lacks source_page_evidence_id",
                        "stage": "KNOWLEDGE_PROVENANCE",
                        "source_type": "knowledge_page_evidence",
                        "source_id": str(evidence.get("page_number", "")),
                        "severity": "blocking",
                    }
                )

    if blockers:
        status = (
            "INVALID"
            if any(b.get("code") == "KNOWLEDGE_PROVENANCE_UNAVAILABLE" for b in blockers)
            else "PENDING"
        )
        return {
            "required": True,
            "available": False,
            "status": status,
            "blockers": blockers,
            "source_references": source_references,
        }

    return {
        "required": True,
        "available": bool(source_references),
        "status": "AVAILABLE" if source_references else "PENDING",
        "blockers": [],
        "source_references": source_references,
    }


def enrich_knowledge_provenance_projection(
    projection: dict[str, Any],
    *,
    knowledge_revisions: list[dict[str, Any]],
    page_evidence_by_revision: dict[str, list[dict[str, Any]]],
    document_summaries: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach persisted page-evidence display fields without changing assessment semantics."""
    enriched: dict[str, Any] = dict(projection)
    summaries = document_summaries or {}
    base_refs = {
        str(ref.get("revision_id", "")): ref for ref in projection.get("source_references", [])
    }

    enriched_refs: list[dict[str, Any]] = []
    for revision in knowledge_revisions:
        revision_id = str(revision.get("id", ""))
        document_id = str(revision.get("document_id", ""))
        page_evidence = page_evidence_by_revision.get(revision_id, [])
        doc_summary = summaries.get(document_id, {})
        base = base_refs.get(revision_id, {})

        enriched_refs.append(
            {
                **base,
                "revision_id": revision_id,
                "document_id": document_id,
                "document_code": doc_summary.get("code", page_evidence[0].get("document_code", ""))
                if page_evidence
                else doc_summary.get("code", ""),
                "document_title": doc_summary.get("title", page_evidence[0].get("document_title", ""))
                if page_evidence
                else doc_summary.get("title", ""),
                "content_sha256": revision.get("content_sha256", base.get("content_sha256", "")),
                "original_filename": revision.get("original_filename", ""),
                "version_label": revision.get("version_label", ""),
                "revision_number": revision.get("revision_number"),
                "review_status": revision.get("review_status", ""),
                "requires_review": revision.get("requires_review", base.get("requires_review", True)),
                "requires_ocr": revision.get("requires_ocr", base.get("requires_ocr", False)),
                "ingestion_status": revision.get(
                    "ingestion_status", base.get("ingestion_status", "")
                ),
                "page_evidence": page_evidence,
                "page_evidence_available": bool(page_evidence),
            }
        )

    enriched["source_references"] = enriched_refs
    return enriched


def extract_knowledge_revision_ids(content_json: dict[str, Any]) -> list[str]:
    """Collect knowledge revision IDs referenced in assembled report content."""
    ids: list[str] = []
    for value in _walk_json(content_json):
        if isinstance(value, dict):
            source_type = value.get("source_type")
            if source_type in {"knowledge_revision", "KNOWLEDGE_REVISION"}:
                source_id = value.get("source_id") or value.get("revision_id")
                if isinstance(source_id, str) and source_id:
                    ids.append(source_id)
            revision_id = value.get("revision_id")
            if (
                value.get("document_id")
                and isinstance(revision_id, str)
                and revision_id
                and (value.get("content_sha256") or value.get("persisted_content_hash"))
            ):
                ids.append(revision_id)
    return sorted(set(ids))


def _contains_knowledge_source_reference(node: Any) -> bool:
    if isinstance(node, dict):
        source_type = node.get("source_type")
        if source_type in {"knowledge_revision", "KNOWLEDGE_REVISION"}:
            return True
        if node.get("knowledge_references"):
            return True
        return any(_contains_knowledge_source_reference(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_knowledge_source_reference(item) for item in node)
    return False


def _walk_json(node: Any) -> list[Any]:
    items: list[Any] = [node]
    if isinstance(node, dict):
        for value in node.values():
            items.extend(_walk_json(value))
    elif isinstance(node, list):
        for value in node:
            items.extend(_walk_json(value))
    return items


def canonical_json_hash(payload: dict[str, Any]) -> str:
    """Deterministic hash helper for lineage comparisons."""
    import hashlib

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
