from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = Field(default="AgenticRAG", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/agenticrag",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    vector_store_backend: str = Field(default="qdrant", alias="VECTOR_STORE_BACKEND")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_collection_name: str = Field(default="agenticrag_chunks", alias="QDRANT_COLLECTION_NAME")
    qdrant_dense_vector_name: str = Field(default="dense", alias="QDRANT_DENSE_VECTOR_NAME")
    qdrant_sparse_vector_name: str = Field(default="sparse", alias="QDRANT_SPARSE_VECTOR_NAME")
    embedding_backend: str = Field(default="tei", alias="EMBEDDING_BACKEND")
    tei_base_url: str = Field(default="http://127.0.0.1:8080", alias="TEI_BASE_URL")
    tei_api_key: str | None = Field(default=None, alias="TEI_API_KEY")
    embedding_model_name: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL_NAME")
    embedding_dimension: int = Field(default=1024, alias="EMBEDDING_DIMENSION")
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")
    sparse_vector_size: int = Field(default=65536, alias="SPARSE_VECTOR_SIZE")
    retrieval_candidate_limit: int = Field(default=20, alias="RETRIEVAL_CANDIDATE_LIMIT")
    retrieval_rrf_k: int = Field(default=60, alias="RETRIEVAL_RRF_K")
    retrieval_query_limit: int = Field(default=5, alias="RETRIEVAL_QUERY_LIMIT")
    retrieval_context_history_limit: int = Field(default=3, alias="RETRIEVAL_CONTEXT_HISTORY_LIMIT")
    answer_context_max_items: int = Field(default=5, alias="ANSWER_CONTEXT_MAX_ITEMS")
    answer_context_max_chars: int = Field(default=4000, alias="ANSWER_CONTEXT_MAX_CHARS")
    reranker_enabled: bool = Field(default=True, alias="RERANKER_ENABLED")
    reranker_backend: str = Field(default="simple", alias="RERANKER_BACKEND")
    reranker_model_name: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="RERANKER_MODEL_NAME",
    )
    reranker_lazy_load: bool = Field(default=True, alias="RERANKER_LAZY_LOAD")
    minimax_base_url: str | None = Field(default=None, alias="ANTHROPIC_BASE_URL")
    minimax_api_key: str | None = Field(default=None, alias="ANTHROPIC_AUTH_TOKEN")
    minimax_model: str = Field(default="MiniMax-M2.7", alias="ANTHROPIC_MODEL")
    upload_dir: Path = Field(default=ROOT_DIR / "var" / "uploads", alias="UPLOAD_DIR")
    parsed_dir: Path = Field(default=ROOT_DIR / "var" / "parsed", alias="PARSED_DIR")
    index_dir: Path = Field(default=ROOT_DIR / "var" / "indexes", alias="INDEX_DIR")
    rq_ingestion_queue: str = Field(default="ingestion", alias="RQ_INGESTION_QUEUE")
    rq_indexing_queue: str = Field(default="indexing", alias="RQ_INDEXING_QUEUE")
    rq_ingestion_timeout_seconds: int = Field(default=900, alias="RQ_INGESTION_TIMEOUT_SECONDS")
    rq_indexing_timeout_seconds: int = Field(default=900, alias="RQ_INDEXING_TIMEOUT_SECONDS")
    rq_max_retries: int = Field(default=2, alias="RQ_MAX_RETRIES")
    rq_worker_class: str = Field(default="simple", alias="RQ_WORKER_CLASS")
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")
    parser_timeout_seconds: float = Field(default=60.0, alias="PARSER_TIMEOUT_SECONDS")
    log_dir: Path = Field(default=ROOT_DIR / "var" / "logs", alias="LOG_DIR")
    log_file: str = Field(default="agenticrag.log", alias="LOG_FILE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_max_bytes: int = Field(default=10 * 1024 * 1024, alias="LOG_MAX_BYTES")
    log_backup_count: int = Field(default=5, alias="LOG_BACKUP_COUNT")

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.parsed_dir.mkdir(parents=True, exist_ok=True)
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    return settings
