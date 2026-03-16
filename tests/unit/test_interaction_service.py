"""Tests for user interaction tracking and behavior pattern queries."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.interaction_service import InteractionService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return InteractionService(mock_session)


class TestRecordInteraction:
    async def test_records_search(self, service, mock_session):
        await service.record(user_id=1, interaction_type="search", payload="robot vacuum")
        mock_session.add.assert_called_once()

    async def test_records_button_click(self, service, mock_session):
        await service.record(user_id=1, interaction_type="button_click", payload="buy:B08N5WRWNW")
        mock_session.add.assert_called_once()


class TestBehaviorQuery:
    async def test_repeated_search_detection(self, service, mock_session):
        # Mock: user searched "robot vacuum" 3 times in 7 days
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("robot vacuum", 3),
            ("airpods", 1),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        patterns = await service.get_repeated_searches(user_id=1, min_count=3, days=7)
        assert len(patterns) >= 1
        assert patterns[0][0] == "robot vacuum"
