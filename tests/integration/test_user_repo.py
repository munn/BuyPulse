"""Integration tests for user-layer DB operations."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import DealDismissal, TelegramUser, UserInteraction
from cps.services.interaction_service import InteractionService
from cps.services.user_service import NotificationState, UserService


class TestUserService:
    async def test_get_or_create_new_user(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user = await svc.get_or_create(telegram_id=99999, username="inttest")
        assert user.id is not None
        assert user.telegram_id == 99999
        assert user.language == "en"
        assert user.notification_state == "active"

    async def test_get_or_create_existing(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user1 = await svc.get_or_create(telegram_id=99998)
        user2 = await svc.get_or_create(telegram_id=99998)
        assert user1.id == user2.id

    async def test_state_transition(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user = await svc.get_or_create(telegram_id=99997)
        assert await svc.transition_state(user, NotificationState.DEGRADED_WEEKLY) is True
        assert user.notification_state == "degraded_weekly"

    async def test_blocked_is_terminal(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user = await svc.get_or_create(telegram_id=99996)
        await svc.mark_blocked(user)
        assert await svc.transition_state(user, NotificationState.ACTIVE) is False


class TestInteractionService:
    async def test_record_and_query(self, db_session: AsyncSession):
        user_svc = UserService(db_session)
        user = await user_svc.get_or_create(telegram_id=99995)

        int_svc = InteractionService(db_session)
        for _ in range(3):
            await int_svc.record(user.id, "search", "robot vacuum")
        await int_svc.record(user.id, "search", "airpods")

        patterns = await int_svc.get_repeated_searches(user.id, min_count=3, days=7)
        assert len(patterns) == 1
        assert patterns[0][0] == "robot vacuum"


class TestDealDismissal:
    async def test_dismiss_category(self, db_session: AsyncSession):
        user_svc = UserService(db_session)
        user = await user_svc.get_or_create(telegram_id=99994)

        dismissal = DealDismissal(user_id=user.id, dismissed_category="Electronics")
        db_session.add(dismissal)
        await db_session.flush()

        result = await db_session.execute(
            select(DealDismissal).where(DealDismissal.user_id == user.id)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].dismissed_category == "Electronics"
