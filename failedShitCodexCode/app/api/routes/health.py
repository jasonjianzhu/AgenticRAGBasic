from __future__ import annotations

from fastapi import Depends
from fastapi import APIRouter

from app.core.config import Settings
from app.core.dependencies import get_settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "environment": settings.app_env,
    }
