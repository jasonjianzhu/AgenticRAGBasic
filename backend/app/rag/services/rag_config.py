"""RAG configuration service — runtime config with DB persistence.

Stores RAG config as key-value pairs in the rag_configs table.
Falls back to Settings defaults when no DB override exists.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger

logger = get_logger(__name__)

# DB table for config persistence (simple key-value)
# We use the existing JSONB pattern — store all RAG config as a single row
_CONFIG_KEY = "rag_config"


class RAGConfigService:
    """Manage RAG runtime configuration with DB persistence.

    Config is stored as a single JSON blob in the rag_configs table.
    Missing keys fall back to Settings defaults.

    Args:
        session: Async SQLAlchemy session.
        settings: Application settings (for defaults).
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    def _defaults(self) -> dict[str, Any]:
        """Build default config from Settings."""
        return {
            "search_top_k": self._settings.rag_search_top_k,
            "answer_top_k": self._settings.rag_answer_top_k,
            "rerank_enabled": self._settings.reranker_enabled,
            "rerank_top_n": self._settings.reranker_top_n,
            "rewrite_enabled": self._settings.rag_rewrite_enabled,
            "context_window_tokens": self._settings.rag_context_window_tokens,
            "score_threshold": self._settings.rag_score_threshold,
            "refusal_threshold": self._settings.rag_refusal_threshold,
            "rrf_k": self._settings.retrieval_rrf_k,
            "llm_model": self._settings.llm_model,
            "llm_temperature": self._settings.llm_temperature,
            "llm_max_tokens": self._settings.llm_max_tokens,
        }

    async def get_config(self) -> dict[str, Any]:
        """Get current RAG config (DB overrides merged with defaults)."""
        defaults = self._defaults()
        overrides = await self._load_overrides()
        merged = {**defaults, **overrides}
        return merged

    async def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Update RAG config (partial update, persisted to DB).

        Args:
            updates: Dict of field_name → new_value. Only non-None values.

        Returns:
            Full merged config after update.
        """
        # Load existing overrides
        overrides = await self._load_overrides()

        # Apply updates
        for key, value in updates.items():
            if value is not None:
                overrides[key] = value

        # Save
        await self._save_overrides(overrides)

        logger.info("rag_config_updated", updates=list(updates.keys()))

        # Return merged
        defaults = self._defaults()
        return {**defaults, **overrides}

    async def _load_overrides(self) -> dict[str, Any]:
        """Load config overrides from DB."""
        from app.common.db.models import Base
        from sqlalchemy import text

        # Use raw SQL to avoid needing a dedicated model for a single config row
        # Table: rag_configs (id, key, value, updated_at)
        try:
            result = await self._session.execute(
                text("SELECT value FROM rag_configs WHERE key = :key"),
                {"key": _CONFIG_KEY},
            )
            row = result.first()
            if row and row[0]:
                return dict(row[0])
        except Exception:
            # Table might not exist yet (before migration)
            logger.debug("rag_configs_table_not_available")
        return {}

    async def _save_overrides(self, overrides: dict[str, Any]) -> None:
        """Save config overrides to DB (upsert)."""
        import json
        from sqlalchemy import text

        try:
            # Try update first
            result = await self._session.execute(
                text(
                    "UPDATE rag_configs SET value = :value, updated_at = NOW() "
                    "WHERE key = :key"
                ),
                {"key": _CONFIG_KEY, "value": json.dumps(overrides)},
            )
            if result.rowcount == 0:
                # Insert
                await self._session.execute(
                    text(
                        "INSERT INTO rag_configs (id, key, value, updated_at) "
                        "VALUES (gen_random_uuid(), :key, :value, NOW())"
                    ),
                    {"key": _CONFIG_KEY, "value": json.dumps(overrides)},
                )
            await self._session.flush()
        except Exception as e:
            logger.warning("rag_config_save_failed", error=str(e))
            # Config save failure is non-fatal — config still works from defaults
