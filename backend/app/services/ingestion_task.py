"""Ingestion task service — runs the full parse → chunk → persist pipeline.

This service is designed to be called synchronously by RQ workers.
It uses synchronous DB sessions (not async) since RQ tasks are synchronous.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentVersion, JobLog
from app.rag.chunking.base import ChunkData
from app.rag.chunking.registry import default_registry
from app.rag.classification.rule_based import RuleBasedClassifier
from app.rag.parsing.base import ParsedDocument
from app.rag.parsing.docling_parser import DoclingParser
from app.rag.parsing.fallback import FallbackParser
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage

logger = get_logger(__name__)


class IngestionTaskError(Exception):
    """Raised when the ingestion task fails."""


class IngestionTaskService:
    """Runs the full ingestion pipeline: parse → chunk → persist.

    Designed for synchronous execution inside an RQ worker.
    All DB operations use a synchronous SQLAlchemy session.
    """

    def __init__(
        self,
        session: Session,
        storage: StorageBackend,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings or get_settings()

    def run(self, document_id: uuid.UUID, parser_profile: str = "balanced") -> None:
        """Execute ingestion for a document (synchronous, called by worker).

        Steps:
        1. Update document status to "parsing"
        2. Create a DocumentVersion record
        3. Try DoclingParser first, fall back to FallbackParser on failure
        4. Save parsed output to storage via serialization
        5. Run the appropriate chunker (from KB settings or default)
        6. Also run table_chunker on tables
        7. Save chunks to DB
        8. Run document type classification
        9. Update document status to "chunked"
        10. Update document_type if classified
        """
        doc = self.session.get(Document, document_id)
        if doc is None:
            raise IngestionTaskError(f"Document {document_id} not found")

        try:
            # 1. Update status to parsing
            doc.status = "parsing"
            self.session.flush()

            # 2. Create DocumentVersion
            version_number = self._next_version_number(document_id)
            version = DocumentVersion(
                document_id=document_id,
                version_number=version_number,
                parser_profile=parser_profile,
                status="parsing",
            )
            self.session.add(version)
            self.session.flush()

            # 3. Parse document
            file_path = self._resolve_file_path(doc.storage_path)
            parsed = self._parse_document(file_path, parser_profile)

            # 4. Save parsed output
            parsed_storage_path = self._save_parsed_output(
                kb_id=str(doc.knowledge_base_id),
                doc_id=str(document_id),
                version=version_number,
                parsed=parsed,
            )
            version.parsed_path = parsed_storage_path
            version.status = "parsed"
            self.session.flush()

            # 5 & 6. Run chunkers
            chunks = self._run_chunking(parsed, doc)

            # 7. Save chunks to DB
            self._save_chunks(
                knowledge_base_id=doc.knowledge_base_id,
                document_id=document_id,
                document_version_id=version.id,
                chunks=chunks,
            )

            # 8. Classify document type
            classified_type = self._classify_document(parsed, doc)

            # 9. Update document status to chunked
            doc.status = "chunked"
            version.status = "chunked"

            # 10. Update document_type if classified
            if classified_type and classified_type != "unknown":
                doc.document_type = classified_type

            self.session.flush()

            logger.info(
                "ingestion_complete",
                document_id=str(document_id),
                version=version_number,
                chunk_count=len(chunks),
                document_type=doc.document_type,
            )

        except Exception as e:
            # On failure: update document status to "failed"
            doc.status = "failed"
            self.session.flush()
            logger.exception(
                "ingestion_failed",
                document_id=str(document_id),
                error=str(e),
            )
            raise IngestionTaskError(f"Ingestion failed for document {document_id}: {e}") from e

    def _next_version_number(self, document_id: uuid.UUID) -> int:
        """Get the next version number for a document."""
        from sqlalchemy import func, select
        result = self.session.execute(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                DocumentVersion.document_id == document_id
            )
        )
        current_max = result.scalar() or 0
        return current_max + 1

    def _resolve_file_path(self, storage_path: str) -> str:
        """Resolve the storage path to an absolute file path."""
        # Run the async get_full_path in a sync context
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self.storage.get_full_path(storage_path))

    def _parse_document(self, file_path: str, profile: str) -> ParsedDocument:
        """Try DoclingParser first, fall back to FallbackParser."""
        loop = _get_or_create_event_loop()

        # Try Docling first
        try:
            docling = DoclingParser()
            parsed = loop.run_until_complete(docling.parse(file_path, profile))
            logger.info("parsed_with_docling", file_path=file_path, profile=profile)
            return parsed
        except Exception as docling_err:
            logger.warning(
                "docling_parse_failed_falling_back",
                file_path=file_path,
                error=str(docling_err),
            )

        # Fall back to FallbackParser
        fallback = FallbackParser()
        parsed = loop.run_until_complete(fallback.parse(file_path, profile))
        logger.info("parsed_with_fallback", file_path=file_path)
        return parsed

    def _save_parsed_output(
        self,
        kb_id: str,
        doc_id: str,
        version: int,
        parsed: ParsedDocument,
    ) -> str:
        """Save parsed document to storage."""
        import json
        from app.rag.parsing.serialization import parsed_json_path

        path = parsed_json_path(kb_id, doc_id, version)
        data = json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")

        loop = _get_or_create_event_loop()
        written_path = loop.run_until_complete(self.storage.write(path, data))
        return written_path

    def _run_chunking(self, parsed: ParsedDocument, doc: Document) -> list[ChunkData]:
        """Run the appropriate chunker + table chunker."""
        # Determine chunker name from KB settings or default
        kb = doc.knowledge_base
        chunker_name = "docling_hybrid"
        if kb and hasattr(kb, "settings") and isinstance(kb.settings, dict):
            chunker_name = kb.settings.get("default_chunker", "docling_hybrid")

        # Run main chunker
        try:
            chunker = default_registry.get(chunker_name)
        except KeyError:
            chunker = default_registry.get("docling_hybrid")

        chunks = chunker.chunk(parsed)

        # Run table chunker on tables
        if parsed.tables:
            try:
                table_chunker = default_registry.get("table")
                table_chunks = table_chunker.chunk(parsed)
                # Adjust ordinals for table chunks to follow text chunks
                offset = len(chunks)
                for tc in table_chunks:
                    tc.ordinal = offset + tc.ordinal
                chunks.extend(table_chunks)
            except KeyError:
                logger.warning("table_chunker_not_found")

        return chunks

    def _save_chunks(
        self,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        chunks: list[ChunkData],
    ) -> None:
        """Save chunks to DB using synchronous session."""
        import hashlib
        from app.db.models import Chunk

        for chunk_data in chunks:
            content_hash = hashlib.sha256(chunk_data.content.encode("utf-8")).hexdigest()
            chunk = Chunk(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                document_version_id=document_version_id,
                ordinal=chunk_data.ordinal,
                chunk_type=chunk_data.chunk_type,
                section_path=chunk_data.section_path,
                content=chunk_data.content,
                content_hash=content_hash,
                token_count=chunk_data.token_count,
                page_start=chunk_data.page_start,
                page_end=chunk_data.page_end,
                metadata_=chunk_data.metadata,
            )
            self.session.add(chunk)
        self.session.flush()

    def _classify_document(self, parsed: ParsedDocument, doc: Document) -> str:
        """Run rule-based document type classification."""
        classifier = RuleBasedClassifier()
        # Use human override if document_type was explicitly set
        human_override = doc.document_type if doc.document_type != "unknown" else None
        return classifier.classify(
            content=parsed.content,
            filename=doc.source_filename,
            human_override=human_override,
        )


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get the current event loop or create a new one for sync contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
