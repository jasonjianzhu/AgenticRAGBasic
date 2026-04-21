from __future__ import annotations

from app.db.base import Base
from app.db.models import Chunk, Document, DocumentVersion, JobLog, KnowledgeBase, QueryLog


def test_phase1_core_tables_are_registered() -> None:
    expected_tables = {
        "knowledge_bases",
        "documents",
        "document_versions",
        "chunks",
        "job_logs",
        "query_logs",
        "app_configs",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_document_model_has_phase1_lifecycle_columns() -> None:
    columns = Document.__table__.columns

    for name in ("status", "is_enabled", "document_type", "content_hash", "metadata"):
        assert name in columns


def test_chunk_model_has_retrieval_metadata_columns() -> None:
    columns = Chunk.__table__.columns

    for name in ("chunk_type", "page_start", "page_end", "language", "product_model", "qdrant_point_id"):
        assert name in columns


def test_models_cover_required_phase1_domains() -> None:
    assert KnowledgeBase.__tablename__ == "knowledge_bases"
    assert DocumentVersion.__tablename__ == "document_versions"
    assert JobLog.__tablename__ == "job_logs"
    assert QueryLog.__tablename__ == "query_logs"
