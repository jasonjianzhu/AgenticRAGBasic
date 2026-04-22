"""Synchronous database session management for RQ worker tasks.

RQ workers run synchronous code, so they need a synchronous DB session
rather than the async one used by FastAPI request handlers.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.common.core.config import get_settings


def _build_sync_engine():
    """Build a synchronous SQLAlchemy engine from settings."""
    settings = get_settings()
    return create_engine(
        settings.database_url_sync,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


_engine = None
_session_factory = None


def get_sync_engine():
    """Return the (lazily-created) synchronous engine singleton."""
    global _engine
    if _engine is None:
        _engine = _build_sync_engine()
    return _engine


def get_sync_session_factory() -> sessionmaker:
    """Return the (lazily-created) synchronous session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_sync_engine(),
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def sync_session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Usage::

        with sync_session_scope() as session:
            session.query(...)
    """
    factory = get_sync_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_sync_engine() -> None:
    """Reset the engine and session factory (useful for testing)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
