"""Session request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    """Single session in list."""
    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    message_count: int = 0


class SessionListResponse(BaseModel):
    """Paginated session list."""
    items: list[SessionResponse]
    total: int
    page: int = 1
    page_size: int = 20


class MessageResponse(BaseModel):
    """Single message in session detail."""
    id: str
    role: str
    content: str
    message_type: str
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str


class SessionDetailResponse(BaseModel):
    """Session with full message history."""
    id: str
    title: str
    status: str
    messages: list[MessageResponse]
    created_at: str
    updated_at: str
