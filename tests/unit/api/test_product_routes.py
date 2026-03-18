"""Tests for product API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestProductList:
    async def test_returns_paginated_response(self, auth_client, mock_db):
        """Product list returns paginated format."""
        # Mock count query
        mock_db.scalar.return_value = 0
        # Mock items query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/products")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data


class TestAddProduct:
    async def test_add_single_product(self, auth_client, mock_db):
        with patch("cps.seeds.manager.SeedManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.add_single = AsyncMock(return_value=True)
            mock_sm_cls.return_value = mock_sm

            async with await auth_client() as client:
                resp = await client.post(
                    "/api/v1/products",
                    json={"platform_id": "B08N5WRWNW"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                assert resp.status_code == 200


class TestBatchAdd:
    async def test_batch_add_products(self, auth_client, mock_db):
        with patch("cps.seeds.manager.SeedManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.add_single = AsyncMock(return_value=True)
            mock_sm_cls.return_value = mock_sm

            async with await auth_client() as client:
                resp = await client.post(
                    "/api/v1/products/batch",
                    json={"items": [{"platform_id": "B08N5WRWNW"}, {"platform_id": "B09V3KXJPB"}]},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                assert resp.status_code == 200

    async def test_batch_limit_500(self, auth_client, mock_db):
        items = [{"platform_id": f"B{'0' * 9}{i:01d}"} for i in range(501)]
        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/products/batch",
                json={"items": items},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert resp.status_code == 422  # validation error


class TestProductAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/products")
            assert resp.status_code == 401
