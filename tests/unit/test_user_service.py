"""Tests for user service — CRUD, language, density, state transitions.

Uses a mock AsyncSession to avoid DB dependency.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.user_service import NotificationState, UserService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return UserService(mock_session)


class TestNotificationState:
    def test_all_states_defined(self):
        states = {s.value for s in NotificationState}
        assert states == {
            "active", "degraded_weekly", "degraded_monthly",
            "stopped", "paused_by_user", "blocked",
        }

    def test_is_pushable(self):
        assert NotificationState.ACTIVE.is_pushable is True
        assert NotificationState.DEGRADED_WEEKLY.is_pushable is True
        assert NotificationState.STOPPED.is_pushable is False
        assert NotificationState.BLOCKED.is_pushable is False


class TestGetOrCreate:
    async def test_creates_new_user(self, service, mock_session):
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        user = await service.get_or_create(telegram_id=12345, username="test")
        mock_session.add.assert_called_once()

    async def test_returns_existing_user(self, service, mock_session):
        existing = MagicMock(telegram_id=12345)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )
        user = await service.get_or_create(telegram_id=12345)
        assert user is existing
        mock_session.add.assert_not_called()


class TestStateTransitions:
    def test_valid_downgrade_path(self):
        assert NotificationState.ACTIVE.can_transition_to(NotificationState.DEGRADED_WEEKLY)
        assert NotificationState.DEGRADED_WEEKLY.can_transition_to(NotificationState.DEGRADED_MONTHLY)
        assert NotificationState.DEGRADED_MONTHLY.can_transition_to(NotificationState.STOPPED)

    def test_reactivation_path(self):
        for state in NotificationState:
            if state != NotificationState.BLOCKED:
                assert state.can_transition_to(NotificationState.ACTIVE) is True

    def test_blocked_is_terminal(self):
        assert NotificationState.BLOCKED.can_transition_to(NotificationState.ACTIVE) is False
