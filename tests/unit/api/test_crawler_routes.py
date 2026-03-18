"""Tests for crawler API routes."""

from unittest.mock import MagicMock

import pytest


class TestCrawlerTasks:
    async def test_returns_paginated_tasks(self, auth_client, mock_db):
        mock_db.scalar.return_value = 0
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/crawler/tasks")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data


class TestCrawlerStats:
    async def test_returns_stats(self, auth_client, mock_db):
        # Mock counts for each status + speed
        mock_db.scalar.side_effect = [10, 2, 500, 15, 48]

        async with await auth_client() as client:
            resp = await client.get("/api/v1/crawler/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert "pending" in data
            assert "failed" in data


class TestCrawlerAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/crawler/tasks")
            assert resp.status_code == 401
