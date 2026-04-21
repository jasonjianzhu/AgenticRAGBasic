from __future__ import annotations

import hashlib
import logging
import uuid
from multiprocessing import get_context
from multiprocessing.queues import Queue
from pathlib import Path
from queue import Empty
from typing import Any

from app.db.models import Chunk
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository
from app.rag.chunking.models import ChunkDraft, ChunkingOptions
from app.rag.chunking.registry import ChunkerRegistry, build_default_chunker_registry
from app.rag.chunking.utils import detect_language, estimate_token_count
from app.rag.classification.base import DocumentClassifier
from app.rag.classification.models import DocumentClassification
from app.rag.classification.rule_based import RuleBasedDocumentClassifier
from app.rag.parsing.base import DocumentParser
from app.rag.parsing.models import ParseOptions, ParsedDocument, ParserProfile
from app.rag.parsing.serialization import read_parsed_document, write_parsed_document
from app.rag.parsing.simple_parser import MinimalTextParser, _sanitize_text


logger = logging.getLogger(__name__)


class DocumentIngestionService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        parser: DocumentParser,
        classifier: DocumentClassifier | None = None,
        chunker_registry: ChunkerRegistry | None = None,
        chunking_options: ChunkingOptions | None = None,
    ):
        self.session = session
        self.settings = settings
        self.parser = parser
        self.classifier = classifier or RuleBasedDocumentClassifier()
        self.chunker_registry = chunker_registry or build_default_chunker_registry()
        self.chunking_options = chunking_options or ChunkingOptions()

    def parse_document(self, document_id: str | uuid.UUID, profile: ParserProfile | str = ParserProfile.BALANCED):
        version, _parsed_document = self._parse_document(document_id, profile)
        return version

    def ingest_document(self, document_id: str | uuid.UUID, profile: ParserProfile | str = ParserProfile.BALANCED):
        logger.info("Ingestion started: document_id=%s profile=%s", document_id, profile)
        version, parsed_document = self._parse_document(document_id, profile)
        document_uuid = uuid.UUID(str(document_id))
        document_repository = DocumentRepository(self.session)
        version_repository = DocumentVersionRepository(self.session)
        document = document_repository.get(document_uuid)
        if document is None:
            raise ValueError(f"Document not found: {document_uuid}")

        classification = self._classify(document_type=document.document_type, parsed_document=parsed_document)
        logger.info(
            "Document classified: document_id=%s document_type=%s confidence=%s strategy=%s",
            document.id,
            classification.document_type,
            classification.confidence,
            classification.strategy,
        )
        document_repository.update_document_type(document.id, classification.document_type)

        chunker = self.chunker_registry.select(document_type=classification.document_type)
        chunk_drafts = chunker.chunk(parsed_document, self.chunking_options)
        logger.info(
            "Document chunked: document_id=%s version_id=%s chunker=%s draft_count=%s",
            document.id,
            version.id,
            chunker.name,
            len(chunk_drafts),
        )
        self._persist_chunks(document=document, version=version, chunk_drafts=chunk_drafts, chunker_name=chunker.name)

        version_repository.mark_chunked(
            version.id,
            metadata={
                "chunk_count": len(chunk_drafts),
                "chunker": chunker.name,
                "document_type": classification.document_type,
                "classification": {
                    "strategy": classification.strategy,
                    "confidence": classification.confidence,
                    "metadata": classification.metadata,
                },
            },
        )
        document_repository.update_status(document.id, "chunked")
        self.session.flush()
        logger.info("Ingestion finished: document_id=%s version_id=%s", document.id, version.id)
        return version

    def _parse_document(
        self,
        document_id: str | uuid.UUID,
        profile: ParserProfile | str = ParserProfile.BALANCED,
    ) -> tuple:
        document_uuid = uuid.UUID(str(document_id))
        document_repository = DocumentRepository(self.session)
        version_repository = DocumentVersionRepository(self.session)
        document = document_repository.get(document_uuid)
        if document is None:
            raise ValueError(f"Document not found: {document_uuid}")

        logger.info("Parsing started: document_id=%s path=%s profile=%s", document.id, document.storage_path, profile)
        document_repository.update_status(document.id, "parsing")
        latest_version = version_repository.get_latest_for_document(document.id)
        next_version_number = 1 if latest_version is None else latest_version.version_number + 1
        version = version_repository.create(
            document_id=document.id,
            version_number=next_version_number,
            parser_profile=str(profile),
            status="parsing",
        )

        options = ParseOptions.from_profile(profile)
        parsed_document = self._parse_with_cache(document, version.version_number, options)
        parsed_path = self.settings.parsed_dir / f"{document.id}" / f"v{version.version_number}.json"
        write_parsed_document(parsed_document, parsed_path)
        logger.info(
            "Parsed document written: document_id=%s version_id=%s parsed_path=%s parser=%s",
            document.id,
            version.id,
            parsed_path,
            parsed_document.metadata.get("parser"),
        )

        version_repository.mark_parsed(
            version.id,
            parsed_path=str(parsed_path),
            metadata=parsed_document.metadata,
        )
        document_repository.update_status(document.id, "parsed")
        self.session.flush()
        return version, parsed_document

    def _parse_with_cache(self, document, version_number: int, options: ParseOptions) -> ParsedDocument:
        cache_path = self.settings.parsed_dir / f"{document.id}" / f"v{version_number}.json"
        document_path = Path(document.storage_path)
        if cache_path.exists():
            cached = read_parsed_document(cache_path)
            if cached.source_path == document_path:
                logger.info("Using parsed document cache: document_id=%s version=%s path=%s", document.id, version_number, cache_path)
                return cached
            logger.warning(
                "Ignoring stale parsed cache because source path changed: document_id=%s version=%s cached_source=%s current_source=%s",
                document.id,
                version_number,
                cached.source_path,
                document_path,
            )

        path = document_path
        timeout = self.settings.parser_timeout_seconds
        context = get_context("spawn")
        result_queue = context.Queue(maxsize=1)
        process = context.Process(target=_parse_in_child_process, args=(self.parser, path, options, result_queue))
        process.start()
        process.join(timeout)

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            logger.warning(
                "Primary parser timed out and was terminated, falling back to minimal parser: document_id=%s timeout=%s",
                document.id,
                timeout,
            )
            return MinimalTextParser().parse(path, options)

        try:
            payload = result_queue.get_nowait()
        except Empty:
            logger.error("Primary parser exited without a result, falling back to minimal parser: document_id=%s", document.id)
            return MinimalTextParser().parse(path, options)

        if payload["status"] == "ok":
            return payload["document"]

        logger.error(
            "Primary parser failed, falling back to minimal parser: document_id=%s error=%s",
            document.id,
            payload["error"],
        )
        return MinimalTextParser().parse(path, options)

    def _classify(self, document_type: str, parsed_document: ParsedDocument) -> DocumentClassification:
        if document_type != "unknown":
            return DocumentClassification(
                document_type=document_type,
                confidence=1.0,
                strategy="manual_override",
            )
        return self.classifier.classify(parsed_document)

    def _persist_chunks(self, document, version, chunk_drafts: list[ChunkDraft], chunker_name: str) -> None:
        repository = ChunkRepository(self.session)
        repository.delete_by_document_version(version.id)
        chunks: list[Chunk] = []
        for index, chunk in enumerate(chunk_drafts, start=1):
            clean_content = _sanitize_text(chunk.content).strip()
            if not clean_content:
                continue
            clean_section_path = _sanitize_text(chunk.section_path).strip() if chunk.section_path else None
            chunks.append(
                Chunk(
                    knowledge_base_id=document.knowledge_base_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    ordinal=index,
                    chunk_type=chunk.chunk_type,
                    section_path=clean_section_path or None,
                    content=clean_content,
                    content_hash=hashlib.sha256(clean_content.encode("utf-8")).hexdigest(),
                    token_count=estimate_token_count(clean_content),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    language=detect_language(clean_content),
                    product_model=chunk.metadata.get("product_model"),
                    metadata_={
                        "chunker": chunker_name,
                        **chunk.metadata,
                    },
                )
            )
        repository.create_many(chunks)
        logger.info(
            "Chunks persisted: document_id=%s version_id=%s chunker=%s chunk_count=%s",
            document.id,
            version.id,
            chunker_name,
            len(chunks),
        )


def _parse_in_child_process(parser: DocumentParser, path: Path, options: ParseOptions, result_queue: Queue) -> None:
    try:
        result_queue.put({"status": "ok", "document": parser.parse(path, options)})
    except Exception as exc:
        result_queue.put({"status": "error", "error": str(exc)})
