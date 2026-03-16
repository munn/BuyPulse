"""Tests for three-tier search waterfall: DB → API → fallback link."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.search_service import SearchResult, SearchService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return SearchService(mock_session, affiliate_tag="buypulse-20")


class TestTier1DbSearch:
    async def test_finds_product_by_title(self, service, mock_session):
        product = MagicMock(id=1, asin="B08N5WRWNW", title="AirPods Pro 2")
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = product
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.search("airpods pro")
        assert result.product is product
        assert result.source == "db"

    async def test_falls_through_when_no_match(self, service, mock_session):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.search("some obscure product xyz")
        assert result.product is None
        assert result.source == "fallback"
        assert "amazon.com/s?" in result.fallback_url
        assert "buypulse-20" in result.fallback_url


class TestTier3Fallback:
    async def test_fallback_url_contains_query(self, service, mock_session):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.search("robot vacuum")
        assert "robot" in result.fallback_url.lower()
