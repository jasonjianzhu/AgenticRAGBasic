"""Tests for the ingestion task service (S5-05, S5-06, S6-09).

Tests the full ingestion pipeline with mocked parsers and storage.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.db.base import Base
from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.knowledge.rag.parsing.base import ParsedDocument, ParsedPage, ParsedTable
from app.knowledge.services.ingestion_task import IngestionTaskService, IngestionTaskError
from app.common.storage.local import LocalStorage


# --- Fake parsed document for mocking ---

FAKE_PARSED = ParsedDocument(
    content="# Title\n\nSome content about 操作手册 and maintenance.\n\nMore text here.",
    pages=[ParsedPage(page_number=1, content="Some content")],
    tables=[
        ParsedTable(
            content="| Col1 | Col2 |\n|---|---|\n| A | B |",
            page_number=1,
            caption="Table 1",
        )
    ],
    metadata={"parser_name": "fake", "profile": "balanced"},
)

FAKE_MANUAL_PARSED = ParsedDocument(
    content="# 操作手册\n\n本操作手册介绍了产品的使用方法。\n\n维护手册内容。",
    pages=[ParsedPage(page_number=1, content="操作手册内容")],
    tables=[],
    metadata={"parser_name": "fake", "profile": "balanced"},
)


def _make_pdf_bytes() -> bytes:
    """Minimal valid PDF bytes (recognized by filetype but not parseable)."""
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n115\n%%EOF"
    )


def _make_sync_session(tmp_path=None):
    """Create a sync SQLite session for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory(), engine


def _setup_doc(session, storage, *, filename="test.pdf"):
    """Create a KB and document with a stored PDF file (sync)."""
    import asyncio

    kb = KnowledgeBase(
        name=f"Test KB {uuid.uuid4().hex[:8]}",
        settings={"default_chunker": "docling_hybrid", "default_parser_profile": "balanced"},
    )
    session.add(kb)
    session.flush()

    doc_id = uuid.uuid4()
    pdf_data = _make_pdf_bytes()
    storage_path = f"{kb.id}/{doc_id}/{filename}"

    loop = asyncio.new_event_loop()
    loop.run_until_complete(storage.write(storage_path, pdf_data))
    loop.close()

    doc = Document(
        id=doc_id,
        knowledge_base_id=kb.id,
        title=filename,
        source_filename=filename,
        storage_path=storage_path,
        content_hash=hashlib.sha256(pdf_data).hexdigest(),
        mime_type="application/pdf",
        file_size_bytes=len(pdf_data),
        document_type="unknown",
        status="uploaded",
    )
    session.add(doc)
    session.flush()
    session.commit()
    return doc, kb


def _make_settings():
    from app.common.core.config import Settings
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///",
        DATABASE_URL_SYNC="sqlite:///",
        APP_ENV="testing",
    )


@pytest.mark.unit
class TestIngestionTaskServiceSync:
    """Tests for IngestionTaskService using synchronous SQLite session."""

    def test_run_document_not_found(self, tmp_path):
        """Should raise IngestionTaskError when document not found."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)
        try:
            service = IngestionTaskService(session, storage, _make_settings())
            with pytest.raises(IngestionTaskError, match="not found"):
                service.run(uuid.uuid4())
        finally:
            session.close()
            engine.dispose()

    def test_run_success_full_pipeline(self, tmp_path):
        """Full pipeline: parse → chunk → persist → classify."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)

            service = IngestionTaskService(session, storage, _make_settings())

            # Mock the parser to return our fake parsed document
            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id, parser_profile="balanced")

            session.refresh(doc)
            assert doc.status == "chunked"

            # Verify DocumentVersion was created
            result = session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
            )
            versions = list(result.scalars().all())
            assert len(versions) == 1
            assert versions[0].version_number == 1
            assert versions[0].parser_profile == "balanced"
            assert versions[0].status == "chunked"
            assert versions[0].parsed_path is not None

            # Verify chunks were created
            result = session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )
            chunks = list(result.scalars().all())
            assert len(chunks) > 0

        finally:
            session.close()
            engine.dispose()

    def test_run_failure_sets_status_to_failed(self, tmp_path):
        """On failure, document status should be set to 'failed'."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)

            service = IngestionTaskService(session, storage, _make_settings())

            # Mock the parser to raise an error
            with patch.object(service, "_parse_document", side_effect=RuntimeError("Parse failed!")):
                with pytest.raises(IngestionTaskError):
                    service.run(doc.id)

            session.refresh(doc)
            assert doc.status == "failed"

        finally:
            session.close()
            engine.dispose()

    def test_classification_updates_document_type(self, tmp_path):
        """Classification should update document_type when not 'unknown'."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage, filename="操作手册.pdf")

            service = IngestionTaskService(session, storage, _make_settings())

            # Use content that triggers "manual" classification
            with patch.object(service, "_parse_document", return_value=FAKE_MANUAL_PARSED):
                service.run(doc.id)

            session.refresh(doc)
            assert doc.document_type == "manual"

        finally:
            session.close()
            engine.dispose()

    def test_version_number_increments(self, tmp_path):
        """Running ingestion twice should create version 1 and 2."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)

            service = IngestionTaskService(session, storage, _make_settings())

            # First run
            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id)

            session.refresh(doc)
            assert doc.status == "chunked"

            # Reset status for second run
            doc.status = "uploaded"
            session.commit()

            # Second run
            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id)

            result = session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.version_number)
            )
            versions = list(result.scalars().all())
            assert len(versions) == 2
            assert versions[0].version_number == 1
            assert versions[1].version_number == 2

        finally:
            session.close()
            engine.dispose()

    def test_chunks_have_correct_metadata(self, tmp_path):
        """Chunks should have correct document and KB references."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)

            service = IngestionTaskService(session, storage, _make_settings())

            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id)

            result = session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )
            chunks = list(result.scalars().all())
            for chunk in chunks:
                assert chunk.knowledge_base_id == kb.id
                assert chunk.document_id == doc.id
                assert chunk.content_hash is not None
                assert chunk.ordinal >= 0

        finally:
            session.close()
            engine.dispose()

    def test_table_chunks_created(self, tmp_path):
        """Table chunker should create table-type chunks."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)

            service = IngestionTaskService(session, storage, _make_settings())

            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id)

            result = session.execute(
                select(Chunk).where(
                    Chunk.document_id == doc.id,
                    Chunk.chunk_type == "table",
                )
            )
            table_chunks = list(result.scalars().all())
            assert len(table_chunks) > 0

        finally:
            session.close()
            engine.dispose()

    def test_parsed_output_saved_to_storage(self, tmp_path):
        """Parsed output should be saved as JSON to storage."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)

            service = IngestionTaskService(session, storage, _make_settings())

            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id)

            # Check that parsed JSON exists
            result = session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
            )
            version = result.scalars().first()
            assert version.parsed_path is not None

            # Verify the file exists on disk
            parsed_path = Path(version.parsed_path)
            assert parsed_path.exists()

            # Verify it's valid JSON
            with open(parsed_path) as f:
                data = json.load(f)
            assert "content" in data
            assert "pages" in data

        finally:
            session.close()
            engine.dispose()

    def test_status_flow_uploaded_to_parsing_to_chunked(self, tmp_path):
        """Should follow uploaded → parsing → chunked status flow."""
        session, engine = _make_sync_session()
        storage = LocalStorage(base_dir=tmp_path)

        try:
            doc, kb = _setup_doc(session, storage)
            assert doc.status == "uploaded"

            statuses_seen = []
            original_flush = session.flush

            def tracking_flush(*args, **kwargs):
                statuses_seen.append(doc.status)
                return original_flush(*args, **kwargs)

            session.flush = tracking_flush

            service = IngestionTaskService(session, storage, _make_settings())

            with patch.object(service, "_parse_document", return_value=FAKE_PARSED):
                service.run(doc.id)

            assert "parsing" in statuses_seen
            assert "chunked" in statuses_seen

            session.flush = original_flush

        finally:
            session.close()
            engine.dispose()


@pytest.mark.unit
class TestIngestionTaskServiceInterface:
    """Tests for IngestionTaskService class interface."""

    def test_has_expected_methods(self):
        """IngestionTaskService should have the expected public interface."""
        assert hasattr(IngestionTaskService, "run")
        assert callable(getattr(IngestionTaskService, "run"))

    def test_instantiation(self, tmp_path):
        """Should be instantiable with required args."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///", echo=False)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = factory()
        storage = LocalStorage(base_dir=tmp_path)

        service = IngestionTaskService(session, storage, _make_settings())
        assert service.session is session
        assert service.storage is storage

        session.close()
        engine.dispose()


@pytest.mark.unit
class TestUploadEnqueuesJob:
    """Tests that upload → enqueue chain works (S5-05)."""

    @pytest.mark.asyncio
    async def test_upload_returns_job_id(self, tmp_path):
        """Upload of a new document should return a job_id."""
        from httpx import ASGITransport, AsyncClient
        from app.knowledge.api.routes.documents import get_job_queue, get_storage
        from app.common.core.dependencies import get_db
        from app.knowledge.jobs.queue import InMemoryJobQueue
        from app.common.core.config import Settings
        from app.main_knowledge import create_knowledge_app
        _test_app = create_knowledge_app(settings=Settings(APP_ENV="testing"))

        engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            kb = KnowledgeBase(
                name="Upload Job KB",
                settings={"default_parser_profile": "balanced"},
            )
            session.add(kb)
            await session.flush()
            await session.commit()
            kb_id = kb.id

        app = _test_app
        job_queue = InMemoryJobQueue()

        async def _override_db():
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_storage] = lambda: LocalStorage(base_dir=Path(tmp_path))
        app.dependency_overrides[get_job_queue] = lambda: job_queue

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pdf_bytes = _make_pdf_bytes()
            response = await client.post(
                "/documents/upload",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
                data={"knowledge_base_id": str(kb_id)},
            )

        app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["job_id"] is not None
        uuid.UUID(data["job_id"])

        # Verify job was enqueued
        assert len(job_queue.jobs) == 1
        assert job_queue.jobs[0]["job_type"] == "ingest"

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_duplicate_upload_no_job_id(self, tmp_path):
        """Duplicate upload should return job_id=None."""
        from httpx import ASGITransport, AsyncClient
        from app.knowledge.api.routes.documents import get_job_queue, get_storage
        from app.common.core.dependencies import get_db
        from app.knowledge.jobs.queue import InMemoryJobQueue
        from app.common.core.config import Settings
        from app.main_knowledge import create_knowledge_app
        _test_app = create_knowledge_app(settings=Settings(APP_ENV="testing"))

        engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            kb = KnowledgeBase(
                name="Dedup Job KB",
                settings={"default_parser_profile": "balanced"},
            )
            session.add(kb)
            await session.flush()
            await session.commit()
            kb_id = kb.id

        app = _test_app
        job_queue = InMemoryJobQueue()

        async def _override_db():
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_storage] = lambda: LocalStorage(base_dir=Path(tmp_path))
        app.dependency_overrides[get_job_queue] = lambda: job_queue

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pdf_bytes = _make_pdf_bytes()

            # First upload
            resp1 = await client.post(
                "/documents/upload",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
                data={"knowledge_base_id": str(kb_id)},
            )
            assert resp1.status_code == 201
            assert resp1.json()["job_id"] is not None

            # Second upload (duplicate)
            resp2 = await client.post(
                "/documents/upload",
                files={"file": ("test2.pdf", pdf_bytes, "application/pdf")},
                data={"knowledge_base_id": str(kb_id)},
            )
            assert resp2.status_code == 200
            assert resp2.json()["job_id"] is None

        app.dependency_overrides.clear()

        # Only one job should have been enqueued
        assert len(job_queue.jobs) == 1

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_upload_job_id_field_present_in_response(self, tmp_path):
        """DocumentResponse should always include job_id field."""
        from httpx import ASGITransport, AsyncClient
        from app.knowledge.api.routes.documents import get_job_queue, get_storage
        from app.common.core.dependencies import get_db
        from app.knowledge.jobs.queue import InMemoryJobQueue
        from app.common.core.config import Settings
        from app.main_knowledge import create_knowledge_app
        _test_app = create_knowledge_app(settings=Settings(APP_ENV="testing"))

        engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            kb = KnowledgeBase(
                name="Field Test KB",
                settings={"default_parser_profile": "balanced"},
            )
            session.add(kb)
            await session.flush()
            await session.commit()
            kb_id = kb.id

        app = _test_app
        job_queue = InMemoryJobQueue()

        async def _override_db():
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_storage] = lambda: LocalStorage(base_dir=Path(tmp_path))
        app.dependency_overrides[get_job_queue] = lambda: job_queue

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pdf_bytes = _make_pdf_bytes()
            response = await client.post(
                "/documents/upload",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
                data={"knowledge_base_id": str(kb_id)},
            )

        app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        # job_id should always be present in the response
        assert "job_id" in data

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
