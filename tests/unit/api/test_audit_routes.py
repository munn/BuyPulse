"""Tests for audit API routes."""

from unittest.mock import MagicMock

import pytest


class TestAuditList:
    async def test_returns_paginated(self, auth_client, mock_db):
        mock_db.scalar.return_value = 0
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/audit")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data


class TestAuditAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/audit")
            assert resp.status_code == 401
