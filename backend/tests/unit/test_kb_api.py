"""Tests for knowledge base API endpoints (S2-01, S2-02, S2-03)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.dependencies import get_db
from app.db.base import Base
from app.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.main import create_app


@pytest_asyncio.fixture
async def api_session():
    """Create an isolated async engine and session for API tests."""
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(api_session: AsyncSession):
    """Provide an async HTTP test client with DB dependency override."""
    app = create_app()

    async def _override_get_db():
        try:
            yield api_session
            await api_session.commit()
        except Exception:
            await api_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.unit
class TestCreateKB:
    """Tests for POST /kb."""

    @pytest.mark.asyncio
    async def test_create_kb_success(self, api_client: AsyncClient):
        """Should create a KB and return 201."""
        payload = {
            "name": "储能产品知识库",
            "description": "储能产品手册和FAQ",
            "settings": {
                "default_chunker": "docling_hybrid",
                "default_parser_profile": "balanced",
                "embedding_model": "BAAI/bge-m3",
            },
        }
        response = await api_client.post("/kb", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "储能产品知识库"
        assert data["description"] == "储能产品手册和FAQ"
        assert data["settings"]["default_chunker"] == "docling_hybrid"
        assert data["settings"]["default_parser_profile"] == "balanced"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data
        # Validate UUID format
        uuid.UUID(data["id"])

    @pytest.mark.asyncio
    async def test_create_kb_minimal(self, api_client: AsyncClient):
        """Should create a KB with only required fields."""
        payload = {"name": "Minimal KB"}
        response = await api_client.post("/kb", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal KB"
        assert data["settings"]["default_chunker"] == "docling_hybrid"
        assert data["settings"]["default_parser_profile"] == "balanced"

    @pytest.mark.asyncio
    async def test_create_kb_duplicate_name_409(self, api_client: AsyncClient):
        """Should return 409 when name already exists."""
        payload = {"name": "Duplicate KB"}
        await api_client.post("/kb", json=payload)

        response = await api_client.post("/kb", json=payload)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_kb_empty_name_422(self, api_client: AsyncClient):
        """Should return 422 for empty name."""
        payload = {"name": ""}
        response = await api_client.post("/kb", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_kb_invalid_settings_422(self, api_client: AsyncClient):
        """Should return 422 for invalid settings fields."""
        payload = {
            "name": "Invalid Settings KB",
            "settings": {
                "default_chunker": "docling_hybrid",
                "unknown_field": "bad",
            },
        }
        response = await api_client.post("/kb", json=payload)
        assert response.status_code == 422


@pytest.mark.unit
class TestListKBs:
    """Tests for GET /kb."""

    @pytest.mark.asyncio
    async def test_list_kbs_empty(self, api_client: AsyncClient):
        """Should return empty list when no KBs exist."""
        response = await api_client.get("/kb")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_kbs_multiple(self, api_client: AsyncClient):
        """Should return all created KBs."""
        await api_client.post("/kb", json={"name": "KB 1"})
        await api_client.post("/kb", json={"name": "KB 2"})
        await api_client.post("/kb", json={"name": "KB 3"})

        response = await api_client.get("/kb")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_kbs_pagination(self, api_client: AsyncClient):
        """Should support skip and limit query params."""
        for i in range(5):
            await api_client.post("/kb", json={"name": f"Paginated KB {i}"})

        response = await api_client.get("/kb", params={"skip": 2, "limit": 2})

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2


@pytest.mark.unit
class TestGetKB:
    """Tests for GET /kb/{kb_id}."""

    @pytest.mark.asyncio
    async def test_get_kb_success(self, api_client: AsyncClient):
        """Should return KB detail with statistics."""
        create_resp = await api_client.post("/kb", json={"name": "Detail KB"})
        kb_id = create_resp.json()["id"]

        response = await api_client.get(f"/kb/{kb_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == kb_id
        assert data["name"] == "Detail KB"
        assert "statistics" in data
        assert data["statistics"]["document_count"] == 0
        assert data["statistics"]["chunk_count"] == 0
        assert data["statistics"]["ready_doc_count"] == 0
        assert data["statistics"]["failed_doc_count"] == 0

    @pytest.mark.asyncio
    async def test_get_kb_not_found_404(self, api_client: AsyncClient):
        """Should return 404 for non-existent KB."""
        fake_id = str(uuid.uuid4())
        response = await api_client.get(f"/kb/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_kb_invalid_uuid_422(self, api_client: AsyncClient):
        """Should return 422 for invalid UUID."""
        response = await api_client.get("/kb/not-a-uuid")
        assert response.status_code == 422


@pytest.mark.unit
class TestUpdateKB:
    """Tests for PUT /kb/{kb_id}."""

    @pytest.mark.asyncio
    async def test_update_kb_name(self, api_client: AsyncClient):
        """Should update KB name."""
        create_resp = await api_client.post("/kb", json={"name": "Original Name"})
        kb_id = create_resp.json()["id"]

        response = await api_client.put(f"/kb/{kb_id}", json={"name": "Updated Name"})

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_kb_settings(self, api_client: AsyncClient):
        """Should update KB settings (S2-02)."""
        create_resp = await api_client.post("/kb", json={"name": "Settings Update KB"})
        kb_id = create_resp.json()["id"]

        new_settings = {
            "default_chunker": "recursive_token",
            "default_parser_profile": "accurate",
            "embedding_model": "custom-model",
        }
        response = await api_client.put(f"/kb/{kb_id}", json={"settings": new_settings})

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["default_chunker"] == "recursive_token"
        assert data["settings"]["default_parser_profile"] == "accurate"
        assert data["settings"]["embedding_model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_update_kb_not_found_404(self, api_client: AsyncClient):
        """Should return 404 for non-existent KB."""
        fake_id = str(uuid.uuid4())
        response = await api_client.put(f"/kb/{fake_id}", json={"name": "Nope"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_kb_duplicate_name_409(self, api_client: AsyncClient):
        """Should return 409 when updating to an existing name."""
        await api_client.post("/kb", json={"name": "Existing KB"})
        create_resp = await api_client.post("/kb", json={"name": "Another KB"})
        kb_id = create_resp.json()["id"]

        response = await api_client.put(f"/kb/{kb_id}", json={"name": "Existing KB"})
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_update_kb_deactivate(self, api_client: AsyncClient):
        """Should be able to deactivate a KB."""
        create_resp = await api_client.post("/kb", json={"name": "Active KB"})
        kb_id = create_resp.json()["id"]

        response = await api_client.put(f"/kb/{kb_id}", json={"is_active": False})

        assert response.status_code == 200
        assert response.json()["is_active"] is False


@pytest.mark.unit
class TestDeleteKB:
    """Tests for DELETE /kb/{kb_id}."""

    @pytest.mark.asyncio
    async def test_delete_kb_success(self, api_client: AsyncClient):
        """Should delete KB and return 204."""
        create_resp = await api_client.post("/kb", json={"name": "Delete Me KB"})
        kb_id = create_resp.json()["id"]

        response = await api_client.delete(f"/kb/{kb_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await api_client.get(f"/kb/{kb_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_kb_not_found_404(self, api_client: AsyncClient):
        """Should return 404 for non-existent KB."""
        fake_id = str(uuid.uuid4())
        response = await api_client.delete(f"/kb/{fake_id}")
        assert response.status_code == 404


@pytest.mark.unit
class TestKBStatistics:
    """Tests for KB statistics in GET /kb/{kb_id} (S2-03)."""

    @pytest.mark.asyncio
    async def test_statistics_with_documents(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should return correct document and chunk counts."""
        # Create KB via API
        create_resp = await api_client.post("/kb", json={"name": "Stats Test KB"})
        kb_id = uuid.UUID(create_resp.json()["id"])

        # Add documents directly to DB
        for i, status in enumerate(["ready", "ready", "failed", "uploaded"]):
            doc = Document(
                knowledge_base_id=kb_id,
                title=f"Doc {i}",
                source_filename=f"doc{i}.pdf",
                storage_path=f"/path/doc{i}.pdf",
                content_hash=f"stathash{i}",
                mime_type="application/pdf",
                file_size_bytes=1000,
                status=status,
            )
            api_session.add(doc)
        await api_session.flush()

        # Get KB detail
        response = await api_client.get(f"/kb/{kb_id}")

        assert response.status_code == 200
        stats = response.json()["statistics"]
        assert stats["document_count"] == 4
        assert stats["ready_doc_count"] == 2
        assert stats["failed_doc_count"] == 1
        assert stats["chunk_count"] == 0
