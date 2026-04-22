"""RAG configuration API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.rag.api.schemas.config import RAGConfigResponse, RAGConfigUpdate
from app.rag.services.rag_config import RAGConfigService

router = APIRouter(prefix="/rag", tags=["rag-config"])


def _get_config_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RAGConfigService:
    return RAGConfigService(session, settings)


@router.get("/config", response_model=RAGConfigResponse)
async def get_rag_config(
    service: RAGConfigService = Depends(_get_config_service),
) -> RAGConfigResponse:
    """Get current RAG configuration."""
    config = await service.get_config()
    return RAGConfigResponse(**config)


@router.put("/config", response_model=RAGConfigResponse)
async def update_rag_config(
    payload: RAGConfigUpdate,
    service: RAGConfigService = Depends(_get_config_service),
) -> RAGConfigResponse:
    """Update RAG configuration (partial update)."""
    updates = payload.model_dump(exclude_none=True)
    config = await service.update_config(updates)
    return RAGConfigResponse(**config)
