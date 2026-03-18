"""Tests for auth API routes."""

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
