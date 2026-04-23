"""Business database admin routes — schema inspection and connection test."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.core.config import Settings, get_settings
from app.agent.sql.executor import SQLExecutor, _get_business_session_factory
from app.agent.sql.schema_loader import SchemaLoader

router = APIRouter(prefix="/agent/db", tags=["agent-db"])


def _parse_allowed_tables(config_value: str) -> set[str] | None:
    if config_value.strip() == "*":
        return None
    return {t.strip() for t in config_value.split(",") if t.strip()}


@router.get("/schema")
async def get_db_schema(settings: Settings = Depends(get_settings)) -> dict:
    """Get business database table schemas."""
    try:
        factory = _get_business_session_factory(settings)
        allowed = _parse_allowed_tables(settings.business_db_allowed_tables)
        loader = SchemaLoader(factory, allowed_tables=allowed)
        tables = await loader.load_schema()
        return {"tables": loader.to_api_response(tables)}
    except Exception as e:
        return {"tables": [], "error": str(e)}


@router.post("/test")
async def test_db_connection(settings: Settings = Depends(get_settings)) -> dict:
    """Test business database connection."""
    executor = SQLExecutor(settings)
    ok = await executor.test_connection()
    return {"connected": ok}
