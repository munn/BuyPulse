"""Tests for FastAPI app factory."""

from httpx import ASGITransport, AsyncClient
from cps.api.app import create_app


class TestCreateApp:
    def test_returns_fastapi_instance(self):
        app = create_app()
        assert app is not None

    async def test_health_endpoint(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
