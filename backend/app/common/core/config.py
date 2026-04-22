"""Application configuration management using pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Central application settings loaded from environment / .env file."""

    # --- Application ---
    app_name: str = Field(default="AgenticRAG", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    debug: bool = Field(default=False, alias="DEBUG")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/agenticrag",
        alias="DATABASE_URL",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/agenticrag",
        alias="DATABASE_URL_SYNC",
    )

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- Qdrant ---
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_collection_name: str = Field(default="agenticrag_chunks", alias="QDRANT_COLLECTION_NAME")

    # --- Embedding ---
    tei_base_url: str = Field(default="http://127.0.0.1:8080", alias="TEI_BASE_URL")
    tei_api_key: str | None = Field(default=None, alias="TEI_API_KEY")
    embedding_model_name: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL_NAME")
    embedding_model_path: str = Field(default="", alias="EMBEDDING_MODEL_PATH")
    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    embedding_dimension: int = Field(default=1024, alias="EMBEDDING_DIMENSION")
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")
    embedding_use_fp16: bool = Field(default=True, alias="EMBEDDING_USE_FP16")

    # --- LLM ---
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="minimax-m2.7", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")
    llm_timeout: float = Field(default=60.0, alias="LLM_TIMEOUT")

    # --- Reranker ---
    reranker_base_url: str = Field(default="", alias="RERANKER_BASE_URL")
    reranker_api_key: str = Field(default="", alias="RERANKER_API_KEY")
    reranker_enabled: bool = Field(default=False, alias="RERANKER_ENABLED")
    reranker_top_n: int = Field(default=20, alias="RERANKER_TOP_N")

    # --- RAG ---
    rag_search_top_k: int = Field(default=10, alias="RAG_SEARCH_TOP_K")
    rag_answer_top_k: int = Field(default=5, alias="RAG_ANSWER_TOP_K")
    rag_rewrite_enabled: bool = Field(default=True, alias="RAG_REWRITE_ENABLED")
    rag_context_window_tokens: int = Field(default=4000, alias="RAG_CONTEXT_WINDOW_TOKENS")
    rag_score_threshold: float = Field(default=0.3, alias="RAG_SCORE_THRESHOLD")
    rag_refusal_threshold: float = Field(default=0.2, alias="RAG_REFUSAL_THRESHOLD")

    # --- Langfuse ---
    langfuse_host: str = Field(default="", alias="LANGFUSE_HOST")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")

    # --- RQ / Worker ---
    rq_ingestion_queue: str = Field(default="ingestion", alias="RQ_INGESTION_QUEUE")
    rq_indexing_queue: str = Field(default="indexing", alias="RQ_INDEXING_QUEUE")
    rq_ingestion_timeout: int = Field(default=300, alias="RQ_INGESTION_TIMEOUT")
    rq_indexing_timeout: int = Field(default=300, alias="RQ_INDEXING_TIMEOUT")
    rq_max_retries: int = Field(default=2, alias="RQ_MAX_RETRIES")

    # --- File Storage ---
    upload_dir: Path = Field(default=ROOT_DIR / "var" / "uploads", alias="UPLOAD_DIR")
    parsed_dir: Path = Field(default=ROOT_DIR / "var" / "parsed", alias="PARSED_DIR")
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")

    # --- Logging ---
    log_dir: Path = Field(default=ROOT_DIR / "var" / "logs", alias="LOG_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="agenticrag.log", alias="LOG_FILE")
    log_max_bytes: int = Field(default=10 * 1024 * 1024, alias="LOG_MAX_BYTES")
    log_backup_count: int = Field(default=5, alias="LOG_BACKUP_COUNT")

    # --- Parser ---
    parser_timeout_seconds: float = Field(default=300.0, alias="PARSER_TIMEOUT_SECONDS")

    # --- Retrieval ---
    retrieval_rrf_k: int = Field(default=60, alias="RETRIEVAL_RRF_K")
    qdrant_write_batch_size: int = Field(default=100, alias="QDRANT_WRITE_BATCH_SIZE")

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        for d in (self.upload_dir, self.parsed_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
