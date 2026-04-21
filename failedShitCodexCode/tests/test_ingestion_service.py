from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.rag.parsing.models import ParseOptions, ParsedBlock, ParsedBlockType, ParsedDocument
from app.rag.parsing.simple_parser import MinimalTextParser, SimpleTextParser
from app.services.ingestion import DocumentIngestionService


def test_document_ingestion_service_parses_and_persists_artifact(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    source_path = tmp_path / "manual.txt"
    source_path.write_text("Intro\n\nAlarm table", encoding="utf-8")

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="Manual",
            source_filename="manual.txt",
            storage_path=str(source_path),
            content_hash="hash",
            mime_type="text/plain",
            file_size_bytes=source_path.stat().st_size,
        )

        version = DocumentIngestionService(
            session=session,
            settings=settings,
            parser=SimpleTextParser(),
        ).parse_document(document.id, profile="fast")

        updated_document = DocumentRepository(session).get(document.id)
        latest_version = DocumentVersionRepository(session).get_latest_for_document(document.id)
        assert updated_document is not None
        assert updated_document.status == "parsed"
        assert latest_version is not None
        assert latest_version.id == version.id
        assert latest_version.status == "parsed"
        assert latest_version.parsed_path is not None

        payload = json.loads((tmp_path / "parsed" / str(document.id) / "v1.json").read_text(encoding="utf-8"))
        assert payload["metadata"]["parser"] == "simple_text"
        assert [block["text"] for block in payload["blocks"]] == ["Intro", "Alarm table"]


class StubStructuredParser:
    def parse(self, path, options: ParseOptions) -> ParsedDocument:
        return ParsedDocument(
            source_path=Path(path),
            text="# Installation\n\nSafety precautions\n\n| Code | Meaning |\n|---|---|\n|E101|Overheat|",
            blocks=[
                ParsedBlock(type=ParsedBlockType.TEXT, text="# Installation", page_start=1),
                ParsedBlock(type=ParsedBlockType.TEXT, text="Safety precautions", page_start=1),
                ParsedBlock(
                    type=ParsedBlockType.TABLE,
                    text="| Code | Meaning |\n|---|---|\n|E101|Overheat|",
                    page_start=2,
                    page_end=2,
                ),
            ],
            metadata={"parser": "stub"},
        )


def test_document_ingestion_service_classifies_and_persists_chunks(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    source_path = tmp_path / "manual.txt"
    source_path.write_text("placeholder", encoding="utf-8")

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="Manual",
            source_filename="manual.txt",
            storage_path=str(source_path),
            content_hash="hash",
            mime_type="text/plain",
            file_size_bytes=source_path.stat().st_size,
        )

        version = DocumentIngestionService(
            session=session,
            settings=settings,
            parser=StubStructuredParser(),
        ).ingest_document(document.id, profile="fast")

        updated_document = DocumentRepository(session).get(document.id)
        latest_version = DocumentVersionRepository(session).get_latest_for_document(document.id)
        chunks = ChunkRepository(session).list_by_document(document.id)

        assert updated_document is not None
        assert updated_document.status == "chunked"
        assert updated_document.document_type == "manual"
        assert latest_version is not None
        assert latest_version.id == version.id
        assert latest_version.status == "chunked"
        assert latest_version.metadata_["chunk_count"] == 2
        assert len(chunks) == 2
        assert chunks[0].metadata_["chunker"] == "docling_hybrid"
        assert chunks[1].chunk_type == "table"


def test_document_ingestion_service_sanitizes_binary_text_before_persisting_chunks(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    source_path = tmp_path / "manual.pdf"
    source_path.write_bytes(b"hello\x00world\n\nsection\x07text")

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="Manual",
            source_filename="manual.pdf",
            storage_path=str(source_path),
            content_hash="hash",
            mime_type="application/pdf",
            file_size_bytes=source_path.stat().st_size,
            document_type="faq",
        )

        DocumentIngestionService(
            session=session,
            settings=settings,
            parser=MinimalTextParser(),
        ).ingest_document(document.id, profile="fast")

        chunks = ChunkRepository(session).list_by_document(document.id)
        assert chunks
        assert all("\x00" not in chunk.content for chunk in chunks)


class StubDirtyChunkParser:
    def parse(self, path, options: ParseOptions) -> ParsedDocument:
        return ParsedDocument(
            source_path=Path(path),
            text="# head\x00ing\n\nbody\x00text",
            blocks=[ParsedBlock(type=ParsedBlockType.TEXT, text="# head\x00ing\n\nbody\x00text")],
            metadata={"parser": "dirty"},
        )


def test_document_ingestion_service_sanitizes_section_path_before_persisting_chunks(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    source_path = tmp_path / "manual.txt"
    source_path.write_text("placeholder", encoding="utf-8")

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="Manual",
            source_filename="manual.txt",
            storage_path=str(source_path),
            content_hash="hash",
            mime_type="text/plain",
            file_size_bytes=source_path.stat().st_size,
            document_type="faq",
        )

        DocumentIngestionService(
            session=session,
            settings=settings,
            parser=StubDirtyChunkParser(),
        ).ingest_document(document.id, profile="fast")

        chunks = ChunkRepository(session).list_by_document(document.id)
        assert chunks
        assert all(chunk.section_path is None or "\x00" not in chunk.section_path for chunk in chunks)
