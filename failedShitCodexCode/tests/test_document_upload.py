from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.dependencies import _get_settings
from app.db.base import Base
from app.db.models import Document, JobLog, KnowledgeBase
from app.db.session import get_db_session
from app.jobs.queue import get_indexing_queue, get_ingestion_queue
from app.main import create_app


class FakeJob:
    def __init__(self, id_: str):
        self.id = id_


class FakeQueue:
    name = "ingestion"

    def __init__(self):
        self.enqueued: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def enqueue(self, func, *args, **kwargs) -> FakeJob:
        self.enqueued.append((func, args, kwargs))
        return FakeJob(f"fake-job-{len(self.enqueued)}")


class FakeNamedQueue(FakeQueue):
    def __init__(self, name: str):
        super().__init__()
        self.name = name


@pytest.fixture
def upload_client(tmp_path) -> Iterator[tuple[TestClient, Session, FakeQueue, FakeNamedQueue]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    db_session = session_factory()

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
        VECTOR_STORE_BACKEND="memory",
    )
    app = create_app()
    fake_queue = FakeQueue()
    fake_index_queue = FakeNamedQueue("indexing")

    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[_get_settings] = lambda: settings
    app.dependency_overrides[get_ingestion_queue] = lambda: fake_queue
    app.dependency_overrides[get_indexing_queue] = lambda: fake_index_queue

    with TestClient(app) as test_client:
        yield test_client, db_session, fake_queue, fake_index_queue

    db_session.close()


def test_upload_document_persists_file_and_database_record(upload_client) -> None:
    client, db_session, _fake_queue, _fake_index_queue = upload_client

    response = client.post(
        "/documents/upload",
        files={"file": ("Manual 中文.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_filename"] == "Manual_.pdf"
    assert payload["status"] == "uploaded"
    assert payload["mime_type"] == "application/pdf"

    document = db_session.scalar(select(Document))
    assert document is not None
    assert document.content_hash == payload["content_hash"]
    assert document.storage_path

    knowledge_base = db_session.scalar(select(KnowledgeBase))
    assert knowledge_base is not None
    assert knowledge_base.name == "default"


def test_upload_duplicate_document_reuses_existing_record(upload_client) -> None:
    client, db_session, _fake_queue, _fake_index_queue = upload_client

    first = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"same content", "application/pdf")},
    )
    second = client.post(
        "/documents/upload",
        files={"file": ("pcs-copy.pdf", b"same content", "application/pdf")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(db_session.scalars(select(Document)).all()) == 1


def test_upload_duplicate_failed_document_requeues_ingestion(upload_client) -> None:
    client, db_session, fake_queue, _fake_index_queue = upload_client

    first = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"same content", "application/pdf")},
    )
    document = db_session.scalar(select(Document))
    job_log = db_session.scalar(select(JobLog))
    assert document is not None
    assert job_log is not None
    document.status = "failed"
    job_log.status = "failed"
    db_session.commit()

    second = client.post(
        "/documents/upload",
        files={"file": ("pcs-copy.pdf", b"same content", "application/pdf")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(fake_queue.enqueued) == 2
    assert len(db_session.scalars(select(JobLog)).all()) == 2


def test_upload_duplicate_unfinished_document_refreshes_storage_path(upload_client) -> None:
    client, db_session, fake_queue, _fake_index_queue = upload_client

    first = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"same content", "application/pdf")},
    )
    document = db_session.scalar(select(Document))
    assert document is not None
    original_path = document.storage_path
    document.status = "failed"
    document.storage_path = "var/uploads/missing.pdf"
    db_session.scalar(select(JobLog)).status = "failed"
    db_session.commit()

    second = client.post(
        "/documents/upload",
        files={"file": ("pcs-copy.pdf", b"same content", "application/pdf")},
    )
    db_session.refresh(document)

    assert first.status_code == 201
    assert second.status_code == 201
    assert document.storage_path != original_path
    assert document.storage_path != "var/uploads/missing.pdf"
    assert document.source_filename == "pcs-copy.pdf"
    assert len(fake_queue.enqueued) == 2


def test_upload_document_enqueues_ingestion_job_and_records_job_log(upload_client) -> None:
    client, db_session, fake_queue, _fake_index_queue = upload_client

    response = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"content to ingest", "application/pdf")},
    )

    assert response.status_code == 201
    assert len(fake_queue.enqueued) == 1
    _func, args, kwargs = fake_queue.enqueued[0]
    assert args[0] == response.json()["id"]
    assert args[1] == str(db_session.scalar(select(JobLog)).id)
    assert kwargs["job_timeout"] == client.app.dependency_overrides[_get_settings]().rq_ingestion_timeout_seconds
    assert "retry" in kwargs

    job_log = db_session.scalar(select(JobLog))
    assert job_log is not None
    assert args[1] == str(job_log.id)
    assert job_log.queue_name == "ingestion"
    assert job_log.job_type == "ingest_document"
    assert job_log.status == "queued"
    assert job_log.rq_job_id == "fake-job-1"


def test_upload_document_rejects_non_pdf(upload_client) -> None:
    client, _db_session, fake_queue, _fake_index_queue = upload_client

    response = client.post(
        "/documents/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert fake_queue.enqueued == []


def test_upload_document_rejects_oversized_pdf(upload_client) -> None:
    client, _db_session, fake_queue, _fake_index_queue = upload_client
    original_settings = client.app.dependency_overrides[_get_settings]()
    client.app.dependency_overrides[_get_settings] = lambda: Settings(
        MAX_UPLOAD_SIZE_BYTES=4,
        UPLOAD_DIR=original_settings.upload_dir,
        PARSED_DIR=original_settings.parsed_dir,
        INDEX_DIR=original_settings.index_dir,
    )

    response = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"%PDF-too-large", "application/pdf")},
    )

    assert response.status_code == 400
    assert fake_queue.enqueued == []


def test_document_management_routes_support_enable_disable_reindex_and_retry(upload_client) -> None:
    client, db_session, fake_queue, fake_index_queue = upload_client

    response = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"content to ingest", "application/pdf")},
    )
    document_id = response.json()["id"]
    document = db_session.scalar(select(Document))
    assert document is not None

    disable_response = client.post(f"/documents/{document_id}/disable")
    enable_response = client.post(f"/documents/{document_id}/enable")
    reindex_response = client.post(f"/documents/{document_id}/reindex")

    job_log = db_session.scalar(select(JobLog).where(JobLog.job_type == "ingest_document"))
    assert job_log is not None
    job_log.status = "failed"
    db_session.commit()

    retry_response = client.post(f"/documents/{document_id}/jobs/{job_log.id}/retry")

    assert disable_response.status_code == 200
    assert disable_response.json()["is_enabled"] is False
    assert enable_response.status_code == 200
    assert enable_response.json()["is_enabled"] is True
    assert reindex_response.status_code == 202
    assert retry_response.status_code == 202
    assert fake_index_queue.enqueued
    assert len(fake_queue.enqueued) == 2
    assert len(fake_index_queue.enqueued[0][1]) == 2


def test_document_delete_route_removes_document(upload_client) -> None:
    client, db_session, _fake_queue, _fake_index_queue = upload_client

    response = client.post(
        "/documents/upload",
        files={"file": ("pcs.pdf", b"%PDF-1.4 content", "application/pdf")},
    )
    document_id = response.json()["id"]

    delete_response = client.delete(f"/documents/{document_id}")

    assert delete_response.status_code == 204
    assert db_session.scalar(select(Document)) is None
