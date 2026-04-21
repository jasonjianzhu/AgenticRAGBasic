from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.repositories import JobLogRepository
from app.jobs.lifecycle import run_with_job_lifecycle


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    with session_factory() as db_session:
        yield db_session


def test_run_with_job_lifecycle_marks_success(session: Session) -> None:
    job = JobLogRepository(session).create(queue_name="ingestion", job_type="ingest_document")
    session.commit()

    result = run_with_job_lifecycle(session, job.id, lambda: "ok")

    updated = JobLogRepository(session).get(job.id)
    assert result == "ok"
    assert updated is not None
    assert updated.status == "finished"
    assert updated.attempts == 1
    assert updated.started_at is not None
    assert updated.finished_at is not None


def test_run_with_job_lifecycle_marks_failure_and_reraises(session: Session) -> None:
    job = JobLogRepository(session).create(queue_name="ingestion", job_type="ingest_document")
    session.commit()

    with pytest.raises(RuntimeError, match="boom"):
        run_with_job_lifecycle(session, job.id, lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    updated = JobLogRepository(session).get(job.id)
    assert updated is not None
    assert updated.status == "failed"
    assert updated.attempts == 1
    assert updated.error_message == "boom"
    assert updated.finished_at is not None


def test_run_with_job_lifecycle_rolls_back_before_marking_failure(session: Session) -> None:
    job = JobLogRepository(session).create(queue_name="ingestion", job_type="ingest_document")
    session.commit()

    def failing_operation() -> None:
        session.rollback()
        raise SQLAlchemyError("flush failed")

    with pytest.raises(SQLAlchemyError, match="flush failed"):
        run_with_job_lifecycle(session, job.id, failing_operation)

    updated = JobLogRepository(session).get(job.id)
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error_message == "flush failed"
