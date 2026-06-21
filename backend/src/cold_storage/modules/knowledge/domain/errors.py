"""Knowledge domain errors."""


class KnowledgeDomainError(Exception):
    """Base error for the knowledge domain."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class DocumentNotFoundError(KnowledgeDomainError):
    """Raised when a requested document does not exist."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Document not found")


class RevisionNotFoundError(KnowledgeDomainError):
    """Raised when a requested revision does not exist."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Revision not found")


class DuplicateContentError(KnowledgeDomainError):
    """Raised when a revision with identical content hash already exists."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Duplicate content hash already exists for this document")


class InvalidLifecycleTransitionError(KnowledgeDomainError):
    """Raised when a state transition is not allowed by the lifecycle rules."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Invalid lifecycle transition")


class ApprovedRevisionImmutabilityError(KnowledgeDomainError):
    """Raised when attempting to modify an approved revision."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Approved revisions are immutable")


class IngestionFailedError(KnowledgeDomainError):
    """Raised when the ingestion pipeline encounters a fatal error."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Ingestion failed")


class UnsupportedFileTypeError(KnowledgeDomainError):
    """Raised when the file extension or MIME type is not supported."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Unsupported file type")


class FileTooLargeError(KnowledgeDomainError):
    """Raised when the uploaded file exceeds the size limit."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "File too large")


class EncryptedPdfError(KnowledgeDomainError):
    """Raised when a PDF is encrypted and cannot be parsed."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Encrypted PDF is not supported")


class OcrRequiredError(KnowledgeDomainError):
    """Raised when a document contains only images and requires OCR."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Document requires OCR processing")


class InvalidChunkingConfigError(KnowledgeDomainError):
    """Raised when chunking configuration parameters are invalid."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Invalid chunking configuration")


class ZipBombDetectedError(KnowledgeDomainError):
    """Raised when a compressed file expansion ratio exceeds safety limits."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Zip bomb detected — compressed file ratio too high")


class PathTraversalError(KnowledgeDomainError):
    """Raised when a file path attempts directory traversal."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Path traversal detected")


class StorageError(KnowledgeDomainError):
    """Raised on file system or storage backend errors."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Storage error")


class SearchQueryEmptyError(KnowledgeDomainError):
    """Raised when a search query is empty or contains no meaningful tokens."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message or "Search query is empty")
