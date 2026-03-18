"""Tests for CSRF middleware."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cps.api.middleware import CSRFMiddleware


@pytest.fixture
def csrf_app():
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/api/v1/test")
    async def get_test():
        return {"ok": True}

    @app.post("/api/v1/test")
    async def post_test():
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    async def login():
        return {"ok": True}

    return app


class TestCSRFMiddleware:
    async def test_get_requests_pass_through(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/test")
            assert resp.status_code == 200

    async def test_post_without_header_rejected(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/test")
            assert resp.status_code == 403

    async def test_post_with_header_allowed(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/test", headers={"X-Requested-With": "XMLHttpRequest"})
            assert resp.status_code == 200

    async def test_login_exempt_from_csrf(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/login")
            assert resp.status_code == 200
