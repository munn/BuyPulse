"""Tests for three-layer deal detection (spec Section 4.1)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.deal_service import DealService, Deal


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return DealService(mock_session)


class TestGlobalBestDeals:
    async def test_finds_products_at_historical_low(self, service, mock_session):
        # Product where current_price == lowest_price
        deal_row = (
            MagicMock(platform_id="B08N5WRWNW", platform="amazon", title="AirPods Pro 2", category="Electronics"),
            MagicMock(current_price=16900, lowest_price=16900, highest_price=24900),
        )
        mock_result = MagicMock()
        mock_result.all.return_value = [deal_row]
        mock_session.execute = AsyncMock(return_value=mock_result)

        deals = await service.find_global_best(limit=10)
        assert len(deals) >= 1
        assert deals[0].platform_id == "B08N5WRWNW"


class TestDealFiltering:
    def test_filters_dismissed_categories(self):
        deals = [
            Deal(platform_id="B1", platform="amazon", title="T1", category="Electronics", current=100, was=200),
            Deal(platform_id="B2", platform="amazon", title="T2", category="Books", current=100, was=200),
        ]
        dismissed = {"Electronics"}
        filtered = DealService.filter_dismissed(deals, dismissed_categories=dismissed)
        assert len(filtered) == 1
        assert filtered[0].category == "Books"
