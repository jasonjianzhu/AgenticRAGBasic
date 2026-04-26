"""Shared FastAPI application factory.

Each service (knowledge, rag, agent) has its own entry point that
calls create_base_app() and registers only its own routers.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.core.config import get_settings
from app.common.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_base_app(
    title: str = "AgenticRAG",
    description: str = "AgenticRAG - 面向储能行业的智能知识库与问答平台",
) -> FastAPI:
    """Create a base FastAPI app with common middleware and logging.

    Each service entry point calls this, then registers its own routers.
    """
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=title,
        version="0.1.0",
        description=description,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
