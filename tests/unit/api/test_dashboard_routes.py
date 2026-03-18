"""Tests for dashboard API routes."""

from unittest.mock import MagicMock

import pytest


class TestDashboardOverview:
    async def test_returns_stats(self, auth_client, mock_db):
        """Overview returns stat fields."""
        # Mock DB responses for the 5 scalar queries
        mock_db.scalar.side_effect = [
            50000,    # products_total
            120,      # products_today
            32000,    # crawled_total
            850,      # crawled_today
            2100000,  # price_records_total
        ]
        # Success rate query returns two values
        mock_result = MagicMock()
        mock_result.one.return_value = MagicMock(total=1000, success=945)
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/dashboard/overview")
            assert resp.status_code == 200
            data = resp.json()
            assert "products_total" in data
            assert "success_rate_24h" in data


class TestDashboardWorkers:
    async def test_returns_worker_list(self, auth_client, mock_db):
        """Workers endpoint returns list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/dashboard/workers")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)


class TestDashboardAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/dashboard/overview")
            assert resp.status_code == 401
