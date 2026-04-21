"""Document ingestion service - upload handling and validation."""
from __future__ import annotations

import hashlib
import uuid

import filetype
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Document
from app.db.repositories.documents import DocumentRepository
from app.db.repositories.kb import KBRepository
from app.storage.base import StorageBackend

logger = get_logger(__name__)


class IngestionServiceError(Exception):
    """Base exception for ingestion service errors."""


class KBNotFoundError(IngestionServiceError):
    """Raised when the target knowledge base is not found."""


class InvalidFileError(IngestionServiceError):
    """Raised when the uploaded file fails validation."""


class FileTooLargeError(IngestionServiceError):
    """Raised when the uploaded file exceeds size limit."""


class DuplicateDocumentError(IngestionServiceError):
    """Raised when a duplicate document is detected."""

    def __init__(self, message: str, existing_document: Document) -> None:
        super().__init__(message)
        self.existing_document = existing_document


class IngestionService:
    """Service layer for document upload and ingestion."""

    def __init__(
        self,
        session: AsyncSession,
        storage: StorageBackend,
        settings: Settings,
    ) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings
        self.doc_repo = DocumentRepository(session)
        self.kb_repo = KBRepository(session)

    def _compute_sha256(self, data: bytes) -> str:
        """Compute SHA-256 hash of file data."""
        return hashlib.sha256(data).hexdigest()

    def _validate_mime_type(self, data: bytes, content_type: str | None) -> str:
        """Validate file MIME type using magic bytes and Content-Type header.

        Returns the validated MIME type string.
        Raises InvalidFileError if not a valid PDF.
        """
        # Check magic bytes first
        kind = filetype.guess(data)
        magic_mime = kind.mime if kind else None

        if magic_mime != "application/pdf":
            raise InvalidFileError(
                f"Invalid file type: expected application/pdf, "
                f"got '{magic_mime or 'unknown'}' from file content"
            )

        # Also validate Content-Type header if provided
        if content_type and content_type != "application/pdf":
            raise InvalidFileError(
                f"Content-Type mismatch: header says '{content_type}', "
                f"expected 'application/pdf'"
            )

        return "application/pdf"

    def _validate_file_size(self, data: bytes) -> None:
        """Validate file size against configured limit.

        Raises FileTooLargeError if file exceeds max_upload_size_bytes.
        """
        max_size = self.settings.max_upload_size_bytes
        if len(data) > max_size:
            raise FileTooLargeError(
                f"File size {len(data)} bytes exceeds maximum "
                f"allowed size of {max_size} bytes ({max_size // (1024 * 1024)}MB)"
            )

    async def upload_document(
        self,
        *,
        knowledge_base_id: uuid.UUID,
        filename: str,
        content_type: str | None,
        file_data: bytes,
        document_type: str = "unknown",
        parser_profile: str | None = None,
    ) -> tuple[Document, bool]:
        """Upload a document to a knowledge base.

        Returns:
            A tuple of (document, is_new) where is_new is True if the document
            was newly created, False if it was a duplicate.

        Raises:
            KBNotFoundError: If the knowledge base doesn't exist.
            InvalidFileError: If the file type is invalid.
            FileTooLargeError: If the file exceeds size limit.
        """
        # 1. Validate KB exists
        kb = await self.kb_repo.get_by_id(knowledge_base_id)
        if kb is None:
            raise KBNotFoundError(f"Knowledge base {knowledge_base_id} not found")

        # 2. Validate file size
        self._validate_file_size(file_data)

        # 3. Validate MIME type
        mime_type = self._validate_mime_type(file_data, content_type)

        # 4. Compute content hash
        content_hash = self._compute_sha256(file_data)

        # 5. Check for duplicate
        existing = await self.doc_repo.get_by_kb_and_hash(knowledge_base_id, content_hash)
        if existing is not None:
            logger.info(
                "duplicate_document_detected",
                kb_id=str(knowledge_base_id),
                content_hash=content_hash,
                existing_doc_id=str(existing.id),
            )
            return existing, False

        # 6. Generate doc ID and storage path
        doc_id = uuid.uuid4()
        storage_path = f"{knowledge_base_id}/{doc_id}/{filename}"

        # 7. Save file to storage
        await self.storage.write(storage_path, file_data)

        # 8. Create document record
        doc = await self.doc_repo.create(
            knowledge_base_id=knowledge_base_id,
            title=filename,
            source_filename=filename,
            storage_path=storage_path,
            content_hash=content_hash,
            mime_type=mime_type,
            file_size_bytes=len(file_data),
            document_type=document_type,
            status="uploaded",
        )
        # Override the auto-generated ID with our pre-generated one for path consistency
        doc.id = doc_id
        await self.session.flush()

        logger.info(
            "document_uploaded",
            doc_id=str(doc.id),
            kb_id=str(knowledge_base_id),
            filename=filename,
            size=len(file_data),
            content_hash=content_hash,
        )

        return doc, True
