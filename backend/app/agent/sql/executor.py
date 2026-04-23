"""SQL executor — runs validated queries against the business database."""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton for the business DB engine
_business_engine = None
_business_session_factory: async_sessionmaker | None = None


def _get_business_session_factory(settings: Settings | None = None) -> async_sessionmaker:
    """Get or create the business database session factory (singleton)."""
    global _business_engine, _business_session_factory
    if _business_session_factory is not None:
        return _business_session_factory

    settings = settings or get_settings()
    _business_engine = create_async_engine(
        settings.business_db_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _business_session_factory = async_sessionmaker(
        _business_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return _business_session_factory


class SQLExecutor:
    """Executes read-only SQL queries against the business database.

    Args:
        settings: Application settings (for connection config).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._factory = _get_business_session_factory(self._settings)
        self._timeout = self._settings.business_db_query_timeout

    async def execute(self, sql: str) -> tuple[list[str], list[list[Any]], int]:
        """Execute a SQL query and return (columns, rows, row_count).

        Raises:
            asyncio.TimeoutError: If query exceeds timeout.
            Exception: On database errors.
        """
        async with self._factory() as session:
            try:
                result = await asyncio.wait_for(
                    session.execute(text(sql)),
                    timeout=self._timeout,
                )
                columns = list(result.keys())
                rows_raw = result.fetchall()
                rows = [list(self._serialize_row(row)) for row in rows_raw]
                return columns, rows, len(rows)
            except asyncio.TimeoutError:
                logger.warning("sql_query_timeout", sql=sql[:200], timeout=self._timeout)
                raise
            except Exception as e:
                logger.error("sql_query_error", sql=sql[:200], error=str(e))
                raise

    @staticmethod
    def _serialize_row(row) -> list[Any]:
        """Convert a row to a list of JSON-serializable values."""
        result = []
        for val in row:
            if hasattr(val, "isoformat"):
                result.append(val.isoformat())
            elif val is None:
                result.append(None)
            else:
                result.append(val)
        return result

    async def test_connection(self) -> bool:
        """Test if the business database is reachable."""
        try:
            async with self._factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("business_db_connection_failed", error=str(e))
            return False
