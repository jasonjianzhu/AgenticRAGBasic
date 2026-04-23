"""Session management routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.dependencies import get_db
from app.agent.api.schemas.sessions import (
    MessageResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)
from app.agent.services.session import SessionService

router = APIRouter(prefix="/agent", tags=["agent"])


def _get_session_service(session: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(session)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: str | None = "active",
    skip: int = 0,
    limit: int = 20,
    service: SessionService = Depends(_get_session_service),
) -> SessionListResponse:
    """List chat sessions."""
    items, total = await service.list_sessions(status=status, skip=skip, limit=limit)
    return SessionListResponse(
        items=[
            SessionResponse(
                id=str(s.id),
                title=s.title,
                status=s.status,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
                message_count=0,  # filled below
            )
            for s in items
        ],
        total=total,
        page=skip // limit + 1 if limit else 1,
        page_size=limit,
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    service: SessionService = Depends(_get_session_service),
) -> SessionDetailResponse:
    """Get session detail with message history."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的会话 ID")

    session = await service.get_session(sid)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return SessionDetailResponse(
        id=str(session.id),
        title=session.title,
        status=session.status,
        messages=[
            MessageResponse(
                id=str(m.id),
                role=m.role,
                content=m.content,
                message_type=m.message_type,
                tool_name=m.tool_name,
                tool_args=m.tool_args,
                tool_result=m.tool_result,
                metadata=m.metadata_,
                created_at=m.created_at.isoformat(),
            )
            for m in session.messages
        ],
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    service: SessionService = Depends(_get_session_service),
) -> dict:
    """Delete a chat session."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的会话 ID")

    deleted = await service.delete_session(sid)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"message": "会话已删除"}
