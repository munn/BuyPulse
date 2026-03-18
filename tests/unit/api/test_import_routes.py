"""Tests for import API routes."""

from unittest.mock import MagicMock

import pytest


class TestImportList:
    async def test_returns_list(self, auth_client, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/imports")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)


class TestImportAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/imports")
            assert resp.status_code == 401
