"""Tests for configuration management (S1-01)."""
from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.mark.unit
class TestSettings:
    """Configuration settings tests."""

    def test_default_settings(self):
        """Settings should have sensible defaults."""
        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///",
            DATABASE_URL_SYNC="sqlite:///",
        )
        assert settings.app_name == "AgenticRAG"
        assert settings.app_env == "development"
        assert settings.app_port == 8000
        assert settings.max_upload_size_bytes == 50 * 1024 * 1024
        assert settings.rq_max_retries == 2
        assert settings.rq_ingestion_timeout == 300
        assert settings.rq_indexing_timeout == 300
        assert settings.embedding_batch_size == 32
        assert settings.embedding_dimension == 1024

    def test_ensure_dirs_creates_directories(self, tmp_path):
        """ensure_dirs should create required directories."""
        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///",
            DATABASE_URL_SYNC="sqlite:///",
            UPLOAD_DIR=str(tmp_path / "uploads"),
            PARSED_DIR=str(tmp_path / "parsed"),
            LOG_DIR=str(tmp_path / "logs"),
        )
        settings.ensure_dirs()
        assert (tmp_path / "uploads").exists()
        assert (tmp_path / "parsed").exists()
        assert (tmp_path / "logs").exists()
