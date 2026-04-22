"""Pydantic schemas for job API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobResponse(BaseModel):
    """Schema for job log response."""

    id: uuid.UUID
    rq_job_id: str | None = None
    queue_name: str
    job_type: str
    status: str  # queued / started / finished / failed / retrying
    document_id: uuid.UUID | None = None
    attempts: int
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobListResponse(BaseModel):
    """Schema for listing jobs."""

    items: list[JobResponse]
    total: int


class JobRetryResponse(BaseModel):
    """Schema for retry response."""

    id: uuid.UUID
    status: str
    attempts: int
    message: str
