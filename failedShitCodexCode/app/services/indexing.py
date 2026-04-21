from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Chunk
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository
from app.rag.embedding.base import EmbeddingProvider
from app.rag.retrieval.sparse import build_sparse_vector
from app.rag.vector_store.base import VectorPoint


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexingResult:
    document_id: uuid.UUID
    indexed_chunk_count: int


class DocumentIndexingService:
    def __init__(self, session: Session, settings: Settings, embedding_provider: EmbeddingProvider, vector_store):
        self.session = session
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def index_document(self, document_id: str | uuid.UUID) -> IndexingResult:
        document_uuid = uuid.UUID(str(document_id))
        logger.info("Indexing started: document_id=%s", document_uuid)
        document_repository = DocumentRepository(self.session)
        version_repository = DocumentVersionRepository(self.session)
        chunk_repository = ChunkRepository(self.session)

        document = document_repository.get(document_uuid)
        if document is None:
            raise ValueError(f"Document not found: {document_uuid}")

        latest_version = version_repository.get_latest_for_document(document_uuid)
        if latest_version is None:
            raise ValueError(f"Document version not found: {document_uuid}")

        document_repository.update_status(document.id, "indexing")
        chunks = chunk_repository.list_by_document(document.id, document_version_id=latest_version.id)
        logger.info(
            "Indexing chunks loaded: document_id=%s version_id=%s chunk_count=%s",
            document.id,
            latest_version.id,
            len(chunks),
        )
        if not chunks:
            raise ValueError(f"No chunks to index for document: {document.id}")
        self.vector_store.delete_by_payload(
            self.settings.qdrant_collection_name,
            {"document_id": str(document.id)},
        )
        logger.info("Existing vectors deleted: document_id=%s collection=%s", document.id, self.settings.qdrant_collection_name)
        vectors = self.embedding_provider.embed_documents([chunk.content for chunk in chunks])
        logger.info("Embeddings generated: document_id=%s vector_count=%s", document.id, len(vectors))
        points: list[VectorPoint] = []
        for chunk, vector in zip(chunks, vectors, strict=False):
            point_id = str(uuid.uuid4())
            chunk.qdrant_point_id = point_id
            points.append(
                VectorPoint(
                    id=point_id,
                    vector=vector,
                    sparse_vector=build_sparse_vector(chunk.content, self.settings.sparse_vector_size),
                    payload={
                        "chunk_id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                        "knowledge_base_id": str(chunk.knowledge_base_id),
                        "chunk_type": chunk.chunk_type,
                        "language": chunk.language,
                        "product_model": chunk.product_model,
                        "document_type": document.document_type,
                        "document_status": "ready",
                        "is_enabled": document.is_enabled,
                    },
                )
            )

        self.vector_store.upsert(self.settings.qdrant_collection_name, points)
        logger.info("Vectors upserted: document_id=%s collection=%s point_count=%s", document.id, self.settings.qdrant_collection_name, len(points))
        latest_version.status = "ready"
        latest_version.metadata_ = {**latest_version.metadata_, "indexed_chunk_count": len(points)}
        document_repository.update_status(document.id, "ready")
        self.session.flush()
        logger.info("Indexing finished: document_id=%s indexed_chunk_count=%s", document.id, len(points))
        return IndexingResult(document_id=document.id, indexed_chunk_count=len(points))
