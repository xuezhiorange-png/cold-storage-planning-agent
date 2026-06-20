from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    document_type: str
    version: str
    validity_status: str
    content: str
    requires_ocr: bool = False


class KnowledgeService:
    def __init__(self) -> None:
        self.documents: dict[str, KnowledgeDocument] = {}

    def add_text_document(
        self, document_id: str, title: str, document_type: str, version: str, content: str
    ) -> KnowledgeDocument:
        requires_ocr = document_type.lower() == "pdf" and not content.strip()
        document = KnowledgeDocument(
            document_id=document_id,
            title=title,
            document_type=document_type,
            version=version,
            validity_status="unverified",
            content=content,
            requires_ocr=requires_ocr,
        )
        self.documents[document_id] = document
        return document

    def search(self, query: str) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for document in self.documents.values():
            if query in document.content or query in document.title:
                results.append(
                    {
                        "title": document.title,
                        "version": document.version,
                        "section": "全文",
                        "page_range": None,
                        "validity_status": document.validity_status,
                        "summary": document.content[:160],
                        "relevance_score": 0.8,
                    }
                )
        return results
