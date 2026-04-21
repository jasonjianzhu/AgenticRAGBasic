"""RQ task functions for async job execution.

These functions are called by RQ workers. They will be fully implemented
in Sprint 5 (ingestion) and Sprint 7 (indexing).
"""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


def run_ingestion(document_id: str, **kwargs) -> None:
    """Execute document ingestion (parse + chunk).

    Called by RQ worker from the ingestion queue.
    Full implementation in Sprint 5.
    """
    logger.info("run_ingestion_called", document_id=document_id, kwargs=kwargs)
    raise NotImplementedError("Ingestion task not yet implemented (Sprint 5)")


def run_indexing(document_id: str, **kwargs) -> None:
    """Execute document indexing (embed + write to Qdrant).

    Called by RQ worker from the indexing queue.
    Full implementation in Sprint 7.
    """
    logger.info("run_indexing_called", document_id=document_id, kwargs=kwargs)
    raise NotImplementedError("Indexing task not yet implemented (Sprint 7)")
