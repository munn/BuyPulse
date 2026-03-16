"""Tests for monitor service — CRUD, 20-limit, cooldown, target suggestions."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.monitor_service import MonitorService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return MonitorService(mock_session)


class TestCreateMonitor:
    async def test_rejects_when_at_limit(self, service, mock_session):
        # Simulate 20 existing monitors
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 20
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.create_monitor(user_id=1, product_id=99, monitor_limit=20)
        assert result is None  # rejected

    async def test_creates_when_under_limit(self, service, mock_session):
        # First call: count = 5, second call: check existing = None
        count_result = MagicMock(scalar_one=MagicMock(return_value=5))
        existing_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_session.execute = AsyncMock(side_effect=[count_result, existing_result])

        result = await service.create_monitor(user_id=1, product_id=99, monitor_limit=20)
        mock_session.add.assert_called_once()


class TestCooldownCheck:
    def test_cooldown_not_expired(self):
        last_notified = datetime.now(timezone.utc) - timedelta(hours=12)
        assert MonitorService.is_cooldown_active(last_notified) is True

    def test_cooldown_expired(self):
        last_notified = datetime.now(timezone.utc) - timedelta(hours=25)
        assert MonitorService.is_cooldown_active(last_notified) is False

    def test_never_notified(self):
        assert MonitorService.is_cooldown_active(None) is False
