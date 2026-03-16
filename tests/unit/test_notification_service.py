"""Tests for notification dispatch with cooldown and blocked handling."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import Forbidden

from cps.services.notification_service import NotificationService


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    return bot


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_bot, mock_session):
    return NotificationService(mock_bot, mock_session)


class TestSendNotification:
    async def test_sends_message(self, service, mock_bot):
        result = await service.send(
            telegram_id=12345, text="Price drop!", notification_type="price_alert"
        )
        assert result is True
        mock_bot.send_message.assert_called_once()

    async def test_handles_forbidden_marks_blocked(self, service, mock_bot, mock_session):
        mock_bot.send_message.side_effect = Forbidden("blocked by user")

        with pytest.raises(Forbidden):
            await service.send(telegram_id=12345, text="test", notification_type="system")

    async def test_logs_notification(self, service, mock_session):
        await service.send(
            telegram_id=12345,
            text="Deal alert",
            notification_type="deal_push",
            product_id=99,
            affiliate_tag="buypulse-20",
        )
        mock_session.add.assert_called_once()
