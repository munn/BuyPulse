"""User CRUD, preferences, and notification state machine.

Notification states (spec Section 8):
  active → degraded_weekly → degraded_monthly → stopped
  any (except blocked) → active (re-engagement)
  any → blocked (Telegram Forbidden)
  active ↔ paused_by_user
"""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import TelegramUser


class NotificationState(str, Enum):
    ACTIVE = "active"
    DEGRADED_WEEKLY = "degraded_weekly"
    DEGRADED_MONTHLY = "degraded_monthly"
    STOPPED = "stopped"
    PAUSED_BY_USER = "paused_by_user"
    BLOCKED = "blocked"

    @property
    def is_pushable(self) -> bool:
        """Can we send deal pushes in this state?"""
        return self in (
            NotificationState.ACTIVE,
            NotificationState.DEGRADED_WEEKLY,
            NotificationState.DEGRADED_MONTHLY,
        )

    def can_transition_to(self, target: "NotificationState") -> bool:
        """Validate state transition."""
        if self == NotificationState.BLOCKED:
            return False  # terminal state
        if target == NotificationState.BLOCKED:
            return True  # any → blocked
        if target == NotificationState.ACTIVE:
            return self != NotificationState.BLOCKED
        return (self, target) in _VALID_TRANSITIONS


_VALID_TRANSITIONS = {
    (NotificationState.ACTIVE, NotificationState.DEGRADED_WEEKLY),
    (NotificationState.ACTIVE, NotificationState.PAUSED_BY_USER),
    (NotificationState.DEGRADED_WEEKLY, NotificationState.DEGRADED_MONTHLY),
    (NotificationState.DEGRADED_MONTHLY, NotificationState.STOPPED),
    (NotificationState.PAUSED_BY_USER, NotificationState.ACTIVE),
}


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> TelegramUser:
        """Find user by telegram_id or create new one."""
        result = await self._session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> TelegramUser | None:
        result = await self._session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def update_language(self, user: TelegramUser, language: str) -> None:
        user.language = language
        await self._session.flush()

    async def update_density(self, user: TelegramUser, density: str) -> None:
        user.density_preference = density
        await self._session.flush()

    async def record_interaction(self, user: TelegramUser) -> None:
        """Update last_interaction_at timestamp."""
        user.last_interaction_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def mark_blocked(self, user: TelegramUser) -> None:
        """Mark user as blocked (Telegram Forbidden)."""
        user.notification_state = NotificationState.BLOCKED.value
        await self._session.flush()

    async def transition_state(
        self, user: TelegramUser, new_state: NotificationState
    ) -> bool:
        """Transition notification state. Returns False if invalid."""
        current = NotificationState(user.notification_state)
        if not current.can_transition_to(new_state):
            return False
        user.notification_state = new_state.value
        await self._session.flush()
        return True

    def needs_reengagement(self, user: TelegramUser) -> bool:
        """Check if user returning from degraded/stopped state needs re-engagement prompt."""
        return user.notification_state in (
            NotificationState.DEGRADED_WEEKLY.value,
            NotificationState.DEGRADED_MONTHLY.value,
            NotificationState.STOPPED.value,
            NotificationState.PAUSED_BY_USER.value,
        )
