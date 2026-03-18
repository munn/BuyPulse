"""Tests for auth API routes."""

from unittest.mock import MagicMock


class TestLogin:
    async def test_login_invalid_credentials_returns_401(self, anon_client, mock_db):
        """Login with wrong credentials returns 401."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        async with await anon_client() as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrongpassword"},
            )
            assert resp.status_code == 401


class TestGetMe:
    async def test_returns_current_user(self, auth_client):
        async with await auth_client() as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "admin"
            assert data["role"] == "admin"

    async def test_unauthenticated_returns_401(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 401


class TestLogout:
    async def test_logout_returns_200(self, auth_client):
        async with await auth_client() as client:
            resp = await client.post("/api/v1/auth/logout", headers={"X-Requested-With": "XMLHttpRequest"})
            assert resp.status_code == 200
            assert resp.json()["detail"] == "Logged out"
