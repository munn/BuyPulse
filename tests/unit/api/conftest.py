"""Shared fixtures for API route tests."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from cps.api.deps import get_current_user, get_db
from cps.db.models import AdminUser


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_user():
    user = MagicMock(spec=AdminUser)
    user.id = 1
    user.username = "admin"
    user.role = "admin"
    user.is_active = True
    user.locale = "zh-CN"
    user.created_at = "2026-01-01T00:00:00+00:00"
    return user


@pytest.fixture
def make_app(mock_db, mock_user):
    def _make(authenticated=True):
        from cps.api.app import create_app
        app = create_app()

        async def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db
        if authenticated:
            app.dependency_overrides[get_current_user] = lambda: mock_user
        return app
    return _make


@pytest.fixture
def auth_client(make_app):
    async def _client():
        from httpx import ASGITransport, AsyncClient
        app = make_app(authenticated=True)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")
    return _client


@pytest.fixture
def anon_client(make_app):
    async def _client():
        from httpx import ASGITransport, AsyncClient
        app = make_app(authenticated=False)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")
    return _client
