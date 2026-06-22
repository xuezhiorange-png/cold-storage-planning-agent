"""Knowledge query port — public read-only interface for knowledge data.

This module defines the architecture boundary between the reports module
and the knowledge module.  Reports consume knowledge data through this
port without touching ORM models, Session objects, or infrastructure
internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class KnowledgeQueryPort(ABC):
    """Public read-only port for knowledge data."""

    @abstractmethod
    def get_approved_revisions_for_document(self, document_id: str) -> list[dict[str, Any]]:
        """Return approved revisions for a specific document."""
        ...

    @abstractmethod
    def get_approved_documents(self) -> list[dict[str, Any]]:
        """Return all documents that have at least one approved revision."""
        ...


class KnowledgeQueryService(KnowledgeQueryPort):
    """Implementation backed by KnowledgeRepository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def get_approved_revisions_for_document(self, document_id: str) -> list[dict[str, Any]]:
        revisions = self._repo.list_revisions(document_id)
        approved = [r for r in revisions if r.review_status == "approved"]
        return [
            {
                "id": r.id,
                "document_id": r.document_id,
                "revision_number": r.revision_number,
                "version_label": r.version_label,
                "original_filename": r.original_filename,
                "content_sha256": r.content_sha256,
                "review_status": r.review_status,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            }
            for r in approved
        ]

    def get_approved_documents(self) -> list[dict[str, Any]]:
        docs = self._repo.list_documents()
        result: list[dict[str, Any]] = []
        for doc in docs:
            revisions = self._repo.list_revisions(doc.id)
            approved_revisions = [r for r in revisions if r.review_status == "approved"]
            if approved_revisions:
                result.append(
                    {
                        "id": doc.id,
                        "code": doc.code,
                        "title": doc.title,
                        "document_category": doc.document_category,
                        "source_type": doc.source_type,
                        "owner": doc.owner,
                        "current_revision_number": doc.current_revision_number,
                        "created_at": doc.created_at.isoformat() if doc.created_at else "",
                        "approved_revisions": [
                            {
                                "id": r.id,
                                "revision_number": r.revision_number,
                                "version_label": r.version_label,
                                "content_sha256": r.content_sha256,
                                "approved_at": (
                                    r.approved_at.isoformat() if r.approved_at else None
                                ),
                            }
                            for r in approved_revisions
                        ],
                    }
                )
        return result
