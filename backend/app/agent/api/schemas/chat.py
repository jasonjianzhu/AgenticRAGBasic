"""Chat request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /agent/chat."""
    session_id: str | None = Field(default=None, description="会话 ID，不传则创建新会话")
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    kb_ids: list[str] = Field(default_factory=list, description="知识库 ID 列表")
