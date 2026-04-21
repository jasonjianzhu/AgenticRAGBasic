"""Tests for health check endpoint (S1-01)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.unit
class TestHealthCheck:
    """Health check endpoint tests."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient):
        """GET /health should return 200 with status ok."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "agenticrag"

    @pytest.mark.asyncio
    async def test_health_response_structure(self, client: AsyncClient):
        """Health response should have expected keys."""
        response = await client.get("/health")
        data = response.json()
        assert "status" in data
        assert "service" in data
